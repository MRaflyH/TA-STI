"""Stage 3 — build the derived features and declare the transform chain.

    python3 -m gfd.selection.prepare            # inspect the chain on both domains
    python3 -m gfd.selection.prepare --domain tropis

The only module in `selection/` that changes a value. D-18 splits the work:
`selection/` owns **what** the chain is, `training/` owns **when and on what**
— it fits the chain on each fold's training rows and applies it to the rest.
Neither duplicates the other, and no third place transforms anything.

`screen.py` and `ablate.py` import the derived features from here rather than
rebuilding them, per §3: a benchmark that constructs its own version can
measure something different from the one that trains.

The chain, in order:

  1. **Derive.** Five temporal encodings (D-20) and two features from existing
     columns (D-21 step 2). Nothing is materialised in either table (D-13).
  2. **Select.** The modelled set for this domain and stage, read through the
     contract (D-22, D-24, D-25, D-27).
  3. **Scale.** Two classes (D-28). A variable with a definitional bound uses
     that bound. Everything else uses `arctan((x - median) / IQR)` with the
     median and IQR fitted on training rows only.
  4. **Nothing else.** No skew transform and no point-mass handling (D-29).

The output range is [0, pi]. The feature map is periodic with period pi in the
data, so that is one full period rather than an arbitrary convention, and a
value outside it wraps to a different angle with no error raised.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from .. import config as cfg
from ..dataset import features as feat

ROTATION_MAX = np.pi

# --------------------------------------------------------------------------
# Scaling classes (D-28)
# --------------------------------------------------------------------------
# A definitional bound is used only where the variable can actually occupy it.
# `RH2M` runs to exactly 100 on 56 512 subtropis rows, and the cyclic encodings
# span [-1, 1] by construction, so both are genuinely bounded in the data.
#
# `lat` and `lon` are bounded by the planet and are deliberately NOT here. A
# tropis box spanning 2 degrees of latitude scaled by [-90, 90] would occupy
# 1,1% of the rotation range -- a definitional bound the data comes nowhere
# near is worse than a fitted one, not better. They take the fitted map like
# any other unbounded variable.
PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    "RH2M": (0.0, 100.0),
    "hour_sin": (-1.0, 1.0),
    "hour_cos": (-1.0, 1.0),
    "doy_sin": (-1.0, 1.0),
    "doy_cos": (-1.0, 1.0),
    "cos_sza": (-1.0, 1.0),
}


# --------------------------------------------------------------------------
# Step 1 — derive
# --------------------------------------------------------------------------
def solar_zenith_cos(day_of_year, hour_local, lat_deg):
    """Cosine of the solar zenith angle. Standard astronomical approximation."""
    decl = np.radians(23.44) * np.sin(2 * np.pi * (day_of_year - 81) / 365.25)
    ha = np.radians(15.0 * (hour_local - 12.0))
    lat = np.radians(lat_deg)
    return np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(ha)


def temporal_candidates(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """D-20. Five encodings; the ablation decided which survive.

    An integer hour puts 23:00 and 00:00 23 apart, which is why none of the
    raw temporal columns may be a predictor in its raw form.
    """
    h = df["hour_of_day_local"].to_numpy()
    d = df["day_of_year"].to_numpy()
    return {
        "hour_sin": np.sin(2 * np.pi * h / 24.0),
        "hour_cos": np.cos(2 * np.pi * h / 24.0),
        "doy_sin": np.sin(2 * np.pi * d / 365.25),
        "doy_cos": np.cos(2 * np.pi * d / 365.25),
        "cos_sza": solar_zenith_cos(d, h, df["lat"].to_numpy()),
    }


def derived_candidates(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """D-21 step 2. Functions of existing columns, with no external source.

    `cloud_water` -- column-integrated condensate, liquid plus ice. The two
    domains favour different phases, so the sum is phase-agnostic.

    `dewpoint_depression` -- T2M minus the dew point in matching units. The
    parents correlate at 0,795 in subtropis; their difference is a distinct
    quantity, the low-level moisture deficit and a proxy for the lifting
    condensation level.
    """
    return {
        "cloud_water": df["TCLW"].to_numpy() + df["TCIW"].to_numpy(),
        "dewpoint_depression": df["T2M"].to_numpy() - (df["D2M"].to_numpy() - 273.15),
    }


def with_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Every candidate the pipeline can see: table columns plus derivations."""
    out = {c: df[c].to_numpy() for c in feat.CANDIDATES if c in df.columns}
    out.update(temporal_candidates(df))
    out.update(derived_candidates(df))
    return pd.DataFrame(out, index=df.index)


