"""Load raw cloud-to-ground strike records and aggregate them into monthly GFD.

Two very different raw formats come in here:

* PLN Puslitbang LDS  -- one .xlsx per year (or one workbook with one sheet
  per year). Columns are the Vaisala/TLS export layout.
* NASA MERLIN         -- many small .csv exports, because the web archive
  only lets you pull a short window at a time.

Both are normalised to the same tidy strike frame::

    timestamp (tz-aware UTC) | lat | lon | peak_current_ka | polarity | source

and then gridded to one row per (grid cell, month).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as cfg

STRIKE_COLUMNS = ["timestamp", "lat", "lon", "peak_current_ka", "polarity", "source"]

EARTH_DEG_KM = 111.320  # length of one degree of longitude at the equator


# ==========================================================================
# 1. PLN Puslitbang (tropis)
# ==========================================================================
def load_pln_workbook(path: str | Path, sheets: list[str] | None = None) -> pd.DataFrame:
    """Read one PLN LDS workbook into the tidy strike frame.

    Every sheet in the workbook is read and concatenated unless ``sheets`` is
    given, so a workbook holding 2018..2024 as separate sheets works without
    further configuration.
    """
    path = Path(path)
    raw = pd.read_excel(path, sheet_name=sheets if sheets else None, engine="openpyxl")
    if isinstance(raw, pd.DataFrame):          # single sheet requested by name
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

    # Keep cloud-to-ground only. Earlier years of the LDS export may contain
    # intra-cloud rows ("IC"); 2024 happens to contain none.
    strikes = strikes[strikes["discrimination"].str.upper().str.startswith("CG", na=False)]
    strikes["polarity"] = np.where(
        strikes["discrimination"].str.endswith("+", na=False), "positive", "negative"
    )
    strikes = strikes.drop(columns=["discrimination"])

    strikes = strikes.dropna(subset=["timestamp", "lat", "lon"])
    strikes["timestamp"] = (
        strikes["timestamp"].dt.tz_localize(cfg.TROPIS.tz, ambiguous="NaT", nonexistent="NaT")
        .dt.tz_convert("UTC")
    )
    return strikes.dropna(subset=["timestamp"])[STRIKE_COLUMNS].reset_index(drop=True)


def load_pln(directory: str | Path = cfg.RAW_PLN_DIR, pattern: str = "*.xlsx") -> pd.DataFrame:
    """Read every PLN workbook in ``directory`` and concatenate."""
    files = sorted(Path(directory).glob(pattern))
    if not files:
        raise FileNotFoundError(f"no PLN workbooks matching {pattern!r} under {directory}")
    return pd.concat([load_pln_workbook(f) for f in files], ignore_index=True)


# ==========================================================================
# 2. NASA MERLIN (subtropis)
# ==========================================================================
def load_merlin_file(path: str | Path) -> pd.DataFrame:
    """Read one MERLIN cloud-to-ground CSV export into the tidy strike frame."""
    path = Path(path)
    df = pd.read_csv(path, dtype=str)
    df = df.rename(columns=lambda c: str(c).strip())

    missing = {"Date", "Time", "Latitude", "Longitude"} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")

    # "07/15/2023" + "00:00:07.3337970" -> pandas only keeps microseconds, so
    # trim the 7-digit fractional seconds to 6 digits before parsing.
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
    """Read and concatenate every MERLIN export in ``directory``.

    The archive caps each export at a short window, so the expected layout is
    a folder of many files. Exact-duplicate strike records that appear where
    two exports overlap at a boundary are dropped.
    """
    files = sorted(Path(directory).glob(pattern))
    if not files:
        raise FileNotFoundError(f"no MERLIN exports matching {pattern!r} under {directory}")

    frames = [load_merlin_file(f) for f in files]
    strikes = pd.concat(frames, ignore_index=True)

    before = len(strikes)
    strikes = strikes.drop_duplicates(subset=["timestamp", "lat", "lon", "peak_current_ka"])
    dropped = before - len(strikes)
    if dropped:
        print(f"[merlin] dropped {dropped:,} duplicate strikes across overlapping exports")

    return strikes.sort_values("timestamp").reset_index(drop=True)


# ==========================================================================
# 3. Gridding: strikes -> monthly GFD per 0.5 deg cell
# ==========================================================================
def _cell_area_km2(lat_center: float, grid_deg: float = cfg.GRID_DEG) -> float:
    """Approximate area of a lat/lon cell, accounting for meridian convergence."""
    dy = grid_deg * 110.574
    dx = grid_deg * EARTH_DEG_KM * math.cos(math.radians(lat_center))
    return dy * dx


def assign_grid(df: pd.DataFrame, grid_deg: float = cfg.GRID_DEG) -> pd.DataFrame:
    """Attach ``lat_bin`` / ``lon_bin`` cell centres to a frame with lat/lon."""
    out = df.copy()
    out["lat_bin"] = np.floor(out["lat"] / grid_deg) * grid_deg + grid_deg / 2
    out["lon_bin"] = np.floor(out["lon"] / grid_deg) * grid_deg + grid_deg / 2
    return out


def full_cell_index(domain: cfg.Domain, grid_deg: float = cfg.GRID_DEG) -> pd.DataFrame:
    """Every grid-cell centre inside a domain's snapped bounding box."""
    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    lats = np.arange(lat_lo, lat_hi, grid_deg) + grid_deg / 2
    lons = np.arange(lon_lo, lon_hi, grid_deg) + grid_deg / 2
    grid = pd.MultiIndex.from_product([lats, lons], names=["lat_bin", "lon_bin"])
    return grid.to_frame(index=False)


