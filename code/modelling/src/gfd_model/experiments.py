"""The runner: scenarios, folds, seeds, sweeps, and results on disk.

Five scenarios, THREE trainings. The cross-domain arms reuse a fitted model
rather than fitting a new one -- that is both the point of the experiment and
the largest compute saving available.

    tropis_in       fit tropis,    test tropis
    subtropis_in    fit subtropis, test subtropis
    tropis_to_sub   fit tropis,    test subtropis     <- reuses tropis_in
    sub_to_tropis   fit subtropis, test tropis        <- reuses subtropis_in
    pooled          fit both,      test both

THE SOURCE SCALER TRAVELS WITH THE MODEL. A cross-domain evaluation applies
the scaler fitted on the SOURCE domain to the target's rows. Re-fitting on the
target would leak target statistics into a model that is supposed never to
have seen it, and the leak is invisible in the results -- it just makes the
transfer look better than it is.

Budget, measured rather than estimated (7,25 ms/sample at 15 qubits):

    training     4.000 rows x 30 epochs
    validation   2.000 rows x 30 epochs
    test        ~43.000 rows, once
    x 36 runs (2 stages x 2 domains x 3 folds x 3 seeds)  ~= 12 h

Earlier projections in this project counted training samples only and
understated the total by roughly 3 hours. `estimate_budget()` below counts all
three.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import classical as C
from . import config as mcfg
from . import dataset as ds
from . import metrics as M
from . import training as T
from .qnn import QuantumModel, n_features_configured


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------
@dataclass
class Run:
    """One (scenario, stage, model, fold, seed) result."""
    scenario: str
    stage: str
    model: str
    fold: str
    seed: int
    train_rows: int
    n_params: int
    seconds: float
    epochs_run: int
    best_epoch: int
    stopped_early: bool
    metrics: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)


def _config_snapshot() -> dict:
    """Enough config to replay a run. Mirrors the pipeline's meta.json habit."""
    return {
        "task": mcfg.TASK,
        "hour_encoding": mcfg.HOUR_ENCODING,
        "base_features": list(mcfg.BASE_FEATURES),
        "feature_map": mcfg.FEATURE_MAP,
        "ansatz": mcfg.ANSATZ,
        "ansatz_reps": mcfg.ANSATZ_REPS,
        "observable": mcfg.OBSERVABLE,
        "device": mcfg.DEVICE,
        "diff_method": mcfg.DIFF_METHOD,
        "shots": mcfg.SHOTS,
        "optimizer": mcfg.OPTIMIZER,
        "learning_rate": mcfg.LEARNING_RATE,
        "batch_size": mcfg.BATCH_SIZE,
        "max_epochs": mcfg.MAX_EPOCHS,
        "patience": mcfg.EARLY_STOPPING_PATIENCE,
        "train_zero_ratio": mcfg.TRAIN_ZERO_RATIO,
        "test_days": mcfg.TEST_DAYS,
        "max_val_rows": mcfg.MAX_VAL_ROWS,
    }


