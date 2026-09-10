"""Raw strike records in, gridded hourly flash counts out.

    PLN Puslitbang LDS   .xlsx, Vaisala/TLS export layout
    NASA MERLIN          many small .csv exports, one per archive window

Both normalise to timestamp (UTC), lat, lon, peak_current_ka, polarity, source,
then grid to one row per (0.5 deg cell, clock hour).

This module owns the grid. era5.py and power.py import assign_grid and
full_cell_index from here so a cell is defined in one place.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config as cfg

STRIKE_COLUMNS = ["timestamp", "lat", "lon", "peak_current_ka", "polarity", "source"]

# Length of one degree of longitude at the equator, km.
EARTH_DEG_KM = 111.320


# ==========================================================================
# PLN Puslitbang (tropis)
# ==========================================================================
def load_pln_workbook(path: str | Path, sheets: list[str] | None = None) -> pd.DataFrame:
    """Read one PLN workbook. Every sheet unless `sheets` says otherwise."""
    path = Path(path)
    raw = pd.read_excel(path, sheet_name=sheets if sheets else None, engine="openpyxl")
    if isinstance(raw, pd.DataFrame):
        raw = {path.stem: raw}

    frames = []
    for sheet_name, df in raw.items():
        df = df.rename(columns=lambda c: str(c).strip())
        missing = {"Date and time", "Latitude", "Longitude"} - set(df.columns)
        if missing:
            raise ValueError(f"{path.name}[{sheet_name}]: missing columns {sorted(missing)}")

        out = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(df["Date and time"], errors="coerce"),
                "lat": pd.to_numeric(df["Latitude"], errors="coerce"),
                "lon": pd.to_numeric(df["Longitude"], errors="coerce"),
                "peak_current_ka": pd.to_numeric(
                    df.get("Signal (kA)", pd.Series(np.nan, index=df.index)),
                    errors="coerce",
                ),
                "discrimination": df.get(
                    "Discrimination", pd.Series("CG", index=df.index)
                ).astype("string"),
            }
        )
        out["source"] = f"pln:{path.name}#{sheet_name}"
        frames.append(out)

    strikes = pd.concat(frames, ignore_index=True)

    # Cloud-to-ground only.
    before = len(strikes)
    strikes = strikes[strikes["discrimination"].str.upper().str.startswith("CG", na=False)]
    dropped_ic = before - len(strikes)

    strikes["polarity"] = np.where(
        strikes["discrimination"].str.endswith("+", na=False), "positive", "negative"
    )
    strikes = strikes.drop(columns=["discrimination"])
    strikes = strikes.dropna(subset=["timestamp", "lat", "lon"])

    # Export doesn't state its clock. See cfg.TROPIS.
    strikes["timestamp"] = (
        strikes["timestamp"]
        .dt.tz_localize(cfg.TROPIS.tz, ambiguous="NaT", nonexistent="NaT")
        .dt.tz_convert("UTC")
    )
    out = strikes.dropna(subset=["timestamp"])[STRIKE_COLUMNS].reset_index(drop=True)
    print(f"[pln] {path.name}: {len(out):,} CG strikes ({dropped_ic:,} non-CG dropped)")
    return out


def load_pln(directory: str | Path = cfg.RAW_PLN_DIR, pattern: str = "*.xlsx") -> pd.DataFrame:
    files = sorted(Path(directory).glob(pattern))
    if not files:
        raise FileNotFoundError(f"no PLN workbooks matching {pattern!r} under {directory}")
    return pd.concat([load_pln_workbook(f) for f in files], ignore_index=True)


# ==========================================================================
# NASA MERLIN (subtropis)
# ==========================================================================
def load_merlin_file(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_csv(path, dtype=str)
    df = df.rename(columns=lambda c: str(c).strip())

    missing = {"Date", "Time", "Latitude", "Longitude"} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")

    # 7 fractional digits; pandas stops at microseconds.
    time_str = df["Time"].str.replace(r"(\.\d{6})\d+", r"\1", regex=True)
    ts = pd.to_datetime(
        df["Date"].str.strip() + " " + time_str.str.strip(),
        format="%m/%d/%Y %H:%M:%S.%f",
        errors="coerce",
    )

    signal = pd.to_numeric(df.get("Signal Strength"), errors="coerce")
    out = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": pd.to_numeric(df["Latitude"], errors="coerce"),
            "lon": pd.to_numeric(df["Longitude"], errors="coerce"),
            "peak_current_ka": signal,
            "polarity": np.where(signal >= 0, "positive", "negative"),
            "source": f"merlin:{path.name}",
        }
    )
    out = out.dropna(subset=["timestamp", "lat", "lon"])
    out["timestamp"] = out["timestamp"].dt.tz_localize("UTC")
    return out[STRIKE_COLUMNS].reset_index(drop=True)


def load_merlin(
    directory: str | Path = cfg.RAW_MERLIN_DIR, pattern: str = "*.csv"
) -> pd.DataFrame:
    """Every MERLIN export. Windows overlap, so exact duplicates are dropped."""
    files = sorted(Path(directory).glob(pattern))
    if not files:
        raise FileNotFoundError(f"no MERLIN exports matching {pattern!r} under {directory}")

    strikes = pd.concat([load_merlin_file(f) for f in files], ignore_index=True)

    before = len(strikes)
    strikes = strikes.drop_duplicates(subset=["timestamp", "lat", "lon", "peak_current_ka"])
    if before - len(strikes):
        print(f"[merlin] dropped {before - len(strikes):,} duplicates across overlapping exports")

    return strikes.sort_values("timestamp").reset_index(drop=True)


LOADERS = {"tropis": load_pln, "subtropis": load_merlin}


# ==========================================================================
# The grid
# ==========================================================================
def _cell_area_km2(lat_center: float, grid_deg: float = cfg.GRID_DEG) -> float:
    """Cell area, accounting for meridian convergence."""
    dy = grid_deg * 110.574
    dx = grid_deg * EARTH_DEG_KM * math.cos(math.radians(lat_center))
    return dy * dx


def assign_grid(df: pd.DataFrame, grid_deg: float = cfg.GRID_DEG) -> pd.DataFrame:
    """Attach lat_bin / lon_bin cell centres to anything carrying lat/lon."""
    out = df.copy()
    out["lat_bin"] = np.floor(out["lat"] / grid_deg) * grid_deg + grid_deg / 2
    out["lon_bin"] = np.floor(out["lon"] / grid_deg) * grid_deg + grid_deg / 2
    return out


def full_cell_index(domain: cfg.Domain, grid_deg: float = cfg.GRID_DEG) -> pd.DataFrame:
    """Every cell centre inside a domain's snapped box."""
    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    lats = np.arange(lat_lo, lat_hi, grid_deg) + grid_deg / 2
    lons = np.arange(lon_lo, lon_hi, grid_deg) + grid_deg / 2
    grid = pd.MultiIndex.from_product([lats, lons], names=["lat_bin", "lon_bin"])
    return grid.to_frame(index=False)


