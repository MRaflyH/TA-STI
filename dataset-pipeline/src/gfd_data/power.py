"""NASA POWER: download and parse meteorology on a 0.5 deg grid.

POWER is an open HTTP API. There is no account, no key, no queue -- you build
a URL and get data back synchronously.

THE SPATIAL OPTION DEPENDS ON THE ENDPOINT, and this is the thing that bites:

  * ``hourly``  -> **point only**. ``/api/temporal/hourly/regional`` does not
    exist and returns 404, not a helpful error. So the hourly fetch loops over
    native POWER grid points and issues one request each.
  * ``daily``, ``monthly`` -> regional works, one parameter per request.

The point endpoint accepts up to 15 parameters at once, so the hourly loop asks
for all of them in a single request per point -- fewer requests than the old
regional-per-parameter scheme, not more.

Which endpoint each parameter uses follows ``cfg.POWER_PARAM_FREQ``: a
parameter POWER does not publish at ``cfg.TIME_FREQ`` is fetched at its own
coarsest-available resolution and broadcast across the finer periods.
``AOD_55_ADJ`` is the current case -- monthly only, so at hourly resolution it
is held constant across ~730 consecutive rows. See the note in config.py.

Other constraints from the POWER docs that shape the code:

1. A *regional* request is limited to ONE parameter and a 4.5 x 4.5 degree box.
2. ``start``/``end`` are ``YYYYMMDD`` for hourly and daily, bare ``YYYY`` for
   monthly.
3. Hourly defaults to Local Solar Time. LST is a 15-degree longitude swath, not
   a civil timezone, so ``time-standard=UTC`` is sent explicitly -- see
   cfg.TZ_MODE for why UTC is the only workable convention across all four
   sources.
4. Hourly precipitation is mm/hour, where the monthly product is mm/day. The
   units of PRECTOTCORR are NOT comparable across resolutions; say so in Bab IV
   if the two builds are ever put side by side.
5. POWER asks that you not repeatedly request the same underlying grid cell.
   Hence requesting POWER's native points rather than the project's cell
   centres, several of which share a POWER longitude cell.

Every response is written to ``data/raw/power/`` before parsing, so a parse
failure never costs a re-download and the raw payload stays auditable.
"""

from __future__ import annotations

import json
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import config as cfg

BASE_URL = "https://power.larc.nasa.gov/api/temporal/{endpoint}/{spatial}"
COMMUNITY = "RE"

ENDPOINT = {"h": "hourly", "D": "daily", "M": "monthly"}
KEY_LEN_FREQ = {6: "M", 8: "D", 10: "h"}


# ==========================================================================
# Native grid
# ==========================================================================
def native_points(domain: cfg.Domain) -> list[tuple[float, float]]:
    """Every POWER grid point inside a domain's snapped bounding box.

    POWER meteorology inherits the MERRA-2 grid: latitudes on exact multiples
    of 0.5, longitudes on exact multiples of 0.625. Asking for these directly
    means POWER returns the cell you meant, rather than snapping several
    project cell centres onto the same underlying point and billing you for
    each -- which the docs explicitly warn about.
    """
    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()

    lats = np.arange(
        np.ceil(lat_lo / cfg.POWER_GRID_LAT) * cfg.POWER_GRID_LAT,
        lat_hi + 1e-9,
        cfg.POWER_GRID_LAT,
    )
    lons = np.arange(
        np.ceil(lon_lo / cfg.POWER_GRID_LON) * cfg.POWER_GRID_LON,
        lon_hi + 1e-9,
        cfg.POWER_GRID_LON,
    )
    return [(round(float(la), 4), round(float(lo), 4)) for la in lats for lo in lons]


# ==========================================================================
# Download
# ==========================================================================
def _windows(domain: cfg.Domain, freq: str) -> list[tuple[str, str]]:
    """Every (start, end) pair needed to cover a domain at one frequency."""
    if freq == "M":
        return [(str(domain.year_start), str(domain.year_end))]

    if freq == "h" and cfg.POWER_HOURLY_CHUNK == "ALL":
        return [(f"{domain.year_start}0101", f"{domain.year_end}1231")]

    return [(f"{y}0101", f"{y}1231")
            for y in range(domain.year_start, domain.year_end + 1)]


def _tag(value: float) -> str:
    """Filename-safe coordinate: -7.5 -> 'm007p500', 108.125 -> 'p108p125'."""
    sign = "m" if value < 0 else "p"
    whole, frac = divmod(abs(value), 1)
    return f"{sign}{int(whole):03d}p{int(round(frac * 1000)):03d}"