def observed_months(
    strikes: pd.DataFrame, domain: cfg.Domain
) -> pd.DataFrame:
    """Distinct calendar days present in the raw data, per month.

    Absence of a strike record is ambiguous: it can mean "the detector was
    running and saw nothing" or "there is no data for this period at all".
    Nothing in an LDS or MERLIN export distinguishes the two, so this uses the
    only available proxy -- a day on which *some* strike was recorded anywhere
    in the domain is a day the network was observing. Over an area the size of
    West Java or Florida that is a safe read.

    Days with genuinely zero flashes domain-wide get counted as unobserved.
    That slightly under-counts coverage in the dry season, which biases GFD
    upward a little; the alternative -- treating six missing years as six years
    of zero lightning -- is far worse.
    """
    local_day = strikes["timestamp"].dt.tz_convert(domain.tz).dt.tz_localize(None)
    per_month = (
        pd.DataFrame({"month": local_day.dt.to_period("M"), "day": local_day.dt.normalize()})
        .groupby("month")["day"]
        .nunique()
        .rename("observed_days")
        .reset_index()
    )
    per_month["days_in_month"] = per_month["month"].dt.days_in_month
    per_month["coverage"] = per_month["observed_days"] / per_month["days_in_month"]
    return per_month


def aggregate_gfd(
    strikes: pd.DataFrame,
    domain: cfg.Domain,
    grid_deg: float = cfg.GRID_DEG,
    fill_empty_cells: bool = True,
    min_coverage: float = 0.0,
) -> pd.DataFrame:
    """Aggregate strike records into one row per (cell, month).

    ``fill_empty_cells`` inserts explicit zero-flash rows -- but only for
    months the raw data actually covers. Filling the whole configured year
    range instead would invent zeros for periods with no data at all, which is
    not a quiet inaccuracy: it hands the model thousands of rows whose target
    is zero for reasons that have nothing to do with meteorology.

    ``min_coverage`` drops months observed for less than this fraction of their
    days. A month with two days of data yields a GFD estimate built on two
    days; it is normalised correctly by ``observed_days``, but it is still a
    far noisier estimate than a full month. Raising this to e.g. 0.9 keeps only
    near-complete months.
    """
    df = assign_grid(strikes, grid_deg)
    df = df[
        df["lat_bin"].between(*domain.snapped_bbox()[:2])
        & df["lon_bin"].between(*domain.snapped_bbox()[2:])
    ]
    # Bin by *local* calendar month. A "January" of West Java lightning should
    # be January in Jakarta time, not a UTC window shifted seven hours back.
    df["month"] = (
        df["timestamp"].dt.tz_convert(domain.tz).dt.tz_localize(None).dt.to_period("M")
    )

    coverage = observed_months(strikes, domain)
    configured = pd.period_range(
        f"{domain.year_start}-01", f"{domain.year_end}-12", freq="M"
    )
    absent = [str(m) for m in configured if m not in set(coverage["month"])]
    if absent:
        print(
            f"[{domain.name}] NO DATA for {len(absent)} of {len(configured)} "
            f"configured months -- these are excluded, not zero-filled "
            f"({absent[0]} .. {absent[-1]})"
        )

    if min_coverage > 0:
        thin = coverage[coverage["coverage"] < min_coverage]
        if len(thin):
            print(
                f"[{domain.name}] dropping {len(thin)} months below "
                f"{min_coverage:.0%} coverage: "
                + ", ".join(f"{r.month} ({r.observed_days}d)" for r in thin.head(6).itertuples())
                + (" ..." if len(thin) > 6 else "")
            )
        coverage = coverage[coverage["coverage"] >= min_coverage]

    df = df[df["month"].isin(set(coverage["month"]))]

    agg = (
        df.groupby(["lat_bin", "lon_bin", "month"], observed=True)
        .agg(
            flash_count=("lat", "size"),
            mean_peak_current_ka=("peak_current_ka", "mean"),
            positive_share=("polarity", lambda s: (s == "positive").mean()),
        )
        .reset_index()
    )

    if fill_empty_cells:
        cells = full_cell_index(domain, grid_deg)
        skeleton = cells.merge(coverage[["month"]], how="cross")
        agg = skeleton.merge(agg, on=["lat_bin", "lon_bin", "month"], how="left")
        agg["flash_count"] = agg["flash_count"].fillna(0).astype("int64")

    agg = agg.merge(coverage, on="month", how="left")
    agg["area_km2"] = agg["lat_bin"].map(lambda la: _cell_area_km2(la, grid_deg))

    # Normalise by days actually observed, not by calendar length. A month with
    # one day of data must not be read as a month with one day of lightning.
    agg["gfd_per_km2_per_day"] = agg["flash_count"] / agg["area_km2"] / agg["observed_days"]
    agg["gfd_per_km2_per_year"] = agg["gfd_per_km2_per_day"] * 365.25

    agg = agg.rename(columns={"lat_bin": "lat", "lon_bin": "lon"})
    agg["domain"] = domain.name
    return agg.sort_values(["month", "lat", "lon"]).reset_index(drop=True)