def to_utc_naive(ts: pd.Series) -> pd.Series:
    """To the naive UTC calendar used for binning. Every source has to agree on
    the label or the join matches nothing, silently."""
    return ts.dt.tz_convert("UTC").dt.tz_localize(None)


# ==========================================================================
# Coverage
# ==========================================================================
def observed_months(strikes: pd.DataFrame) -> pd.DataFrame:
    """Distinct calendar days present in the raw data, per month.

    An absent record is ambiguous: detector up and seeing nothing, or no data
    at all. The proxy is that a day with some strike anywhere in the domain is
    a day the network was up.

    Monthly on purpose -- see aggregate_gfd.
    """
    day = to_utc_naive(strikes["timestamp"])
    per_month = (
        pd.DataFrame({"month": day.dt.to_period("M"), "day": day.dt.normalize()})
        .groupby("month")["day"]
        .nunique()
        .rename("observed_days")
        .reset_index()
    )
    per_month["days_in_month"] = per_month["month"].dt.days_in_month
    per_month["coverage"] = per_month["observed_days"] / per_month["days_in_month"]
    return per_month


def _hour_index(coverage: pd.DataFrame) -> pd.DataFrame:
    """Every hour the skeleton holds, from the months that survived the filter,
    so a month with no data contributes nothing rather than 744 zeros."""
    hours = [
        p
        for m in pd.PeriodIndex(coverage["month"])
        for p in pd.period_range(m.start_time, m.end_time, freq="h")
    ]
    return pd.DataFrame({cfg.TIME_COL: pd.PeriodIndex(hours, freq="h")})


