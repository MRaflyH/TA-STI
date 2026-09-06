"""One-chunk smoke test for the ERA5 CDS download. Run before the bulk fetch.

    python -m gfd_data.smoke_era5                      # tropis, most recent Jan
    python -m gfd_data.smoke_era5 --domain subtropis
    python -m gfd_data.smoke_era5 --year 2024 --month 7
    python -m gfd_data.smoke_era5 --clean              # delete the test file

Submits exactly ONE request at the resolution cfg.TIME_FREQ asks for, then
reads it back through the same code path the real build uses. 168 requests is
a long way to get before discovering that a variable name is wrong.

Five things it checks, in the order they tend to fail:

1. CLIENT + TOKEN. ``~/.cdsapirc`` present and in the current single-token
   format, not the retired ``<UID>:<APIKEY>`` one.
2. LICENCE. Accepted for THIS dataset. Licences are per-dataset, and hourly
   (``reanalysis-era5-single-levels``) is a different entry from monthly means
   -- accepting one does not accept the other. The failure is a 403 that says
   nothing about your token being fine.
3. VARIABLE NAMES. Whether all six requested variables actually came back.
   ``vertical_integral_of_divergence_of_cloud_frozen_water_flux`` and
   ``..._liquid_water_flux`` are the two never verified against the live
   catalogue; a wrong name is rejected outright, and a name that is valid but
   maps to an unexpected NetCDF short name shows up here as an unmapped column.
4. SHORTNAME MAP. Whether every NetCDF variable found has an entry in
   cfg.ERA5_SHORTNAME_MAP, and whether every mapped name was found.
5. SHAPE. Timesteps, grid points, cell mapping, and the missing-value share --
   so a silently empty variable is visible before it becomes 168 empty files.

By default the download is written into ``data/raw/era5/`` under its normal
name, so the real fetch reuses it rather than re-requesting. ``--scratch``
isolates it in ``data/interim/`` instead; ``--clean`` deletes whatever the test
wrote and exits.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import config as cfg
from . import era5 as era5_mod

SCRATCH_DIR = cfg.INTERIM_DIR / "era5_smoke"


def _dataset_name() -> str:
    return (
        era5_mod.DATASET_MONTHLY if cfg.TIME_FREQ == "M"
        else era5_mod.DATASET_HOURLY
    )


def check_client() -> bool:
    try:
        import cdsapi
    except ImportError:
        print("!! cdsapi is not installed: pip install cdsapi xarray netcdf4")
        return False

    rc = Path.home() / ".cdsapirc"
    if not rc.exists():
        print(f"!! {rc} not found. Copy the two lines from "
              f"https://cds.climate.copernicus.eu/how-to-api")
        return False

    text = rc.read_text(encoding="utf-8")
    if "/api/v2" in text or text.count(":") > 3:
        print("!! ~/.cdsapirc looks like the RETIRED format "
              "(url .../api/v2 and key <UID>:<APIKEY>). The key is a single "
              "token now; re-copy it from the how-to-api page.")
        return False

    try:
        cdsapi.Client()
    except Exception as exc:  # noqa: BLE001 -- report whatever it says
        print(f"!! cdsapi.Client() failed: {exc}")
        return False

    print(f"  client OK, dataset = {_dataset_name()}")
    return True


def fetch_one(domain: cfg.Domain, year: int, month: int, out_dir: Path) -> Path | None:
    try:
        if cfg.TIME_FREQ == "M":
            return era5_mod.fetch_year_monthly(domain, year, out_dir=out_dir)
        return era5_mod.fetch_chunk_hourly(domain, year, month, out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        print(f"\n!! request failed: {msg[:500]}")
        if "licence" in msg.lower() or "403" in msg:
            print(
                f"\n   This is the licence, not the token. Open the dataset "
                f"page for {_dataset_name()}, go to the Download tab, and "
                f"accept the licence. Licences are per-dataset."
            )
        elif "not valid" in msg.lower() or "invalid" in msg.lower():
            print(
                "\n   Likely a variable name. On the dataset's Download tab, "
                "tick the six variables and press 'Show API request' -- the "
                "CDS prints the exact strings. Paste them into "
                "cfg.ERA5_VARIABLES."
            )
        return None


def inspect(path: Path, domain: cfg.Domain) -> None:
    import zipfile

    print(f"\n--- file ---")
    print(f"  {path.name}  ({path.stat().st_size / 1e6:.2f} MB)")
    print(f"  zip-wrapped : {zipfile.is_zipfile(path)} "
          f"(expected when instantaneous and flux fields are mixed)")

    df = era5_mod.parse_era5_netcdf(path)

    found = [c for c in df.columns if c not in ("lat", "lon", "time")]
    mapped = set(cfg.ERA5_SHORTNAME_MAP)

    print(f"\n--- variables ---")
    print(f"  requested   : {len(cfg.ERA5_VARIABLES)}")
    print(f"  found in nc : {sorted(found)}")

    missing = sorted(mapped - set(found))
    extra = sorted(set(found) - mapped)
    if missing:
        print(f"  !! MAPPED BUT NOT FOUND: {missing}")
        print("     Either the CDS name in cfg.ERA5_VARIABLES is wrong, or its "
              "NetCDF short name differs from the key in "
              "cfg.ERA5_SHORTNAME_MAP. 'Show API request' settles the first; "
              "the list above settles the second.")
    if extra:
        print(f"  !! FOUND BUT NOT MAPPED: {extra}")
        print("     Add these to cfg.ERA5_SHORTNAME_MAP or they are dropped "
              "silently.")
    if not missing and not extra:
        print("  OK -- every requested variable is present and mapped.")

    print(f"\n--- shape ---")
    times = pd.to_datetime(df["time"])
    print(f"  rows        : {len(df):,}")
    print(f"  timesteps   : {times.nunique():,}  "
          f"({times.min()} .. {times.max()}, UTC)")
    print(f"  grid points : {df[['lat','lon']].drop_duplicates().shape[0]}")
    print(f"  lat range   : {df['lat'].min()} .. {df['lat'].max()}")
    print(f"  lon range   : {df['lon'].min()} .. {df['lon'].max()}  "
          f"(should be -180..180, not 0..360)")

    if cfg.TIME_FREQ == "h":
        per_day = times.dt.hour.nunique()
        print(f"  hours/day   : {per_day} "
              f"{'OK' if per_day == 24 else '!! expected 24'}")

    print(f"\n--- missing values ---")
    for c in sorted(found):
        share = df[c].isna().mean()
        flag = "  !! all-NaN" if share == 1.0 else ""
        print(f"  {c:<8s} {share:>6.1%}{flag}")

    print(f"\n--- cell mapping ---")
    binned = era5_mod._hourly_frame(path, domain) if cfg.TIME_FREQ == "h" else None
    if binned is not None:
        cells = era5_mod._spatial_mean(binned)
        print(f"  {df[['lat','lon']].drop_duplicates().shape[0]} native points "
              f"-> {cells[['lat','lon']].drop_duplicates().shape[0]} cells, "
              f"{cells[cfg.TIME_COL].nunique():,} hours")
        print(f"  time key sample: {cells[cfg.TIME_COL].iloc[0]!r} "
              f"(dtype {cells[cfg.TIME_COL].dtype})")
        print("\n  head:")
        print(cells.head(3).to_string(index=False))
    else:
        print("  (skipped: only checked for the hourly path)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), default="tropis")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--month", type=int, default=1)
    ap.add_argument("--scratch", action="store_true",
                    help=f"write to {SCRATCH_DIR} instead of data/raw/era5/")
    ap.add_argument("--clean", action="store_true",
                    help="delete the scratch folder and exit")
    args = ap.parse_args()

    if args.clean:
        if SCRATCH_DIR.exists():
            for p in SCRATCH_DIR.iterdir():
                p.unlink()
            SCRATCH_DIR.rmdir()
            print(f"removed {SCRATCH_DIR}")
        else:
            print(f"{SCRATCH_DIR} does not exist; nothing to clean")
        return

    domain = cfg.DOMAINS[args.domain]
    year = args.year or domain.year_end
    out_dir = SCRATCH_DIR if args.scratch else cfg.RAW_ERA5_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"ERA5 smoke test -- {domain.name}, {year}-{args.month:02d}, "
          f"{cfg.freq_slug()} resolution\n")

    if not check_client():
        return

    path = fetch_one(domain, year, args.month, out_dir)
    if path is None:
        return

    inspect(path, domain)

    print(
        f"\nIf everything above is clean, the bulk fetch is "
        f"`python3 -m gfd_data.era5`. This file is already on disk under its "
        f"normal name, so it will be skipped rather than re-requested."
        if not args.scratch else
        f"\nScratch file kept at {path}. Remove it with --clean."
    )


if __name__ == "__main__":
    main()
