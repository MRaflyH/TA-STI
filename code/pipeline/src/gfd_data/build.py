"""Join the four sources into one model-ready table per climate domain.

Run after the raw files are in place::

    python -m gfd_data.build

Output: ``data/processed/gfd_<domain>_<hourly|daily|monthly>.parquet`` (and
.csv, size permitting), one row per (0.5 deg cell, period), with spatial +
meteorological predictors and the GFD target. The period follows
``cfg.TIME_FREQ``; the resolution is in the file name so that builds at
different resolutions sit side by side and can be compared.

The join is a LEFT join onto the lightning skeleton, so a cell-period that
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

# Above this many rows, the CSV mirror is skipped unless --force-csv is given.
# At hourly resolution a domain runs to millions of rows and the CSV is an
# order of magnitude larger and slower than the parquet, for no benefit --
# nothing downstream reads it by hand.
CSV_ROW_LIMIT = 500_000


def _add_time_features(table: pd.DataFrame, domain: cfg.Domain) -> list[str]:
    """Derive calendar columns from the time key. Returns their names."""
    periods = table[cfg.TIME_COL]
    table["year"] = periods.dt.year
    table["month_of_year"] = periods.dt.month
    cols = ["year", "month_of_year"]

    if cfg.TIME_FREQ in ("h", "D"):
        table["day_of_year"] = periods.dt.dayofyear
        cols.append("day_of_year")

    if cfg.TIME_FREQ == "h":
        # Bins are UTC (cfg.TZ_MODE), so UTC hour is the raw key and local hour
        # is the physically meaningful one: convection over West Java peaks in
        # the local afternoon, and a model given only the UTC hour has to learn
        # the offset separately for each domain -- which is exactly the kind of
        # domain-specific quirk the cross-domain experiment is trying not to
        # measure.
        #
        # Consider encoding it cyclically (sin/cos of 2*pi*h/24) before
        # modelling: hour 23 and hour 0 are adjacent, and a raw integer says
        # they are 23 apart. Not done here because it doubles a column against
        # a very scarce qubit budget -- decide it in the modelling code and
        # record the choice.
        local = (
            periods.dt.to_timestamp()
            .dt.tz_localize("UTC")
            .dt.tz_convert(domain.solar_tz)
        )
        table["hour_of_day_utc"] = periods.dt.hour
        table["hour_of_day_local"] = local.dt.hour
        cols += ["hour_of_day_utc", "hour_of_day_local"]

    return cols


def build_domain(
    domain: cfg.Domain,
    include_power: bool = True,
    include_era5: bool = True,
) -> pd.DataFrame:
    """Build the model-ready table for one domain."""
    noun = cfg.freq_noun()
    print(f"\n=== {domain.name} :: {domain.label}  [{cfg.freq_slug()}] ===")

    strikes = LIGHTNING_LOADER[domain.name]()
    print(f"  strikes           : {len(strikes):,}")

    table = lit.aggregate_gfd(strikes, domain)
    print(f"  cell-{noun}s{'':<7s}: {len(table):,} "
          f"({int((table.flash_count > 0).sum()):,} with at least one flash)")

    cov = table[["month", "coverage"]].drop_duplicates()
    print(f"  months covered    : {len(cov)} "
          f"(mean day-coverage {cov['coverage'].mean():.0%}, "
          f"min {cov['coverage'].min():.0%})")

    if include_power:
        try:
            p = power_mod.load_power(domain)
            table = table.merge(p, on=["lat", "lon", cfg.TIME_COL], how="left")
            print(f"  + NASA POWER      : {len(p):,} cell-{noun}s")
        except (FileNotFoundError, ValueError) as exc:
            print(f"  ~ NASA POWER      : SKIPPED ({exc})")

    if include_era5:
        try:
            e = era5_mod.load_era5(domain)
            table = table.merge(e, on=["lat", "lon", cfg.TIME_COL], how="left")
            print(f"  + ERA5            : {len(e):,} cell-{noun}s")
        except FileNotFoundError as exc:
            print(f"  ~ ERA5            : SKIPPED ({exc})")

    time_cols = _add_time_features(table, domain)

    present = [c for c in cfg.FEATURE_COLUMNS
               if c in table.columns and c not in ("lat", "lon")]
    ordered = (
        ["domain", cfg.TIME_COL] + time_cols
        + ["lat", "lon"] + present
        + ["flash_count"] + cfg.INTENSITY_COLUMNS
        + ["area_km2", "days_in_month", "observed_days",
           "coverage", "period_days", "gfd_per_km2_per_day", cfg.TARGET_COLUMN]
    )
    table = table[[c for c in ordered if c in table.columns]]

    # D-08. Intensity is a conditional target: it exists only where lightning
    # occurred. Report the usable row count here so the modelling code is not
    # the first place anyone notices how small that subset is.
    kept_intensity = [c for c in cfg.INTENSITY_COLUMNS if c in table.columns]
    if kept_intensity:
        n_nonzero = int((table["flash_count"] > 0).sum())
        n_usable = int(table.loc[table["flash_count"] > 0, kept_intensity]
                       .notna().all(axis=1).sum())
        print(f"  intensity target  : {n_usable:,} of {n_nonzero:,} non-zero "
              f"cell-{noun}s carry all {len(kept_intensity)} statistics "
              f"({n_usable / max(n_nonzero, 1):.1%})")

    missing_feats = [c for c in cfg.FEATURE_COLUMNS if c not in table.columns]
    if missing_feats:
        print(f"  !! absent features: {missing_feats}")

    dead = table.groupby(["lat", "lon"])["flash_count"].sum().eq(0).sum()
    if dead:
        n_cells = table[["lat", "lon"]].drop_duplicates().shape[0]
        print(f"  !! {dead} of {n_cells} cells have ZERO flashes in every covered "
              f"{noun} -- check whether these are sea or outside detector range")

    zero_share = float((table["flash_count"] == 0).mean())
    print(f"  zero-target share : {zero_share:.2%} of rows")

    if cfg.TIME_FREQ == "h":
        nonzero = table.loc[table["flash_count"] > 0, "flash_count"]
        print(
            f"  !! at hourly resolution the target is a COUNT process, not a "
            f"density: {zero_share:.1%} zeros, and the non-zero rows run "
            f"{int(nonzero.min())}..{int(nonzero.max())} flashes. "
            f"{cfg.TARGET_COLUMN} annualises a single hour, so one flash "
            f"becomes ~{365.25 * 24:.0f} x its per-hour rate. Use flash_count "
            f"as the modelling target, or a log/anscombe transform of it, and "
            f"keep {cfg.TARGET_COLUMN} only for unit-consistent reporting "
            f"against the daily and monthly builds."
        )

    nan_share = table[present].isna().mean().sort_values(ascending=False)
    worst = nan_share[nan_share > 0]
    if len(worst):
        print("  missing-value share by feature:")
        for name, share in worst.items():
            print(f"      {name:<14s} {share:6.1%}")

    return table


def write(table: pd.DataFrame, domain: cfg.Domain, force_csv: bool = False) -> dict[str, Path]:
    """Write the table and a small provenance sidecar."""
    out: dict[str, Path] = {}
    stem = cfg.PROCESSED_DIR / f"gfd_{domain.name}_{cfg.freq_slug()}"

    try:
        parquet_path = stem.with_suffix(".parquet")
        table.to_parquet(parquet_path, index=False)
        out["parquet"] = parquet_path
    except ImportError:
        print("  (pyarrow not installed -- install it, the CSV is 10x larger)")

    if len(table) <= CSV_ROW_LIMIT or force_csv:
        csv_table = table.copy()
        csv_table[cfg.TIME_COL] = csv_table[cfg.TIME_COL].astype(str)
        csv_path = stem.with_suffix(".csv")
        csv_table.to_csv(csv_path, index=False)
        out["csv"] = csv_path
    else:
        print(f"  (CSV skipped: {len(table):,} rows > {CSV_ROW_LIMIT:,}; "
              f"pass --force-csv to write it anyway)")

    # F-05: every build records enough config to be replayed. The temporal
    # choices below are not bookkeeping -- they change what the dataset *is* --
    # so they are recorded next to the model hyperparameters, not underneath.
    periods = table[cfg.TIME_COL].astype(str)
    cov = table[["observed_days", "coverage"]].drop_duplicates()
    meta = {
        "domain": domain.name,
        "bbox_snapped": domain.snapped_bbox(),
        "years_configured": [domain.year_start, domain.year_end],
        "time_freq": cfg.TIME_FREQ,
        "time_resolution": cfg.freq_slug(),
        "tz_mode": "utc" if cfg.TIME_FREQ == "h" else cfg.TZ_MODE,
        "min_coverage": cfg.MIN_COVERAGE,
        "power_param_freq": cfg.POWER_PARAM_FREQ,
        "power_time_standard": cfg.POWER_TIME_STANDARD if cfg.TIME_FREQ == "h" else None,
        "era5_daily_stats": cfg.ERA5_DAILY_STATS if cfg.TIME_FREQ == "D" else None,
        "era5_product": (
            "reanalysis-era5-single-levels-monthly-means" if cfg.TIME_FREQ == "M"
            else "reanalysis-era5-single-levels"
        ),
        "periods_observed": {
            "first": periods.min(),
            "last": periods.max(),
            "n": int(table[cfg.TIME_COL].nunique()),
            "total_observed_days": int(cov["observed_days"].sum()),
            "mean_day_coverage": round(float(cov["coverage"].mean()), 4),
            "min_day_coverage": round(float(cov["coverage"].min()), 4),
        },
        "n_cells": int(table[["lat", "lon"]].drop_duplicates().shape[0]),
        "n_rows": int(len(table)),
        "zero_target_share": round(float((table["flash_count"] == 0).mean()), 6),
        "timezone": domain.tz,
        "grid_deg": cfg.GRID_DEG,
        "random_seed": cfg.RANDOM_SEED,
        "power_params": cfg.POWER_PARAMS,
        "era5_variables": cfg.ERA5_VARIABLES,
        "target": cfg.TARGET_COLUMN,
        # F-05. The modelling contracts are part of what this dataset IS, not
        # commentary on it: which columns may be predictors, which are the
        # second target, and which predictor was dropped for cross-domain
        # symmetry. A replay that reads the parquet without these reads a
        # different dataset. See code/modelling/DECISIONS.md, D-01 and D-08.
        "intensity_columns": [c for c in cfg.INTENSITY_COLUMNS if c in table.columns],
        "dropped_predictors": cfg.DROPPED_PREDICTORS,
        "exclude_columns": cfg.EXCLUDE_COLUMNS,
        "columns": list(table.columns),
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


def main(
    include_power: bool = True,
    include_era5: bool = True,
    force_csv: bool = False,
) -> None:
    for domain in cfg.DOMAINS.values():
        table = build_domain(domain, include_power, include_era5)
        write(table, domain, force_csv=force_csv)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build the GFD modelling tables.")
    ap.add_argument("--no-power", action="store_true",
                    help="skip NASA POWER (useful before the first download)")
    ap.add_argument("--no-era5", action="store_true",
                    help="skip ERA5 (useful before the first download)")
    ap.add_argument("--force-csv", action="store_true",
                    help=f"write the CSV mirror even above {CSV_ROW_LIMIT:,} rows")
    args = ap.parse_args()
    main(
        include_power=not args.no_power,
        include_era5=not args.no_era5,
        force_csv=args.force_csv,
    )
