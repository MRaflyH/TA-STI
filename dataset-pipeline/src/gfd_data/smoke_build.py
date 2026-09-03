"""End-to-end build test on ONE month. ~8 network requests, not 589.

    python -m gfd_data.smoke_build                        # tropis, latest Jan
    python -m gfd_data.smoke_build --domain subtropis --year 2024 --month 7
    python -m gfd_data.smoke_build --no-fetch             # use what's on disk

Runs the real pipeline -- real loaders, real regridding, real join -- over a
single month, so that every failure mode shows up before the bulk download.

THE FAILURE THIS EXISTS TO CATCH is the join matching nothing. A left join onto
the lightning skeleton does not raise when the right-hand side has no matching
keys; it returns the full lightning table with every predictor column NaN. That
looks like a successful build. Three things cause it, and all three are
invisible in the per-source smoke tests:

  * a dtype mismatch on the time key (Period[h] vs Period[D] vs object string);
  * a timezone or clock-convention difference, so the keys are real but offset;
  * a coordinate convention difference -- ERA5 longitudes on 0..360 against
    lightning longitudes on -180..180, which silently fails only for the
    Florida domain because West Java's longitudes are positive either way.

So this script checks key overlap explicitly, before and after the merge, and
tells you which side is empty.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

import pandas as pd

from . import build as build_mod
from . import config as cfg
from . import era5 as era5_mod
from . import lightning as lit
from . import power as power_mod


def _month_window(year: int, month: int, freq: str) -> tuple[str, str]:
    if freq == "M":
        return (str(year), str(year))
    last = pd.Period(f"{year}-{month:02d}", freq="M").days_in_month
    return (f"{year}{month:02d}01", f"{year}{month:02d}{last}")


def fetch_minimum(domain: cfg.Domain, year: int, month: int) -> None:
    """Fetch exactly what one month needs."""
    print("--- fetching one month of meteorology ---")

    hourly = [p for p in cfg.POWER_PARAMS if cfg.power_native_freq(p) == "h"]
    if hourly:
        window = _month_window(year, month, "h")
        points = power_mod.native_points(domain)
        print(f"  {len(points)} POWER points x 1 window")
        for lat, lon in points:
            try:
                power_mod.fetch_point(domain, lat, lon, hourly, window)
            except Exception as exc:  # noqa: BLE001
                print(f"  !! POWER point ({lat}, {lon}) failed: {str(exc)[:200]}")

    for p in cfg.POWER_PARAMS:
        freq = cfg.power_native_freq(p)
        if freq == "h":
            continue
        try:
            power_mod.fetch_regional(domain, p, freq, _month_window(year, month, freq))
        except Exception as exc:  # noqa: BLE001
            print(f"  !! POWER {p} failed: {str(exc)[:200]}")

    try:
        if cfg.TIME_FREQ == "M":
            era5_mod.fetch_year_monthly(domain, year)
        else:
            era5_mod.fetch_chunk_hourly(domain, year, month)
    except Exception as exc:  # noqa: BLE001
        print(f"  !! ERA5 failed: {str(exc)[:300]}")
    

def _key_report(name: str, frame: pd.DataFrame, target: pd.DataFrame) -> None:
    """How well one predictor frame's keys line up with the lightning grid."""
    key = ["lat", "lon", cfg.TIME_COL]
    print(f"\n--- {name} key overlap ---")

    for col in key:
        lhs, rhs = target[col].dtype, frame[col].dtype
        flag = "" if lhs == rhs else "   !! DTYPE MISMATCH -- join will fail"
        print(f"  {col:<6s} lightning={str(lhs):<22s} {name}={str(rhs)}{flag}")

    tset = set(map(tuple, target[key].drop_duplicates().to_numpy()))
    fset = set(map(tuple, frame[key].drop_duplicates().to_numpy()))
    hit = len(tset & fset)

    print(f"  lightning keys : {len(tset):,}")
    print(f"  {name} keys{'':<5s}: {len(fset):,}")
    print(f"  overlap        : {hit:,}  ({hit / max(len(tset), 1):.1%} of the "
          f"lightning grid)")

    if hit == 0:
        print(
            "  !! ZERO OVERLAP. The merge will produce an all-NaN block that "
            "does not raise. Compare one key from each side before going "
            "further:"
        )
        print(f"     lightning: {sorted(tset)[0]}")
        print(f"     {name}: {sorted(fset)[0]}")
    elif hit < len(tset) * 0.5:
        print("  !! Partial overlap. Usually a bbox edge or a missing chunk; "
              "check the coordinate ranges above before accepting it.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), default="tropis")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--month", type=int, default=1)
    ap.add_argument("--no-fetch", action="store_true",
                    help="use only what is already on disk")
    args = ap.parse_args()

    domain = cfg.DOMAINS[args.domain]
    year = args.year or domain.year_end
    period = pd.Period(f"{year}-{args.month:02d}", freq="M")

    print(f"end-to-end test -- {domain.name}, {period}, "
          f"{cfg.freq_slug()} resolution\n")

    if not args.no_fetch:
        fetch_minimum(domain, year, args.month)

    # ---- lightning ------------------------------------------------------
    print(f"\n--- lightning ---")
    strikes = build_mod.LIGHTNING_LOADER[domain.name]()
    naive = lit._bin_timestamps(strikes["timestamp"], domain)
    strikes = strikes[naive.dt.to_period("M") == period]
    if strikes.empty:
        print(f"  no strikes in {period}. Pick another month with --month.")
        return
    print(f"  strikes in {period}: {len(strikes):,}")

    scoped = replace(domain, year_start=year, year_end=year)
    table = lit.aggregate_gfd(strikes, scoped, min_coverage=0.0)
    print(f"  rows: {len(table):,}  "
          f"cells: {table[['lat','lon']].drop_duplicates().shape[0]}  "
          f"periods: {table[cfg.TIME_COL].nunique():,}")

    # ---- predictors -----------------------------------------------------
    for name, loader in (("power", power_mod.load_power),
                         ("era5", era5_mod.load_era5)):
        try:
            frame = loader(scoped)
        except (FileNotFoundError, ValueError) as exc:
            print(f"\n--- {name} --- SKIPPED ({exc})")
            continue

        frame = frame[pd.PeriodIndex(frame[cfg.TIME_COL]).asfreq("M") == period]
        if frame.empty:
            print(f"\n--- {name} --- no rows in {period}; "
                  f"the fetch covered a different window")
            continue

        _key_report(name, frame, table)
        table = table.merge(frame, on=["lat", "lon", cfg.TIME_COL], how="left")

    # ---- verdict --------------------------------------------------------
    present = [c for c in cfg.FEATURE_COLUMNS if c in table.columns]
    print(f"\n--- joined table ---")
    print(f"  rows     : {len(table):,}")
    print(f"  features : {len(present)} of {len(cfg.FEATURE_COLUMNS)} present")

    if present:
        nan = table[present].isna().mean().sort_values(ascending=False)
        for c, share in nan.items():
            flag = "  !! ALL MISSING" if share == 1.0 else ""
            print(f"    {c:<14s} {share:>6.1%}{flag}")

        dead = [c for c in present if table[c].isna().all()]
        if dead:
            print(f"\n  !! {len(dead)} feature(s) joined to nothing: {dead}")
            print("     Fix this before the bulk fetch. A build that looks "
                  "successful and produces an all-NaN predictor block is the "
                  "expensive failure here.")
        else:
            print("\n  OK -- every present feature has real values. "
                  "The join works; the bulk fetch is safe to start.")

    print(f"\n  zero-target share: {(table['flash_count'] == 0).mean():.2%}")
    print("\n  head:")
    cols = ([cfg.TIME_COL, "lat", "lon"] + present[:4]
            + ["flash_count", cfg.TARGET_COLUMN])
    print(table[[c for c in cols if c in table.columns]].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
