"""Paths, domains, the grid, the time key, the target.

Only things two subpackages could silently disagree about. Request shapes and
variable lists live next to the code that uses them.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
# code/gfd/config.py -> code/gfd -> code -> repo root. Nothing here is relative
# to the working directory, which is what lets commands run from anywhere.
PROJECT_ROOT = Path(os.environ.get("GFD_REPO_ROOT", Path(__file__).resolve().parents[2]))

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_PLN_DIR = RAW_DIR / "pln"
RAW_MERLIN_DIR = RAW_DIR / "merlin"
RAW_POWER_DIR = RAW_DIR / "power"
RAW_ERA5_DIR = RAW_DIR / "era5"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

# Never mkdir raw/. If the root resolves wrong, creating it turns a wrong path
# into "no files found -- run fetch first", which is a much harder bug to see.
if not RAW_DIR.is_dir():
    raise RuntimeError(
        f"{RAW_DIR} does not exist.\n"
        f"PROJECT_ROOT resolved to {PROJECT_ROOT}. If that's wrong, set "
        f"GFD_REPO_ROOT. If it's right, the raw data is missing."
    )

for _d in (INTERIM_DIR, PROCESSED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 18222067

# --------------------------------------------------------------------------
# Grid and time
# --------------------------------------------------------------------------
GRID_DEG = 0.5

TIME_FREQ = "h"
TIME_COL = "time"
PERIOD_DAYS = 1.0 / 24.0

# Not a resolution setting. NASA POWER publishes some parameters coarser than
# hourly and those get broadcast; this is only for comparing those.
FREQ_ORDER = {"h": 0, "D": 1, "M": 2}

# Off. `coverage` rides on every row and is reported, never acted on.
MIN_COVERAGE = 0.0

# --------------------------------------------------------------------------
# Target
# --------------------------------------------------------------------------
# Fit on log1p, invert with expm1 before any aggregation.
TARGET = "flash_count"

# The same count in GFD units, for reporting only. Annualising a single hour
# turns one flash into ~8766x its per-hour rate, so don't fit on this.
TARGET_REPORTING = "gfd_per_km2_per_year"


# --------------------------------------------------------------------------
# Domains
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Domain:
    name: str
    label: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    year_start: int
    year_end: int
    tz: str = "UTC"          # clock the raw strike timestamps are in
    local_tz: str | None = None   # clock the solar day runs on, for hour_of_day_local

    @property
    def solar_tz(self) -> str:
        return self.local_tz or self.tz

    def snapped_bbox(self, pad: float = 0.0) -> tuple[float, float, float, float]:
        """Box expanded outward to whole GRID_DEG boundaries."""
        g = GRID_DEG
        return (
            math.floor((self.lat_min - pad) / g) * g,
            math.ceil((self.lat_max + pad) / g) * g,
            math.floor((self.lon_min - pad) / g) * g,
            math.ceil((self.lon_max + pad) / g) * g,
        )


TROPIS = Domain(
    name="tropis",
    label="Jawa Barat (PLN Puslitbang LDS)",
    lat_min=-8.0, lat_max=-5.5,
    lon_min=106.0, lon_max=109.0,
    year_start=2018, year_end=2024,
    # The export doesn't say. Confirmed by the diurnal check -- run
    # lightning.check_diurnal after any change to raw/pln.
    tz="Asia/Jakarta",
)

SUBTROPIS = Domain(
    name="subtropis",
    label="Florida (NASA MERLIN)",
    lat_min=26.5, lat_max=30.5,
    lon_min=-82.0, lon_max=-78.5,
    year_start=2018, year_end=2024,
    tz="UTC",
    # UTC-5, EST all year. POSIX inverts the sign. Not America/New_York: DST
    # would make the diurnal feature mean different things in each domain.
    local_tz="Etc/GMT+5",
)

DOMAINS = {d.name: d for d in (TROPIS, SUBTROPIS)}

FREQ_NOUN = {"h": "hour", "D": "day", "M": "month"}
FREQ_SLUG = {"h": "hourly", "D": "daily", "M": "monthly"}


def coarser(a: str, b: str) -> str:
    return a if FREQ_ORDER[a] >= FREQ_ORDER[b] else b