# ==========================================================================
# Aggregate
# ==========================================================================
def aggregate_gfd(
    strikes: pd.DataFrame,
    domain: cfg.Domain,
    grid_deg: float = cfg.GRID_DEG,
    fill_empty_cells: bool = True,
    min_coverage: float | None = None,
) -> pd.DataFrame:
    """Strikes to one row per (cell, hour).

    `fill_empty_cells` adds zero-flash rows, but only for months the raw data
    covers. Filling the configured range would invent zeros for stretches with
    no data at all.

    Coverage is judged monthly because the proxy can't work at hourly
    resolution: a quiet 3 a.m. and an offline detector look identical, and
    calling the quiet hour unobserved would delete most of the zero class.
    """
    if min_coverage is None:
        min_coverage = cfg.MIN_COVERAGE

    df = assign_grid(strikes, grid_deg)
    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    df = df[df["lat_bin"].between(lat_lo, lat_hi) & df["lon_bin"].between(lon_lo, lon_hi)]

    naive = to_utc_naive(df["timestamp"])
    df[cfg.TIME_COL] = naive.dt.to_period("h")
    df["month"] = naive.dt.to_period("M")

    # From `strikes`, not the clipped `df`: the proxy is "was the network up
    # anywhere", so a strike outside the box is still evidence. Don't "fix".
    coverage = observed_months(strikes)

    configured = pd.period_range(f"{domain.year_start}-01", f"{domain.year_end}-12", freq="M")
    absent = [str(m) for m in configured if m not in set(coverage["month"])]
    if absent:
        print(
            f"[{domain.name}] NO DATA for {len(absent)} of {len(configured)} configured "
            f"months -- excluded, not zero-filled ({absent[0]} .. {absent[-1]})"
        )

    if min_coverage > 0:
        thin = coverage[coverage["coverage"] < min_coverage]
        if len(thin):
            print(f"[{domain.name}] dropping {len(thin)} months below {min_coverage:.0%} coverage")
        coverage = coverage[coverage["coverage"] >= min_coverage]

    if coverage.empty:
        raise ValueError(
            f"[{domain.name}] no month reaches {min_coverage:.0%} day-coverage."
        )

    df = df[df["month"].isin(set(coverage["month"]))]

    # Not predictors -- same strikes as the target -- but a second target, and
    # recovering them later means a full rebuild.
    #
    # Signed mean because polarity is physical; spread statistics on absolute
    # value, because one +40 and one -40 average to nothing.
    df = df.assign(abs_peak_current_ka=df["peak_current_ka"].abs())

    agg = (
        df.groupby(["lat_bin", "lon_bin", cfg.TIME_COL], observed=True)
        .agg(
            flash_count=("lat", "size"),
            mean_peak_current_ka=("peak_current_ka", "mean"),
            positive_share=("polarity", lambda s: (s == "positive").mean()),
            median_abs_peak_current_ka=("abs_peak_current_ka", "median"),
            max_abs_peak_current_ka=("abs_peak_current_ka", "max"),
            # Python lambda over ~100k groups. Tens of seconds. Drop if build
            # time ever matters more than the statistic.
            p95_abs_peak_current_ka=("abs_peak_current_ka", lambda s: s.quantile(0.95)),
        )
        .reset_index()
    )

    if fill_empty_cells:
        cells = full_cell_index(domain, grid_deg)
        hours = _hour_index(coverage)
        n_rows = len(cells) * len(hours)
        if n_rows > 2_000_000:
            print(
                f"[{domain.name}] skeleton is {len(cells)} cells x {len(hours):,} hours "
                f"= {n_rows:,} rows -- memory high-water mark of the build"
            )
        skeleton = cells.merge(hours, how="cross")
        agg = skeleton.merge(agg, on=["lat_bin", "lon_bin", cfg.TIME_COL], how="left")
        agg["flash_count"] = agg["flash_count"].fillna(0).astype("int64")

    agg["month"] = agg[cfg.TIME_COL].dt.asfreq("M")
    agg = agg.merge(coverage, on="month", how="left")
    agg["area_km2"] = agg["lat_bin"].map(lambda la: _cell_area_km2(la, grid_deg))

    agg["period_days"] = cfg.PERIOD_DAYS
    agg["gfd_per_km2_per_day"] = agg["flash_count"] / agg["area_km2"] / agg["period_days"]
    agg[cfg.TARGET_REPORTING] = agg["gfd_per_km2_per_day"] * 365.25

    agg = agg.rename(columns={"lat_bin": "lat", "lon_bin": "lon"})
    agg["domain"] = domain.name

    zero_share = float((agg[cfg.TARGET] == 0).mean())
    print(
        f"[{domain.name}] {zero_share:.2%} of cell-hours have zero flashes. Predicting "
        f"zero everywhere already explains most of this target's variance -- report the "
        f"zero share beside any R^2, and beat a trivial baseline first."
    )

    return agg.sort_values([cfg.TIME_COL, "lat", "lon"]).reset_index(drop=True)


# ==========================================================================
# Validation
# ==========================================================================
def check_diurnal(strikes: pd.DataFrame, domain: cfg.Domain) -> int:
    """Flash count by local hour. This is what settled the PLN clock.

    Convection peaks in the local afternoon. A peak in the small hours means
    the source clock is wrong, which at hourly resolution displaces every row
    of a domain. Re-run after any change to the raw strike files.
    """
    local = strikes["timestamp"].dt.tz_convert(domain.solar_tz)
    hist = local.dt.hour.value_counts().reindex(range(24), fill_value=0)
    peak, top = int(hist.idxmax()), int(hist.max())

    print(f"\n[{domain.name}] diurnal cycle, {domain.solar_tz}")
    for h in range(24):
        n = int(hist.loc[h])
        bar = "#" * int(round(40 * n / top)) if top else ""
        print(f"  {h:02d}:00  {n:>9,}  {bar}{'  <-- peak' if h == peak else ''}")

    if 12 <= peak <= 21:
        print(f"  OK -- peak {peak:02d}:00, consistent with convective lightning.")
    else:
        print(
            f"  !! peak {peak:02d}:00 is not the local afternoon. Either the configured "
            f"timezone is wrong or the source exports a different clock. Settle it with "
            f"the provider before building anything -- it will not average out."
        )
    return peak
