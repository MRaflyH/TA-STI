"""Step 4, part one: measure the tables so the decisions have evidence.

    python3 -m gfd.selection.description
    python3 -m gfd.selection.description --domain tropis
    python3 -m gfd.selection.description --step transforms
    python3 -m gfd.selection.description --json

Every figure quoted in DECISIONS.md from 2026-09-11 onward comes from here.
Nothing in this module fits, scales or selects; it reports.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, yeojohnson

from .. import config as cfg
from ..dataset import features

PI = np.pi

# Fractions of [0, pi] the middle 98% and the middle 50% of a column occupy
# after a source-fitted min-max. The circuit sees one full period of RZ(2x)
# across [0, pi], so these are the shares of that period the data actually uses.
SPREADS = (0.98, 0.50)

REDUNDANCY_THRESHOLD = 0.90


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def load(domain: str) -> pd.DataFrame:
    path = cfg.PROCESSED_DIR / f"gfd_{domain}_hourly.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist -- run `python3 -m gfd.dataset.build` first."
        )
    return pd.read_parquet(path)


def observed(df: pd.DataFrame) -> pd.DataFrame:
    """Rows where the target was observed at all.

    D-8 keeps months with coverage 0 so an unobserved zero is labelled rather
    than dropped. Every statistic about the target has to honour that label or
    it counts an absence of observation as an observation of absence.
    """
    return df.loc[df["coverage"] > 0]


def predictors(df: pd.DataFrame) -> list[str]:
    return [c for c in features.CANDIDATES if c in df.columns]


# --------------------------------------------------------------------------
# Transforms -- candidates for O-7, applied before the min-max onto [0, pi]
# --------------------------------------------------------------------------
def _identity(x: np.ndarray) -> np.ndarray:
    return x


def _log1p_shift(x: np.ndarray) -> np.ndarray:
    lo = np.nanmin(x)
    return np.log1p(x - lo if lo < 0 else x)


def _yeo_johnson(x: np.ndarray) -> np.ndarray:
    finite = x[np.isfinite(x)]
    if finite.size == 0 or np.nanstd(finite) == 0:
        return x
    try:
        return yeojohnson(finite.astype(np.float64))[0]
    except (ValueError, RuntimeWarning):
        return x


def _quantile_uniform(x: np.ndarray) -> np.ndarray:
    order = np.argsort(np.argsort(x))
    return order / max(len(x) - 1, 1)


TRANSFORMS = {
    "minmax": _identity,
    "log1p": _log1p_shift,
    "yeojohnson": _yeo_johnson,
    "quantile": _quantile_uniform,
}


def spread_of_period(x: np.ndarray, inner: float) -> float:
    """Share of [0, pi] the inner fraction of a min-maxed column occupies."""
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    lo, hi = float(np.min(x)), float(np.max(x))
    if hi <= lo:
        return 0.0
    tail = (1.0 - inner) / 2.0
    q_lo, q_hi = np.quantile(x, [tail, 1.0 - tail])
    return float((q_hi - q_lo) / (hi - lo))


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------
def contract(df: pd.DataFrame) -> dict:
    features.check_against_table(df.columns)
    names = predictors(df)
    return {
        "n_rows": int(len(df)),
        "n_columns": int(df.shape[1]),
        "n_candidates_present": len(names),
        "candidates_present": names,
        "n_cells": int(df[["lat", "lon"]].drop_duplicates().shape[0]),
    }


def target_shape(df: pd.DataFrame) -> dict:
    d = observed(df)
    y = d[cfg.TARGET].to_numpy(dtype=float)
    nz = y[y > 0]
    m, v = float(y.mean()), float(y.var())

    p_poisson = float(np.exp(-m))
    p_negbin = float("nan")
    if v > m > 0:
        r = m ** 2 / (v - m)
        p_negbin = float((r / (r + m)) ** r)

    return {
        "n_observed": int(len(d)),
        "n_unobserved": int(len(df) - len(d)),
        "zero_share_observed": float((y == 0).mean()),
        "zero_share_all": float((df[cfg.TARGET] == 0).mean()),
        "mean": m,
        "variance": v,
        "var_over_mean": float(v / m) if m else float("nan"),
        "nonzero_count": int(nz.size),
        "nonzero_skew_raw": float(pd.Series(nz).skew()),
        "nonzero_skew_log1p": float(pd.Series(np.log1p(nz)).skew()),
        "poisson_implied_p0": p_poisson,
        "negbin_implied_p0": p_negbin,
        "negbin_excess": float((y == 0).mean() - p_negbin),
        "mean_coverage": float(df["coverage"].mean()),
    }


def zero_structure(df: pd.DataFrame) -> dict:
    """Zero share under progressively harder convective conditioning.

    Answers whether the occurrence gate separates cleanly. A share that stays
    high under maximal conditioning means sampling zeros are irreducible at
    this resolution, which is a property of the grid rather than the model.
    """
    d = observed(df).sort_values(["lat", "lon", cfg.TIME_COL])
    y = d[cfg.TARGET].to_numpy(dtype=float)
    wet = y > 0

    def share(mask: np.ndarray) -> dict:
        n = int(mask.sum())
        return {
            "n": n,
            "zero_share": float((y[mask] == 0).mean()) if n else float("nan"),
        }

    out = {"unconditional": share(np.ones(len(d), dtype=bool))}

    top = {}
    for col in ("CAPE", "KX", "TCIW"):
        if col in d.columns:
            top[col] = d[col].to_numpy() >= d[col].quantile(0.90)

    if "CAPE" in top:
        out["top_decile_CAPE"] = share(top["CAPE"])
    if {"CAPE", "KX"} <= top.keys():
        out["top_decile_CAPE_KX"] = share(top["CAPE"] & top["KX"])
    if {"CAPE", "KX", "TCIW"} <= top.keys():
        out["top_decile_CAPE_KX_TCIW"] = share(
            top["CAPE"] & top["KX"] & top["TCIW"]
        )

    near = (
        pd.Series(wet.astype(float), index=d.index)
        .groupby([d["lat"], d["lon"]])
        .transform(lambda s: s.rolling(7, center=True, min_periods=1).max())
        .to_numpy()
        > 0
    )
    out["cell_active_within_3h"] = share(near)

    domain_active = d.groupby(cfg.TIME_COL)[cfg.TARGET].transform("max").to_numpy() > 0
    out["domain_active_this_hour"] = share(domain_active)
    out["domain_and_cell_active"] = share(domain_active & near)

    hourly = d.groupby("hour_of_day_local")[cfg.TARGET].apply(lambda s: (s == 0).mean())
    monthly = d.groupby("month_of_year")[cfg.TARGET].apply(lambda s: (s == 0).mean())
    out["by_local_hour"] = {int(k): float(v) for k, v in hourly.items()}
    out["by_month"] = {int(k): float(v) for k, v in monthly.items()}
    out["diurnal_spread"] = float(hourly.max() - hourly.min())
    out["seasonal_spread"] = float(monthly.max() - monthly.min())
    return out


def transform_spread(df: pd.DataFrame) -> pd.DataFrame:
    """O-7: how much of the encoding period each predictor uses, per transform."""
    d = observed(df)
    rows = []
    for col in predictors(d):
        x = d[col].to_numpy(dtype=float)
        row = {"feature": col}
        for tname, fn in TRANSFORMS.items():
            t = fn(x)
            for inner in SPREADS:
                row[f"{tname}_p{int(inner * 100)}"] = spread_of_period(t, inner)
        rows.append(row)
    return pd.DataFrame(rows).set_index("feature")


def redundancy(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Spearman among predictors, plus the pairs a screen would act on.

    The matrix is the Bab VI figure; the pair list is the decision object. A
    redundant predictor costs a qubit, which a classical model does not pay.
    """
    d = observed(df)
    names = predictors(d)
    matrix = d[names].corr(method="spearman")

    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            r = float(matrix.loc[a, b])
            if abs(r) >= REDUNDANCY_THRESHOLD:
                pairs.append({"a": a, "b": b, "spearman": r})
    pairs.sort(key=lambda p: -abs(p["spearman"]))
    return matrix, pairs


