"""NASA POWER meteorology, regridded onto the project cells.

An open HTTP API -- no account, no key, no queue.

    python3 -m gfd.dataset.power           # download both domains
    python3 -m gfd.dataset.power --check   # what's on disk vs what's expected

Hourly is point-only -- `/hourly/regional` 404s -- while daily and monthly take
a regional box, one parameter per request. So the hourly fetch loops over native
POWER points, all parameters in one request each.

It asks for POWER's own grid points rather than the project's cell centres
because POWER asks you not to re-request the same underlying cell, and several
project cells share one POWER longitude cell.
"""

from __future__ import annotations

import argparse
import json
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .. import config as cfg
from .lightning import full_cell_index

BASE_URL = "https://power.larc.nasa.gov/api/temporal/{endpoint}/{spatial}"
COMMUNITY = "RE"
ENDPOINT = {"h": "hourly", "D": "daily", "M": "monthly"}
KEY_LEN_FREQ = {6: "M", 8: "D", 10: "h"}

FILL_VALUE = -999.0

# What POWER publishes each parameter at. A fact about POWER, not a resolution
# setting. Anything coarser than hourly gets broadcast.
# AOD_55_ADJ dropped, D-5. Its files are still on disk.
PARAM_FREQ = {
    "PS": "h",             # surface pressure, kPa
    "PRECTOTCORR": "h",    # precipitation, mm/hour
    "T2M": "h",            # 2 m air temperature, degC
    "RH2M": "h",           # 2 m relative humidity, %
    "WS2M": "h",           # 2 m wind speed, m/s
}

PARAMS = list(PARAM_FREQ)

# Hourly defaults to Local Solar Time, which is a 15-degree longitude swath and
# not a civil timezone. Everything here bins on UTC.
TIME_STANDARD = "UTC"

# MERRA-2 native grid, which POWER's meteorology inherits.
GRID_LAT = 0.5
GRID_LON = 0.625

# Per point per year, 588 requests. "ALL" is 84, but a failure then costs seven
# years of a point instead of one.
HOURLY_CHUNK = "Y"


def native_freq(parameter: str) -> str:
    """The frequency to actually fetch one parameter at."""
    return cfg.coarser(cfg.TIME_FREQ, PARAM_FREQ[parameter])


# ==========================================================================
# Native grid
# ==========================================================================
def native_points(domain: cfg.Domain) -> list[tuple[float, float]]:
    """Every POWER grid point inside a domain's snapped box."""
    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    lats = np.arange(np.ceil(lat_lo / GRID_LAT) * GRID_LAT, lat_hi + 1e-9, GRID_LAT)
    lons = np.arange(np.ceil(lon_lo / GRID_LON) * GRID_LON, lon_hi + 1e-9, GRID_LON)
    return [(round(float(la), 4), round(float(lo), 4)) for la in lats for lo in lons]


def _windows(domain: cfg.Domain, freq: str) -> list[tuple[str, str]]:
    """Every (start, end) pair covering a domain at one frequency."""
    if freq == "M":
        return [(str(domain.year_start), str(domain.year_end))]
    if freq == "h" and HOURLY_CHUNK == "ALL":
        return [(f"{domain.year_start}0101", f"{domain.year_end}1231")]
    return [(f"{y}0101", f"{y}1231") for y in range(domain.year_start, domain.year_end + 1)]


def _tag(value: float) -> str:
    """Filename-safe coordinate: -7.5 -> m007p500, 108.125 -> p108p125."""
    sign = "m" if value < 0 else "p"
    whole, frac = divmod(abs(value), 1)
    return f"{sign}{int(whole):03d}p{int(round(frac * 1000)):03d}"


