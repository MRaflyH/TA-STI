"""Join lightning, POWER and ERA5 into one table per domain.

    python3 -m gfd.dataset.build
    python3 -m gfd.dataset.build --domain tropis --no-era5

Writes data/processed/gfd_<domain>_hourly.parquet, one row per (0.5 deg cell,
clock hour), plus a .meta.json recording what produced it.

The join is a LEFT join onto the lightning skeleton, so a cell-hour missing
from POWER or ERA5 becomes a row of NaN rather than disappearing. That is also
the dangerous case: a join matching nothing returns a full table of NaN
predictors and raises nothing, so _check_keys runs before every merge.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .. import config as cfg
from . import era5 as era5_mod
from . import features as feat
from . import lightning as lit
from . import power as power_mod

KEY = ["lat", "lon", cfg.TIME_COL]


# ==========================================================================
# Time features
# ==========================================================================
def _add_time_features(table: pd.DataFrame, domain: cfg.Domain) -> list[str]:
    """Raw calendar columns from the time key. Returns their names.

    Raw only. Cyclical encodings and solar geometry are representation choices
    and belong to selection/, which can change them without a rebuild.
    """
    periods = table[cfg.TIME_COL]
    stamps = periods.dt.to_timestamp()

    table["year"] = periods.dt.year
    table["month_of_year"] = periods.dt.month
    table["day_of_year"] = periods.dt.dayofyear
    table["hour_of_day_utc"] = periods.dt.hour

    local = stamps.dt.tz_localize("UTC").dt.tz_convert(domain.solar_tz)
    table["hour_of_day_local"] = local.dt.hour

    return list(feat.RAW_TEMPORAL)


# ==========================================================================
# The join
# ==========================================================================
def _check_keys(name: str, frame: pd.DataFrame, target: pd.DataFrame) -> None:
    """Key compatibility, before a merge that would not complain.

    A dtype mismatch on the time key or a clock difference will do it, and
    neither raises on its own. Has never fired: both domains report 100%.
    """
    for col in KEY:
        lhs, rhs = target[col].dtype, frame[col].dtype
        if lhs != rhs:
            raise TypeError(
                f"{name}: {col} is {rhs} against lightning's {lhs}. The merge "
                f"would match nothing and return all-NaN predictors."
            )

    tset = set(map(tuple, target[KEY].drop_duplicates().to_numpy()))
    fset = set(map(tuple, frame[KEY].drop_duplicates().to_numpy()))
    hit = len(tset & fset)
    share = hit / max(len(tset), 1)

    if hit == 0:
        raise ValueError(
            f"{name}: zero key overlap with the lightning grid.\n"
            f"  lightning sample: {sorted(tset)[0]}\n"
            f"  {name} sample: {sorted(fset)[0]}"
        )
    if share < 0.5:
        print(
            f"[build] !! {name} covers {share:.1%} of the lightning grid. "
            f"Usually a bbox edge or a missing chunk -- check before accepting."
        )
    else:
        print(f"[build] {name:<6s} key overlap {share:.1%} ({hit:,} cell-hours)")


def build_domain(
    domain: cfg.Domain, include_power: bool = True, include_era5: bool = True
) -> pd.DataFrame:
    print(f"\n=== {domain.name} :: {domain.label} ===")

    strikes = lit.LOADERS[domain.name]()
    print(f"[build] strikes {len(strikes):,}")

    table = lit.aggregate_gfd(strikes, domain)
    print(
        f"[build] {len(table):,} cell-hours "
        f"({int((table[cfg.TARGET] > 0).sum()):,} with at least one flash)"
    )

    sources = []
    if include_power:
        try:
            p = power_mod.load_power(domain)
            _check_keys("power", p, table)
            table = table.merge(p, on=KEY, how="left")
            sources.append("power")
        except (FileNotFoundError, ValueError) as exc:
            print(f"[build] power SKIPPED: {exc}")

    if include_era5:
        try:
            e = era5_mod.load_era5(domain)
            _check_keys("era5", e, table)
            table = table.merge(e, on=KEY, how="left")
            sources.append("era5")
        except FileNotFoundError as exc:
            print(f"[build] era5 SKIPPED: {exc}")

    time_cols = _add_time_features(table, domain)

    # Check before reordering. Ordering used to drop anything the contract did
    # not name, which made this check inspect its own output and silently
    # discard newly acquired columns.
    feat.check_against_table(table.columns)

    predictors = [c for c in feat.CANDIDATES if c in table.columns and c not in ("lat", "lon")]
    ordered = (
        ["domain", cfg.TIME_COL] + time_cols + ["lat", "lon"] + predictors
        + [cfg.TARGET] + feat.INTENSITY
        + ["month", "area_km2", "days_in_month", "observed_days", "coverage",
           "period_days", "gfd_per_km2_per_day", cfg.TARGET_REPORTING]
    )
    seen: set[str] = set()
    front = [c for c in ordered if c in table.columns and not (c in seen or seen.add(c))]
    # Everything else keeps its place at the end. The table is allowed to be
    # wider than the contract; the model reads MODELLED.
    table = table[front + [c for c in table.columns if c not in seen]]
    _report(table, predictors)
    return table


def _report(table: pd.DataFrame, predictors: list[str]) -> None:
    zero_share = float((table[cfg.TARGET] == 0).mean())
    print(f"[build] zero-target share {zero_share:.2%}")

    dead = table.groupby(["lat", "lon"])[cfg.TARGET].sum().eq(0).sum()
    if dead:
        n_cells = table[["lat", "lon"]].drop_duplicates().shape[0]
        print(f"[build] !! {dead} of {n_cells} cells have zero flashes in every hour")

    nan = table[predictors].isna().mean().sort_values(ascending=False)
    worst = nan[nan > 0]
    if len(worst):
        print("[build] missing by predictor:")
        for name, share in worst.items():
            flag = "  !! ALL MISSING" if share == 1.0 else ""
            print(f"          {name:<14s} {share:6.1%}{flag}")

    usable = int(
        table.loc[table[cfg.TARGET] > 0, [c for c in feat.INTENSITY if c in table.columns]]
        .notna().all(axis=1).sum()
    )
    nonzero = int((table[cfg.TARGET] > 0).sum())
    print(f"[build] intensity target usable on {usable:,} of {nonzero:,} non-zero rows")


# ==========================================================================
# Write
# ==========================================================================
def write(table: pd.DataFrame, domain: cfg.Domain) -> Path:
    stem = cfg.PROCESSED_DIR / f"gfd_{domain.name}_hourly"
    path = stem.with_suffix(".parquet")
    table.to_parquet(path, index=False)

    periods = table[cfg.TIME_COL].astype(str)
    cov = table[["observed_days", "coverage"]].drop_duplicates()
    meta = {
        "domain": domain.name,
        "bbox_snapped": domain.snapped_bbox(),
        "years": [domain.year_start, domain.year_end],
        "grid_deg": cfg.GRID_DEG,
        "time_freq": cfg.TIME_FREQ,
        "min_coverage": cfg.MIN_COVERAGE,
        "random_seed": cfg.RANDOM_SEED,
        "target": cfg.TARGET,
        "target_reporting": cfg.TARGET_REPORTING,
        "era5_variables": era5_mod.VARIABLES,
        "power_params": power_mod.PARAMS,
        # The contract is part of what this table IS. A replay that reads the
        # parquet without it reads a different dataset.
        "candidates": feat.CANDIDATES,
        "exclude": feat.EXCLUDE,
        "columns": list(table.columns),
        "n_rows": int(len(table)),
        "n_cells": int(table[["lat", "lon"]].drop_duplicates().shape[0]),
        "zero_target_share": round(float((table[cfg.TARGET] == 0).mean()), 6),
        "first_period": periods.min(),
        "last_period": periods.max(),
        "mean_coverage": round(float(cov["coverage"].mean()), 4),
        "min_coverage_observed": round(float(cov["coverage"].min()), 4),
    }
    meta_path = stem.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[build] wrote {path}")
    print(f"[build] wrote {meta_path}")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), default=None)
    ap.add_argument("--no-power", action="store_true")
    ap.add_argument("--no-era5", action="store_true")
    args = ap.parse_args()

    domains = [cfg.DOMAINS[args.domain]] if args.domain else list(cfg.DOMAINS.values())
    for d in domains:
        table = build_domain(d, not args.no_power, not args.no_era5)
        write(table, d)


if __name__ == "__main__":
    main()
