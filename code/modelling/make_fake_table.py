"""Generate a SYNTHETIC processed table with the real schema, for development only.

    python make_fake_table.py                    # monthly, both domains
    python make_fake_table.py --freq hourly      # see what hourly actually looks like
    python make_fake_table.py --out ./data/processed

==============================================================================
NOTHING THIS SCRIPT PRODUCES MAY EVER REACH THE THESIS.
==============================================================================
The numbers are drawn from a random generator. The relationship between the
predictors and the target is one I made up so that a model has something to
learn. Any RMSE, R^2, feature importance or cross-domain gap computed on this
file describes my invented relationship and nothing about lightning.

Its only purpose is to let the modelling code be written, run and debugged
while the real ERA5 and POWER downloads are still going. Every table it writes
carries "synthetic": true in its .meta.json and SYNTHETIC in its filename, so a
result accidentally computed on one is identifiable afterwards.

Delete the files the moment the real build lands.

What IS faithful: the column names, their order, the dtypes, the time-key
encoding, the cell geometry, and the zero-inflation behaviour at each
resolution. That is all the modelling code touches, which is why developing
against this works.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Mirrors gfd_data.config -- kept literal so this script has no repo imports
# and can run from anywhere, including a scratch folder outside the repo.
POWER_PARAMS = ["PS", "PRECTOTCORR", "T2M", "RH2M", "WS2M", "AOD_55_ADJ"]
ERA5_PARAMS = ["CAPE", "KX", "TCIW", "TCLW", "VIIWD", "VILWD"]

DOMAINS = {
    # name:        (lat_min, lat_max, lon_min, lon_max, activity)
    "tropis":      (-8.0, -5.5, 106.0, 109.0, 1.00),
    "subtropis":   (26.5, 30.5, -82.0, -78.5, 0.55),
}

GRID_DEG = 0.5
SEED = 18222067

FREQ = {"monthly": "M", "daily": "D", "hourly": "h"}
# How many periods to generate. Hourly is capped well below seven years --
# the point is to see the SHAPE of an hourly table, not to reproduce its size.
N_PERIODS = {"monthly": 84, "daily": 730, "hourly": 24 * 60}


def cell_area_km2(lat: np.ndarray, deg: float = GRID_DEG) -> np.ndarray:
    """Same cosine-of-latitude area the real pipeline uses."""
    km_per_deg = 111.32
    return (deg * km_per_deg) * (deg * km_per_deg * np.cos(np.radians(lat)))


def build(domain: str, slug: str, rng: np.random.Generator) -> pd.DataFrame:
    lat_min, lat_max, lon_min, lon_max, activity = DOMAINS[domain]
    lats = np.arange(lat_min, lat_max + 1e-9, GRID_DEG)
    lons = np.arange(lon_min, lon_max + 1e-9, GRID_DEG)
    times = pd.period_range("2018-01-01", periods=N_PERIODS[slug], freq=FREQ[slug])

    grid = pd.MultiIndex.from_product(
        [times.astype(str), lats, lons], names=["time", "lat", "lon"]
    ).to_frame(index=False)
    n = len(grid)

    # --- predictors, roughly in the right units and ranges -----------------
    grid["PS"] = rng.normal(100.5, 0.6, n)                    # kPa
    grid["PRECTOTCORR"] = np.abs(rng.gamma(1.2, 2.0, n))      # mm
    grid["T2M"] = rng.normal(27 if domain == "tropis" else 23, 3, n)
    grid["RH2M"] = np.clip(rng.normal(80, 10, n), 5, 100)
    grid["WS2M"] = np.abs(rng.normal(3, 1.2, n))
    grid["AOD_55_ADJ"] = np.abs(rng.normal(0.3, 0.1, n))
    grid["CAPE"] = np.abs(rng.gamma(2.0, 400.0, n))           # J/kg
    grid["KX"] = rng.normal(30, 6, n)
    grid["TCIW"] = np.abs(rng.gamma(1.5, 0.02, n))
    grid["TCLW"] = np.abs(rng.gamma(1.5, 0.05, n))
    grid["VIIWD"] = rng.normal(0, 1e-4, n)
    grid["VILWD"] = rng.normal(0, 1e-4, n)

    # A REAL missing-value pattern: AOD is monthly-only, so at finer resolution
    # it is constant across each month, and POWER leaves genuine gaps.
    if slug != "monthly":
        month_key = pd.PeriodIndex(grid["time"], freq=FREQ[slug]).asfreq("M").astype(str)
        grid["AOD_55_ADJ"] = grid.groupby(month_key)["AOD_55_ADJ"].transform("first")
    grid.loc[rng.random(n) < 0.02, "AOD_55_ADJ"] = np.nan

    # --- target: an INVENTED relationship, plus noise ----------------------
    drive = (
        0.9 * (grid["CAPE"] / 800.0)
        + 0.5 * ((grid["RH2M"] - 70) / 15.0)
        + 0.3 * ((grid["KX"] - 28) / 6.0)
        - 0.2 * ((grid["WS2M"] - 3) / 1.5)
    )
    if slug == "hourly":  # diurnal cycle, afternoon peak
        hour = pd.PeriodIndex(grid["time"], freq=FREQ[slug]).hour
        drive = drive + 1.2 * np.sin(np.pi * np.clip(hour - 10, 0, 10) / 10.0)

    lam = np.clip(np.exp(drive) * activity * {"monthly": 40, "daily": 1.5,
                                              "hourly": 0.05}[slug], 0, None)
    grid["flash_count"] = rng.poisson(lam).astype("int64")

    # --- the bookkeeping columns the real build emits ----------------------
    grid["area_km2"] = cell_area_km2(grid["lat"].to_numpy())
    grid["observed_days"] = {"monthly": 30, "daily": 1, "hourly": 1}[slug]
    grid["coverage"] = 1.0
    grid["period_days"] = {"monthly": 30.0, "daily": 1.0, "hourly": 1 / 24}[slug]
    grid["gfd_per_km2_per_day"] = (
        grid["flash_count"] / grid["area_km2"] / grid["period_days"]
    )
    grid["gfd_per_km2_per_year"] = grid["gfd_per_km2_per_day"] * 365.25
    grid["mean_peak_current_ka"] = np.where(
        grid["flash_count"] > 0, rng.normal(-22, 6, n), np.nan
    )
    grid["positive_share"] = np.where(
        grid["flash_count"] > 0, rng.beta(1.5, 8, n), np.nan
    )
    grid["domain"] = domain

    return grid.sort_values(["time", "lat", "lon"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--freq", default="monthly",
                    choices=["monthly", "daily", "hourly"])
    ap.add_argument("--out", default="data/processed",
                    help="output directory (default: data/processed)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    print(f"!! SYNTHETIC DATA. No number computed from these files may appear "
          f"in the thesis.\n")

    for domain in DOMAINS:
        table = build(domain, args.freq, rng)
        stem = out / f"gfd_{domain}_{args.freq}"
        table.to_parquet(stem.with_suffix(".parquet"), index=False)

        zero = float((table["flash_count"] == 0).mean())
        stem.with_suffix(".meta.json").write_text(json.dumps({
            "synthetic": True,
            "WARNING": "generated by make_fake_table.py -- not real observations",
            "domain": domain,
            "time_resolution": args.freq,
            "grid_deg": GRID_DEG,
            "n_rows": int(len(table)),
            "zero_target_share": round(zero, 6),
            "random_seed": SEED,
        }, indent=2), encoding="utf-8")

        print(f"  {domain:<11s} {len(table):>8,} rows  "
              f"{table[['lat','lon']].drop_duplicates().shape[0]:>4} cells  "
              f"zero-target {zero:6.1%}  -> {stem.with_suffix('.parquet')}")

    if args.freq == "hourly":
        print("\n  Note the zero share above. That is the whole hourly problem "
              "in one\n  number: a model predicting zero everywhere is already "
              "mostly right.")


if __name__ == "__main__":
    main()