# ==========================================================================
# Download
# ==========================================================================
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
    """One hourly point request: all parameters, one point, one window."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = window
    dest = out_dir / f"power_{domain.name}_hourly_{_tag(lat)}_{_tag(lon)}_{start}_{end}.json"

    if dest.exists() and not overwrite:
        print(f"[power] cached {dest.name}")
        return dest

    print(f"[power] GET   hourly ({lat}, {lon}) {start}..{end}", flush=True)
    resp = requests.get(
        BASE_URL.format(endpoint="hourly", spatial="point"),
        params={
            "parameters": ",".join(parameters),
            "community": COMMUNITY,
            "latitude": lat,
            "longitude": lon,
            "start": start,
            "end": end,
            "format": "JSON",
            "time-standard": TIME_STANDARD,
        },
        timeout=timeout,
    )
    if resp.status_code == 422:
        raise ValueError(f"POWER rejected {parameters} hourly (422): {resp.text[:400]}")
    resp.raise_for_status()

    dest.write_text(resp.text, encoding="utf-8")
    print(f"[power] saved {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
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
    """One regional request, one parameter. Daily and monthly only."""
    if freq == "h":
        raise ValueError("POWER has no hourly regional endpoint -- it 404s. Use fetch_point.")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    endpoint = ENDPOINT[freq]
    start, end = window
    dest = out_dir / f"power_{domain.name}_{parameter}_{endpoint}_{start}_{end}.json"

    if dest.exists() and not overwrite:
        print(f"[power] cached {dest.name}")
        return dest

    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    print(f"[power] GET   {parameter} {endpoint} {start}", flush=True)
    resp = requests.get(
        BASE_URL.format(endpoint=endpoint, spatial="regional"),
        params={
            "parameters": parameter,
            "community": COMMUNITY,
            "latitude-min": lat_lo,
            "latitude-max": lat_hi,
            "longitude-min": lon_lo,
            "longitude-max": lon_hi,
            "start": start,
            "end": end,
            "format": "JSON",
        },
        timeout=timeout,
    )
    if resp.status_code == 422:
        raise ValueError(f"POWER rejected {parameter!r} at {endpoint} (422): {resp.text[:400]}")
    resp.raise_for_status()

    dest.write_text(resp.text, encoding="utf-8")
    print(f"[power] saved {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest


def expected_filenames(domain: cfg.Domain) -> set[str]:
    """Exactly what a complete fetch writes. Built the way fetch_domain names
    them, so a diff against the directory is exact rather than a count."""
    names = set()
    hourly = [p for p in PARAMS if native_freq(p) == "h"]
    if hourly:
        for lat, lon in native_points(domain):
            for start, end in _windows(domain, "h"):
                names.add(
                    f"power_{domain.name}_hourly_{_tag(lat)}_{_tag(lon)}_{start}_{end}.json"
                )
    for prm in PARAMS:
        freq = native_freq(prm)
        if freq == "h":
            continue
        for start, end in _windows(domain, freq):
            names.add(f"power_{domain.name}_{prm}_{ENDPOINT[freq]}_{start}_{end}.json")
    return names


def fetch_domain(domain: cfg.Domain, pause_s: float = 2.0, **kw) -> list[Path]:
    """Every parameter for one domain. Cached files are skipped."""
    paths: list[Path] = []
    hourly = [p for p in PARAMS if native_freq(p) == "h"]
    coarse = [p for p in PARAMS if native_freq(p) != "h"]

    if hourly:
        points = native_points(domain)
        windows = _windows(domain, "h")
        print(
            f"[power] {len(hourly)} hourly parameters, one request each x "
            f"{len(points)} points x {len(windows)} windows = "
            f"{len(points) * len(windows)} requests"
        )
        for i, (lat, lon) in enumerate(points, 1):
            for window in windows:
                paths.append(fetch_point(domain, lat, lon, hourly, window, **kw))
                _time.sleep(pause_s)
            print(f"[power] point {i}/{len(points)} done")

    for p in coarse:
        for window in _windows(domain, native_freq(p)):
            paths.append(fetch_regional(domain, p, native_freq(p), window, **kw))
            _time.sleep(pause_s)

    return paths


# ==========================================================================
# Parse
# ==========================================================================
def _period_from_key(key: str) -> pd.Period | None:
    """POWER date keys: YYYYMM, YYYYMMDD or YYYYMMDDHH."""
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
    """One saved response to a long frame: lat, lon, time, parameter, value, freq.

    A regional request answers with a GeoJSON FeatureCollection, a point request
    with a single Feature. Both carry properties.parameter keyed by date.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    if "features" in payload:
        features = payload["features"]
    elif payload.get("type") == "Feature":
        features = [payload]
    else:
        raise ValueError(
            f"{Path(path).name}: unrecognised shape, top-level keys {sorted(payload)}"
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
        raise ValueError(f"{Path(path).name}: mixed key lengths {freqs}, one file one endpoint")
    df["freq"] = freqs.pop()

    # Real NaN, so imputation stays an explicit step.
    df.loc[df["value"] <= FILL_VALUE, "value"] = pd.NA
    return df


# ==========================================================================
# Regrid
# ==========================================================================
def _nearest_map(targets: np.ndarray, sources: np.ndarray) -> dict[float, float]:
    idx = np.abs(targets[:, None] - sources[None, :]).argmin(axis=1)
    return {float(t): float(sources[i]) for t, i in zip(targets, idx)}


def _regrid_parameter(param_df: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    """Nearest-neighbour regrid of ONE parameter onto the project cells.

    Driven from the cells, not the source points: each cell asks which POWER
    point is closest. The other direction leaves holes wherever the source grid
    is coarser, which the 0.625 deg longitude step guarantees.

    One parameter at a time -- they don't share a native grid, and a map built
    from the union invents pairs that exist for some parameters and not others.
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


def _broadcast(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Repeat each coarse row across every hour inside it.

    The result is a step function, so feature importance will rank it near zero
    whatever the physics says.
    """
    if freq == cfg.TIME_FREQ:
        return df

    coarse = pd.PeriodIndex(df[cfg.TIME_COL])
    fine = pd.period_range(coarse.min().start_time, coarse.max().end_time, freq=cfg.TIME_FREQ)
    mapping = pd.DataFrame({cfg.TIME_COL: fine})
    mapping["_coarse"] = pd.PeriodIndex(mapping[cfg.TIME_COL]).asfreq(freq)

    return (
        df.rename(columns={cfg.TIME_COL: "_coarse"})
        .merge(mapping, on="_coarse", how="inner")
        .drop(columns=["_coarse"])
    )


# ==========================================================================
# Load
# ==========================================================================
def _files(domain: cfg.Domain, directory: Path) -> list[Path]:
    # Not recursive, so anything parked in a subdirectory is left alone.
    return sorted(directory.glob(f"power_{domain.name}_*.json"))


def load_power(domain: cfg.Domain, directory: str | Path = cfg.RAW_POWER_DIR) -> pd.DataFrame:
    """All saved files for a domain, wide, on the project grid, keyed hourly."""
    directory = Path(directory)
    files = _files(domain, directory)
    if not files:
        raise FileNotFoundError(
            f"no POWER files for {domain.name!r} in {directory} -- run fetch_domain() first"
        )

    extra = sorted({f.name for f in files} - expected_filenames(domain))
    if extra:
        print(
            f"[power] {len(extra)} file(s) here that a fetch wouldn't write: {extra}. "
            f"Parsed and discarded unless they hold a parameter in PARAMS -- but "
            f"anything unexpected should be identified, not tolerated."
        )

    print(f"[power] reading {len(files)} files for {domain.name} ...")
    long = pd.concat([parse_power_json(f) for f in files], ignore_index=True)
    cells = full_cell_index(domain)

    out: pd.DataFrame | None = None
    for param in PARAMS:
        native = native_freq(param)
        chunk = long[(long["parameter"] == param) & (long["freq"] == native)]
        if chunk.empty:
            have = sorted(long.loc[long["parameter"] == param, "freq"].unique())
            print(f"[power] {param:<12s} MISSING at {native!r} (on disk: {have or 'nothing'})")
            continue

        wide = (
            chunk.pivot_table(index=["lat", "lon", cfg.TIME_COL], values="value", aggfunc="mean")
            .reset_index()
            .rename(columns={"value": param})
        )

        n_pts = wide[["lat", "lon"]].drop_duplicates().shape[0]
        gridded = _regrid_parameter(wide, cells)
        note = ""
        if native != cfg.TIME_FREQ:
            gridded = _broadcast(gridded, native)
            note = f"  ({cfg.FREQ_SLUG[native]}, broadcast to hours)"

        print(
            f"[power] {param:<12s} {n_pts:>3d} points -> {len(cells):>3d} cells "
            f"({gridded[param].isna().mean():.0%} empty){note}"
        )

        out = gridded if out is None else out.merge(
            gridded, on=["lat", "lon", cfg.TIME_COL], how="outer"
        )

    if out is None:
        raise ValueError(f"no usable POWER parameter for {domain.name} -- see above")

    front = ["lat", "lon", cfg.TIME_COL]
    return out[front + [c for c in out.columns if c not in front]]


# ==========================================================================
# Checks
# ==========================================================================
def check_files(domain: cfg.Domain, directory: str | Path = cfg.RAW_POWER_DIR) -> None:
    """Disk against what a complete fetch would write, by name."""
    directory = Path(directory)
    on_disk = {f.name for f in _files(directory=directory, domain=domain)}
    expected = expected_filenames(domain)

    print(f"\n[power] {domain.name}: {len(on_disk)} files, {len(expected)} expected")
    print(f"  {len(native_points(domain))} points x {len(_windows(domain, 'h'))} windows")

    missing = sorted(expected - on_disk)
    extra = sorted(on_disk - expected)

    if missing:
        print(f"  !! {len(missing)} missing, e.g. {missing[:3]} -- re-run, cached are skipped")
    if extra:
        # Files for a parameter that has since been dropped land here. That is
        # expected; anything else is not.
        print(f"  {len(extra)} not part of a fetch: {extra}")
    if not missing and not extra:
        print("  OK")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), default=None)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    domains = [cfg.DOMAINS[args.domain]] if args.domain else list(cfg.DOMAINS.values())
    for d in domains:
        if args.check:
            check_files(d)
        else:
            fetch_domain(d, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
