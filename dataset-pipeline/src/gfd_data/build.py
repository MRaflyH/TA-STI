"""Join the four sources into one model-ready table per climate domain.

Run after the raw files are in place::

    python -m gfd_data.build

Output: ``data/processed/gfd_<domain>.parquet`` (and .csv), one row per
(0.5 deg cell, month), with spatial + meteorological predictors and the GFD
target.

The join is a LEFT join onto the lightning skeleton, so a cell-month that
exists in the lightning grid but is missing from POWER or ERA5 shows up as a
row full of NaN rather than silently disappearing. Check the coverage report
this prints before modelling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config as cfg
from . import era5 as era5_mod
from . import lightning as lit
from . import power as power_mod

LIGHTNING_LOADER = {
    "tropis": lit.load_pln,
    "subtropis": lit.load_merlin,
}


def build_domain(
    domain: cfg.Domain,
    include_power: bool = True,
    include_era5: bool = True,
) -> pd.DataFrame:
    """Build the model-ready table for one domain."""
    print(f"\n=== {domain.name} :: {domain.label} ===")

    strikes = LIGHTNING_LOADER[domain.name]()
    print(f"  strikes           : {len(strikes):,}")
    table = lit.aggregate_gfd(strikes, domain)
    print(f"  cell-months       : {len(table):,} "
          f"({int((table.flash_count > 0).sum()):,} with at least one flash)")
    cov = table[["month", "coverage"]].drop_duplicates()
    print(f"  months covered    : {len(cov)} "
          f"(mean day-coverage {cov['coverage'].mean():.0%}, "
          f"min {cov['coverage'].min():.0%})")

    if include_power:
        try:
            p = power_mod.load_power(domain)
            table = table.merge(p, on=["lat", "lon", "month"], how="left")
            print(f"  + NASA POWER      : {len(p):,} cell-months")
        except FileNotFoundError as exc:
            print(f"  ~ NASA POWER      : SKIPPED ({exc})")

    if include_era5:
        try:
            e = era5_mod.load_era5(domain)
            table = table.merge(e, on=["lat", "lon", "month"], how="left")
            print(f"  + ERA5            : {len(e):,} cell-months")
        except FileNotFoundError as exc:
            print(f"  ~ ERA5            : SKIPPED ({exc})")

    table["year"] = table["month"].dt.year
    table["month_of_year"] = table["month"].dt.month

    present = [c for c in cfg.FEATURE_COLUMNS if c in table.columns]
    ordered = (
        ["domain", "month", "year", "month_of_year"]
        + present
        + ["flash_count", "area_km2", "days_in_month", "observed_days",
           "coverage", "gfd_per_km2_per_day", cfg.TARGET_COLUMN]
    )
    table = table[[c for c in ordered if c in table.columns]]

    missing_feats = [c for c in cfg.FEATURE_COLUMNS if c not in table.columns]
    if missing_feats:
        print(f"  !! absent features: {missing_feats}")

    dead = (
        table.groupby(["lat", "lon"])["flash_count"].sum().eq(0).sum()
    )
    if dead:
        n_cells = table[["lat", "lon"]].drop_duplicates().shape[0]
        print(f"  !! {dead} of {n_cells} cells have ZERO flashes in every covered "
              f"month -- check whether these are sea or outside detector range")

    nan_share = table[present].isna().mean().sort_values(ascending=False)
    worst = nan_share[nan_share > 0]
    if len(worst):
        print("  missing-value share by feature:")
        for name, share in worst.items():
            print(f"      {name:<14s} {share:6.1%}")

    return table


def write(table: pd.DataFrame, domain: cfg.Domain) -> dict[str, Path]:
    """Write the table and a small provenance sidecar."""
    out = {}
    stem = cfg.PROCESSED_DIR / f"gfd_{domain.name}"

    csv_table = table.copy()
    csv_table["month"] = csv_table["month"].astype(str)
    csv_path = stem.with_suffix(".csv")
    csv_table.to_csv(csv_path, index=False)
    out["csv"] = csv_path

    try:
        parquet_path = stem.with_suffix(".parquet")
        table.to_parquet(parquet_path, index=False)
        out["parquet"] = parquet_path
    except ImportError:
        print("  (pyarrow not installed -- CSV only)")

    # F-05: every build records enough config to be replayed.
    months = table["month"].astype(str)
    cov = table[["month", "observed_days", "coverage"]].drop_duplicates()
    meta = {
        "domain": domain.name,
        "bbox_snapped": domain.snapped_bbox(),
        "years_configured": [domain.year_start, domain.year_end],
        "months_observed": {
            "first": months.min(),
            "last": months.max(),
            "n": int(table["month"].nunique()),
            "total_observed_days": int(cov["observed_days"].sum()),
            "mean_day_coverage": round(float(cov["coverage"].mean()), 4),
            "min_day_coverage": round(float(cov["coverage"].min()), 4),
        },
        "n_cells": int(table[["lat", "lon"]].drop_duplicates().shape[0]),
        "timezone": domain.tz,
        "grid_deg": cfg.GRID_DEG,
        "time_freq": cfg.TIME_FREQ,
        "random_seed": cfg.RANDOM_SEED,
        "power_params": cfg.POWER_PARAMS,
        "era5_variables": cfg.ERA5_VARIABLES,
        "target": cfg.TARGET_COLUMN,
        "n_rows": int(len(table)),
        # Only this domain's inputs, and no OS clutter (.DS_Store, Icon\r).
        "sources": sorted(
            p.name
            for d, pat in (
                (cfg.RAW_PLN_DIR if domain.name == "tropis" else cfg.RAW_MERLIN_DIR, "*"),
                (cfg.RAW_POWER_DIR, f"power_{domain.name}_*"),
                (cfg.RAW_ERA5_DIR, f"era5_{domain.name}_*"),
            )
            for p in d.glob(pat)
            if p.is_file() and not p.name.startswith(".")
        ),
    }
    meta_path = stem.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    out["meta"] = meta_path

    for k, v in out.items():
        print(f"  wrote {k:<8s} {v}")
    return out


def main(include_power: bool = True, include_era5: bool = True) -> None:
    for domain in cfg.DOMAINS.values():
        table = build_domain(domain, include_power, include_era5)
        write(table, domain)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build the GFD modelling tables.")
    ap.add_argument("--no-power", action="store_true",
                    help="skip NASA POWER (useful before the first download)")
    ap.add_argument("--no-era5", action="store_true",
                    help="skip ERA5 (useful before the first download)")
    args = ap.parse_args()
    main(include_power=not args.no_power, include_era5=not args.no_era5)