"""ERA5 from the Copernicus Climate Data Store, at hourly, daily or monthly.

Unlike NASA POWER this is *not* a plain URL fetch. It needs:

  * a free CDS account,
  * a personal access token in ``~/.cdsapirc``,
  * the dataset licence accepted once in the web UI -- SEPARATELY FOR EACH
    DATASET, and sub-monthly mode uses a different dataset from monthly mode,
  * ``pip install cdsapi xarray netcdf4``,

and requests are queued server-side. See RUNBOOK step 4.

Which product is used depends on ``cfg.TIME_FREQ``:

  * ``"h"`` -> ``reanalysis-era5-single-levels`` (hourly), used as-is.
  * ``"D"`` -> the same hourly download, collapsed to daily here via
    ``cfg.ERA5_DAILY_STATS``. The CDS also publishes
    ``derived-era5-single-levels-daily-statistics``, which would cut the
    download 24-fold, but it computes one statistic per request and its
    variable coverage needs checking against the six wanted here; collapsing
    locally keeps the daily-max-CAPE choice visible in code.
  * ``"M"`` -> ``reanalysis-era5-single-levels-monthly-means``.

The hourly and daily paths share their raw files, so switching between them
costs nothing once the download is done.

ONE TIMING CAVEAT, and it only bites at hourly resolution: ERA5 hourly fields
are *instantaneous* values at the top of the hour, while a target row counts
every flash inside the hour. The convention this pipeline adopts is that the
predictor at time T is paired with strikes in [T, T+1h) -- the atmospheric
state at the opening of the interval, predicting what happens during it. State
that in Bab III; it is a defensible choice but it is a choice, and daily or
monthly aggregation used to hide it.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from . import config as cfg

DATASET_MONTHLY = "reanalysis-era5-single-levels-monthly-means"
DATASET_HOURLY = "reanalysis-era5-single-levels"
MONTHS = [f"{m:02d}" for m in range(1, 13)]
ALL_DAYS = [f"{d:02d}" for d in range(1, 32)]  # CDS ignores the surplus


# ==========================================================================
# Download
# ==========================================================================
def _submit(dataset: str, request: dict, dest: Path, tag: str) -> Path:
    import cdsapi

    print(f"[era5] submit  {tag} ...", flush=True)
    client = cdsapi.Client()
    client.retrieve(dataset, request, str(dest))
    print(f"[era5] saved   {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest


def fetch_year_monthly(
    domain: cfg.Domain,
    year: int,
    variables: list[str] | None = None,
    out_dir: str | Path = cfg.RAW_ERA5_DIR,
    overwrite: bool = False,
) -> Path:
    """One CDS monthly-means request for one domain-year."""
    variables = variables or cfg.ERA5_VARIABLES
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"era5_{domain.name}_monthly_{year}.nc"

    if dest.exists() and not overwrite:
        print(f"[era5] cached  {dest.name}")
        return dest

    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    request = {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": variables,
        "year": [str(year)],
        "month": MONTHS,
        "time": ["00:00"],
        # CDS wants [North, West, South, East].
        "area": [lat_hi, lon_lo, lat_lo, lon_hi],
        "data_format": "netcdf",
        # Without this the CDS wraps the payload in a .zip and the reader below
        # will fail on what looks like a corrupt NetCDF.
        "download_format": "unarchived",
    }
    return _submit(DATASET_MONTHLY, request, dest, f"{domain.name} {year} monthly")


def fetch_chunk_hourly(
    domain: cfg.Domain,
    year: int,
    month: int | None = None,
    variables: list[str] | None = None,
    out_dir: str | Path = cfg.RAW_ERA5_DIR,
    overwrite: bool = False,
) -> Path:
    """One CDS hourly request for one domain-month (or domain-year).

    ``month=None`` requests the whole year in one job. That is 8 760 timesteps
    x 6 variables; it may exceed the CDS per-request field limit and it will
    certainly queue longer. Try exactly one by hand before setting
    ``cfg.ERA5_HOURLY_CHUNK = "Y"``.
    """
    variables = variables or cfg.ERA5_VARIABLES
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = f"{year}" if month is None else f"{year}{month:02d}"
    dest = out_dir / f"era5_{domain.name}_hourly_{stamp}.nc"

    if dest.exists() and not overwrite:
        print(f"[era5] cached  {dest.name}")
        return dest

    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    request = {
        "product_type": ["reanalysis"],
        "variable": variables,
        "year": [str(year)],
        "month": MONTHS if month is None else [f"{month:02d}"],
        "day": ALL_DAYS,
        "time": cfg.ERA5_HOURS,
        "area": [lat_hi, lon_lo, lat_lo, lon_hi],
        "data_format": "netcdf",
        "download_format": "unarchived",
    }
    return _submit(DATASET_HOURLY, request, dest, f"{domain.name} {stamp} hourly")


def fetch_domain(domain: cfg.Domain, **kwargs) -> list[Path]:
    """Download everything this domain needs, at cfg.TIME_FREQ."""
    years = range(domain.year_start, domain.year_end + 1)

    if cfg.TIME_FREQ == "M":
        return [fetch_year_monthly(domain, y, **kwargs) for y in years]

    if cfg.ERA5_HOURLY_CHUNK == "Y":
        return [fetch_chunk_hourly(domain, y, **kwargs) for y in years]
    return [
        fetch_chunk_hourly(domain, y, m, **kwargs)
        for y in years
        for m in range(1, 13)
    ]


# ==========================================================================
# Parse
# ==========================================================================
def _open_members(path: Path) -> list:
    """Open a CDS download as a list of xarray Datasets.

    The CDS ignores ``download_format: "unarchived"`` whenever the requested
    variables do not all share a GRIB ``stepType``. Instantaneous fields (CAPE,
    KX, TCIW, TCLW) and time-averaged flux fields (VIIWD, VILWD) do not, so the
    response arrives as a ZIP holding one NetCDF per stepType, still named
    ``.nc``. Both members carry the same lat/lon/time axes, so they are opened
    separately and merged on those axes.
    """
    import xarray as xr

    if not zipfile.is_zipfile(path):
        return [xr.open_dataset(path)]

    datasets = []
    with zipfile.ZipFile(path) as zf:
        members = [n for n in zf.namelist() if n.endswith(".nc")]
        if not members:
            raise ValueError(f"{path.name}: zip contains no .nc members: {zf.namelist()}")
        for name in members:
            # h5netcdf/netcdf4 need a real file, so extract to a temp dir.
            with tempfile.TemporaryDirectory() as tmp:
                extracted = Path(zf.extract(name, tmp))
                datasets.append(xr.open_dataset(extracted).load())
    return datasets


def parse_era5_netcdf(path: str | Path) -> pd.DataFrame:
    """Flatten one ERA5 download into a tidy frame.

    Returns ``lat, lon, time`` (a real timestamp, not yet binned) plus one
    column per NetCDF short name. Handles both a bare NetCDF and the
    ZIP-of-NetCDFs the CDS usually sends.
    """
    path = Path(path)
    members = _open_members(path)

    frames = []
    for ds in members:
        renames = {}
        for cand, target in (
            ("valid_time", "time"), ("forecast_reference_time", "time"),
            ("latitude", "lat"), ("longitude", "lon"),
        ):
            if cand in ds.coords or cand in ds.dims:
                renames[cand] = target
        ds = ds.rename(renames)

        # A download may carry a length-1 expver / pressure_level /
        # forecast_period dimension; collapse anything that is not lat/lon/time.
        for dim in list(ds.dims):
            if dim not in ("lat", "lon", "time") and ds.sizes[dim] == 1:
                ds = ds.squeeze(dim, drop=True)

        df = ds.to_dataframe().reset_index()
        ds.close()

        keep = {"lat", "lon", "time"} | set(cfg.ERA5_SHORTNAME_MAP)
        # 'number' (ensemble member) and 'expver' (ERA5 vs ERA5T) are always
        # present and always length-1 here; not worth reporting every file.
        benign = {"number", "expver"}
        unknown = [c for c in df.columns if c not in keep and c not in benign]
        if unknown:
            print(f"[era5] {path.name}: ignoring columns {unknown}")
        df = df[[c for c in df.columns if c in keep]]

        if "time" not in df.columns:
            raise ValueError(f"{path.name}: no recognisable time coordinate")
        df["time"] = pd.to_datetime(df["time"])
        frames.append(df)

    out = frames[0]
    for extra in frames[1:]:
        # Merge the stepType members back together on their shared axes.
        out = out.merge(extra, on=["lat", "lon", "time"], how="outer")

    # ERA5 longitudes may come back on a 0..360 grid; put them on -180..180 to
    # match the lightning and POWER frames.
    out["lon"] = ((out["lon"] + 180) % 360) - 180
    return out


# ==========================================================================
# Temporal binning
# ==========================================================================
def _bin_time(times: pd.Series, domain: cfg.Domain) -> pd.Series:
    """Bin hourly ERA5 timestamps onto the project's time key.

    ERA5 timestamps are UTC. Under cfg.TZ_MODE == "local" (daily mode only)
    they are shifted to the domain's clock first, so the predictors and the
    target agree on where a day starts. At hourly resolution the mode is forced
    to "utc" -- see cfg.TZ_MODE.
    """
    utc = pd.to_datetime(times, utc=True)
    if cfg.TIME_FREQ != "h" and cfg.TZ_MODE == "local":
        utc = utc.dt.tz_convert(domain.tz)
    return utc.dt.tz_localize(None).dt.to_period(cfg.TIME_FREQ)


def _hourly_frame(path: Path, domain: cfg.Domain) -> pd.DataFrame:
    """One hourly file, keyed on the project's time column. No aggregation."""
    df = parse_era5_netcdf(path)
    # cfg.TIME_COL is itself "time", so bind the result before dropping the
    # source column -- assigning first and dropping after deletes both.
    binned = _bin_time(df["time"], domain)
    df = df.drop(columns=["time"])
    df[cfg.TIME_COL] = binned
    return df


