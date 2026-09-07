"""Load the processed tables and turn them into (X, y) the models can train on.

Everything that could silently poison a result lives here, so this is the file
to read sceptically:

  * feature selection, which is where leakage enters (D-02),
  * fold boundaries, which is where the future leaks into the past (D-06),
  * subsampling, which may touch training rows and must never touch test rows
    (D-07),
  * scaling, which must be fitted on training rows alone.

Each of those is checked at runtime rather than trusted. `assert_no_leakage`
raises instead of warning, because a warning in a sweep of two hundred runs is
a line of output nobody reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as mcfg


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def load(domain: str, columns: list[str] | None = None) -> pd.DataFrame:
    """Read one domain's processed table.

    The time key is converted from period to timestamp on the way in. Every
    downstream operation -- fold boundaries, window aggregation, the hour
    encoding -- wants a timestamp, and converting once here means no other
    function has to remember to.
    """
    path = mcfg.table_path(domain)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Run `python -m gfd_data.build` from "
            f"code/pipeline/src first."
        )

    df = pd.read_parquet(path, columns=columns)
    if isinstance(df[mcfg.TIME_COL].dtype, pd.PeriodDtype):
        df[mcfg.TIME_COL] = df[mcfg.TIME_COL].dt.to_timestamp()

    if mcfg.DROP_ALL_ZERO_CELLS:
        # D-11. Six tropis cells hold zero flashes across all seven years.
        totals = df.groupby(["lat", "lon"])[mcfg.COUNT_COLUMN].transform("sum")
        dropped = int((totals == 0).sum())
        df = df.loc[totals > 0].copy()
        if dropped:
            print(f"[{domain}] dropped {dropped:,} rows in all-zero cells")

    return df


def load_pooled() -> pd.DataFrame:
    """Both domains stacked, for the `pooled` scenario.

    `domain` is in EXCLUDE_COLUMNS, so the column survives the concat for
    bookkeeping but can never reach the feature matrix -- it would be a free
    giveaway in exactly the comparison this scenario exists to make.
    """
    return pd.concat([load(d) for d in mcfg.DOMAINS], ignore_index=True)


# --------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------
def feature_names(df: pd.DataFrame) -> list[str]:
    """The feature columns for this table, in a fixed order.

    Fixed order matters: the cross-domain scenarios apply a model fitted on
    one table to another, and column order is the only thing tying a weight to
    a physical quantity. Sorting or set operations anywhere in this path would
    reintroduce the bug silently.
    """
    names = [c for c in mcfg.BASE_FEATURES if c in df.columns]

    missing = [c for c in mcfg.BASE_FEATURES if c not in df.columns]
    if missing:
        raise ValueError(
            f"base features absent from the table: {missing}. If this is KX, "
            f"it should already have been removed by DROPPED_PREDICTORS -- "
            f"check gfd_data.config."
        )

    if mcfg.HOUR_ENCODING == "cyclic":
        names += ["hour_sin", "hour_cos"]
    elif mcfg.HOUR_ENCODING == "raw":
        names += [mcfg.HOUR_COLUMN]
    elif mcfg.HOUR_ENCODING != "none":
        raise ValueError(f"unknown HOUR_ENCODING: {mcfg.HOUR_ENCODING!r}")

    return names


def add_hour_encoding(df: pd.DataFrame) -> pd.DataFrame:
    """Materialise the cyclic hour columns, if the config asks for them.

    Hour 23 and hour 0 are adjacent; a raw integer asserts they are 23 apart.
    Two columns costs two qubits, which is why 13/14/15 is a sweep axis rather
    than a settled default (D-02).
    """
    if mcfg.HOUR_ENCODING != "cyclic":
        return df

    if mcfg.HOUR_COLUMN not in df.columns:
        raise ValueError(
            f"{mcfg.HOUR_COLUMN} is not in the table. It only exists at "
            f"hourly resolution -- check gfd_data.config.TIME_FREQ."
        )

    theta = 2.0 * np.pi * df[mcfg.HOUR_COLUMN].to_numpy() / 24.0
    return df.assign(hour_sin=np.sin(theta), hour_cos=np.cos(theta))


def assert_no_leakage(names: list[str]) -> None:
    """Raise if any feature is one the target can be reconstructed from.

    Raises rather than warns. In a sweep of two hundred runs a warning is a
    line nobody reads, and the failure mode is a result that looks excellent
    and means nothing.
    """
    banned = set(mcfg.EXCLUDE_COLUMNS)
    caught = sorted(set(names) & banned)
    if caught:
        raise ValueError(
            f"leakage: {caught} are in EXCLUDE_COLUMNS but reached the "
            f"feature matrix. See DECISIONS.md D-02 and D-08."
        )
    if not names:
        raise ValueError("no features selected")


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------
def make_target(df: pd.DataFrame, stage: str) -> np.ndarray:
    """The target vector for one stage of the task (D-03, D-13).

    stage="occurrence" -> binary, did any lightning occur in this cell-hour
    stage="count"      -> log1p(flash_count), on the rows given
    """
    counts = df[mcfg.COUNT_COLUMN].to_numpy()

    if stage == "occurrence":
        return (counts > 0).astype(np.float64)

    if stage != "count":
        raise ValueError(f"unknown stage: {stage!r}")

    if mcfg.TARGET_TRANSFORM == "log1p":
        return np.log1p(counts)
    if mcfg.TARGET_TRANSFORM == "anscombe":
        return 2.0 * np.sqrt(counts + 3.0 / 8.0)
    if mcfg.TARGET_TRANSFORM == "none":
        return counts.astype(np.float64)
    raise ValueError(f"unknown TARGET_TRANSFORM: {mcfg.TARGET_TRANSFORM!r}")


def invert_target(y: np.ndarray) -> np.ndarray:
    """Back to raw counts.

    NEVER aggregate before calling this. Summing log1p values and inverting
    once gives a geometric mean, not a total -- a silent wrong answer that
    D-03 exists to prevent. expm1 first, then sum.
    """
    if mcfg.TARGET_TRANSFORM == "log1p":
        return np.expm1(y)
    if mcfg.TARGET_TRANSFORM == "anscombe":
        return np.square(y / 2.0) - 3.0 / 8.0
    return y


def stage_rows(df: pd.DataFrame, stage: str) -> pd.DataFrame:
    """The rows a stage trains on.

    Stage 2 sees non-zero rows only -- 104.955 tropis and 99.273 subtropis.
    That is the hurdle model's structure and it is also why stage 2 is
    QNN-tractable without aggressive subsampling (D-07, D-13).
    """
    if stage == "count" and mcfg.TASK == "hurdle":
        return df.loc[df[mcfg.COUNT_COLUMN] > 0]
    return df


# --------------------------------------------------------------------------
# D-06. Folds
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Fold:
    index: int
    train_years: tuple[int, ...]
    test_year: int

    @property
    def name(self) -> str:
        return f"fold{self.index}_{self.train_years[0]}-" \
               f"{self.train_years[-1]}_test{self.test_year}"


def folds() -> list[Fold]:
    return [Fold(i, tr, te) for i, (tr, te) in enumerate(mcfg.FOLDS)]


def split(df: pd.DataFrame, fold: Fold) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(train, validation, test) for one fold.

    Validation is the LATEST slice of the training window, not a random
    sample. A random validation set would let rows from 2021 inform the
    stopping decision for a model that will be judged on 2022 -- the same
    leak the chronological split exists to prevent, reintroduced one level
    down.

    Rows outside both windows are dropped rather than silently swept into
    training: fold 1 tests on 2022 and must not train on 2023-2024.
    """
    year = df[mcfg.TIME_COL].dt.year
    train_all = df.loc[year.isin(fold.train_years)]
    test = df.loc[year == fold.test_year]

    if train_all.empty or test.empty:
        raise ValueError(
            f"{fold.name}: train={len(train_all):,} test={len(test):,}. "
            f"Check that the table covers these years."
        )

    cut = train_all[mcfg.TIME_COL].quantile(1.0 - mcfg.VAL_FRACTION)
    train = train_all.loc[train_all[mcfg.TIME_COL] <= cut]
    val = train_all.loc[train_all[mcfg.TIME_COL] > cut]

    return train, val, test


