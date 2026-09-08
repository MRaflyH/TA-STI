"""One source of truth for the modelling half of the project.

Mirrors the role `gfd_data.config` plays for the pipeline: nothing else in this
package hard-codes a path, a column name, a hyperparameter or a seed. If you
find yourself typing a literal into `qnn.py` or `training.py`, it belongs here.

Every constant that a reader could reasonably have set differently carries the
DECISIONS.md ID that justifies it. When you change one, change the decision
record too -- a config that disagrees with DECISIONS.md is worse than either
one alone, because it looks authoritative.

The pipeline's config is imported rather than duplicated. There is ONE
environment and ONE repo, so adding the pipeline's src to sys.path is honest
and explicit; copying `EXCLUDE_COLUMNS` into this file would let the two drift
apart silently, which is exactly the failure D-02 exists to prevent.
"""

from __future__ import annotations

import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Paths, and the pipeline config
# --------------------------------------------------------------------------
# code/modelling/src/gfd_model/config.py -> repo root is five parents up.
REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELINE_SRC = REPO_ROOT / "code" / "pipeline" / "src"
MODELLING_ROOT = REPO_ROOT / "code" / "modelling"
RESULTS_DIR = MODELLING_ROOT / "results"        # NOT in git
FIGURES_DIR = MODELLING_ROOT / "figures"        # NOT in git

if str(PIPELINE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_SRC))

from gfd_data import config as pcfg  # noqa: E402

PROCESSED_DIR = pcfg.PROCESSED_DIR
TIME_COL = pcfg.TIME_COL
DOMAINS = ("tropis", "subtropis")


def table_path(domain: str) -> Path:
    """The parquet the pipeline wrote for this domain, at cfg.TIME_FREQ."""
    return PROCESSED_DIR / f"gfd_{domain}_{pcfg.freq_slug()}.parquet"


# --------------------------------------------------------------------------
# D-13. What the model predicts
# --------------------------------------------------------------------------
#   "hurdle"     -- stage 1 classifies occurrence, stage 2 regresses
#                   log1p(flash_count) on non-zero rows, and reporting
#                   combines them as P(occurrence) * E[count | occurrence].
#                   THE DEFAULT, and the reason is measured: at a 6-hour
#                   reporting window the target is still 85,40% / 91,35%
#                   zeros, so single-model count regression stays badly
#                   conditioned no matter how wide the window gets.
#   "count"      -- one regressor on every row. Kept runnable so the
#                   single-model comparison is available if a reviewer asks.
#   "occurrence" -- stage 1 alone. Useful for isolating classification
#                   behaviour without paying for stage 2.
TASK = "hurdle"

# D-03. Fit on log1p(flash_count); invert with expm1 and convert to GFD units
# for every reported number. `gfd_per_km2_per_year` is never a fitting target
# at hourly resolution -- it annualises a single hour, so one flash becomes
# ~8.766x its per-hour rate.
COUNT_COLUMN = "flash_count"
TARGET_TRANSFORM = "log1p"          # "log1p" | "anscombe" | "none"

# D-04. Reporting windows, in hours. The model always predicts ONE cell-hour;
# these aggregate predictions afterwards. Aggregation changes the REPORTING
# target only -- training stays hourly and stays 94,30% / 97,00% zeros.
#
# Measured zero share by window (build of 2026-09-06):
#     window   tropis   subtropis
#        1 h   94,30%      97,00%
#        3 h   90,09%      94,52%
#        6 h   85,40%      91,35%
#       24 h   64,63%      76,63%
REPORTING_WINDOWS_H = (1, 3, 6, 24)
PRIMARY_WINDOW_H = 6

# D-05. Spatial blocks, in cells per side. Tropis is 30 cells so 2 is about
# the limit; subtropis is 56 and 3 may be available -- confirm the lat x lon
# shape before enabling it.
SPATIAL_BLOCKS = (1, 2)

# --------------------------------------------------------------------------
# D-01, D-02. Features
# --------------------------------------------------------------------------
# 13 base predictors: lat, lon, six NASA POWER, five of six ERA5. KX is
# excluded from BOTH domains -- it is present in the tropis table and absent
# from subtropis, and the cross-domain experiment needs an identical feature
# set on both sides.
BASE_FEATURES: list[str] = [
    c for c in pcfg.FEATURE_COLUMNS if c not in pcfg.DROPPED_PREDICTORS
]

