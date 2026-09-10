"""Scoring: window aggregation, GFD conversion, and the metric sets.

Three ideas do most of the work here.

D-04, aggregation. The model predicts one cell-hour. Reported results sum
those predictions into 1, 3, 6 and 24-hour windows. This is a REPORTING
change: training stays hourly and stays 94,30% / 97,00% zeros. Measured zero
share by window, build of 2026-09-06:

    window   tropis   subtropis
       1 h   94,30%      97,00%
       3 h   90,09%      94,52%
       6 h   85,40%      91,35%
      24 h   64,63%      76,63%

D-03, inversion order. Predictions come out of the models in standardised log
space. They must be un-standardised, then expm1'd, and only THEN summed.
Summing in log space gives a geometric mean, not a total -- a silent wrong
answer, so `aggregate_windows` takes RAW COUNTS and refuses to guess.

D-07 and D-12, the floor. Against a 94-97% zero target, "predict zero
everywhere" already explains most of the variance. Every metric table here
carries the trivial baseline's score in the same units, because an R2 without
it is uninterpretable rather than merely incomplete.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as mcfg

HOURS_PER_YEAR = 365.25 * 24.0          # 8766, matching the pipeline


# --------------------------------------------------------------------------
# D-03. Getting predictions back onto the count scale
# --------------------------------------------------------------------------
def to_counts(y_model: np.ndarray, scaler) -> np.ndarray:
    """Standardised log space -> raw counts. Order matters and is fixed here.

    inverse_y undoes the standardisation; invert_target undoes the log1p.
    Doing either alone, or doing them in the other order, produces plausible
    numbers that are wrong -- which is why no caller is trusted to remember.
    """
    from .dataset import invert_target
    return np.maximum(invert_target(scaler.inverse_y(y_model)), 0.0)


# --------------------------------------------------------------------------
# D-04. Windows
# --------------------------------------------------------------------------
def aggregate_windows(
    index: pd.DataFrame,
    predicted_counts: np.ndarray,
    observed_counts: np.ndarray,
    hours: int,
) -> pd.DataFrame:
    """Sum RAW counts per (cell, window). Both inputs must be counts already.

    Floor-and-group rather than resample: resample would invent rows inside
    the three excluded MERLIN months and score them as zeros. Grouping on a
    floored timestamp touches only rows that exist.

    Returns one row per (lat, lon, window) with predicted, observed, the cell
    area and the window length -- everything `to_gfd` needs.
    """
    if len(index) != len(predicted_counts) or len(index) != len(observed_counts):
        raise ValueError(
            f"length mismatch: index {len(index)}, predicted "
            f"{len(predicted_counts)}, observed {len(observed_counts)}"
        )

    df = index.copy()
    df["predicted"] = np.asarray(predicted_counts, dtype=float)
    df["observed"] = np.asarray(observed_counts, dtype=float)

    if hours == 1:
        out = df.rename(columns={mcfg.TIME_COL: "window"})
    else:
        df["window"] = df[mcfg.TIME_COL].dt.floor(f"{hours}h")
        out = (df.groupby(["lat", "lon", "window"], observed=True)
                 .agg(predicted=("predicted", "sum"),
                      observed=("observed", "sum"),
                      area_km2=("area_km2", "first"),
                      n_hours=("predicted", "size"))
                 .reset_index())

    if "n_hours" not in out.columns:
        out["n_hours"] = 1
    return out


def to_gfd(counts: np.ndarray, area_km2: np.ndarray,
           n_hours: np.ndarray) -> np.ndarray:
    """Counts in a window -> flashes per km2 per year.

    The units the thesis speaks in (D-03). Annualising an hourly window
    inflates a single flash by ~8.766x, which is exactly why the models are
    not fitted on this scale -- but it is the right scale to REPORT on,
    because it is comparable across the hourly, daily and monthly builds and
    it is what the predecessor study used.
    """
    years = np.asarray(n_hours, dtype=float) / HOURS_PER_YEAR
    return np.asarray(counts, dtype=float) / np.asarray(area_km2, float) / years


# --------------------------------------------------------------------------
# Metric sets
# --------------------------------------------------------------------------
def smearing_factor(observed_counts: np.ndarray,
                    predicted_counts: np.ndarray) -> float:
    """Multiplicative correction for retransformation bias (D-03, D-04).

    Fitting MSE on log1p(count) gives the conditional mean IN LOG SPACE.
    expm1 of that is a median-like quantity, and by Jensen's inequality it
    sits below the conditional mean of the count. So inverting a log-space
    prediction systematically UNDER-predicts, and D-04's summation multiplies
    the error rather than cancelling it.

    Measured on tropis fold 2: mean predicted 6-hour GFD was 0,37 to 0,45 of
    mean observed across the whole ladder -- every model, so it is the
    transform and not the model.

    This is the one-parameter version of Duan's smearing estimator: rescale so
    the mean predicted count matches the mean observed count. FIT ON
    VALIDATION, never on test -- a factor fitted on test rows is target
    leakage dressed as calibration.

    Returns 1,0 when the correction cannot be computed, so a degenerate model
    passes through unchanged rather than producing infinities.
    """
    pred_mean = float(np.mean(predicted_counts))
    obs_mean = float(np.mean(observed_counts))
    if not np.isfinite(pred_mean) or pred_mean <= 1e-12:
        return 1.0
    factor = obs_mean / pred_mean
    return float(factor) if np.isfinite(factor) and factor > 0 else 1.0


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                       baseline: float | None = None) -> dict:
    """RMSE, MAE, R2, NRMSE, bias -- with the floor alongside.

    NRMSE is normalised by the observed RANGE, which is the convention NF-01
    was written against. On a target this sparse it is dominated by the
    maximum, so report it beside RMSE rather than instead of it.

    `bias` is mean(pred) - mean(true). It matters more here than usual: D-04
    sums hourly predictions into windows, and a systematic per-hour bias does
    not cancel under summation, it multiplies.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    resid = y_pred - y_true
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    rng = float(y_true.max() - y_true.min())

    out = {
        "rmse": rmse,
        "mae": float(np.mean(np.abs(resid))),
        "r2": float(1.0 - np.sum(resid ** 2) / ss_tot) if ss_tot > 0 else float("nan"),
        "nrmse": rmse / rng if rng > 0 else float("nan"),
        "bias": float(resid.mean()),
        "mean_observed": float(y_true.mean()),
        "mean_predicted": float(y_pred.mean()),
        "n": int(len(y_true)),
    }
    if baseline is not None:
        # The floor, in the same units. Without it an R2 near zero looks like
        # failure and an R2 near 0,9 looks like success, and on a 94%-zero
        # target neither reading is safe.
        base_rmse = float(np.sqrt(np.mean((y_true - baseline) ** 2)))
        out["baseline_rmse"] = base_rmse
        out["skill_score"] = float(1.0 - rmse / base_rmse) if base_rmse > 0 else float("nan")
    return out