def matrix(df: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """The named columns, in the given order. Order is part of the contract.

    A trained circuit is N rotations bound to N named variables in a fixed
    order, so a reordered matrix is a different model's input (D-27).
    """
    have = with_derived(df)
    missing = [n for n in names if n not in have.columns]
    if missing:
        raise KeyError(f"{missing} are neither table columns nor derived here. "
                       f"If they should exist, add them to this module.")
    return have[list(names)]


# --------------------------------------------------------------------------
# Step 3 — the chain
# --------------------------------------------------------------------------
class Chain:
    """Fitted on training rows, applied to anything. Carries its own parameters.

    §3 requires a fitted model to travel with the scaler it was fitted with, so
    `training/` returns the model and its Chain together and `evaluation/` has
    no way to reach for a different one.
    """

    def __init__(self, names: list[str]):
        self.names = list(names)
        self.params: dict[str, dict] = {}

    def fit(self, X: pd.DataFrame) -> "Chain":
        if list(X.columns) != self.names:
            raise ValueError(f"column order differs from the chain's: "
                             f"{list(X.columns)} against {self.names}")
        for c in self.names:
            v = X[c].to_numpy(dtype=float)
            if not np.isfinite(v).all():
                raise ValueError(
                    f"{c} carries non-finite values. D-19 drops structurally "
                    f"undefined columns and nothing is imputed, so this is a "
                    f"fault rather than an expected case."
                )
            if c in PHYSICAL_BOUNDS:
                lo, hi = PHYSICAL_BOUNDS[c]
                self.params[c] = {"kind": "bound", "lo": lo, "hi": hi}
            else:
                med = float(np.median(v))
                q1, q3 = np.quantile(v, [0.25, 0.75])
                iqr = float(q3 - q1)
                if iqr <= 0:
                    # A column that is one value across the training rows would
                    # divide by zero. Raise rather than silently emit a
                    # constant qubit -- that is the fault D-27 excludes lat and
                    # lon from the shared set to avoid.
                    raise ValueError(
                        f"{c} has zero interquartile range on the training "
                        f"rows, so it would arrive at the circuit as a "
                        f"constant. Selection should not have chosen it."
                    )
                self.params[c] = {"kind": "arctan", "centre": med, "scale": iqr}
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        if not self.params:
            raise RuntimeError("Chain.transform called before fit.")
        if list(X.columns) != self.names:
            raise ValueError(f"column order differs from the chain's: "
                             f"{list(X.columns)} against {self.names}")
        cols = []
        for c in self.names:
            p = self.params[c]
            v = X[c].to_numpy(dtype=float)
            if p["kind"] == "bound":
                # Clipping is correct here and only here: the bound is
                # definitional, so a value outside it is impossible rather than
                # unseen.
                u = np.clip((v - p["lo"]) / (p["hi"] - p["lo"]), 0.0, 1.0)
            else:
                # Nothing clips. An unseen value larger than anything in
                # training still maps above it -- compressed, but ordered and
                # distinguishable (D-28).
                u = np.arctan((v - p["centre"]) / p["scale"]) / np.pi + 0.5
            cols.append(u * ROTATION_MAX)
        return np.column_stack(cols)

    def to_dict(self) -> dict:
        return {"names": self.names, "rotation_max": ROTATION_MAX,
                "params": self.params}


def chain_for(df: pd.DataFrame, names: list[str]) -> tuple[Chain, np.ndarray]:
    """Fit on these rows and return the chain with the angles it produced.

    The rows handed in must be training rows. This module has no way to check
    that, so `training/` owns the guarantee.
    """
    X = matrix(df, names)
    ch = Chain(names).fit(X)
    return ch, ch.transform(X)


# --------------------------------------------------------------------------
# Inspection
# --------------------------------------------------------------------------
def describe(domain: str) -> dict:
    """What the chain does to each feature, for every set this domain uses."""
    path = cfg.processed_table(domain)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist -- run gfd.dataset.build first.")
    df = pd.read_parquet(path)
    train = df[df["year"] != 2024]

    print(f"\n{'=' * 78}\n{domain.upper()} — {cfg.DOMAINS[domain].label}\n{'=' * 78}")
    print(f"  fitted on {len(train):,} training rows, 2024 held out")

    out = {}
    sets = {f"within/{st}": feat.modelled(domain, st) for st in feat.STAGES}
    sets.update({f"shared/{st}": feat.modelled_shared(st) for st in feat.STAGES})

    for label, names in sets.items():
        ch, Z = chain_for(train, names)
        q = np.quantile(Z, [0.25, 0.75], axis=0)
        span = q[1] - q[0]
        out[label] = {"chain": ch.to_dict(),
                      "iqr_share_of_range": {n: float(s / ROTATION_MAX)
                                             for n, s in zip(names, span)}}
        print(f"\n  [{label}] {len(names)} features")
        print(f"  {'feature':<22}{'class':>10}{'centre':>14}{'scale':>14}{'iqr share':>11}")
        for n, s in zip(names, span):
            p = ch.params[n]
            if p["kind"] == "bound":
                print(f"  {n:<22}{'bound':>10}{p['lo']:>14.4g}{p['hi']:>14.4g}"
                      f"{s / ROTATION_MAX:>11.4f}")
            else:
                print(f"  {n:<22}{'arctan':>10}{p['centre']:>14.4g}{p['scale']:>14.4g}"
                      f"{s / ROTATION_MAX:>11.4f}")
        print(f"  'iqr share' is the share of [0, pi] this feature's middle 50% occupies.")
        print(f"  angles span {Z.min():.4f} to {Z.max():.4f}; the encoding's period is "
              f"{ROTATION_MAX:.4f}.")

        # The two classes do not produce comparable spreads, and D-30 requires
        # the gap to be reported rather than left to be noticed. A sinusoid
        # spends most of its time near its extremes, so a bounded feature's
        # middle half genuinely spans most of the range; arctan compresses
        # tails by construction and lands near 0,29 whatever it is given.
        bound = [float(s_) / ROTATION_MAX for n, s_ in zip(names, span)
                 if ch.params[n]["kind"] == "bound"]
        fitted = [float(s_) / ROTATION_MAX for n, s_ in zip(names, span)
                  if ch.params[n]["kind"] == "arctan"]
        if bound and fitted:
            mb, mf = float(np.mean(bound)), float(np.mean(fitted))
            out[label]["class_spread"] = {
                "bound_mean": mb, "fitted_mean": mf, "ratio": mb / mf,
                "n_bound": len(bound), "n_fitted": len(fitted),
            }
            print(f"  class spread: {len(bound)} bounded mean {mb:.4f}, "
                  f"{len(fitted)} fitted mean {mf:.4f} — ratio {mb / mf:.2f}x (D-30)")
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description="Stage 3. Declares the transform chain; training/ executes it.")
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS))
    ap.add_argument("--no-json", action="store_true")
    args = ap.parse_args(argv)

    domains = [args.domain] if args.domain else sorted(cfg.DOMAINS)
    results = {d: describe(d) for d in domains}

    print(f"\n{'=' * 78}")
    print("The chain is declared here and fitted per fold by training/ (D-18). The")
    print("parameters above come from all training years at once and are for")
    print("inspection only — a fold fits its own.")

    if not args.no_json:
        for d, r in results.items():
            p = cfg.PROCESSED_DIR / f"prepare_{d}.json"
            p.write_text(json.dumps(r, indent=2), encoding="utf-8")
            print(f"\n[write] {p}")


if __name__ == "__main__":
    main()