def fetch_point(
    domain: cfg.Domain,
    lat: float,
    lon: float,
    parameters: list[str],
    window: tuple[str, str],
    out_dir: str | Path = cfg.RAW_POWER_DIR,
    overwrite: bool = False,
    timeout: int = 300,
) -> Path:
    """One hourly point request: all parameters, one grid point, one window."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    start, end = window
    dest = (out_dir /
            f"power_{domain.name}_hourly_{_tag(lat)}_{_tag(lon)}_{start}_{end}.json")

    if dest.exists() and not overwrite:
        print(f"[power] cached  {dest.name}")
        return dest

    params = {
        "parameters": ",".join(parameters),
        "community": COMMUNITY,
        "latitude": lat,
        "longitude": lon,
        "start": start,
        "end": end,
        "format": "JSON",
        "time-standard": cfg.POWER_TIME_STANDARD,
    }

    print(f"[power] GET    hourly point ({lat}, {lon}) {start}..{end} ...", flush=True)
    resp = requests.get(
        BASE_URL.format(endpoint="hourly", spatial="point"),
        params=params, timeout=timeout,
    )
    if resp.status_code == 422:
        raise ValueError(
            f"POWER rejected {parameters} at hourly resolution (HTTP 422). "
            f"Response: {resp.text[:400]}"
        )
    resp.raise_for_status()

    dest.write_text(resp.text, encoding="utf-8")
    print(f"[power] saved  {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest


def fetch_regional(
    domain: cfg.Domain,
    parameter: str,
    freq: str,
    window: tuple[str, str],
    out_dir: str | Path = cfg.RAW_POWER_DIR,
    overwrite: bool = False,
    timeout: int = 300,
) -> Path:
    """One regional request: one parameter, the whole box. Daily/monthly only."""
    if freq == "h":
        raise ValueError(
            "POWER has no hourly regional endpoint -- it returns 404. "
            "Use fetch_point() for hourly."
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    endpoint = ENDPOINT[freq]
    start, end = window
    dest = out_dir / f"power_{domain.name}_{parameter}_{endpoint}_{start}_{end}.json"

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
        "start": start,
        "end": end,
        "format": "JSON",
    }

    print(f"[power] GET    {parameter} / {domain.name} / {endpoint} {start} ...",
          flush=True)
    resp = requests.get(
        BASE_URL.format(endpoint=endpoint, spatial="regional"),
        params=params, timeout=timeout,
    )
    if resp.status_code == 422:
        raise ValueError(
            f"POWER rejected {parameter!r} at {endpoint} resolution "
            f"(HTTP 422). Response: {resp.text[:400]}"
        )
    resp.raise_for_status()

    dest.write_text(resp.text, encoding="utf-8")
    print(f"[power] saved  {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest


def fetch_domain(domain: cfg.Domain, pause_s: float = 2.0, **kwargs) -> list[Path]:
    """Download every configured parameter for one domain, at cfg.TIME_FREQ."""
    paths: list[Path] = []

    hourly = [p for p in cfg.POWER_PARAMS if cfg.power_native_freq(p) == "h"]
    coarse = [p for p in cfg.POWER_PARAMS if cfg.power_native_freq(p) != "h"]

    if hourly:
        points = native_points(domain)
        windows = _windows(domain, "h")
        total = len(points) * len(windows)
        print(f"[power] {len(hourly)} hourly parameters in one request each x "
              f"{len(points)} grid points x {len(windows)} window(s) "
              f"= {total} requests")

        for i, (lat, lon) in enumerate(points, 1):
            for window in windows:
                paths.append(fetch_point(domain, lat, lon, hourly, window, **kwargs))
                _time.sleep(pause_s)  # be polite to a public API
            print(f"[power] point {i}/{len(points)} done")

    for p in coarse:
        freq = cfg.power_native_freq(p)
        for window in _windows(domain, freq):
            paths.append(fetch_regional(domain, p, freq, window, **kwargs))
            _time.sleep(pause_s)

    return paths


# ==========================================================================
# Parse
# ==========================================================================
def _period_from_key(key: str) -> pd.Period | None:
    """POWER date keys: YYYYMM, YYYYMMDD, or YYYYMMDDHH."""
    freq = KEY_LEN_FREQ.get(len(key))
    if freq is None:
        return None
    if freq == "M":
        if key.endswith("13"):
            return None  # annual roll-up, not a month
        return pd.Period(f"{key[:4]}-{key[4:6]}", freq="M")
    if freq == "D":
        return pd.Period(f"{key[:4]}-{key[4:6]}-{key[6:8]}", freq="D")
    return pd.Period(f"{key[:4]}-{key[4:6]}-{key[6:8]} {key[8:10]}:00", freq="h")


def parse_power_json(path: str | Path) -> pd.DataFrame:
    """Turn one saved POWER response into a tidy long frame.

    Returns columns: ``lat, lon, time (Period), parameter, value, freq``.

    Handles both response shapes: a regional request answers with a GeoJSON
    FeatureCollection (one feature per grid point), a point request with a
    single GeoJSON Feature. Both carry ``properties.parameter`` mapping a
    parameter name to a dict keyed by date -- ``YYYYMM`` monthly (plus a
    synthetic month 13 annual roll-up, dropped here), ``YYYYMMDD`` daily,
    ``YYYYMMDDHH`` hourly.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    if "features" in payload:
        features = payload["features"]
    elif payload.get("type") == "Feature":
        features = [payload]
    else:
        raise ValueError(
            f"{Path(path).name}: unrecognised response shape. Top-level keys "
            f"are {sorted(payload)}. Inspect the raw file before parsing."
        )

    records: list[dict] = []
    freqs: set[str] = set()
    for feat in features:
        lon, lat = feat["geometry"]["coordinates"][:2]
        for param, series in feat["properties"]["parameter"].items():
            for key, value in series.items():
                period = _period_from_key(key)
                if period is None:
                    continue
                freqs.add(KEY_LEN_FREQ[len(key)])
                records.append(
                    {
                        "lat": float(lat),
                        "lon": float(lon),
                        cfg.TIME_COL: period,
                        "parameter": param,
                        "value": float(value),
                    }
                )

    df = pd.DataFrame.from_records(records)
    if df.empty:
        raise ValueError(f"{Path(path).name}: parsed zero records")
    if len(freqs) != 1:
        raise ValueError(
            f"{Path(path).name}: mixed date-key lengths {freqs}. "
            f"One file should come from one endpoint."
        )
    df["freq"] = freqs.pop()

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


