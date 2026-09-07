"""Load raw cloud-to-ground strike records and aggregate them into gridded GFD.

Two very different raw formats come in here:

* PLN Puslitbang LDS  -- one .xlsx per year (or one workbook with one sheet
  per year). Columns are the Vaisala/TLS export layout.
* NASA MERLIN         -- many small .csv exports, because the web archive
  only lets you pull a short window at a time.

Both are normalised to the same tidy strike frame::

    timestamp (tz-aware UTC) | lat | lon | peak_current_ka | polarity | source

and then gridded to one row per (grid cell, period), where the period follows
cfg.TIME_FREQ -- a clock hour at the current setting, not a month.
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

    # Keep cloud-to-ground only. The filter runs unconditionally.
    #
    # When only 2024 was on disk, that year contained no IC rows at all. The
    # full 2018-2024 set is now loaded and whether the earlier years carry any
    # is a countable fact nobody has counted -- run the filter with a counter
    # if the number matters for Bab IV, rather than repeating the 2024 result
    # as though it held for all seven years.
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
# 3. Gridding: strikes -> GFD per 0.5 deg cell per cfg.TIME_FREQ period
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


def _bin_timestamps(ts: pd.Series, domain: cfg.Domain) -> pd.Series:
    """Convert tz-aware strike timestamps to the naive calendar used for binning.

    At monthly resolution the calendar was always the domain's *local* one: a
    "January" of West Java lightning should be January in Jakarta time, not a
    UTC window shifted seven hours back. Seven hours moves almost no strikes
    across a month boundary, so the choice was nearly free.

    At hourly resolution the choice stops being about which storms land in
    which bin -- an hour is the same hour on either clock -- and becomes about
    how the bin is *labelled*. Every source has to agree on the label or the
    join produces nothing at all, silently. NASA POWER's hourly endpoint offers
    local solar time, but LST is derived from longitude and is not
    Asia/Jakarta, so UTC is the only convention all four sources can honour.
    cfg.TZ_MODE is therefore forced to "utc" at hourly resolution.

    The diurnal cycle is not lost by this. build.py emits `hour_of_day_local`,
    which is the form a model can use anyway -- and a cyclical feature is a
    better representation of "3 p.m. local" than a shifted bin label is.
    """
    if cfg.TIME_FREQ == "h" or cfg.TZ_MODE == "utc":
        return ts.dt.tz_convert("UTC").dt.tz_localize(None)
    return ts.dt.tz_convert(domain.tz).dt.tz_localize(None)


def _time_index(coverage: pd.DataFrame) -> pd.DataFrame:
    """Every time period the skeleton should contain, at cfg.TIME_FREQ.

    Built from the months that survived the coverage filter, so a month with no
    data contributes no rows at all -- neither one monthly row, nor thirty
    daily ones, nor seven hundred hourly ones.
    """
    months = pd.PeriodIndex(coverage["month"])
    if cfg.TIME_FREQ == "M":
        return pd.DataFrame({cfg.TIME_COL: months})

    periods = [
        p
        for m in months
        for p in pd.period_range(m.start_time, m.end_time, freq=cfg.TIME_FREQ)
    ]
    return pd.DataFrame({cfg.TIME_COL: pd.PeriodIndex(periods, freq=cfg.TIME_FREQ)})


def observed_months(strikes: pd.DataFrame, domain: cfg.Domain) -> pd.DataFrame:
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

    This stays MONTHLY regardless of cfg.TIME_FREQ, on purpose. See
    aggregate_gfd.
    """
    local_day = _bin_timestamps(strikes["timestamp"], domain)
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
    min_coverage: float | None = None,
) -> pd.DataFrame:
    """Aggregate strike records into one row per (cell, period).

    The period is a clock hour, a calendar day or a calendar month, per
    cfg.TIME_FREQ.

    ``fill_empty_cells`` inserts explicit zero-flash rows -- but only for
    periods the raw data actually covers. Filling the whole configured year
    range instead would invent zeros for stretches with no data at all, which
    is not a quiet inaccuracy: it hands the model rows whose target is zero for
    reasons that have nothing to do with meteorology.

    WHY COVERAGE IS STILL JUDGED MONTHLY
    ------------------------------------
    The observation proxy above -- "a day with at least one strike somewhere in
    the domain is a day the network was up" -- is sound over a month and
    useless over anything shorter, because at sub-monthly resolution the thing
    it cannot distinguish is exactly the thing being predicted. A quiet
    3 a.m. hour and an hour the detector was offline look identical, and
    calling the quiet hour "unobserved" would delete most of the zero class
    from the training set -- which at hourly resolution is almost the entire
    dataset.

    So the gate can only ever be monthly: a month passes or fails on its
    day-coverage, and every period inside a passing month becomes a row,
    zero-flash periods included. The cost is the inverse error -- an offline
    stretch inside an otherwise well-covered month becomes a run of false
    zeros.

    AND THE GATE IS CURRENTLY OFF. cfg.MIN_COVERAGE is 0.0, so the filter below
    is skipped entirely: every month holding at least one strike record
    contributes rows, however thin. A month observed on 6 of 31 days still
    emits 744 hourly rows, and the ~600 hours inside the 25 unobserved days
    become rows asserting "no lightning here" -- absences of observation
    wearing a zero, against a target that is already >99% zeros.

    Two things follow, and neither is optional:

    1. `coverage` and `observed_days` are carried on EVERY output row. Filter
       or weight on `coverage` at modelling time and record the threshold in
       the experiment config (F-05).
    2. Report the distribution of `coverage` over the rows actually trained on,
       beside the zero share.

    Raising the gate to 0.9 would move the error rather than remove it: a 90%
    gate preferentially deletes quiet months, and quiet months are the
    low-target examples the model most needs. There is no setting that avoids
    both. `python -m gfd_data.smoke_lightning` prints the per-month coverage
    table that shows which trade you would actually be making.

    Even with a gate enabled the guarantee would be weak, and the weakness
    belongs in the thesis: a day-coverage gate can only certify that the
    network was up on some fraction of a month's *days*, never that it was up
    for all 24 hours of any one of them.

    ``min_coverage`` defaults to cfg.MIN_COVERAGE.
    """
    if min_coverage is None:
        min_coverage = cfg.MIN_COVERAGE

    df = assign_grid(strikes, grid_deg)
    lat_lo, lat_hi, lon_lo, lon_hi = domain.snapped_bbox()
    df = df[df["lat_bin"].between(lat_lo, lat_hi) & df["lon_bin"].between(lon_lo, lon_hi)]

    naive = _bin_timestamps(df["timestamp"], domain)
    df[cfg.TIME_COL] = naive.dt.to_period(cfg.TIME_FREQ)
    df["month"] = naive.dt.to_period("M")

    # NB: computed from `strikes`, not from the bbox-clipped `df`. Deliberate --
    # the proxy is "was the network up anywhere", so a strike just outside the
    # snapped box is still evidence the detector was running. It does mean the
    # coverage figures are not conditioned on the modelling domain; both
    # loaders return data already confined to their region, so in practice the
    # two are nearly identical. Do not "fix" this to use `df` without deciding
    # which question you want the proxy to answer.
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

    if coverage.empty:
        raise ValueError(
            f"[{domain.name}] no month reaches {min_coverage:.0%} day-coverage. "
            f"Either the raw data is thinner than you think, or "
            f"cfg.MIN_COVERAGE is too strict for this source."
        )

    df = df[df["month"].isin(set(coverage["month"]))]

    # Intensity statistics, per (cell, period). These are NOT predictors --
    # they come from the same strikes as the target -- but they are a second
    # modelling target, and recovering them later would cost a full rebuild.
    #
    # Signed mean is kept because polarity carries physical meaning; the
    # spread statistics use the absolute value, because a cell-hour holding
    # one +40 kA and one -40 kA strike has a mean near zero and a median
    # magnitude of 40, and the second number is the useful one.
    #
    # The median is the headline statistic rather than the mean: CG peak
    # current is heavy-tailed, so the mean of a handful of strikes is
    # dominated by whichever one happened to be largest.
    df = df.assign(abs_peak_current_ka=df["peak_current_ka"].abs())

    agg = (
        df.groupby(["lat_bin", "lon_bin", cfg.TIME_COL], observed=True)
        .agg(
            flash_count=("lat", "size"),
            mean_peak_current_ka=("peak_current_ka", "mean"),
            positive_share=("polarity", lambda s: (s == "positive").mean()),
            median_abs_peak_current_ka=("abs_peak_current_ka", "median"),
            max_abs_peak_current_ka=("abs_peak_current_ka", "max"),
            # The slow one -- a Python-level lambda over every non-empty
            # cell-period. Roughly 105 000 groups for tropis and 99 000 for
            # subtropis, so it costs tens of seconds, not minutes. Drop this
            # line if the build time ever matters more than the statistic.
            p95_abs_peak_current_ka=(
                "abs_peak_current_ka", lambda s: s.quantile(0.95)
            ),
        )
        .reset_index()
    )
    
    if fill_empty_cells:
        cells = full_cell_index(domain, grid_deg)
        times = _time_index(coverage)
        n_rows = len(cells) * len(times)
        if n_rows > 2_000_000:
            print(
                f"[{domain.name}] building a {len(cells)} x {len(times):,} "
                f"skeleton = {n_rows:,} rows -- this is the memory high-water "
                f"mark of the build"
            )
        skeleton = cells.merge(times, how="cross")
        agg = skeleton.merge(agg, on=["lat_bin", "lon_bin", cfg.TIME_COL], how="left")
        agg["flash_count"] = agg["flash_count"].fillna(0).astype("int64")

    agg["month"] = agg[cfg.TIME_COL].dt.asfreq("M")
    agg = agg.merge(coverage, on="month", how="left")
    agg["area_km2"] = agg["lat_bin"].map(lambda la: _cell_area_km2(la, grid_deg))

    # Normalise by the length of the period this row actually represents.
    #   monthly: days actually observed, so a month with one day of data is not
    #            read as a month with one day of lightning;
    #   daily  : exactly one day;
    #   hourly : one twenty-fourth of a day.
    fixed = cfg.period_fraction_of_day()
    agg["period_days"] = agg["observed_days"] if fixed is None else fixed

    agg["gfd_per_km2_per_day"] = agg["flash_count"] / agg["area_km2"] / agg["period_days"]
    agg["gfd_per_km2_per_year"] = agg["gfd_per_km2_per_day"] * 365.25

    agg = agg.rename(columns={"lat_bin": "lat", "lon_bin": "lon"})
    agg["domain"] = domain.name

    if cfg.TIME_FREQ != "M":
        zero_share = float((agg["flash_count"] == 0).mean())
        noun = cfg.freq_noun()
        print(
            f"[{domain.name}] {zero_share:.2%} of cell-{noun}s have zero "
            f"flashes. Predicting zero everywhere already explains most of "
            f"this target's variance -- report the zero share beside any R^2, "
            f"and beat a trivial baseline before claiming the model learned "
            f"anything."
        )

    return agg.sort_values([cfg.TIME_COL, "lat", "lon"]).reset_index(drop=True)