# The single most important feature you have, and it is not in BASE_FEATURES.
# Bins are UTC, so without a local-hour column a model learns the UTC-to-local
# offset separately per domain -- exactly the domain-specific quirk the
# cross-domain experiment is trying not to measure.
#
#   "cyclic" -- sin/cos of 2*pi*h/24. TWO columns, so two qubits. Hour 23 and
#               hour 0 are adjacent and a raw integer says they are 23 apart.
#   "raw"    -- one column, the integer hour. One qubit, wrong topology.
#   "none"   -- 13 columns. The ablation arm.
HOUR_ENCODING = "cyclic"            # -> 15 columns by default
HOUR_COLUMN = "hour_of_day_local"

# Never a predictor, at any setting. Comes from the pipeline so the two halves
# cannot disagree: the target and its deterministic functions, the five
# intensity statistics (D-08), `year` (every test row carries an unseen value
# under a chronological split), `coverage` (D-10), and the bookkeeping columns.
EXCLUDE_COLUMNS: list[str] = list(pcfg.EXCLUDE_COLUMNS)

# --------------------------------------------------------------------------
# D-06. Splits
# --------------------------------------------------------------------------
# Rolling origin: always train on the past, test on the future. Reported as
# mean +/- sd across folds.
#
# A single held-out year would make the headline number hostage to one year's
# climate state, and 2018-2024 is not climatically uniform -- it holds a
# triple-dip La Nina (2020-2023) and a strong El Nino peaking in the 2023-24
# boreal winter. It ALSO spans roughly half a solar cycle monotonically, which
# this record cannot resolve and does not attempt to; see D-06.
FOLDS: list[tuple[tuple[int, ...], int]] = [
    ((2018, 2019, 2020, 2021), 2022),
    ((2018, 2019, 2020, 2021, 2022), 2023),
    ((2018, 2019, 2020, 2021, 2022, 2023), 2024),
]

# Rolling origin for the headline comparison; fold 3 alone for the OFAT
# sweeps. State this asymmetry in Bab IV -- it is defensible only if declared.
SWEEP_FOLD = 2                      # index into FOLDS

# Fraction of the TRAINING years held out for early stopping. Taken as the
# latest slice of the training window, not at random: a random validation set
# leaks future rows into the stopping decision.
VAL_FRACTION = 0.15

# --------------------------------------------------------------------------
# D-07, D-11. Sampling
# --------------------------------------------------------------------------
# The training set may be reshaped. The test set may NOT -- it is the fold's
# held-out year, whole, at its natural class ratio. Rebalancing test rows
# produces a number evaluated against a world that does not exist.
TRAIN_ROWS = 3_000          # final run. Sweeps override to 1_000.
                            # 4.000 x 30 epochs was ~70% of the whole
                            # budget; 3.000 brings the set under a night.
STRATIFY_BY = ("lat", "lon", "month_of_year")

# The quantum layer costs ~7 ms per row, so evaluation is a first-order cost,
# not a rounding error. A full 236.610-row validation set costs 27 min PER
# EPOCH against 7 s of training.
#
# Validation drives early stopping only -- a few thousand rows estimate the
# loss well enough to decide when to stop.
MAX_VAL_ROWS = 1_000

# Test is sampled as WHOLE DAYS, evenly spaced across the test year. Not
# random rows: D-04 aggregates predictions into 6- and 24-hour windows, and
# random rows leave partial windows. Even spacing guarantees every month is
# represented. This preserves the natural class ratio, so D-07 is respected --
# it costs precision, not validity. None = the whole year.
TEST_DAYS: int | None = 30

# Zero-to-non-zero ratio in the TRAINING set. None keeps the natural ratio.
# The sweep runs (None, 0.75, 0.50), always scored on the natural-ratio test.
TRAIN_ZERO_RATIO: float | None = None

