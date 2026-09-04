"""Configuration for the QNN / classical-NN comparison.

Deliberately separate from ``gfd_data.config``: that module describes how the
dataset is *built*, this one how it is *modelled*. The build config is frozen
once a table is written; this one changes every experiment.

F-05 asks that an experiment be replayable. ``experiment.py`` snapshots this
whole module into the results JSON, together with the ``.meta.json`` of the
table it read, so the regridding and temporal-aggregation choices travel with
the model hyperparameters rather than underneath them.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]          # modelling/
# The pipeline writes here and this package only reads. Override with
# GFD_DATA_DIR to point at synthetic tables during development without
# editing code — and to make it obvious which you were reading.
DATA_DIR = Path(os.environ.get(
    "GFD_DATA_DIR", PROJECT_ROOT.parent / "dataset-pipeline" / "data"))
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Reproducibility (NF-02)
# --------------------------------------------------------------------------
# Same seed as the build, so "seed 18222067" means one thing across the project.
RANDOM_SEED = 18222067

# --------------------------------------------------------------------------
# Which table to model
# --------------------------------------------------------------------------
# "monthly" / "daily" / "hourly" -- must match a file the build actually wrote:
#   data/processed/gfd_<domain>_<slug>.parquet
#
# DEFAULT IS MONTHLY ON PURPOSE. See the header of experiment.py: the hourly
# table is a zero-inflated count process, not a density, and it is also ~3
# orders of magnitude too many rows to train a simulated QNN on. Monthly is
# also the only resolution comparable with the predecessor study.
FREQ_SLUG = "monthly"

# Target column. gfd_per_km2_per_year is the reporting unit; at sub-monthly
# resolution the build prints a warning telling you to use flash_count instead.
TARGET_COLUMN = "gfd_per_km2_per_year"

# --------------------------------------------------------------------------
# Feature handling
# --------------------------------------------------------------------------
# Columns never offered to the model. `domain` would be a free giveaway in the
# cross-domain experiment; the coverage columns are build bookkeeping;
# flash_count and the per-day GFD are the target in disguise -- LEAKAGE if left
# in, since gfd_per_km2_per_year is a deterministic function of both.
EXCLUDE_COLUMNS: tuple[str, ...] = (
    "domain", "time", "month", "observed_days", "coverage", "period_days",
    "area_km2", "flash_count", "gfd_per_km2_per_day", "gfd_per_km2_per_year",
    # Derived from the strikes themselves, so also target-derived:
    "mean_peak_current_ka", "positive_share",
)

# Number of qubits == number of PCA components, following the predecessor
# study so the two are comparable. This is HIS dimensionality answer adopted as
# a baseline, not a neutral default -- see the note in data.py.
N_QUBITS = 4

# Set False to feed raw (scaled) features straight in, with n_qubits then fixed
# by the feature count. Use to test whether PCA is helping or hurting.
USE_PCA = True

# Yeo-Johnson on the predictors, as the predecessor did. Applies to both models
# identically, so it cannot advantage either.
USE_POWER_TRANSFORM = True

# --------------------------------------------------------------------------
# Split
# --------------------------------------------------------------------------
# "time"  -- last TEST_FRACTION of periods are the test set, all cells.
#            Blocks the leak the project notes call out: a random split puts
#            adjacent months of the SAME grid cell on both sides, and spatial
#            plus temporal autocorrelation then leaks the answer across.
# "cell"  -- hold out whole grid cells instead. Answers a different question
#            ("can it predict an unseen place?"). Worth running as a second
#            experiment; not the default.
# "random"-- provided only so the optimistic number can be reported next to
#            the honest one. Do not report it alone.
SPLIT_STRATEGY = "time"
TEST_FRACTION = 0.25
VAL_FRACTION = 0.0  # carved out of train, chronologically. 0.0 = no val set.

# --------------------------------------------------------------------------
# Target scaling
# --------------------------------------------------------------------------
# A QNN's output is the expectation value of an observable and therefore lives
# in [-1, 1]. The target must be mapped into that range or the model cannot
# reach it -- this is a hard constraint of the architecture, not a preference.
# The SAME transform is applied to the classical NN so the comparison is like
# for like, and metrics are reported in BOTH scaled and native GFD units.
TARGET_RANGE = (-1.0, 1.0)
# log1p before scaling. GFD is strongly right-skewed and zero-inflated; without
# this the scaled target piles up near -1 and the model learns the mean.
TARGET_LOG1P = True

# --------------------------------------------------------------------------
# QNN architecture -- stock Qiskit circuit-library components
# --------------------------------------------------------------------------
# Both are unmodified qiskit.circuit.library functions. Deliberate: the
# variable under study is the climate domain, not the circuit, so a
# well-characterised standard circuit is the right control. Every value below
# is a documented argument of the corresponding library function.
FEATURE_MAP = "zz"          # "zz" -> zz_feature_map, "z" -> z_feature_map
FEATURE_MAP_REPS = 1        # predecessor found extra reps degraded performance
FEATURE_MAP_ENTANGLEMENT = "linear"

ANSATZ = "real_amplitudes"  # or "efficient_su2"
ANSATZ_REPS = 2
ANSATZ_ENTANGLEMENT = "linear"

# Shallow circuits + few qubits is the agreed barren-plateau mitigation.
# ansatz reps * num_qubits drives the parameter count; keep an eye on it.

# --------------------------------------------------------------------------
# QNN training
# --------------------------------------------------------------------------
OPTIMIZER = "cobyla"        # "cobyla" (gradient-free, cheap) or "lbfgsb"
MAX_ITER = 150

# "statevector" -- exact, noiseless, no shots. Fastest and fully deterministic.
#                  The right default while the science is being settled.
# "aer"         -- shot-based sampling on AerSimulator. Slower; use to show the
#                  result survives finite sampling before claiming anything
#                  about hardware.
ESTIMATOR_BACKEND = "statevector"
SHOTS = 1024                # ESTIMATOR_BACKEND == "aer" only
OPTIMIZATION_LEVEL = 1      # transpiler preset level for the ISA circuit

# --------------------------------------------------------------------------
# Classical NN -- matched to the QNN, not tuned to win
# --------------------------------------------------------------------------
# The point of the baseline is a fair reference, so the hidden layer is sized
# to give the MLP a parameter count in the same ballpark as the ansatz rather
# than the largest network that fits. MATCH_PARAM_COUNT=True computes the
# hidden width from the QNN's weight count at run time.
MATCH_PARAM_COUNT = True
NN_HIDDEN_SIZES = (8,)      # used when MATCH_PARAM_COUNT is False
NN_MAX_ITER = 2000
NN_ACTIVATION = "tanh"      # bounded like the expectation value it is matched against
NN_ALPHA = 1e-3             # L2, sklearn default is 1e-4

# --------------------------------------------------------------------------
# Smoke mode
# --------------------------------------------------------------------------
# Applied by experiment.py --smoke. Everything shrinks at once so a full
# end-to-end pass takes seconds and every code path still executes.
SMOKE = dict(
    N_QUBITS=2,
    MAX_ITER=12,
    ANSATZ_REPS=1,
    NN_MAX_ITER=200,
    MAX_ROWS=200,           # subsample AFTER the split, both sides
)
