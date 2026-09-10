"""The column contract. Nothing else in the package defines one.

    EXCLUDE     never a predictor
    CANDIDATES  everything acquired, frozen at the raw freeze
    MODELLED    what survived the ablation, written by selection/

The built table is wider than any of these. Read lengths from here or from the
table; nothing counts features.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import config as cfg

# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------
# Declared here rather than imported from era5.py / power.py: those own "what
# to request", this owns "what may be a predictor". check_against_table() is
# what keeps them honest, by checking against the real table.

SPATIAL = ["lat", "lon"]

# AOD_55_ADJ dropped, D-5. Its two files are still in data/raw/power/.
POWER = [
    "PS",            # surface pressure, kPa
    "PRECTOTCORR",   # precipitation, mm/hour
    "T2M",           # 2 m air temperature, degC
    "RH2M",          # 2 m relative humidity, %
    "WS2M",          # 2 m wind speed, m/s
]

ERA5 = ["CAPE", "KX", "TCIW", "TCLW", "VIIWD", "VILWD"]

# Derived from the time key by build.py.
#
# Still undecided which of these are candidates. Seasonal phase is inverted
# between the two domains, so month/day may inject a domain artefact into the
# cross-domain number. hour_of_day_local is the one with a clear physical
# reading.
CALENDAR = ["month_of_year", "day_of_year", "hour_of_day_utc", "hour_of_day_local"]

CANDIDATES = SPATIAL + POWER + ERA5 + CALENDAR

# --------------------------------------------------------------------------
# Never a predictor
# --------------------------------------------------------------------------
TARGET_FAMILY = [cfg.TARGET, "gfd_per_km2_per_day", cfg.TARGET_REPORTING]

# Same strikes as the target, so using them as predictors is leakage. NaN
# wherever flash_count is 0 -- the mean intensity of no strikes is undefined,
# not zero. Kept in the table as a second target.
INTENSITY = [
    "mean_peak_current_ka",
    "positive_share",
    "median_abs_peak_current_ka",
    "max_abs_peak_current_ka",
    "p95_abs_peak_current_ka",
]

BOOKKEEPING = [
    "domain",
    cfg.TIME_COL,
    "month",
    "year",           # chronological split means every test row is unseen
    "days_in_month",
    "observed_days",
    "coverage",       # correlates with the target through lightning itself
    "area_km2",
    "period_days",
]

EXCLUDE = TARGET_FAMILY + INTENSITY + BOOKKEEPING

# --------------------------------------------------------------------------
# Modelled
# --------------------------------------------------------------------------
MODELLED_PATH = Path(__file__).parent / "modelled.json"


def modelled() -> list[str]:
    """Written by selection/ after the ablation. Doesn't exist yet.

    Raises rather than falling back to CANDIDATES: a fallback would let a model
    train on the unfiltered set and report it as the selected one.
    """
    if not MODELLED_PATH.exists():
        raise FileNotFoundError(
            f"{MODELLED_PATH} does not exist -- the ablation hasn't run. "
            f"Run selection/ first."
        )
    names = json.loads(MODELLED_PATH.read_text(encoding="utf-8"))
    assert_no_leakage(names)
    return names


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
def assert_no_leakage(names: list[str]) -> None:
    """Raises, never warns, never bypassed."""
    bad = [n for n in names if n in EXCLUDE]
    if bad:
        raise ValueError(
            f"leakage: {bad} are in EXCLUDE and cannot be predictors. If one of "
            f"them should be, change EXCLUDE -- don't filter it at the call site."
        )


def check_against_table(columns) -> None:
    """Compare a built table against the contract. Prints; doesn't raise."""
    have = set(columns)
    missing = [c for c in CANDIDATES if c not in have]
    unclassified = [c for c in columns if c not in CANDIDATES and c not in EXCLUDE]

    if missing:
        print(f"[features] candidates not in the table: {missing}")
    if unclassified:
        print(
            f"[features] in neither list: {unclassified} -- classify them, or a "
            f"downstream 'everything numeric' selection picks them up on its own"
        )
    if not missing and not unclassified:
        print(f"[features] table matches the contract ({len(CANDIDATES)} candidates)")