# D-11. Six tropis cells hold zero flashes across all seven years -- 20% of
# the grid, and probably an artificial rim where the snapped box reaches past
# the LDS network's useful range. Under a cell-holdout split they could land
# entirely in test and score perfectly for the wrong reason. Dropping them is
# defensible; it is off by default so the choice stays visible.
DROP_ALL_ZERO_CELLS = False

# --------------------------------------------------------------------------
# Scaling
# --------------------------------------------------------------------------
# ONE scaler for both models. D-09 says the only difference between the QNN
# and the NN must be the layer, so they cannot have different preprocessing.
# Min-max to [0, pi] is chosen because angle encoding needs a bounded range;
# an MLP is indifferent to it.
#
# Fitted on TRAIN ONLY, then applied to validation and test. Test values
# outside the training range are CLIPPED -- without clipping an out-of-range
# value maps past pi and the rotation aliases back onto a different angle,
# which is a silent wrong answer rather than an error.
FEATURE_RANGE = (0.0, 3.141592653589793)
CLIP_TEST_FEATURES = True

# The target is standardised (after the log1p of D-03) so both models see a
# comparable loss surface. Inverted before any reported number.
STANDARDISE_TARGET = True

# --------------------------------------------------------------------------
# D-09. Quantum model
# --------------------------------------------------------------------------
# One qubit per feature: 15 by default under HOUR_ENCODING = "cyclic".
QUBITS_PER_FEATURE = 1
FEATURE_REDUCTION: str | None = None    # None | "pca6" | "pca8" -- sweep axis

#   "z"  -- z_feature_map, product encoding, no entanglement. Shallow.
#   "zz" -- zz_feature_map, entangling. `full` at 15 qubits is 105 two-qubit
#           blocks and very deep; prefer "linear" or "circular".
FEATURE_MAP = "z"
FEATURE_MAP_REPS = 1
FEATURE_MAP_ENTANGLEMENT = "linear"

ANSATZ = "real_amplitudes"          # "real_amplitudes" | "efficient_su2"
ANSATZ_REPS = 2                     # sweep axis: 1..4
ANSATZ_ENTANGLEMENT = "linear"

# Readout. The stock template's global Z-on-every-qubit saturates badly past a
# handful of qubits and is a known barren-plateau accelerant; the proposal
# already commits to local cost functions as the mitigation.
#   "local_mean" -- mean of single-qubit Z. THE DEFAULT.
#   "single_z"   -- Z on qubit 0 only.
#   "global_z"   -- Z^{tensor n}. The stock template's choice, kept as the
#                   ablation arm that demonstrates why it was not taken.
OBSERVABLE = "local_mean"

# A Pauli expectation lives in [-1, 1]; a standardised log-count target does
# not. Without a trainable affine head the model is structurally incapable of
# reaching the target range, which reads as "the QNN does not learn". The
# stock tutorial omits this because its toy target is already in range.
OUTPUT_AFFINE_HEAD = True

# MEASURED 2026-09-06, 13 qubits / 39 weights / StatevectorEstimator, minutes
# per 10.000-row epoch:
#     ParamShift  40,9    LinComb  104,2    SPSA  1,2
#
# LinComb is SLOWER than ParamShift here, not faster: it builds a
# controlled-gate circuit per parameter and circuit construction dominates in
# the reference primitive. Exact gradients at ~41 min/epoch cannot carry a
# sweep, so SPSA explores and exact gradients confirm the finals. Record this
# split in Bab III rather than letting it surface in the results.
#
# RE-BENCHMARK AGAINST AER before accepting these. qiskit-aer batches through
# compiled C++ instead of a Python loop and may move ParamShift back into
# range, which would simplify the whole design.
# MEASURED, 15 qubits / 45 weights / reps=2. ms per sample -> hours for the
# 36-run final set:
#   Qiskit Statevector + ParamShift   438,70  ->  526,5 h
#   Qiskit Aer         + ParamShift  ~305     -> ~366   h
#   Qiskit Aer         + SPSA k=1      12,01  ->   14,4 h   gradient unusable
#   PennyLane lightning + adjoint       6,97  ->    8,4 h   <-- chosen
#
# qiskit-machine-learning 0.9.1 has no adjoint gradient; parameter shift needs
# 2 circuits per weight (90 per sample), adjoint needs one backward pass for
# all 45. A scaling difference, not a constant factor. See DECISIONS.md D-28.
DEVICE = "lightning.qubit"      # "lightning.qubit" | "default.qubit"
DIFF_METHOD = "adjoint"         # "adjoint" | "backprop" | "parameter-shift"
SHOTS: int | None = None        # None = exact. Shot noise is a sweep axis.

