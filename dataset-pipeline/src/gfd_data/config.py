"""Central configuration for the GFD dataset build.

Everything that a reviewer might want to change -- bounding boxes, grid size,
date ranges, feature lists -- lives here and nowhere else. The loaders and
fetchers import from this module so that a single edit propagates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
# Spatial / temporal grid
# --------------------------------------------------------------------------
# Grid cell size in degrees. 0.5 deg matches the predecessor study and the
# native NASA POWER latitude resolution.
GRID_DEG = 0.5

# Temporal unit of one training row. "M" = calendar month.
# Monthly aggregation is the mitigation agreed in the proposal for satellite
# data sparsity; it is also what makes the ERA5 monthly-means product usable.
TIME_FREQ = "M"


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
    # Timezone the raw lightning timestamps are recorded in. Used only to
    # decide which calendar month a strike belongs to.
    tz: str = "UTC"

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
    tz="UTC",
)

DOMAINS = {d.name: d for d in (TROPIS, SUBTROPIS)}

# --------------------------------------------------------------------------
# Predictor features
# --------------------------------------------------------------------------
# NASA POWER parameter codes (monthly, RE community).
POWER_PARAMS: list[str] = [
    "PS",             # surface pressure, kPa
    "PRECTOTCORR",    # bias-corrected precipitation, mm/day
    "T2M",            # 2 m air temperature, degC
    "RH2M",           # 2 m relative humidity, %
    "WS2M",           # 2 m wind speed, m/s
    "AOD_55_ADJ",     # aerosol optical depth 550 nm, adjusted (sparse!)
]

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

# Final predictor column order for the model-ready table.
FEATURE_COLUMNS: list[str] = (
    ["lat", "lon"]
    + POWER_PARAMS
    + list(ERA5_SHORTNAME_MAP.values())
)

TARGET_COLUMN = "gfd_per_km2_per_year"

# --------------------------------------------------------------------------
# Sentinels
# --------------------------------------------------------------------------
POWER_FILL_VALUE = -999.0  # NASA POWER missing-data sentinel