def _daily_partials(path: Path, domain: cfg.Domain) -> pd.DataFrame:
    """Per-file partial daily statistics at native ERA5 points.

    Emits sum / count / max per variable rather than the finished statistic,
    so that a day split across two downloaded files (which happens whenever
    cfg.TZ_MODE == "local", because the chunks are UTC months) can be combined
    correctly afterwards. Averaging two per-file means would silently weight a
    7-hour fragment the same as a 17-hour one.
    """
    df = _hourly_frame(path, domain)

    value_cols = [c for c in df.columns if c in cfg.ERA5_SHORTNAME_MAP]
    grouped = df.groupby(["lat", "lon", cfg.TIME_COL], observed=True)[value_cols]

    parts = {f"{c}__sum": grouped[c].sum(min_count=1) for c in value_cols}
    parts.update({f"{c}__cnt": grouped[c].count() for c in value_cols})
    parts.update({f"{c}__max": grouped[c].max() for c in value_cols})
    return pd.DataFrame(parts).reset_index()


def _finalise_daily(partials: pd.DataFrame, expected_hours: int = 24) -> pd.DataFrame:
    """Combine per-file partials into one row per (native point, day)."""
    value_cols = sorted({c.split("__")[0] for c in partials.columns if "__" in c})

    agg = {}
    for c in value_cols:
        agg[f"{c}__sum"] = "sum"
        agg[f"{c}__cnt"] = "sum"
        agg[f"{c}__max"] = "max"

    combined = (
        partials.groupby(["lat", "lon", cfg.TIME_COL], observed=True)
        .agg(agg)
        .reset_index()
    )

    out = combined[["lat", "lon", cfg.TIME_COL]].copy()
    incomplete = pd.Series(False, index=combined.index)
    for c in value_cols:
        stat = cfg.ERA5_DAILY_STATS.get(c, "mean")
        if stat == "max":
            out[c] = combined[f"{c}__max"]
        elif stat == "mean":
            out[c] = combined[f"{c}__sum"] / combined[f"{c}__cnt"]
        else:
            raise ValueError(f"unsupported daily statistic {stat!r} for {c!r}")
        incomplete |= combined[f"{c}__cnt"] < expected_hours

    n_bad = int(incomplete.sum())
    if n_bad:
        print(
            f"[era5] dropping {n_bad:,} point-days built from fewer than "
            f"{expected_hours} hours (edges of the downloaded span, or a "
            f"missing chunk)"
        )
        out = out[~incomplete]
    return out


