"""The column contract. Nothing else in the package defines one.

    CANDIDATES    what may be screened -- everything acquired
    RAW_TEMPORAL  raw time, for selection/ to encode as it chooses
    EXCLUDE       never a predictor
    MODELLED      what survived selection, written by selection/

The built table is wider than any of these. Read lengths from here or from the
table; nothing counts features.

A modelled name need not be in `CANDIDATES`. `selection/` derives features
under D-21 step 2 -- the temporal encodings of D-20, `cloud_water`,
`dewpoint_depression` -- and those are legitimate predictors that no table
column carries. What a modelled name may never be is a member of `EXCLUDE`, or
a raw temporal column used in its raw form.
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
# Three sets per stage, because three decisions shaped this file's contents:
#
#   D-25  two stages -- occurrence and count -- each with its own set.
#   D-24  15 features wide, equal across domains within a stage.
#   D-27  the within-domain models use per-domain sets; the transfer arms use
#         one shared set, so a model trained on one domain can read the other's
#         feature vector at all.
#
# So modelled.json has the shape
#
#   {"within": {"tropis":    {"occurrence": [...], "count": [...]},
#               "subtropis": {"occurrence": [...], "count": [...]}},
#    "shared":               {"occurrence": [...], "count": [...]}}
#
# selection/ writes it, models/ and training/ read it, nothing counts it.
MODELLED_PATH = Path(__file__).parent / "modelled.json"

STAGES = ("occurrence", "count")


def _load() -> dict:
    if not MODELLED_PATH.exists():
        raise FileNotFoundError(
            f"{MODELLED_PATH} does not exist -- selection hasn't written it. "
            f"Run gfd.selection.ablate first."
        )
    return json.loads(MODELLED_PATH.read_text(encoding="utf-8"))


def _checked(names: list[str]) -> list[str]:
    assert_no_leakage(names)
    raw = [n for n in names if n in RAW_TEMPORAL]
    if raw:
        raise ValueError(
            f"{raw} are raw temporal columns and cannot be predictors in this "
            f"form -- an integer hour puts 23:00 and 00:00 23 apart. "
            f"selection/ encodes them (D-13, D-20)."
        )
    return names


def modelled(domain: str, stage: str) -> list[str]:
    """The per-domain set for one stage. The within-domain models read this.

    Raises rather than falling back to CANDIDATES: a fallback would let a model
    train on the unfiltered set and report it as the selected one.
    """
    if stage not in STAGES:
        raise KeyError(f"unknown stage {stage!r}; have {STAGES}")
    within = _load()["within"]
    if domain not in within:
        raise KeyError(f"{MODELLED_PATH} has no set for {domain!r}; "
                       f"it has {sorted(within)}.")
    if stage not in within[domain]:
        raise KeyError(f"{MODELLED_PATH} has no {stage!r} set for {domain!r}.")

    # D-24: equal width across domains, within a stage. The two stages need not
    # match each other -- D-25 -- because they are different circuits answering
    # different questions.
    widths = {d: len(v[stage]) for d, v in within.items() if stage in v}
    if len(set(widths.values())) > 1:
        raise ValueError(
            f"D-24 requires equal width across domains for the {stage!r} stage, "
            f"got {widths}. Unequal widths mean unequal qubit counts, and the "
            f"domain comparison then confounds difficulty with model size."
        )
    return _checked(within[domain][stage])


def modelled_shared(stage: str) -> list[str]:
    """The shared set for one stage. The transfer arms read this (D-27).

    Both directions and both shared-set baselines use the same list in the same
    order. A trained circuit is N rotations bound to N named variables in a
    fixed order, so two models cannot exchange feature vectors unless they were
    trained on the same list.
    """
    if stage not in STAGES:
        raise KeyError(f"unknown stage {stage!r}; have {STAGES}")
    shared = _load()["shared"]
    if stage not in shared:
        raise KeyError(f"{MODELLED_PATH} has no shared {stage!r} set.")
    names = shared[stage]

    # D-27: lat and lon measure 0,0000 effective resolution across domains --
    # the boxes do not overlap, so every target row clips to one bound and the
    # qubit arrives as a constant. Dead qubits would make a poor transfer score
    # unattributable: domains differing and a frozen circuit look identical.
    bad = [n for n in names if n in SPATIAL]
    if bad:
        raise ValueError(
            f"{bad} are in the shared transfer set. D-27 excludes them: they "
            f"carry no information across domains and a constant qubit makes a "
            f"poor transfer result impossible to attribute."
        )
    return _checked(names)


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