# --------------------------------------------------------------------------
# Fitting
# --------------------------------------------------------------------------
def fit_models(
    source: str,
    fold: ds.Fold,
    stage: str,
    seed: int,
    models: tuple[str, ...] | None = None,
    train_rows: int | None = None,
    max_epochs: int | None = None,
    verbose: bool = True,
) -> dict:
    """Fit every rung of the ladder on one domain, fold, stage and seed.

    Returns the fitted models, the scaler that must travel with them, and the
    training diagnostics. `nn_full` is fitted on the WHOLE training window
    rather than the subsample -- it is not part of the matched comparison and
    is reported separately (D-09).
    """
    df = ds.load_pooled() if source == "pooled" else ds.load(source)
    n = n_features_configured()

    prep = ds.prepare(df, fold, stage, seed=seed, train_rows=train_rows)
    bias = C.initial_bias(prep.y_train, stage)
    qnn_params = QuantumModel(n, stage=stage, seed=seed).n_trainable

    fitted, diagnostics, rows_used, preps = {}, {}, {}, {}
    for name in (models or mcfg.MODEL_LADDER):
        p = prep
        if name == "nn_full":
            # Every row, not the QNN's subsample. Deliberately breaks parity.
            #
            # NOTE the sentinel. `train_rows=None` means "use the config
            # default" in prepare(), NOT "use everything" -- the first run of
            # this file passed None and nn_full silently trained on 3.000 rows
            # like every other arm, producing numbers identical to nn_large in
            # all 432 rows. A value larger than any table makes subsample() a
            # no-op, which is what this arm needs.
            p = ds.prepare(df, fold, stage, seed=seed, train_rows=10**9)

        model = C.build(name, n, stage, seed=seed,
                        qnn_params=qnn_params, output_bias=bias)
        result = T.fit(model, p.X_train, p.y_train, p.X_val, p.y_val,
                       stage=stage, seed=seed, max_epochs=max_epochs)

        fitted[name] = model
        diagnostics[name] = result
        # Per model, not per prep: nn_full trains on a different table and
        # reporting the shared prep's size made it look like every other arm.
        rows_used[name] = int(len(p.y_train))
        # Keep the Prepared, not just the row count. nn_full's scaler is
        # fitted on 2,4M rows and the shared one on 3.000; evaluating a
        # model through the wrong scaler shifts every test feature.
        preps[name] = p
        if verbose:
            n_par = getattr(model, "n_trainable", 0)
            print(f"    {name:<18s} {n_par:>5d} par  {result.summary()}")

    # D-03/D-04. Retransformation bias, corrected on VALIDATION rows only.
    # Fitting this on test would be target leakage dressed as calibration.
    smearing = {}
    if stage == "count":
        obs_val = M.to_counts(prep.y_val, prep.scaler)
        for name, model in fitted.items():
            pred_val = M.to_counts(
                T.predict(model, prep.X_val, stage=stage), prep.scaler
            )
            smearing[name] = M.smearing_factor(obs_val, pred_val)
            if verbose:
                print(f"    {name:<18s} smearing x{smearing[name]:.3f}")

    return {"models": fitted, "diagnostics": diagnostics, "prepared": prep,
            "smearing": smearing, "rows_used": rows_used, "preps": preps,
            "n_features": n, "source": source}


# --------------------------------------------------------------------------
# Evaluating, possibly on another domain
# --------------------------------------------------------------------------
def evaluate(
    fit: dict,
    target: str,
    fold: ds.Fold,
    stage: str,
    seed: int,
    scenario: str,
) -> list[Run]:
    """Score fitted models on a target domain, using the SOURCE scaler.

    For an in-domain scenario the target equals the source and this is just
    the held-out year. For a cross-domain scenario the target's rows are
    transformed by the scaler fitted on the source -- re-fitting here would
    leak target statistics into a model that must never have seen them.
    """
    default_prep = fit["prepared"]
    preps = fit.get("preps", {})

    # Cross-domain target rows are loaded ONCE, unscaled. Each model then
    # transforms them with its OWN scaler: nn_full's is fitted on 2,4M rows
    # and every other arm's on 3.000, and mixing them shifts every feature.
    target_rows = None
    if target != fit["source"]:
        df = ds.load_pooled() if target == "pooled" else ds.load(target)
        df = ds.add_hour_encoding(df)
        names = ds.feature_names(df)
        ds.assert_no_leakage(names)

        _, _, test = ds.split(df, fold)
        target_rows = (ds.sample_test_days(ds.stage_rows(test, stage)), names)

    runs = []
    for name, model in fit["models"].items():
        diag = fit["diagnostics"][name]
        prep = preps.get(name, default_prep)
        scaler = prep.scaler

        if target_rows is None:
            X, y, index = prep.X_test, prep.y_test, prep.test_index
        else:
            test, names = target_rows
            X = scaler.transform(test[names].to_numpy(dtype=np.float64))
            y = ds.make_target(test, stage)
            if stage == "count":
                y = scaler.transform_y(y)
            index = test[[mcfg.TIME_COL, "lat", "lon", "area_km2",
                          mcfg.COUNT_COLUMN]].reset_index(drop=True)

        pred = T.predict(model, X, stage=stage)

        if stage == "occurrence":
            scores = M.classification_metrics(y.astype(int), pred)
        else:
            scores = M.regression_metrics(y, pred,
                                          baseline=float(y.mean()))
            counts_pred = M.to_counts(pred, scaler)
            counts_obs = index[mcfg.COUNT_COLUMN].to_numpy(dtype=float)

            # Raw and smearing-corrected, both reported. The raw curve shows
            # the size of the retransformation bias; the corrected one is the
            # number to quote. For a CROSS-DOMAIN scenario the factor comes
            # from the SOURCE domain, so it does not fix a target-scale
            # mismatch -- that residual gap is a transfer finding, not an
            # artefact to correct away.
            factor = fit.get("smearing", {}).get(name, 1.0)
            scores["smearing_factor"] = float(factor)
            scores["windows"] = M.evaluate_windows(
                index, counts_pred * factor, counts_obs
            ).to_dict(orient="records")
            scores["windows_raw"] = M.evaluate_windows(
                index, counts_pred, counts_obs
            ).to_dict(orient="records")

        runs.append(Run(
            scenario=scenario, stage=stage, model=name, fold=fold.name,
            seed=seed,
            train_rows=int(len(prep.y_train)),
            n_params=int(getattr(model, "n_trainable", 0)),
            seconds=diag.seconds, epochs_run=diag.epochs_run,
            best_epoch=diag.best_epoch, stopped_early=diag.stopped_early,
            metrics=scores, config=_config_snapshot(),
        ))
    return runs


