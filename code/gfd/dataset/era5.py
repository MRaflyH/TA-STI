"""ERA5 single levels from the Copernicus CDS.

Needs a CDS account, a token in ~/.cdsapirc, and the licence accepted for this
dataset specifically. Requests queue server-side.

    python3 -m gfd.dataset.era5                          # all variables
    python3 -m gfd.dataset.era5 --check                  # disk vs mapping
    python3 -m gfd.dataset.era5 --supplement k_index --domain subtropis
    python3 -m gfd.dataset.era5 --supplement a,b,c --tag tier1 --year 2018 --month 1

One request per domain-month, 168 files. A whole year in one request exceeds
the CDS cost limit -- tried, refused, don't.

ERA5 fields are instantaneous at the top of the hour; a target row counts every
flash inside it. So the predictor at T pairs with strikes in [T, T+1h).
"""

from __future__ import annotations

import argparse
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from .. import config as cfg
from .lightning import assign_grid

DATASET = "reanalysis-era5-single-levels"

# CDS variable name -> the short name it arrives as inside the NetCDF. Both
# halves are needed: one to request it, one to find it again and to name a
# supplement file. Still moving until the raw freeze.
VARIABLE_SHORTNAME = {
    "convective_available_potential_energy": "cape",
    "k_index": "kx",
    "total_column_cloud_ice_water": "tciw",
    "total_column_cloud_liquid_water": "tclw",
    "vertical_integral_of_divergence_of_cloud_frozen_water_flux": "viiwd",
    "vertical_integral_of_divergence_of_cloud_liquid_water_flux": "vilwd",
    # Tier 1 candidates. Short names unverified against a real file -- --check
    # reports anything that lands under a different name.
    "vertical_integral_of_divergence_of_moisture_flux": "vimdf",
    "total_totals_index": "totalx",
    "convective_inhibition": "cin",
    "cloud_base_height": "cbh",
    "total_column_water_vapour": "tcwv",
    "2m_dewpoint_temperature": "d2m",
    "convective_rain_rate": "crr",
}

# What a full fetch requests. Deliberately not all of VARIABLE_SHORTNAME: the
# Tier 1 entries above are known short names, not yet part of the main request.
VARIABLES = [
    "convective_available_potential_energy",
    "k_index",
    "total_column_cloud_ice_water",
    "total_column_cloud_liquid_water",
    "vertical_integral_of_divergence_of_cloud_frozen_water_flux",
    "vertical_integral_of_divergence_of_cloud_liquid_water_flux",
]

# Short name -> column name. Anything missing here is dropped silently;
# check_variables() catches it.
SHORTNAME_MAP = {
    "cape": "CAPE",
    "kx": "KX",
    "tciw": "TCIW",
    "tclw": "TCLW",
    "viiwd": "VIIWD",
    "vilwd": "VILWD",
    "vimdf": "VIMDF",
    "totalx": "TOTALX",
    "cin": "CIN",
    "cbh": "CBH",
    "tcwv": "TCWV",
    "d2m": "D2M",
    "crr": "CRR",
}

HOURS = [f"{h:02d}:00" for h in range(24)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]
DAYS = [f"{d:02d}" for d in range(1, 32)]  # CDS ignores the surplus


def _stamp(year: int, month: int) -> str:
    return f"{year}{month:02d}"