# --------------------------------------------------------------------------
# D-07. Subsampling -- training rows only
# --------------------------------------------------------------------------
def subsample(
    df: pd.DataFrame,
    n: int | None,
    rng: np.random.Generator,
    zero_ratio: float | None = None,
) -> pd.DataFrame:
    """Shrink a TRAINING set. Never call this on test rows.

    Stratified across cell and calendar month so a subsample cannot come out
    all Jakarta and all December -- an unstratified draw from a table with a
    strong seasonal cycle and a 20% dead rim is not a miniature of the whole.

    `zero_ratio` sets the share of zero-target rows in the result. None keeps
    the natural ratio, which is the default: a model trained at 50/50 believes
    lightning is roughly twenty times more common than it is, and every count
    it produces is inflated. That is a legitimate thing to measure (it is a
    sweep axis) but not a legitimate default.
    """
    if n is None or n >= len(df):
        return df

    if zero_ratio is None:
        return _stratified_draw(df, n, rng)

    is_zero = df[mcfg.COUNT_COLUMN] == 0
    n_zero = min(int(round(n * zero_ratio)), int(is_zero.sum()))
    n_nonzero = min(n - n_zero, int((~is_zero).sum()))

    return pd.concat([
        _stratified_draw(df.loc[is_zero], n_zero, rng),
        _stratified_draw(df.loc[~is_zero], n_nonzero, rng),
    ]).sample(frac=1.0, random_state=int(rng.integers(2**31)))