# ==========================================================================
# Load
# ==========================================================================
def _files(domain: cfg.Domain, directory: Path) -> list[Path]:
    if cfg.TIME_FREQ == "M":
        monthly = sorted(directory.glob(f"era5_{domain.name}_monthly_*.nc"))
        # Files downloaded before the resolution switch had no tag in the name.
        legacy = sorted(directory.glob(f"era5_{domain.name}_[0-9][0-9][0-9][0-9].nc"))
        return monthly + legacy
    return sorted(directory.glob(f"era5_{domain.name}_hourly_*.nc"))


def _spatial_mean(df: pd.DataFrame) -> pd.DataFrame:
    """Average native 0.25 deg points onto the 0.5 deg project cells."""
    from .lightning import assign_grid

    df = assign_grid(df)
    value_cols = [c for c in df.columns if c not in
                  {"lat", "lon", cfg.TIME_COL, "lat_bin", "lon_bin"}]
    return (
        df.groupby(["lat_bin", "lon_bin", cfg.TIME_COL], observed=True)[value_cols]
        .mean()
        .reset_index()
        .rename(columns={"lat_bin": "lat", "lon_bin": "lon"})
    )


def load_era5(
    domain: cfg.Domain, directory: str | Path = cfg.RAW_ERA5_DIR
) -> pd.DataFrame:
    """Read every saved ERA5 file for a domain, snapped onto the project grid.

    At daily resolution the order matters: the temporal collapse happens at the
    NATIVE 0.25 deg points, the spatial average onto 0.5 deg cells happens
    afterwards. A cell's CAPE is therefore the mean of four local daily maxima,
    not the maximum of four spatial means -- the former is a statement about
    the cell's convective potential, the latter is dominated by whichever
    quarter of the cell peaked. At hourly resolution the question does not
    arise, which is one of the few things hourly makes simpler.

    Files are reduced one at a time and only the reduced frames are held, so
    seven years of hourly data never sits in memory at once.
    """
    directory = Path(directory)
    files = _files(domain, directory)
    if not files:
        raise FileNotFoundError(
            f"no {cfg.freq_slug()} ERA5 files for domain {domain.name!r} in "
            f"{directory} -- run fetch_domain() first"
        )

    print(f"[era5] reading {len(files)} files for {domain.name} ...")

    if cfg.TIME_FREQ == "h":
        # Reduce each file to cell means before concatenating: a month of
        # hourly data at native resolution is ~260k rows, the same month after
        # the spatial mean is ~20k.
        df = pd.concat(
            [_spatial_mean(_hourly_frame(f, domain)) for f in files],
            ignore_index=True,
        )
        out = (
            df.groupby(["lat", "lon", cfg.TIME_COL], observed=True)
            .mean()
            .reset_index()
        )
        out = out.rename(columns=cfg.ERA5_SHORTNAME_MAP)
        n_native = "n/a (reduced per file)"
    elif cfg.TIME_FREQ == "D":
        partials = pd.concat(
            [_daily_partials(f, domain) for f in files], ignore_index=True
        )
        daily = _finalise_daily(partials)
        n_native = daily[["lat", "lon"]].drop_duplicates().shape[0]
        out = _spatial_mean(daily).rename(columns=cfg.ERA5_SHORTNAME_MAP)
    else:
        monthly = pd.concat([parse_era5_netcdf(f) for f in files], ignore_index=True)
        binned = _bin_time(monthly["time"], domain)
        monthly = monthly.drop(columns=["time"])
        monthly[cfg.TIME_COL] = binned
        n_native = monthly[["lat", "lon"]].drop_duplicates().shape[0]
        out = _spatial_mean(monthly).rename(columns=cfg.ERA5_SHORTNAME_MAP)

    print(f"[era5] {n_native} native points "
          f"-> {out[['lat','lon']].drop_duplicates().shape[0]} cells, "
          f"{out[cfg.TIME_COL].nunique():,} {cfg.freq_noun()}s")
    return out


if __name__ == "__main__":  # python -m gfd_data.era5
    for dom in cfg.DOMAINS.values():
        fetch_domain(dom)