# ==========================================================================
# Download
# ==========================================================================
def _submit(request: dict, dest: Path, tag: str) -> Path:
    import cdsapi

    print(f"[era5] submit {tag} ...", flush=True)
    cdsapi.Client().retrieve(DATASET, request, str(dest))
    print(f"[era5] saved  {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest


def _request(domain: cfg.Domain, year: int, month: int, variables: list[str]) -> dict:
    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    return {
        "product_type": ["reanalysis"],
        "variable": variables,
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": DAYS,
        "time": HOURS,
        # [North, West, South, East]. Nothing else uses this order.
        "area": [lat_hi, lon_lo, lat_lo, lon_hi],
        "data_format": "netcdf",
        # Ignored when the variables don't share a stepType. See _open_members.
        "download_format": "unarchived",
    }


def fetch_chunk(
    domain: cfg.Domain,
    year: int,
    month: int,
    variables: list[str] | None = None,
    out_dir: str | Path = cfg.RAW_ERA5_DIR,
    overwrite: bool = False,
) -> Path:
    """One request for one domain-month."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"era5_{domain.name}_hourly_{_stamp(year, month)}.nc"

    if dest.exists() and not overwrite:
        print(f"[era5] cached {dest.name}")
        return dest
    return _submit(
        _request(domain, year, month, variables or VARIABLES),
        dest,
        f"{domain.name} {_stamp(year, month)}",
    )


def fetch_supplement(
    domain: cfg.Domain,
    year: int,
    month: int,
    variables: str | list[str],
    tag: str | None = None,
    out_dir: str | Path = cfg.RAW_ERA5_DIR,
    overwrite: bool = False,
) -> Path:
    """A request for a subset of variables, suffixed so the main glob skips it.

    Two uses: recovering a variable the main request didn't return (kx for
    subtropis), and adding variables later without re-requesting everything.

    `tag` names the file. Defaults to the short name for a single variable, and
    is required for a batch.
    """
    if isinstance(variables, str):
        variables = [variables]
    unknown = [v for v in variables if v not in VARIABLE_SHORTNAME]
    if unknown:
        raise KeyError(f"no VARIABLE_SHORTNAME entry for {unknown}. Add them first.")

    if tag is None:
        if len(variables) > 1:
            raise ValueError("a multi-variable supplement needs an explicit tag")
        tag = VARIABLE_SHORTNAME[variables[0]]

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"era5_{domain.name}_hourly_{_stamp(year, month)}_{tag}.nc"

    if dest.exists() and not overwrite:
        print(f"[era5] cached {dest.name}")
        return dest
    return _submit(
        _request(domain, year, month, variables),
        dest,
        f"{domain.name} {_stamp(year, month)} [{tag}] {len(variables)} variable(s)",
    )


def fetch_domain(domain: cfg.Domain, **kw) -> list[Path]:
    return [
        fetch_chunk(domain, y, m, **kw)
        for y in range(domain.year_start, domain.year_end + 1)
        for m in range(1, 13)
    ]


def fetch_supplement_domain(
    domain: cfg.Domain, variables: str | list[str], tag: str | None = None, **kw
) -> list[Path]:
    return [
        fetch_supplement(domain, y, m, variables, tag, **kw)
        for y in range(domain.year_start, domain.year_end + 1)
        for m in range(1, 13)
    ]


# ==========================================================================
# Parse
# ==========================================================================
def _open_members(path: Path) -> list:
    """Open a CDS download as one or more xarray Datasets.

    Mixed GRIB stepTypes come back as a ZIP with one NetCDF each, still named
    .nc. Same axes on both, so they merge afterwards.
    """
    import xarray as xr

    if not zipfile.is_zipfile(path):
        return [xr.open_dataset(path)]

    datasets = []
    with zipfile.ZipFile(path) as zf:
        members = [n for n in zf.namelist() if n.endswith(".nc")]
        if not members:
            raise ValueError(f"{path.name}: zip has no .nc members: {zf.namelist()}")
        for name in members:
            # netcdf4 needs a real file. load() before the temp dir vanishes.
            with tempfile.TemporaryDirectory() as tmp:
                datasets.append(xr.open_dataset(Path(zf.extract(name, tmp))).load())
    return datasets


def parse_netcdf(path: str | Path) -> pd.DataFrame:
    """Flatten one download into lat, lon, time plus one column per short name."""
    path = Path(path)
    frames = []

    for ds in _open_members(path):
        renames = {
            src: dst
            for src, dst in (
                ("valid_time", "time"),
                ("forecast_reference_time", "time"),
                ("latitude", "lat"),
                ("longitude", "lon"),
            )
            if src in ds.variables or src in ds.dims or src in ds.coords
        }
        df = ds.rename(renames).to_dataframe().reset_index()

        keep = {"lat", "lon", "time"} | set(SHORTNAME_MAP)
        # number/expver are always there and always length-1.
        unknown = [c for c in df.columns if c not in keep and c not in {"number", "expver"}]
        if unknown:
            print(f"[era5] {path.name}: ignoring {unknown}")
        df = df[[c for c in df.columns if c in keep]]

        if "time" not in df.columns:
            raise ValueError(f"{path.name}: no recognisable time coordinate")
        df["time"] = pd.to_datetime(df["time"])
        frames.append(df)

    out = frames[0]
    for extra in frames[1:]:
        out = out.merge(extra, on=["lat", "lon", "time"], how="outer")

    # ERA5 longitudes can arrive on 0..360. Onto -180..180 to match the other
    # frames. Only bites Florida; West Java is positive either way.
    out["lon"] = ((out["lon"] + 180) % 360) - 180
    return out


def _hourly_frame(path: Path) -> pd.DataFrame:
    """One file keyed on the project's time column."""
    df = parse_netcdf(path)
    # cfg.TIME_COL is itself "time". Bind before dropping or you delete both.
    binned = pd.to_datetime(df["time"], utc=True).dt.tz_localize(None).dt.to_period("h")
    df = df.drop(columns=["time"])
    df[cfg.TIME_COL] = binned
    return df


def _spatial_mean(df: pd.DataFrame) -> pd.DataFrame:
    """Average native 0.25 deg points onto the 0.5 deg project cells."""
    df = assign_grid(df)
    value_cols = [
        c for c in df.columns
        if c not in {"lat", "lon", cfg.TIME_COL, "lat_bin", "lon_bin"}
    ]
    return (
        df.groupby(["lat_bin", "lon_bin", cfg.TIME_COL], observed=True)[value_cols]
        .mean()
        .reset_index()
        .rename(columns={"lat_bin": "lat", "lon_bin": "lon"})
    )


# ==========================================================================
# Load
# ==========================================================================
def _main_files(domain: cfg.Domain, directory: Path) -> list[Path]:
    # Six digits exactly, so supplements stay out.
    return sorted(directory.glob(f"era5_{domain.name}_hourly_[0-9][0-9][0-9][0-9][0-9][0-9].nc"))