def classification_metrics(y_true: np.ndarray, p_pred: np.ndarray,
                           threshold: float | None = None) -> dict:
    """Log loss, AUC, average precision, Brier, and F1 at a threshold.

    AUC and average precision are threshold-free, which matters at a 5,7%
    base rate where any fixed cut is arbitrary. Average precision is the more
    honest headline of the two: AUC flatters a rare-positive problem because
    the vast majority of negative pairs are easy.

    The default threshold is the observed base rate rather than 0,5. At 5,7%
    positives a 0,5 cut predicts almost nothing and reports F1 near zero for
    a model that may be ranking well.
    """
    from sklearn.metrics import (
        average_precision_score, brier_score_loss, f1_score,
        log_loss, roc_auc_score,
    )

    y_true = np.asarray(y_true, dtype=int)
    p = np.clip(np.asarray(p_pred, dtype=float), 1e-9, 1 - 1e-9)
    thr = float(y_true.mean()) if threshold is None else threshold

    out = {
        "log_loss": float(log_loss(y_true, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y_true, p)),
        "threshold": thr,
        "base_rate": float(y_true.mean()),
        "n": int(len(y_true)),
    }
    if 0 < y_true.sum() < len(y_true):
        out["auc"] = float(roc_auc_score(y_true, p))
        out["avg_precision"] = float(average_precision_score(y_true, p))
        out["f1"] = float(f1_score(y_true, (p >= thr).astype(int),
                                   zero_division=0))
    else:
        out["auc"] = out["avg_precision"] = out["f1"] = float("nan")

    # The floor: predict the base rate for every row.
    base = np.full_like(p, out["base_rate"])
    out["baseline_log_loss"] = float(log_loss(y_true, np.clip(base, 1e-9, 1 - 1e-9),
                                              labels=[0, 1]))
    out["skill_score"] = float(1.0 - out["log_loss"] / out["baseline_log_loss"])
    return out


# --------------------------------------------------------------------------
# D-04. Calibration -- the cost of summing predictions
# --------------------------------------------------------------------------
def calibration(windowed: pd.DataFrame) -> dict:
    """Mean predicted against mean observed, per window.

    Summing hourly predictions is unbiased only if the model is. A model that
    under-predicts by 10% per hour under-predicts a 6-hour total by 10% too:
    the error accumulates rather than cancelling. `ratio` below 1 means
    under-prediction, and it should be reported beside every windowed result.
    """
    obs = float(windowed["observed"].mean())
    pred = float(windowed["predicted"].mean())
    return {
        "mean_observed": obs,
        "mean_predicted": pred,
        "ratio": pred / obs if obs > 0 else float("nan"),
        "zero_share_observed": float((windowed["observed"] == 0).mean()),
        "n_windows": int(len(windowed)),
    }


def evaluate_windows(
    index: pd.DataFrame,
    predicted_counts: np.ndarray,
    observed_counts: np.ndarray,
    windows: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    """The D-04 curve: metrics at every reporting window, in GFD units.

    One row per window, so the skill-versus-reporting-resolution curve drops
    straight into Bab IV. Also carries the observed zero share per window, so
    a reader can see the target changing shape as the window widens.
    """
    rows = []
    for hours in (windows or mcfg.REPORTING_WINDOWS_H):
        w = aggregate_windows(index, predicted_counts, observed_counts, hours)
        gfd_pred = to_gfd(w["predicted"], w["area_km2"], w["n_hours"])
        gfd_obs = to_gfd(w["observed"], w["area_km2"], w["n_hours"])

        row = {"window_h": hours}
        row.update(regression_metrics(gfd_obs, gfd_pred,
                                      baseline=float(gfd_obs.mean())))
        row.update({f"cal_{k}": v for k, v in calibration(w).items()})
        rows.append(row)

    return pd.DataFrame(rows)
