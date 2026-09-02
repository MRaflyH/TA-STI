"""ERA5 monthly means from the Copernicus Climate Data Store.

Unlike NASA POWER this is *not* a plain URL fetch. It needs:

  * a free CDS account,
  * a personal access token in ``~/.cdsapirc``,
  * the dataset licence accepted once in the web UI,
  * ``pip install cdsapi xarray netcdf4``,

and requests are queued server-side -- a multi-year monthly-means request
typically returns in minutes, not seconds. See RUNBOOK step 4.

One request per year keeps each job small enough to finish reliably and makes
a failure cheap to retry.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from . import config as cfg

DATASET = "reanalysis-era5-single-levels-monthly-means"
MONTHS = [f"{m:02d}" for m in range(1, 13)]


# ==========================================================================
# Download
# ==========================================================================
def fetch_year(
    domain: cfg.Domain,
    year: int,
    variables: list[str] | None = None,
    out_dir: str | Path = cfg.RAW_ERA5_DIR,
    overwrite: bool = False,
) -> Path:
    """Submit one CDS request for one domain-year. Returns the saved NetCDF."""
    import cdsapi

    variables = variables or cfg.ERA5_VARIABLES
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"era5_{domain.name}_{year}.nc"

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

    print(f"[era5] submit  {domain.name} {year} ...", flush=True)
    client = cdsapi.Client()
    client.retrieve(DATASET, request, str(dest))
    print(f"[era5] saved   {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest


def fetch_domain(domain: cfg.Domain, **kwargs) -> list[Path]:
    """Download every year of a domain, one request per year."""
    return [
        fetch_year(domain, y, **kwargs)
        for y in range(domain.year_start, domain.year_end + 1)
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
    """Flatten one ERA5 monthly-means download into a tidy frame.

    Returns ``lat, lon, month`` plus one column per mapped variable. Handles
    both a bare NetCDF and the ZIP-of-NetCDFs the CDS usually sends.
    """
    import xarray as xr

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

        # Monthly means may carry a length-1 expver / pressure_level /
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
        df["month"] = pd.to_datetime(df["time"]).dt.to_period("M")
        df = df.drop(columns=["time"])
        frames.append(df)

    # Merge the stepType members back together on their shared axes.
    out = frames[0]
    for extra in frames[1:]:
        out = out.merge(extra, on=["lat", "lon", "month"], how="outer")

    out = out.rename(columns=cfg.ERA5_SHORTNAME_MAP)

    # ERA5 longitudes may come back on a 0..360 grid; put them on -180..180 to
    # match the lightning and POWER frames.
    out["lon"] = ((out["lon"] + 180) % 360) - 180
    return out


def load_era5(
    domain: cfg.Domain, directory: str | Path = cfg.RAW_ERA5_DIR
) -> pd.DataFrame:
    """Read every saved ERA5 file for a domain, snapped onto the project grid."""
    files = sorted(Path(directory).glob(f"era5_{domain.name}_*.nc"))
    if not files:
        raise FileNotFoundError(
            f"no ERA5 files for domain {domain.name!r} in {directory} -- "
            f"run fetch_domain() first"
        )

    df = pd.concat([parse_era5_netcdf(f) for f in files], ignore_index=True)

    # ERA5 is 0.25 deg -- finer than the 0.5 deg target grid -- so binning and
    # averaging is the right operation here (four ERA5 points per cell), unlike
    # POWER where the source grid is coarser.
    from .lightning import assign_grid

    df = assign_grid(df)
    value_cols = [c for c in df.columns if c not in
                  {"lat", "lon", "month", "lat_bin", "lon_bin"}]
    out = (
        df.groupby(["lat_bin", "lon_bin", "month"], observed=True)[value_cols]
        .mean()
        .reset_index()
        .rename(columns={"lat_bin": "lat", "lon_bin": "lon"})
    )
    print(f"[era5] {df[['lat','lon']].drop_duplicates().shape[0]} native points "
          f"-> {out[['lat','lon']].drop_duplicates().shape[0]} cells")
    return out


if __name__ == "__main__":  # python -m gfd_data.era5
    for dom in cfg.DOMAINS.values():
        fetch_domain(dom)
