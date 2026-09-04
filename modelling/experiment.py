"""Run the QNN and the classical NN, within-domain and cross-domain.

    python -m gfd_model.experiment --smoke              # seconds. do this first.
    python -m gfd_model.experiment --smoke --domain tropis
    python -m gfd_model.experiment --estimate           # time a full run, don't do it
    python -m gfd_model.experiment                      # the real thing
    python -m gfd_model.experiment --no-cross           # within-domain only
    python -m gfd_model.experiment --freq hourly        # will warn loudly

Results go to results/<timestamp>_<tag>.json with the model config, the build
metadata of the table that was read, and every metric (F-05).

------------------------------------------------------------------------------
READ THIS BEFORE THE FIRST FULL RUN
------------------------------------------------------------------------------
1. RESOLUTION. The default is monthly, and that is a deliberate override of the
   pipeline's current TIME_FREQ="h". Three reasons, in descending order of how
   much they will cost you:

   (a) The hourly target is a count process, not a density -- the build says so
       itself. Most cell-hours are zero, so a model that always predicts zero
       scores a high R^2 while having learned nothing. Every metric here is
       reported against a mean baseline for exactly this reason, but the
       cleaner fix is not to model at that resolution.
   (b) Row count. A simulated QNN evaluates one circuit per sample per
       optimizer iteration. Monthly gives a few thousand rows; hourly gives
       millions. The difference is between an afternoon and a year.
   (c) Comparability. Monthly is the only resolution that can be set beside the
       predecessor study's numbers at all.

   Build the monthly table (gfd_data.config.TIME_FREQ = "M") and model that.
   Keep hourly as a second experiment if there is time.

2. THE ZERO SHARE IS PRINTED FOR EVERY SPLIT. Read it before reading any R^2.

3. NF-01 ASKS FOR R^2 > 0,9 IN BOTH DOMAINS. The predecessor reached 0,7750
   and 0,3856 on materially the same data. Do not be surprised by the gap, and
   raise it with the supervisors rather than discovering it at sidang.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import numpy as np

from . import data as data_mod
from . import mconfig as mcfg
from . import models as M


# ==========================================================================
# Reporting helpers
# ==========================================================================
def _fmt(metrics: dict) -> str:
    flag = "" if metrics["beats_mean_baseline"] else "   <-- LOSES TO MEAN BASELINE"
    return (f"RMSE {metrics['rmse']:.4f}  NRMSE {metrics['nrmse_range']:.4f}  "
            f"MAE {metrics['mae']:.4f}  R2 {metrics['r2']:>7.4f}"
            f"  (baseline R2 {metrics['baseline_mean_r2']:.4f}){flag}")


def _evaluate(name, y_scaled, pred_scaled, y_train_scaled,
              y_native, pre) -> dict:
    """Score in scaled space AND in native GFD units."""
    scaled = M.score(y_scaled, pred_scaled, y_train_scaled)
    pred_native = pre.inverse_y(pred_scaled)
    native = M.score(y_native, pred_native, pre.inverse_y(y_train_scaled))
    print(f"    {name:<28s} {_fmt(scaled)}")
    return {"scaled": scaled, "native": native}


# ==========================================================================
# One domain
# ==========================================================================
def run_domain(domain: str, freq_slug: str, n_qubits: int, max_iter: int,
               max_rows: int | None, verbose: bool = True) -> dict:
    print(f"\n{'=' * 74}\n{domain.upper()}  ({freq_slug})\n{'=' * 74}")

    split, pre, _ = data_mod.prepare(
        domain, freq_slug=freq_slug, n_qubits=n_qubits, max_rows=max_rows
    )
    nq = split.n_qubits

    print(f"\n  -- QNN ({nq} qubits) --")
    qnn_res, qnn_info = M.fit_qnn(
        split.X_train, split.y_train, nq, max_iter=max_iter, verbose=verbose
    )
    print(f"      {qnn_info['n_weights']} weights, depth {qnn_info['circuit_depth']}, "
          f"{qnn_res.fit_seconds:.1f}s")

    print(f"\n  -- classical NN --")
    nn_res = M.fit_nn(split.X_train, split.y_train,
                      n_qnn_weights=qnn_info["n_weights"], verbose=verbose)

    print(f"\n  -- within-domain test --")
    results = {
        "domain": domain,
        "split_meta": {k: v for k, v in split.meta.items() if k != "build_meta"},
        "build_meta": split.meta.get("build_meta"),
        "qnn_info": qnn_info,
        "qnn_fit_seconds": qnn_res.fit_seconds,
        "qnn_loss_curve": qnn_res.loss_curve,
        "nn_info": {"hidden": list(nn_res.hidden), "n_weights": nn_res.n_weights},
        "nn_fit_seconds": nn_res.fit_seconds,
        "within": {},
    }

    qnn_pred = M.predict_qnn(qnn_res, split.X_test)
    nn_pred = M.predict_nn(nn_res, split.X_test)
    results["within"]["qnn"] = _evaluate(
        "QNN", split.y_test, qnn_pred, split.y_train, split.y_test_native, pre)
    results["within"]["nn"] = _evaluate(
        "NN (classical)", split.y_test, nn_pred, split.y_train, split.y_test_native, pre)

    results["_models"] = (qnn_res, nn_res, pre, split)  # stripped before writing
    return results


def run_cross(source: str, target: str, res: dict, freq_slug: str,
              max_rows: int | None) -> dict:
    """Train on source (already done), test on target. The core experiment."""
    qnn_res, nn_res, pre, split = res["_models"]
    print(f"\n  -- cross-domain: trained {source}, tested {target} --")

    try:
        Xc, yc, yc_native = data_mod.prepare_cross_domain(
            source, target, pre, freq_slug=freq_slug, max_rows=max_rows
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"    SKIPPED -- {exc}")
        return {}

    out = {
        "qnn": _evaluate("QNN", yc, M.predict_qnn(qnn_res, Xc),
                         split.y_train, yc_native, pre),
        "nn": _evaluate("NN (classical)", yc, M.predict_nn(nn_res, Xc),
                        split.y_train, yc_native, pre),
    }
    for k in ("qnn", "nn"):
        gap = res["within"][k]["scaled"]["r2"] - out[k]["scaled"]["r2"]
        out[k]["generalization_gap_r2"] = gap
        print(f"      {k} generalization gap (R2 within - R2 cross): {gap:+.4f}")

    print("\n    NOTE FOR BAB V: the two domains come from different detector "
          "networks\n    with different detection efficiencies. Part of this gap "
          "may be\n    instrument, not climate. State that beside the number.")
    return out


# ==========================================================================
# Runtime estimate
# ==========================================================================
def estimate(freq_slug: str, n_qubits: int) -> None:
    """Time a handful of iterations and extrapolate. Costs about a minute."""
    print("Timing a short run to extrapolate a full one...\n")
    for domain in ("tropis", "subtropis"):
        try:
            split, _, df = data_mod.prepare(
                domain, freq_slug=freq_slug, n_qubits=n_qubits,
                max_rows=64, verbose=False
            )
        except FileNotFoundError as exc:
            print(f"  {domain}: no table -- {exc}".split("\n")[0])
            continue

        full = data_mod.load_table(domain, freq_slug)
        n_full_train = int(len(full) * (1 - mcfg.TEST_FRACTION))

        # COBYLA needs at least n_weights + 2 evaluations before it will run,
        # so the probe cannot be shorter than the ansatz is wide.
        probe_iter = 4 * split.n_qubits * mcfg.ANSATZ_REPS + 8

        t0 = time.perf_counter()
        M.fit_qnn(split.X_train, split.y_train, split.n_qubits,
                  max_iter=probe_iter, verbose=False)
        dt = time.perf_counter() - t0

        # Cost scales roughly linearly in rows and in optimizer iterations.
        per_row_iter = dt / (len(split.X_train) * probe_iter)
        projected = per_row_iter * n_full_train * mcfg.MAX_ITER

        print(f"  {domain:<10s} {len(full):>10,} rows  "
              f"({n_full_train:,} train)  "
              f"-> approx {projected / 60:8.1f} min for {mcfg.MAX_ITER} iterations")
        if projected > 6 * 3600:
            print(f"             !! over six hours. Reduce rows, reduce MAX_ITER, "
                  f"or model a coarser resolution.")


# ==========================================================================
# Main
# ==========================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true",
                    help="tiny everything: 2 qubits, 12 iterations, 200 rows")
    ap.add_argument("--estimate", action="store_true",
                    help="time a short run and project a full one, then exit")
    ap.add_argument("--domain", choices=["tropis", "subtropis"], default=None)
    ap.add_argument("--freq", default=None,
                    choices=["monthly", "daily", "hourly"])
    ap.add_argument("--qubits", type=int, default=None)
    ap.add_argument("--max-iter", type=int, default=None)
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--no-cross", action="store_true")
    ap.add_argument("--tag", default="run")
    args = ap.parse_args()

    freq = args.freq or mcfg.FREQ_SLUG
    n_qubits = args.qubits or mcfg.N_QUBITS
    max_iter = args.max_iter or mcfg.MAX_ITER
    max_rows = args.max_rows

    if args.smoke:
        n_qubits = args.qubits or mcfg.SMOKE["N_QUBITS"]
        max_iter = args.max_iter or mcfg.SMOKE["MAX_ITER"]
        max_rows = args.max_rows or mcfg.SMOKE["MAX_ROWS"]
        mcfg.ANSATZ_REPS = mcfg.SMOKE["ANSATZ_REPS"]
        mcfg.NN_MAX_ITER = mcfg.SMOKE["NN_MAX_ITER"]
        print("SMOKE MODE -- results are meaningless, only the plumbing is "
              "being tested.\n")

    if freq == "hourly":
        print("!! freq=hourly. The target at this resolution is a zero-inflated "
              "COUNT,\n   not a density, and the row count is far beyond what a "
              "simulated QNN\n   can train on. Read the header of this file.\n")

    if args.estimate:
        estimate(freq, n_qubits)
        return

    domains = [args.domain] if args.domain else ["tropis", "subtropis"]
    all_results = {}

    for domain in domains:
        try:
            all_results[domain] = run_domain(
                domain, freq, n_qubits, max_iter, max_rows
            )
        except FileNotFoundError as exc:
            print(f"\n{domain}: SKIPPED\n{exc}")

    if not args.no_cross and len(all_results) == 2:
        print(f"\n{'=' * 74}\nCROSS-DOMAIN (the core experiment, F-04)\n{'=' * 74}")
        for src, tgt in (("tropis", "subtropis"), ("subtropis", "tropis")):
            all_results[src][f"cross_to_{tgt}"] = run_cross(
                src, tgt, all_results[src], freq, max_rows
            )
    elif not args.no_cross:
        print("\nCross-domain skipped: needs both tables built.")

    # ---- write ----------------------------------------------------------
    for r in all_results.values():
        r.pop("_models", None)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "timestamp_utc": stamp,
        "smoke": args.smoke,
        "model_config": {
            k: (list(v) if isinstance(v, tuple) else v)
            for k, v in vars(mcfg).items()
            if k.isupper() and not k.startswith("_")
            and isinstance(v, (int, float, str, bool, tuple, list, dict))
        },
        "resolved": {"freq_slug": freq, "n_qubits": n_qubits,
                     "max_iter": max_iter, "max_rows": max_rows},
        "results": all_results,
    }
    out = mcfg.RESULTS_DIR / f"{stamp}_{args.tag}{'_smoke' if args.smoke else ''}.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