def _broadcast(df: pd.DataFrame, native_freq: str) -> pd.DataFrame:
    """Repeat each coarse row across every finer period inside it.

    Used for parameters POWER does not publish at cfg.TIME_FREQ. The resulting
    feature is a step function, constant within its native period; it cannot
    explain variation in the target on any shorter timescale, and any
    feature-importance analysis will rank it near zero for that reason alone
    rather than because the physical quantity is unimportant. Say this in
    Bab IV, or drop the feature.
    """
    if native_freq == cfg.TIME_FREQ:
        return df

    coarse = pd.PeriodIndex(df[cfg.TIME_COL])
    fine = pd.period_range(
        coarse.min().start_time, coarse.max().end_time, freq=cfg.TIME_FREQ
    )
    mapping = pd.DataFrame({cfg.TIME_COL: fine})
    mapping["_coarse"] = pd.PeriodIndex(mapping[cfg.TIME_COL]).asfreq(native_freq)

    return (
        df.rename(columns={cfg.TIME_COL: "_coarse"})
        .merge(mapping, on="_coarse", how="inner")
        .drop(columns=["_coarse"])
    )


def load_power(
    domain: cfg.Domain, directory: str | Path = cfg.RAW_POWER_DIR
) -> pd.DataFrame:
    """Read all saved POWER files for a domain into one wide frame.

    Returns ``lat, lon, time`` plus one column per parameter, regridded onto
    the project's 0.5 deg cells and keyed at cfg.TIME_FREQ, so it can be joined
    to the lightning table.
    """
    files = sorted(Path(directory).glob(f"power_{domain.name}_*.json"))
    if not files:
        raise FileNotFoundError(
            f"no POWER files for domain {domain.name!r} in {directory} -- "
            f"run fetch_domain() first"
        )

    print(f"[power] reading {len(files)} files for {domain.name} ...")
    long = pd.concat([parse_power_json(f) for f in files], ignore_index=True)

    from .lightning import full_cell_index

    cells = full_cell_index(domain)

    out: pd.DataFrame | None = None
    for param in cfg.POWER_PARAMS:
        native = cfg.power_native_freq(param)
        chunk = long[(long["parameter"] == param) & (long["freq"] == native)]
        if chunk.empty:
            have = sorted(long.loc[long["parameter"] == param, "freq"].unique())
            print(
                f"[power] {param:<12s} MISSING at {cfg.freq_slug(native)} "
                f"resolution (files on disk have: {have or 'nothing'}) -- skipped"
            )
            continue

        wide = (
            chunk.pivot_table(
                index=["lat", "lon", cfg.TIME_COL], values="value", aggfunc="mean"
            )
            .reset_index()
            .rename(columns={"value": param})
        )

        n_pts = wide[["lat", "lon"]].drop_duplicates().shape[0]
        gridded = _regrid_parameter(wide, cells)
        note = ""
        if native != cfg.TIME_FREQ:
            gridded = _broadcast(gridded, native)
            note = f"  ({cfg.freq_slug(native)}, broadcast to {cfg.freq_noun()}s)"

        print(
            f"[power] {param:<12s} {n_pts:>3d} native points "
            f"-> {len(cells):>3d} cells "
            f"({gridded[param].isna().mean():.0%} still empty){note}"
        )

        out = gridded if out is None else out.merge(
            gridded, on=["lat", "lon", cfg.TIME_COL], how="outer"
        )

    if out is None:
        raise ValueError(
            f"no usable POWER parameter for {domain.name} at "
            f"{cfg.freq_slug()} resolution -- check the messages above"
        )

    front = ["lat", "lon", cfg.TIME_COL]
    return out[front + [c for c in out.columns if c not in front]]


if __name__ == "__main__":  # python -m gfd_data.power
    for dom in cfg.DOMAINS.values():
        fetch_domain(dom)
