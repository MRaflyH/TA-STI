"""The column contract. Nothing else in the package defines one.

    CANDIDATES    what may be screened -- everything acquired
    RAW_TEMPORAL  raw time, for selection/ to encode as it chooses
    EXCLUDE       never a predictor
    MODELLED      what survived the ablation, written by selection/

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
    "PRECTOTCORR",   # precipitation, mm/day -- D-10. NASA POWER's own unit.
    "T2M",           # 2 m air temperature, degC
    "RH2M",          # 2 m relative humidity, %
    "WS2M",          # 2 m wind speed, m/s
]

ERA5 = [
    "CAPE", "KX", "TCIW", "TCLW", "VIIWD", "VILWD",
    # Tier 1, acquired 2026-09-13. TOTALX and KX both needed a
    # single-variable request for the subtropis box.
    "VIMDF", "CRR", "TOTALX", "CIN", "CBH", "TCWV", "D2M",
]

CANDIDATES = SPATIAL + POWER + ERA5

# Raw time, emitted by build.py. Neither candidates nor excluded: no model uses
# them in this form -- an integer hour puts 23:00 and 00:00 23 apart -- but
# they are the material selection/ builds its temporal encodings from, and it
# owns that choice. Listed here only so check_against_table can tell them from
# a column nobody has looked at.
RAW_TEMPORAL = [
    "year",
    "month_of_year",
    "day_of_year",
    "hour_of_day_utc",
    "hour_of_day_local",
]

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
# D-11: one list per domain, of equal length. selection/ writes this file.
MODELLED_PATH = Path(__file__).parent / "modelled.json"


def modelled(domain: str) -> list[str]:
    """Written by selection/ after the ablation. Doesn't exist yet.

    Raises rather than falling back to CANDIDATES: a fallback would let a model
    train on the unfiltered set and report it as the selected one.
    """
    if not MODELLED_PATH.exists():
        raise FileNotFoundError(
            f"{MODELLED_PATH} does not exist -- the ablation hasn't run. "
            f"Run selection/ first."
        )
    sets = json.loads(MODELLED_PATH.read_text(encoding="utf-8"))
    if domain not in sets:
        raise KeyError(
            f"{MODELLED_PATH} has no set for {domain!r}; it has {sorted(sets)}."
        )
    names = sets[domain]

    widths = {d: len(v) for d, v in sets.items()}
    if len(set(widths.values())) > 1:
        raise ValueError(
            f"D-11 requires equal width across domains, got {widths}. Unequal "
            f"widths mean unequal qubit counts, and the domain comparison then "
            f"confounds difficulty with model size."
        )

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
    known = set(CANDIDATES) | set(EXCLUDE) | set(RAW_TEMPORAL)
    unclassified = [c for c in columns if c not in known]

    if missing:
        print(f"[features] candidates not in the table: {missing}")
    if unclassified:
        print(
            f"[features] in neither list: {unclassified} -- classify them, or a "
            f"downstream 'everything numeric' selection picks them up on its own"
        )
    if not missing and not unclassified:
        print(f"[features] table matches the contract ({len(CANDIDATES)} candidates)")
