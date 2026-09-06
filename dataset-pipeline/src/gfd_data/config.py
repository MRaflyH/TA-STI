"""Central configuration for the GFD dataset build.

Everything that a reviewer might want to change -- bounding boxes, grid size,
date ranges, feature lists, temporal resolution -- lives here and nowhere else.
The loaders and fetchers import from this module so that a single edit
propagates.

THIS FILE IS THE SOURCE OF TRUTH FOR PIPELINE PARAMETERS. Where RUNBOOK.md, the
project instructions, or a chat transcript disagrees with a value here, this
file wins and the prose is what needs fixing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

RAW_PLN_DIR = DATA_DIR / "raw" / "pln"
RAW_MERLIN_DIR = DATA_DIR / "raw" / "merlin"
RAW_POWER_DIR = DATA_DIR / "raw" / "power"
RAW_ERA5_DIR = DATA_DIR / "raw" / "era5"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

for _d in (
    RAW_PLN_DIR, RAW_MERLIN_DIR, RAW_POWER_DIR, RAW_ERA5_DIR,
    INTERIM_DIR, PROCESSED_DIR,
):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Reproducibility (NF-02)
# --------------------------------------------------------------------------
RANDOM_SEED = 18222067

# --------------------------------------------------------------------------
# Spatial grid
# --------------------------------------------------------------------------
# Grid cell size in degrees. 0.5 deg matches the predecessor study and the
# native NASA POWER latitude resolution.
GRID_DEG = 0.5

# --------------------------------------------------------------------------
# Temporal grid  <-- THE SWITCH
# --------------------------------------------------------------------------
# Temporal unit of one training row.
#   "h" = clock hour     (CURRENT AND INTENDED SETTING)
#   "D" = calendar day
#   "M" = calendar month
#
# Hourly is the project's decision, not a placeholder. The "D" and "M" paths
# are kept working, but nothing is currently built at either.
#
# "M" is retained for one specific reason: the predecessor study aggregated
# monthly, so a monthly build is the only artifact that could ever be set
# beside its numbers. If that comparison is wanted, build it deliberately --
# do not assume it exists.
#
# DO NOT CONFUSE THIS WITH POWER_PARAM_FREQ BELOW. A "M" there is a statement
# about what NASA POWER publishes for one parameter (AOD_55_ADJ is monthly-only
# at source) and has nothing to do with the resolution of a training row.
#
# Changing this one value changes: which POWER endpoint is called, which ERA5
# product is downloaded and whether it is collapsed, how strikes are binned,
# and how the target is normalised. Nothing else needs editing. All three
# resolutions can coexist on disk -- raw files are named by resolution, and the
# processed tables are written to gfd_<domain>_<hourly|daily|monthly>.*
TIME_FREQ = "h"

# Fine-to-coarse ordering, used to decide when a source has to be broadcast
# because it is not published at the resolution being asked for.
FREQ_ORDER: dict[str, int] = {"h": 0, "D": 1, "M": 2}

# Internal name of the time key in every intermediate frame. It used to be
# literally "month"; it is now resolution-neutral. The processed table carries
# this column as a period string ("2024-07-15 14:00", "2024-07-15", "2024-07").
TIME_COL = "time"

# Clock used for binning.
#   "utc"   -- bin every source on UTC.
#   "local" -- bin strikes and ERA5 on the domain's local calendar.
#
# IGNORED AT HOURLY RESOLUTION, and forced to "utc". At hourly the choice is
# not about which storms land in which bin -- an hour is the same hour on
# either clock -- it is purely about how the bin is *labelled*, and every
# source has to agree on the label or the join silently produces nothing.
# NASA POWER's hourly endpoint does offer local solar time (LST), but LST is
# longitude-derived and is not Asia/Jakarta, so "align everything on UTC" is
# the only convention all four sources can actually honour.
#
# The diurnal cycle is not lost by this: `hour_of_day_local` is emitted as a
# column, which is the form a model can use anyway.
#
# This does NOT rescue a wrong source timezone. TZ_MODE fixes the label; the
# `tz` field on each Domain decides how the raw timestamps were *interpreted*
# before labelling. See TROPIS below.
TZ_MODE = "utc"

# Minimum fraction of a month's days that must carry data before that month is
# used.
#
# CURRENT VALUE: 0.0 -- THE GATE IS OFF. Every month that contains at least one
# strike record contributes rows, however thin it is. `aggregate_gfd` skips the
# filter entirely when this is 0, so no "dropping N months" line is printed and
# no month is excluded on coverage grounds. (Months with no records at all are
# still excluded, by a separate mechanism, and reported as "NO DATA for N
# months".)
#
# UNDERSTAND WHAT THAT COSTS AT HOURLY RESOLUTION, because it is not neutral.
# A month observed on 6 of 31 days still emits 744 hourly rows, and the ~600
# hours inside the 25 unobserved days become rows asserting "no lightning
# here". They are not observations of zero; they are absences of observation
# wearing a zero. Against a target that is 94,30% zeros in tropis and 97,00% in
# subtropis (measured, build of 2026-09-06 -- earlier comments here estimated
# ">99%" and were wrong), these are invisible in aggregate and impossible to
# distinguish downstream.
#
# The gate is off deliberately for now, so the two mitigations below are not
# optional -- one of them has to happen before any result is reported:
#   1. `coverage` and `observed_days` are carried on EVERY row of the processed
#      table. Filter or weight on `coverage` at modelling time and record the
#      threshold in the experiment config (F-05).
#   2. Report the distribution of `coverage` across the rows actually trained
#      on, in Bab IV, next to the zero share.
#
# Raising this to 0.9 moves the problem rather than removing it: a 90% gate
# preferentially deletes quiet months, and quiet months are the low-target
# examples the model most needs. There is no setting that avoids both errors.
# `python -m gfd_data.smoke_lightning` prints the per-month coverage table that
# lets you see which trade you are actually making.
#
# THE BUILT TABLES MAKE THAT TRADE CONCRETE, AND IT IS WORSE THAN IT SOUNDS.
# A 0.9 gate would delete 56 of 81 subtropis months and 26 of 84 tropis --
# about 70% of Florida. Worse, it deletes OPPOSITE HALVES OF THE YEAR in the
# two domains: tropis thins in the JJAS dry season, subtropis in DJF winter.
# The two training sets would no longer span comparable seasonal ranges, and
# any cross-domain generalization gap measured afterwards would be partly an
# artefact of the filter.
#
# So this stays at 0.0, and the reason is not just "0.9 deletes too much" --
# it is that this is the WRONG LEVER. `coverage` conflates a quiet sky with a
# dead detector, and at 0.9 the quiet skies vastly outnumber the dead
# detectors, so the filter discards hundreds of real observations to remove a
# handful of false ones. Periods known to be instrument gaps should be excluded
# BY DATE instead; see RUNBOOK step 2 and "Still unverified" item 7.
MIN_COVERAGE = 0.0


@dataclass(frozen=True)
class Domain:
    """One climate domain: a bounding box plus the period it is defined over."""

    name: str                 # "tropis" / "subtropis"
    label: str                # human-readable
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    year_start: int
    year_end: int
    # Timezone the raw lightning timestamps are recorded in. Used for reading
    # the source clock and for local calendar binning (TZ_MODE == "local").
    tz: str = "UTC"
    # Timezone of the domain's SOLAR day, used only for hour_of_day_local.
    # Distinct from `tz` because a source can report in UTC while sitting in a
    # different solar day -- MERLIN does exactly that. Defaults to `tz`.
    local_tz: str | None = None

    @property
    def solar_tz(self) -> str:
        """Clock the diurnal-cycle feature is expressed in."""
        return self.local_tz or self.tz

    def snapped_bbox(self, pad: float = 0.0) -> tuple[float, float, float, float]:
        """Bounding box expanded outward to whole GRID_DEG boundaries."""
        import math

        g = GRID_DEG
        return (
            math.floor((self.lat_min - pad) / g) * g,
            math.ceil((self.lat_max + pad) / g) * g,
            math.floor((self.lon_min - pad) / g) * g,
            math.ceil((self.lon_max + pad) / g) * g,
        )


# Bounding boxes below are the observed extents of the supplied strike files,
# snapped outward. Re-check them after adding more years of data.
TROPIS = Domain(
    name="tropis",
    label="Jawa Barat (PLN Puslitbang LDS)",
    lat_min=-8.0, lat_max=-5.5,
    lon_min=106.0, lon_max=109.0,
    year_start=2018, year_end=2024,
    # SETTLED 2026-09-06, but read the reasoning -- it is a validation result
    # worth reproducing, not a value to take on faith.
    #
    # The loader localises `Date and time` as Asia/Jakarta and converts to UTC.
    # Nothing in the export states its clock, so this began as an assumption.
    #
    # At monthly resolution a seven-hour error moved a handful of strikes
    # across month boundaries. At hourly it would displace EVERY tropis row by
    # seven hours in exactly the dimension hourly resolution exists to capture,
    # and produce a plausible cross-domain gap that is pure artefact.
    #
    # `python -m gfd_data.smoke_lightning --domain tropis` checks it physically
    # and gives a clean afternoon convective maximum over all 2.242.100
    # strikes: peak 16:00 local (431.544 flashes), 15:00 and 17:00 flanking it,
    # trough 08:00-10:00. The argument is tighter than "that looks plausible" --
    # the loader localises the raw field as Jakarta and the smoke test converts
    # back, so that histogram is the raw field's OWN hour. If the export were
    # UTC, true local time would be raw + 7 and the peak would fall at 23:00, a
    # midnight maximum for tropical convection, which is not physical.
    #
    # Florida is the control and behaves the same way: MERLIN really is UTC,
    # and its local-hour peak lands at 15:00.
    #
    # Written confirmation from PLN through the pembimbing is still worth
    # having, and this belongs in Bab III as a validation paragraph. But it is
    # no longer a risk to the build.
    tz="Asia/Jakarta",   # confirmed by diurnal check -- see RUNBOOK step 1.
)

SUBTROPIS = Domain(
    name="subtropis",
    label="Florida (NASA MERLIN)",
    lat_min=26.5, lat_max=30.5,
    lon_min=-82.0, lon_max=-78.5,
    year_start=2018, year_end=2024,
    tz="UTC",              # MERLIN timestamps really are UTC
    # Etc/GMT+5 is UTC-5 (the POSIX sign is inverted), i.e. EST year-round.
    # Deliberately NOT America/New_York: that observes DST, which shifts the
    # clock by an hour while the sun does not move. Asia/Jakarta is a fixed
    # +7 offset, so using a DST-observing zone here would make the diurnal
    # feature mean something slightly different in each domain for half the
    # year -- an asymmetry injected into the one comparison the TA exists to
    # make. Fixed offsets on both sides.
    local_tz="Etc/GMT+5",
)

DOMAINS = {d.name: d for d in (TROPIS, SUBTROPIS)}

# --------------------------------------------------------------------------
# Predictor features -- NASA POWER
# --------------------------------------------------------------------------
# The FINEST resolution at which POWER publishes each parameter. A parameter
# whose native resolution is coarser than TIME_FREQ is fetched at its own
# resolution and broadcast across the finer periods -- i.e. held constant
# within its native period.
#
# THIS IS A PER-PARAMETER FACT ABOUT NASA POWER, NOT A PROJECT SETTING. The
# "M" on AOD_55_ADJ means POWER publishes it monthly and nothing finer; it says
# nothing about TIME_FREQ.
#
# The broadcast is a real limitation, not a neutral implementation detail: a
# feature that cannot vary hour to hour cannot explain hour-to-hour variance in
# the target, and it will look artificially unimportant in any
# feature-importance analysis. At hourly resolution AOD_55_ADJ is constant
# across ~730 consecutive rows. Consider dropping it rather than carrying a
# near-constant column against a very scarce qubit budget -- and either way say
# which, in Bab IV.
#
# VERIFY THIS TABLE with `python -m gfd_data.smoke_power` before the full
# download. It probes each parameter at the resolution TIME_FREQ asks for and
# reports what actually came back.
POWER_PARAM_FREQ: dict[str, str] = {
    "PS": "h",             # surface pressure, kPa
    "PRECTOTCORR": "h",    # bias-corrected precipitation, mm/hour
    "T2M": "h",            # 2 m air temperature, degC
    "RH2M": "h",           # 2 m relative humidity, %
    "WS2M": "h",           # 2 m wind speed, m/s
    "AOD_55_ADJ": "M",     # aerosol optical depth 550 nm, adjusted (sparse!)
}

POWER_PARAMS: list[str] = list(POWER_PARAM_FREQ)

# POWER's hourly endpoint accepts UTC or LST. See TZ_MODE for why this is
# pinned to UTC.
POWER_TIME_STANDARD = "UTC"

# POWER's HOURLY API has no regional option -- only "point". So the hourly
# fetch issues one request per native POWER grid point, with all parameters in
# a single request (the point endpoint allows up to 15). The daily and monthly
# endpoints do support regional requests, and AOD_55_ADJ still uses one.
#
# MERRA-2 native grid, which POWER's meteorology inherits: latitudes on exact
# multiples of 0.5, longitudes on exact multiples of 0.625. Requesting these
# rather than the project's own 0.5 deg cell centres matters -- several project
# cells fall in one POWER longitude cell, and the POWER docs warn that
# repeatedly requesting the same underlying location can get you blocked.
POWER_GRID_LAT = 0.5
POWER_GRID_LON = 0.625

# Size of one hourly POWER request, in TIME, per grid point.
#
# The two domains hold 84 native POWER points between them: 6 lat x 5 lon = 30
# for tropis, 9 lat x 6 lon = 54 for subtropis. Every hourly parameter travels
# in the same request, so the point count is the multiplier, not the parameter
# count.
#
#   "ALL" -- one request per point for the whole 2018-2024 span.
#            84 requests. Each returns ~61 000 hours x 5 parameters, a few MB
#            of JSON. Fewest requests, most expensive single retry.
#   "Y"   -- one request per point per year.  <-- CURRENT SETTING
#            84 x 7 = 588 requests. Slower overall, but a failure costs one
#            year of one point instead of seven, and the cache is finer
#            grained so an interrupted run resumes closer to where it stopped.
#
# Anything that is not the literal string "ALL" takes the per-year branch in
# power._windows.
#
# AOD_55_ADJ is separate and unaffected: one regional monthly request per
# domain, 2 in total. So the full POWER fetch at the current settings is
# 588 + 2 = 590 requests. Under "ALL" it would be 84 + 2 = 86.
POWER_HOURLY_CHUNK = "Y"

# --------------------------------------------------------------------------
# Predictor features -- ERA5
# --------------------------------------------------------------------------
# ERA5 single-level variable names, as accepted by the CDS API.
# NOTE: the two flux-divergence names are the ones to double-check against the
# "Show API request" button on the CDS dataset page before the first run --
# see RUNBOOK step 4b. The other four are stable.
ERA5_VARIABLES: list[str] = [
    "convective_available_potential_energy",                       # -> cape
    "k_index",                                                     # -> kx
    "total_column_cloud_ice_water",                                # -> tciw
    "total_column_cloud_liquid_water",                             # -> tclw
    "vertical_integral_of_divergence_of_cloud_frozen_water_flux",  # -> viiwd
    "vertical_integral_of_divergence_of_cloud_liquid_water_flux",  # -> vilwd
]

# Map the short names that appear inside the downloaded NetCDF onto the column
# names used in the modelling table.
#
# KX IS MISSING FROM THE SUBTROPIS BUILD AND NOBODY KNOWS WHY. The build of
# 2026-09-06 reports `!! absent features: ['KX']` for subtropis; tropis carries
# all 14 predictors, subtropis 13. The column is not null -- it never arrives.
# Both domains have the full 84 .nc files, so this is not a download shortfall
# by file count.
#
# Three candidate causes, cheapest first: the subtropis files carry k_index
# under a short name this map does not have (a one-line fix here), a subset of
# subtropis files lack the variable, or the subtropis download requested a
# different variable list (84 CDS requests to fix). Check with:
#
#   python -c "
#   import xarray as xr
#   from gfd_data import config as cfg
#   for dom in ['tropis','subtropis']:
#       files = sorted(cfg.RAW_ERA5_DIR.glob(f'*{dom}*.nc'))
#       seen = {}
#       for f in files:
#           with xr.open_dataset(f) as ds:
#               for v in ds.data_vars: seen[v] = seen.get(v, 0) + 1
#       print(dom, len(files), sorted(seen.items()))
#   "
#
# This is not cosmetic. `run_cross` fits on one domain and applies that model
# to the other, so a 14-feature source against a 13-feature target either
# raises a shape error or gets silently intersected by the shared preprocessing
# chain -- dropping KX from BOTH domains without recording it. K index is also
# one of the fourteen predictors the predecessor study used. If KX is dropped,
# drop it from both domains explicitly here and say so in Bab IV.
ERA5_SHORTNAME_MAP: dict[str, str] = {
    "cape": "CAPE",
    "kx": "KX",
    "tciw": "TCIW",
    "tclw": "TCLW",
    "viiwd": "VIIWD",
    "vilwd": "VILWD",
}

# How each hourly ERA5 field collapses to one value per day. USED ONLY WHEN
# TIME_FREQ == "D"; at hourly resolution there is nothing to collapse, which
# removes this decision from the thesis entirely.
#
# CAPE and KX take the daily MAXIMUM because their daily mean is dominated by
# the overnight minimum and says little about whether a storm could fire. The
# four column-integrated fields take the mean.
ERA5_DAILY_STATS: dict[str, str] = {
    "cape": "max",
    "kx": "max",
    "tciw": "mean",
    "tclw": "mean",
    "viiwd": "mean",
    "vilwd": "mean",
}

# Hours requested from the hourly ERA5 product.
ERA5_HOURS: list[str] = [f"{h:02d}:00" for h in range(24)]

# Size of one hourly-ERA5 CDS request. Ignored when TIME_FREQ == "M".
#
#   "M" -- one request per domain-month. 7 years x 12 months x 2 domains =
#          168 requests, each ~1,3 MB and cheap to retry.  <-- CURRENT
#   "Y" -- one request per domain-year, 14 total. TESTED BY HAND AND REFUSED:
#          `era5.fetch_chunk_hourly(cfg.TROPIS, 2018)` is ~53 000 fields, which
#          exceeds the CDS cost limit. The CDS either declines it outright or
#          gives it very low priority. This is a settled negative result, not
#          an untried option -- do not switch to it.
#
# A quarterly chunk (~13 000 fields, 56 requests) is the untested middle
# ground; the cost threshold sits somewhere between a month and a year and only
# the ends have been probed. Adding it needs a "Q" branch in
# `fetch_chunk_hourly` AND a matching glob in `_files`, or `load_era5` picks up
# the wrong set.
ERA5_HOURLY_CHUNK = "M"

# --------------------------------------------------------------------------
# Final column order and target
# --------------------------------------------------------------------------
# The PREDICTOR columns, in the order the processed table carries them.
#
# This is not the full column list. build.py additionally emits calendar
# features derived from the time key (`year`, `month_of_year`, `day_of_year`,
# `hour_of_day_utc`, `hour_of_day_local`) and the bookkeeping columns
# (`days_in_month`, `observed_days`, `coverage`, `period_days`, `area_km2`).
# Downstream code that selects features by "everything numeric that is not the
# target" will pick those up too -- see the note in the modelling package.
FEATURE_COLUMNS: list[str] = (
    ["lat", "lon"]
    + POWER_PARAMS
    + list(ERA5_SHORTNAME_MAP.values())
)

# The target column carried forward from the monthly build, kept so that the
# three resolutions share a unit. READ THE WARNING build.py prints at hourly
# resolution before using it: annualising a single hour's flash count produces
# a spike-or-zero distribution that is a count process wearing a density's
# units. `flash_count` is the honest hourly target.
TARGET_COLUMN = "gfd_per_km2_per_year"

# --------------------------------------------------------------------------
# Sentinels
# --------------------------------------------------------------------------
POWER_FILL_VALUE = -999.0  # NASA POWER missing-data sentinel


# --------------------------------------------------------------------------
# Small helpers so no other module has to branch on TIME_FREQ by hand
# --------------------------------------------------------------------------
_NOUNS = {"h": "hour", "D": "day", "M": "month"}
_SLUGS = {"h": "hourly", "D": "daily", "M": "monthly"}


def freq_noun(freq: str | None = None) -> str:
    """'hour' / 'day' / 'month' -- for log lines."""
    return _NOUNS[freq or TIME_FREQ]


def freq_slug(freq: str | None = None) -> str:
    """'hourly' / 'daily' / 'monthly' -- for file names and metadata."""
    return _SLUGS[freq or TIME_FREQ]


def coarser(a: str, b: str) -> str:
    """Whichever of two frequencies is the coarser."""
    return a if FREQ_ORDER[a] >= FREQ_ORDER[b] else b


def power_native_freq(parameter: str) -> str:
    """The frequency at which one POWER parameter should actually be fetched.

    The finest endpoint that is no finer than what the parameter is published
    at, and no finer than what the build needs.
    """
    return coarser(TIME_FREQ, POWER_PARAM_FREQ[parameter])


def period_fraction_of_day() -> float | None:
    """Length of one row's period in days.

    None for "M", where the monthly build normalises by *observed* days rather
    than by calendar length.
    """
    return {"h": 1.0 / 24.0, "D": 1.0}.get(TIME_FREQ)
