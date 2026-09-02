"""NASA POWER: download and parse monthly meteorology on a 0.5 deg grid.

POWER is an open HTTP API. There is no account, no key, no queue -- you build
a URL and get data back synchronously.

Two constraints from the POWER docs shape the code below:

1. A *regional* request is limited to ONE parameter. So we loop over
   ``POWER_PARAMS`` and issue one request per parameter, then join.
2. A regional request is limited to a 4.5 x 4.5 degree box (100 grid points).
   Both study domains fit; a larger domain would need tiling.

Every response is written to ``data/raw/power/`` before parsing, so a parse
failure never costs a re-download and the raw payload stays auditable.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import config as cfg

BASE_URL = "https://power.larc.nasa.gov/api/temporal/monthly/regional"
COMMUNITY = "RE"


# ==========================================================================
# Download
# ==========================================================================
def fetch_parameter(
    domain: cfg.Domain,
    parameter: str,
    out_dir: str | Path = cfg.RAW_POWER_DIR,
    overwrite: bool = False,
    timeout: int = 300,
) -> Path:
    """Download one POWER parameter for one domain. Returns the saved path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"power_{domain.name}_{parameter}_{domain.year_start}_{domain.year_end}.json"

    if dest.exists() and not overwrite:
        print(f"[power] cached  {dest.name}")
        return dest

    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    params = {
        "parameters": parameter,
        "community": COMMUNITY,
        "latitude-min": lat_lo,
        "latitude-max": lat_hi,
        "longitude-min": lon_lo,
        "longitude-max": lon_hi,
        "start": domain.year_start,
        "end": domain.year_end,
        "format": "JSON",
    }

    print(f"[power] GET    {parameter} / {domain.name} ...", flush=True)
    resp = requests.get(BASE_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    dest.write_text(resp.text, encoding="utf-8")
    print(f"[power] saved  {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest


def fetch_domain(
    domain: cfg.Domain,
    parameters: list[str] | None = None,
    pause_s: float = 2.0,
    **kwargs,
) -> list[Path]:
    """Download every configured parameter for one domain."""
    parameters = parameters or cfg.POWER_PARAMS
    paths = []
    for p in parameters:
        paths.append(fetch_parameter(domain, p, **kwargs))
        time.sleep(pause_s)  # be polite to a public API
    return paths


# ==========================================================================
# Parse
# ==========================================================================
def parse_power_json(path: str | Path) -> pd.DataFrame:
    """Turn one saved POWER regional JSON response into a tidy long frame.

    Returns columns: ``lat, lon, month (Period[M]), parameter, value``.

    The regional endpoint answers with a GeoJSON FeatureCollection: one
    feature per grid point, whose ``properties.parameter`` maps a parameter
    name to a dict keyed ``"YYYYMM"``. POWER also emits a synthetic month 13
    holding the annual figure -- that key is dropped here.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    features = payload.get("features")
    if features is None:
        raise ValueError(
            f"{Path(path).name}: no 'features' key. Top-level keys are "
            f"{sorted(payload)}. Inspect the raw file before parsing."
        )

    records: list[dict] = []
    for feat in features:
        lon, lat = feat["geometry"]["coordinates"][:2]
        for param, series in feat["properties"]["parameter"].items():
            for key, value in series.items():
                if len(key) != 6 or key.endswith("13"):
                    continue  # annual roll-up, not a month
                records.append(
                    {
                        "lat": float(lat),
                        "lon": float(lon),
                        "month": pd.Period(f"{key[:4]}-{key[4:]}", freq="M"),
                        "parameter": param,
                        "value": float(value),
                    }
                )

    df = pd.DataFrame.from_records(records)
    if df.empty:
        raise ValueError(f"{Path(path).name}: parsed zero records")

    # POWER marks missing data with -999. Turn it into a real NaN so that
    # imputation is an explicit, documented step rather than an accident.
    df.loc[df["value"] <= cfg.POWER_FILL_VALUE, "value"] = pd.NA
    return df


def _nearest_map(targets: np.ndarray, sources: np.ndarray) -> dict[float, float]:
    """Map every target coordinate to the closest available source coordinate."""
    idx = np.abs(targets[:, None] - sources[None, :]).argmin(axis=1)
    return {float(t): float(sources[i]) for t, i in zip(targets, idx)}


def _regrid_parameter(param_df: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    """Nearest-neighbour regrid ONE parameter onto the project cells.

    Driven from the target cells, not from the source points: each cell asks
    which POWER point is closest. Binning the other way leaves holes whenever
    the source grid is coarser than the target grid, which happens twice here
    -- POWER's 0.625 deg longitude step, and AOD_55_ADJ's 1 deg grid.

    Each parameter must be regridded separately because they do not share a
    native grid. Building one coordinate map from the union of all parameters
    produces (lat, lon) pairs that exist for some parameters and not others.
    """
    src_lat = np.sort(param_df["lat"].unique())
    src_lon = np.sort(param_df["lon"].unique())

    lat_map = _nearest_map(cells["lat_bin"].unique(), src_lat)
    lon_map = _nearest_map(cells["lon_bin"].unique(), src_lon)

    keyed = cells.assign(
        lat=cells["lat_bin"].map(lat_map),
        lon=cells["lon_bin"].map(lon_map),
    )
    return (
        keyed.merge(param_df, on=["lat", "lon"], how="left")
        .drop(columns=["lat", "lon"])
        .rename(columns={"lat_bin": "lat", "lon_bin": "lon"})
    )


def load_power(
    domain: cfg.Domain, directory: str | Path = cfg.RAW_POWER_DIR
) -> pd.DataFrame:
    """Read all saved POWER files for a domain into one wide frame.

    Returns ``lat, lon, month`` plus one column per parameter, regridded onto
    the project's 0.5 deg cells so it can be joined to the lightning table.
    """
    files = sorted(Path(directory).glob(f"power_{domain.name}_*.json"))
    if not files:
        raise FileNotFoundError(
            f"no POWER files for domain {domain.name!r} in {directory} -- "
            f"run fetch_domain() first"
        )

    long = pd.concat([parse_power_json(f) for f in files], ignore_index=True)

    from .lightning import full_cell_index

    cells = full_cell_index(domain)

    out: pd.DataFrame | None = None
    for param, chunk in long.groupby("parameter", sort=True):
        wide = chunk.pivot_table(
            index=["lat", "lon", "month"], values="value", aggfunc="mean"
        ).reset_index().rename(columns={"value": param})

        n_pts = wide[["lat", "lon"]].drop_duplicates().shape[0]
        gridded = _regrid_parameter(wide, cells)
        print(
            f"[power] {param:<12s} {n_pts:>3d} native points "
            f"-> {len(cells):>3d} cells "
            f"({gridded[param].isna().mean():.0%} still empty)"
        )

        out = gridded if out is None else out.merge(
            gridded, on=["lat", "lon", "month"], how="outer"
        )

    front = ["lat", "lon", "month"]
    return out[front + [c for c in out.columns if c not in front]]


if __name__ == "__main__":  # python -m gfd_data.power
    for dom in cfg.DOMAINS.values():
        fetch_domain(dom)