def _stratified_draw(df: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Draw n rows, allocated across strata in proportion to stratum size.

    Largest-remainder allocation, so the counts sum to exactly n rather than
    to n plus or minus the number of strata.
    """
    if n <= 0:
        return df.iloc[:0]
    if n >= len(df):
        return df

    keys = [k for k in mcfg.STRATIFY_BY if k in df.columns]
    if not keys:
        return df.sample(n=n, random_state=int(rng.integers(2**31)))

    groups = df.groupby(keys, observed=True, sort=False)
    sizes = groups.size()
    exact = sizes / sizes.sum() * n
    take = np.floor(exact).astype(int)

    remainder = n - int(take.sum())
    if remainder > 0:
        order = (exact - take).sort_values(ascending=False).index[:remainder]
        take.loc[order] += 1
    take = np.minimum(take, sizes)

    seed = int(rng.integers(2**31))
    picked = [
        g.sample(n=int(take.loc[key]), random_state=seed)
        for key, g in groups if take.loc[key] > 0
    ]
    return pd.concat(picked) if picked else df.iloc[:0]


# --------------------------------------------------------------------------
# Scaling -- fitted on training rows alone
# --------------------------------------------------------------------------
@dataclass
class Scaler:
    """Min-max onto FEATURE_RANGE, plus an optional target standardiser.

    ONE scaler serves both models. D-09 requires that the only difference
    between the QNN and the NN be the layer, so they cannot have different
    preprocessing. Min-max to [0, pi] is chosen because angle encoding needs a
    bounded range; an MLP is indifferent.

    Test values outside the training range are CLIPPED. Without clipping, a
    value above the training maximum maps past pi, and a rotation past pi
    aliases back onto a different angle -- the model returns a confident wrong
    answer rather than raising.
    """
    lo: np.ndarray = field(default_factory=lambda: np.empty(0))
    hi: np.ndarray = field(default_factory=lambda: np.empty(0))
    y_mean: float = 0.0
    y_std: float = 1.0

    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> "Scaler":
        self.lo = np.nanmin(X, axis=0)
        self.hi = np.nanmax(X, axis=0)
        # A constant column would divide by zero and produce NaN for every
        # row. Map it to the bottom of the range instead.
        flat = self.hi <= self.lo
        self.hi = np.where(flat, self.lo + 1.0, self.hi)

        if y is not None and mcfg.STANDARDISE_TARGET:
            self.y_mean = float(np.mean(y))
            std = float(np.std(y))
            self.y_std = std if std > 0 else 1.0
        return self

    def transform(self, X: np.ndarray, clip: bool = True) -> np.ndarray:
        unit = (X - self.lo) / (self.hi - self.lo)
        if clip and mcfg.CLIP_TEST_FEATURES:
            unit = np.clip(unit, 0.0, 1.0)
        a, b = mcfg.FEATURE_RANGE
        return a + unit * (b - a)

    def transform_y(self, y: np.ndarray) -> np.ndarray:
        if not mcfg.STANDARDISE_TARGET:
            return y
        return (y - self.y_mean) / self.y_std

    def inverse_y(self, y: np.ndarray) -> np.ndarray:
        if not mcfg.STANDARDISE_TARGET:
            return y
        return y * self.y_std + self.y_mean


# --------------------------------------------------------------------------
# The one call the rest of the package makes
# --------------------------------------------------------------------------
@dataclass
class Prepared:
    X_train: np.ndarray
    y_train: np.ndarray
    X_val: np.ndarray
    y_val: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray
    features: list[str]
    scaler: Scaler
    test_index: pd.DataFrame          # time, lat, lon -- for D-04 aggregation
    stage: str

    @property
    def n_features(self) -> int:
        return len(self.features)


def prepare(
    df: pd.DataFrame,
    fold: Fold,
    stage: str,
    seed: int,
    train_rows: int | None = None,
    zero_ratio: float | None = None,
) -> Prepared:
    """Table + fold + stage -> arrays, with every guard applied in order."""
    rng = np.random.default_rng(seed)

    df = add_hour_encoding(df)
    names = feature_names(df)
    assert_no_leakage(names)

    train, val, test = split(df, fold)

    # Stage filter FIRST, then cap. The other order caps to MAX_VAL_ROWS and
    # then drops zeros, which left the count stage with 112 validation rows --
    # far too few to early-stop on.
    train = stage_rows(train, stage)
    val = stage_rows(val, stage)
    test = stage_rows(test, stage)

    val = cap_val(val, rng)
    test = sample_test_days(test)

    # Training rows may be reshaped. Validation and test may not.
    train = subsample(
        train,
        mcfg.TRAIN_ROWS if train_rows is None else train_rows,
        rng,
        mcfg.TRAIN_ZERO_RATIO if zero_ratio is None else zero_ratio,
    )

    Xtr = train[names].to_numpy(dtype=np.float64)
    ytr = make_target(train, stage)

    scaler = Scaler().fit(Xtr, ytr if stage == "count" else None)
    to_y = scaler.transform_y if stage == "count" else (lambda a: a)

    return Prepared(
        X_train=scaler.transform(Xtr, clip=False),
        y_train=to_y(ytr),
        X_val=scaler.transform(val[names].to_numpy(dtype=np.float64)),
        y_val=to_y(make_target(val, stage)),
        X_test=scaler.transform(test[names].to_numpy(dtype=np.float64)),
        y_test=to_y(make_target(test, stage)),
        features=names,
        scaler=scaler,
        test_index=test[[mcfg.TIME_COL, "lat", "lon", "area_km2",
                         mcfg.COUNT_COLUMN]].reset_index(drop=True),
        stage=stage,
    )

def cap_val(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Validation is for early stopping only; a few thousand rows suffice."""
    if mcfg.MAX_VAL_ROWS is None or len(df) <= mcfg.MAX_VAL_ROWS:
        return df
    return _stratified_draw(df, mcfg.MAX_VAL_ROWS, rng)


def sample_test_days(df: pd.DataFrame) -> pd.DataFrame:
    """Keep whole days, evenly spaced across the test year.

    Deterministic rather than random: even spacing guarantees seasonal
    coverage, and whole days keep every 6- and 24-hour aggregation window
    intact for D-04.
    """
    if mcfg.TEST_DAYS is None:
        return df
    days = df[mcfg.TIME_COL].dt.normalize()
    uniq = np.sort(days.unique())
    if len(uniq) <= mcfg.TEST_DAYS:
        return df
    idx = np.linspace(0, len(uniq) - 1, mcfg.TEST_DAYS).round().astype(int)
    return df.loc[days.isin(set(uniq[idx]))]