# --------------------------------------------------------------------------
# The final set
# --------------------------------------------------------------------------
def run_final(
    seeds: tuple[int, ...] | None = None,
    folds: list[ds.Fold] | None = None,
    stages: tuple[str, ...] = ("occurrence", "count"),
    models: tuple[str, ...] | None = None,
    out_dir: Path | None = None,
) -> pd.DataFrame:
    """The overnight run: every scenario, fold, seed and stage.

    Each fit is reused for its cross-domain partner, so `tropis_to_sub` costs
    only its evaluation. Results are written after every source-fold-seed so
    an interrupted run keeps everything finished so far -- a 12-hour job that
    loses its output to a laptop sleeping is a 12-hour job done twice.
    """
    seeds = seeds or mcfg.SEEDS
    folds = folds or ds.folds()
    out_dir = out_dir or mcfg.RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"final_{stamp}.jsonl"
    started = time.perf_counter()
    all_runs: list[Run] = []

    # (source, [(scenario, target), ...])
    plan = [
        ("tropis", [("tropis_in", "tropis"), ("tropis_to_sub", "subtropis")]),
        ("subtropis", [("subtropis_in", "subtropis"),
                       ("sub_to_tropis", "tropis")]),
    ]

    for stage in stages:
        for source, targets in plan:
            for fold in folds:
                for seed in seeds:
                    print(f"\n[{stage}] fit {source} {fold.name} seed={seed} "
                          f"({(time.perf_counter() - started) / 3600:.1f} h in)")
                    fit = fit_models(source, fold, stage, seed, models=models)

                    for scenario, target in targets:
                        runs = evaluate(fit, target, fold, stage, seed, scenario)
                        all_runs += runs
                        with path.open("a", encoding="utf-8") as fh:
                            for r in runs:
                                fh.write(json.dumps(asdict(r)) + "\n")
                        print(f"      -> {scenario:<15s} "
                              f"{len(runs)} models scored")

    print(f"\nwrote {len(all_runs)} runs to {path} "
          f"in {(time.perf_counter() - started) / 3600:.1f} h")
    return to_frame(all_runs)


# --------------------------------------------------------------------------
# Sweeps
# --------------------------------------------------------------------------
def run_sweep(axis: str, values=None, stage: str = "occurrence",
              seed: int = 0, out_dir: Path | None = None) -> pd.DataFrame:
    """One-factor-at-a-time around the defaults, on the sweep fold only.

    Sweeps are for choosing settings, not for the headline table, so they use
    one fold and one seed and a smaller test sample. State that asymmetry in
    Bab IV -- it is defensible, but only if declared.

    Mutates module-level config for the duration and restores it after. Ugly,
    and deliberate: the alternative is threading every knob through every
    function signature, which makes the common path harder to read for the
    benefit of a path used a handful of times.
    """
    values = values if values is not None else mcfg.SWEEPS[axis]
    fold = ds.folds()[mcfg.SWEEP_FOLD]
    out_dir = out_dir or mcfg.RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    knob = axis.upper()
    saved = getattr(mcfg, knob, None)
    saved_days = mcfg.TEST_DAYS
    mcfg.TEST_DAYS = 20                      # sweeps compare, not measure

    runs: list[Run] = []
    try:
        for value in values:
            if saved is not None:
                setattr(mcfg, knob, value)
            print(f"\n[sweep] {axis}={value}")

            rows = 1_000 if axis != "train_rows" else value
            fit = fit_models("tropis", fold, stage, seed,
                             train_rows=rows, max_epochs=15)
            got = evaluate(fit, "tropis", fold, stage, seed, f"sweep_{axis}")
            for r in got:
                r.config[axis] = value
            runs += got
    finally:
        if saved is not None:
            setattr(mcfg, knob, saved)
        mcfg.TEST_DAYS = saved_days

    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"sweep_{axis}_{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for r in runs:
            fh.write(json.dumps(asdict(r)) + "\n")
    print(f"\nwrote {len(runs)} runs to {path}")
    return to_frame(runs)


