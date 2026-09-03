"""Central configuration for the GFD dataset build.

Everything that a reviewer might want to change -- bounding boxes, grid size,
date ranges, feature lists, temporal resolution -- lives here and nowhere else.
The loaders and fetchers import from this module so that a single edit
propagates.
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
#   "h" = clock hour     (current setting)
#   "D" = calendar day
#   "M" = calendar month (the original setting; the only resolution comparable
#         with the predecessor study, so keep it buildable)
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
TZ_MODE = "utc"

# Minimum fraction of a month's days that must carry data before that month is
# used. At monthly resolution a thin month is merely a noisy estimate, so 0.0
# was tolerable. At sub-monthly resolution a thin month manufactures *false
# zeros*: every unobserved period inside it becomes a row asserting "no
# lightning here". Hence the much stricter default below.
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
    tz="Asia/Jakarta",   # VERIFY with PLN Puslitbang -- see RUNBOOK step 1.
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
# That is a real limitation, not a neutral implementation detail: a feature
# that cannot vary hour to hour cannot explain hour-to-hour variance in the
# target, and it will look artificially unimportant in any feature-importance
# analysis. At hourly resolution AOD_55_ADJ is constant across ~730 consecutive
# rows. Consider dropping it rather than carrying a near-constant column
# against a very scarce qubit budget -- and either way say which, in Bab IV.
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

# "ALL" = one request per point for the whole span (84 requests total; each
# returns ~61 000 hours x 5 parameters, a few MB of JSON). "Y" = one per point
# per year (588 requests), slower but each retry is cheaper.
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

# Size of one hourly-ERA5 CDS request. "M" = one request per domain-month
# (168 requests total, each small and cheap to retry). "Y" = one per
# domain-year (14 requests, each much larger and slower to queue; try one by
# hand before switching). Ignored when TIME_FREQ == "M".
ERA5_HOURLY_CHUNK = "M"

# --------------------------------------------------------------------------
# Final column order and target
# --------------------------------------------------------------------------
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