# --------------------------------------------------------------------------
# D-09. Classical models -- the comparison ladder
# --------------------------------------------------------------------------
# Five entries reported together. The parameter-matched NN alone is not
# enough: it is deliberately crippled to the QNN's weight count and a reviewer
# will say so. The unconstrained NN is the ceiling the QNN is really measured
# against, and the two trivial baselines are the floor without which no R2 on
# a 94-97% zero target means anything.
MODEL_LADDER = (
    "baseline_trivial",     # predict the training mean / the majority class
    "ridge",                # linear reference
    "nn_matched",           # hidden width set to match the QNN weight count
    "qnn",
    "nn_large",
)
NN_LARGE_HIDDEN = (64, 64)
NN_MATCHED_HIDDEN: tuple[int, ...] | None = None   # None -> solve for parity
NN_ACTIVATION = "tanh"      # bounded, like the quantum readout

# --------------------------------------------------------------------------
# Training -- ONE loop, both models
# --------------------------------------------------------------------------
# Same optimizer, batch size, loss, early stopping and seed handling for the
# QNN and the NN. This is what makes the comparison mean anything; if the two
# were trained differently, "the NN was trained differently" is the first
# objection at sidang.
OPTIMIZER = "adam"
LEARNING_RATE = 0.01
BATCH_SIZE = 64
MAX_EPOCHS = 30                 # 50 -> 14,4 h; 30 -> 8,7 h. Early stopping
EARLY_STOPPING_PATIENCE = 6     # usually ends sooner, but budget the ceiling
SEEDS = (0, 1, 2)           # 5 would not fit overnight; report mean +/- sd of 3

# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------
# Five scenarios, THREE trainings. The cross-domain arms reuse a fitted model
# rather than fitting a new one, which is the whole point of the experiment
# and also the largest compute saving available.
SCENARIOS = {
    "tropis_in":      ("tropis", "tropis"),
    "subtropis_in":   ("subtropis", "subtropis"),
    "tropis_to_sub":  ("tropis", "subtropis"),
    "sub_to_tropis":  ("subtropis", "tropis"),
    "pooled":         ("pooled", "both"),
}

# --------------------------------------------------------------------------
# One-factor-at-a-time sweeps, around the defaults above
# --------------------------------------------------------------------------
# A full factorial over these is not affordable and would not be more
# informative. The training-size ladder is the axis the scientific argument
# rests on: QNNs are claimed to be sample-efficient rather than asymptotically
# better, and "does the gap close at small n" is a question this compute
# budget can actually answer.
SWEEPS = {
    "train_rows":       (500, 1_000, 3_000),   # 100k rung dropped, see below
    "hour_encoding":    ("none", "raw", "cyclic"),         # 13 / 14 / 15
    "ansatz_reps":      (1, 2, 3, 4),
    "feature_map":      ("z", "zz"),
    "observable":       ("single_z", "local_mean", "global_z"),
    "train_zero_ratio": (None, 0.75, 0.50),
    "shots":            (None, 4096, 1024),
    "feature_reduction": (None, "pca8", "pca6"),
}

# Two-tier compute budget, D-06 and D-07. Sweeps must be interactive; the
# final run gets one night. 36 QNN runs (2 stages x 2 domains x 3 folds x
# 3 seeds) at ~18 min is ~11 h. Five seeds or 20.000 rows would not fit.
#
# The 100.000-row rung is dropped from the learning curve: at ~450 min per
# point it alone exceeds the whole budget. If the curve is still climbing at
# 4.000, run 100.000 ONCE at one seed at the end and report it as a single
# point with that caveat.

MODEL_LADDER = (
    "baseline_trivial", "ridge", "nn_matched", "qnn", "nn_large",
    "nn_full",          # nn_large on EVERY row, not the QNN's subsample.
                        # Breaks parity on purpose; reported separately.
)

RANDOM_SEED = pcfg.RANDOM_SEED