def _supplement_files(domain: cfg.Domain, directory: Path) -> dict[str, list[Path]]:
    """Supplement files on disk, grouped by tag.

    Grouped by filename, but the columns each group carries are read from the
    files themselves -- a tag says which batch, not which variables.
    """
    groups: dict[str, list[Path]] = {}
    for f in sorted(directory.glob(f"era5_{domain.name}_hourly_[0-9]*_*.nc")):
        tag = f.stem.split("_", 4)[-1]
        groups.setdefault(tag, []).append(f)
    return groups


def _reduce(files: list[Path]) -> pd.DataFrame:
    """One file at a time, reduced to cell means before concatenating. A month
    is ~260k rows native, ~20k after."""
    df = pd.concat([_spatial_mean(_hourly_frame(f)) for f in files], ignore_index=True)
    return df.groupby(["lat", "lon", cfg.TIME_COL], observed=True).mean().reset_index()


def load_era5(
    domain: cfg.Domain, directory: str | Path = cfg.RAW_ERA5_DIR
) -> pd.DataFrame:
    """Every saved file for a domain, on the project grid, supplements merged in."""
    directory = Path(directory)
    files = _main_files(domain, directory)
    if not files:
        raise FileNotFoundError(
            f"no ERA5 files for {domain.name!r} in {directory} -- run fetch_domain() first"
        )

    print(f"[era5] reading {len(files)} files for {domain.name} ...")
    out = _reduce(files)

    for tag, files in _supplement_files(domain, directory).items():
        extra = _reduce(files)
        cols = [c for c in extra.columns if c in SHORTNAME_MAP]
        already = [c for c in cols if c in out.columns and out[c].notna().any()]
        wanted = [c for c in cols if c not in already]

        if already:
            print(
                f"[era5] [{tag}] {already} already in the main files -- not merged. "
                f"Delete one set or the other."
            )
        if not wanted:
            continue

        print(f"[era5] merging {len(files)} [{tag}] files: {wanted}")
        out = out.drop(columns=wanted, errors="ignore").merge(
            extra[["lat", "lon", cfg.TIME_COL] + wanted],
            on=["lat", "lon", cfg.TIME_COL],
            how="left",
        )

    out = out.rename(columns=SHORTNAME_MAP)
    print(
        f"[era5] {out[['lat','lon']].drop_duplicates().shape[0]} cells, "
        f"{out[cfg.TIME_COL].nunique():,} hours, "
        f"columns {[c for c in out.columns if c in SHORTNAME_MAP.values()]}"
    )
    return out


# ==========================================================================
# Checks
# ==========================================================================
def check_variables(domain: cfg.Domain, directory: str | Path = cfg.RAW_ERA5_DIR) -> None:
    """What one file contains, against what's mapped. Run after changing
    VARIABLES: a valid CDS name with an unexpected short name shows up here as
    unmapped instead of as a column that never arrives."""
    directory = Path(directory)
    files = _main_files(domain, directory)
    if not files:
        print(f"[era5] nothing on disk for {domain.name}")
        return

    df = parse_netcdf(files[0])
    found = {c for c in df.columns if c not in ("lat", "lon", "time")}
    # Against what a fetch asks for, not against every name the code knows --
    # SHORTNAME_MAP also holds candidates that were never requested.
    requested = {VARIABLE_SHORTNAME[v] for v in VARIABLES}

    print(f"\n[era5] {domain.name}: {len(files)} files, sampled {files[0].name}")
    print(f"  requested {len(VARIABLES)}, found {sorted(found)}")
    if requested - found:
        print(f"  !! requested but absent: {sorted(requested - found)}")
    if found - set(SHORTNAME_MAP):
        print(f"  !! found but unmapped (dropped silently): "
              f"{sorted(found - set(SHORTNAME_MAP))}")

    for tag, files in _supplement_files(domain, directory).items():
        cols = [c for c in parse_netcdf(files[0]).columns if c in SHORTNAME_MAP]
        print(f"  [{tag}] {len(files)} files, carrying {cols}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), default=None)
    ap.add_argument(
        "--supplement",
        metavar="VARS",
        help="comma-separated CDS variables to fetch on their own",
    )
    ap.add_argument("--tag", help="filename tag, required for more than one variable")
    ap.add_argument("--year", type=int, help="restrict to one year (for a trial)")
    ap.add_argument("--month", type=int, help="restrict to one month (for a trial)")
    ap.add_argument("--check", action="store_true", help="inspect what's on disk")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    domains = [cfg.DOMAINS[args.domain]] if args.domain else list(cfg.DOMAINS.values())

    for d in domains:
        if args.check:
            check_variables(d)
        elif args.supplement:
            variables = [v.strip() for v in args.supplement.split(",")]
            if args.year and args.month:
                fetch_supplement(
                    d, args.year, args.month, variables, args.tag,
                    overwrite=args.overwrite,
                )
            else:
                fetch_supplement_domain(
                    d, variables, args.tag, overwrite=args.overwrite
                )
        else:
            fetch_domain(d, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