def cross_domain_range(source: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    """What a source-fitted min-max does to the other domain's rows.

    Reports saturation, not aliasing: the scaler clips, so an out-of-range
    value becomes exactly 0 or exactly pi. A predictor saturating most of the
    target domain contributes a constant to the circuit, not noise.
    """
    s, t = observed(source), observed(target)
    rows = []
    for col in predictors(s):
        if col not in t.columns:
            continue
        lo, hi = float(s[col].min()), float(s[col].max())
        x = t[col].to_numpy(dtype=float)
        if hi <= lo:
            rows.append({"feature": col, "below": 1.0, "above": 0.0, "saturated": 1.0})
            continue
        below = float((x < lo).mean())
        above = float((x > hi).mean())
        rows.append({
            "feature": col,
            "below": below,
            "above": above,
            "saturated": below + above,
            "source_lo": lo,
            "source_hi": hi,
            "target_lo": float(np.min(x)),
            "target_hi": float(np.max(x)),
        })
    return pd.DataFrame(rows).set_index("feature").sort_values(
        "saturated", ascending=False
    )


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------
def _pct(v: float) -> str:
    return "n/a" if not np.isfinite(v) else f"{v * 100:6.2f}%"


def describe(domain: str, steps: set[str]) -> dict:
    df = load(domain)
    print(f"\n{'=' * 70}\n{domain}")
    report: dict = {"domain": domain}

    if "contract" in steps:
        report["contract"] = contract(df)
        c = report["contract"]
        print(f"  {c['n_rows']:,} rows x {c['n_columns']} cols, "
              f"{c['n_cells']} cells, {c['n_candidates_present']} candidates")

    if "target" in steps:
        report["target"] = t = target_shape(df)
        print(f"\n  -- target")
        print(f"  observed {t['n_observed']:,}  unobserved {t['n_unobserved']:,}")
        print(f"  zero share {_pct(t['zero_share_observed'])} observed, "
              f"{_pct(t['zero_share_all'])} all rows")
        print(f"  mean {t['mean']:.4f}  var {t['variance']:.2f}  "
              f"var/mean {t['var_over_mean']:.2f}")
        print(f"  P(0): observed {t['zero_share_observed']:.4f}  "
              f"Poisson {t['poisson_implied_p0']:.4f}  "
              f"NegBin {t['negbin_implied_p0']:.4f}  "
              f"excess {t['negbin_excess']:+.4f}")
        print(f"  nonzero skew: raw {t['nonzero_skew_raw']:.2f}  "
              f"log1p {t['nonzero_skew_log1p']:.2f}")

    if "zeros" in steps:
        report["zeros"] = z = zero_structure(df)
        print(f"\n  -- zero structure")
        for k in ("unconditional", "top_decile_CAPE", "top_decile_CAPE_KX",
                  "top_decile_CAPE_KX_TCIW", "cell_active_within_3h",
                  "domain_active_this_hour", "domain_and_cell_active"):
            if k in z:
                print(f"  {k:<28} n={z[k]['n']:>9,}  {_pct(z[k]['zero_share'])}")
        print(f"  diurnal spread {z['diurnal_spread'] * 100:.2f} pts   "
              f"seasonal spread {z['seasonal_spread'] * 100:.2f} pts")

    if "transforms" in steps:
        spread = transform_spread(df)
        report["transforms"] = spread.to_dict(orient="index")
        print(f"\n  -- share of [0, pi] used, by transform "
              f"(p98 / p50, higher is better)")
        cols = [f"{t}_p{int(i * 100)}" for t in TRANSFORMS for i in SPREADS]
        print(spread[cols].to_string(
            float_format=lambda v: f"{v * 100:5.1f}"))

    if "redundancy" in steps:
        matrix, pairs = redundancy(df)
        report["redundancy_pairs"] = pairs
        print(f"\n  -- redundant pairs (|spearman| >= {REDUNDANCY_THRESHOLD})")
        if not pairs:
            print("  none")
        for p in pairs:
            print(f"  {p['a']:<20} {p['b']:<20} {p['spearman']:+.3f}")

    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), default=None)
    ap.add_argument(
        "--step",
        action="append",
        choices=["contract", "target", "zeros", "transforms", "redundancy", "cross"],
        help="repeatable; default is every step",
    )
    ap.add_argument("--json", action="store_true",
                    help=f"also write {cfg.PROCESSED_DIR}/description_<domain>.json")
    args = ap.parse_args()

    steps = set(args.step or
                ["contract", "target", "zeros", "transforms", "redundancy", "cross"])
    names = [args.domain] if args.domain else sorted(cfg.DOMAINS)

    reports = {n: describe(n, steps) for n in names}

    if "cross" in steps and len(names) == 2:
        a, b = names
        fa, fb = load(a), load(b)
        for src, tgt, sdf, tdf in ((a, b, fa, fb), (b, a, fb, fa)):
            table = cross_domain_range(sdf, tdf)
            reports[src][f"saturation_on_{tgt}"] = table.to_dict(orient="index")
            print(f"\n{'=' * 70}\n{src} scaler applied to {tgt} rows")
            print(table[["below", "above", "saturated"]].to_string(
                float_format=lambda v: f"{v * 100:6.2f}"))

    if args.json:
        for n, r in reports.items():
            path = cfg.PROCESSED_DIR / f"description_{n}.json"
            path.write_text(json.dumps(r, indent=2), encoding="utf-8")
            print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
    