# --------------------------------------------------------------------------
# Reading results back
# --------------------------------------------------------------------------
def to_frame(runs: list[Run]) -> pd.DataFrame:
    """Flatten runs into a table. The D-04 window curves stay nested."""
    rows = []
    for r in runs:
        row = {k: v for k, v in asdict(r).items()
               if k not in ("metrics", "config")}
        row.update({k: v for k, v in r.metrics.items()
                    if k not in ("windows", "windows_raw")})
        rows.append(row)
    return pd.DataFrame(rows)


def load_results(path: Path) -> pd.DataFrame:
    with Path(path).open(encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    return to_frame([Run(**r) for r in records])


def summarise(frame: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Mean +/- sd across seeds and folds -- the Bab IV table.

    Reported as a spread because QNN training variance is large and a
    single-seed comparison is not evidence (D-06).
    """
    return (frame.groupby(["stage", "scenario", "model"], observed=True)[metric]
                 .agg(["mean", "std", "count"])
                 .round(4)
                 .reset_index())


# --------------------------------------------------------------------------
# Budget
# --------------------------------------------------------------------------
CELLS_PER_DOMAIN = {"tropis": 30, "subtropis": 56}

# Share of hourly rows that survive the stage filter. The count stage trains
# and tests on non-zero rows only (D-13), which is ~5,7% of tropis and ~3,0%
# of subtropis -- a large enough difference to change the budget.
NONZERO_SHARE = {"tropis": 0.0570, "subtropis": 0.0300}


def estimate_budget(ms_per_sample: float = 7.25) -> dict:
    """Hours for the configured final set, counting ALL three costs.

    Three corrections against the naive version, each of which mattered:

      1. Training, validation AND test inference are each first-order at ~7 ms
         per row. Earlier projections in this project counted training only
         and understated the total by ~3 h.
      2. Cell counts differ by domain -- 30 tropis against 56 subtropis -- so
         a single figure understates the subtropis test set by nearly half.
      3. The count stage evaluates on non-zero rows only, so its test set is
         roughly a twentieth of the occurrence stage's.

    This is a WORST CASE: it assumes every run reaches MAX_EPOCHS. Observed
    early stopping fires between epochs 11 and 28, so expect roughly 70% of
    the figure below.
    """
    epochs, rows = mcfg.MAX_EPOCHS, mcfg.TRAIN_ROWS
    val = mcfg.MAX_VAL_ROWS or 2_000
    days = mcfg.TEST_DAYS or 365
    n_repeats = len(mcfg.SEEDS) * len(mcfg.FOLDS)

    per_stage, total_s, n_runs = {}, 0.0, 0
    for stage in ("occurrence", "count"):
        stage_s = 0.0
        for domain, cells in CELLS_PER_DOMAIN.items():
            test = days * 24 * cells
            if stage == "count":
                test *= NONZERO_SHARE[domain]
            samples = rows * epochs + val * epochs + test
            stage_s += ms_per_sample / 1000 * samples * n_repeats
            n_runs += n_repeats
        per_stage[stage] = round(stage_s / 3600, 1)
        total_s += stage_s

    return {
        "hours_occurrence": per_stage["occurrence"],
        "hours_count": per_stage["count"],
        "n_qnn_runs": n_runs,
        "total_hours_worst_case": round(total_s / 3600, 1),
        "total_hours_expected": round(total_s * 0.7 / 3600, 1),
        "fits_one_night": total_s / 3600 <= 12,
    }


if __name__ == "__main__":
    print("gfd_model.experiments\n")
    for k, v in estimate_budget().items():
        print(f"  {k:<22s} {v}")
    print(f"\n  scenarios : {list(mcfg.SCENARIOS)}")
    print(f"  folds     : {[f.name for f in ds.folds()]}")
    print(f"  seeds     : {list(mcfg.SEEDS)}")
    print(f"  ladder    : {list(mcfg.MODEL_LADDER)}")
