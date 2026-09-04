"""Load a processed table and turn it into arrays both models share.

THE WHOLE POINT OF THIS MODULE is that the QNN and the classical NN receive
byte-identical X and y. If the two models each did their own scaling or their
own split, any performance difference between them would be confounded by the
preprocessing and the comparison in Bab V would prove nothing. So: one split,
one imputer, one power transform, one scaler, one PCA, fitted ONCE on the
training rows, and handed to both.

Every transform is fitted on train only and applied to test. Fitting the
scaler or the PCA on the full table before splitting leaks test-set statistics
into training and is the most common way a GFD R^2 comes out too high.

On PCA: the predecessor study set the number of principal components equal to
the qubit count, and that is reproduced here so the two studies are comparable.
It is his answer to the dimensionality problem adopted as a baseline, not a
neutral default -- PCA components are linear mixtures, so any per-feature
importance analysis downstream describes components, not meteorology. Run once
with USE_PCA=False to see what it costs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import MinMaxScaler, PowerTransformer

from . import mconfig as mcfg


# ==========================================================================
# Containers
# ==========================================================================
@dataclass
class Split:
    """One prepared dataset. Both models consume exactly this."""

    X_train: np.ndarray
    y_train: np.ndarray          # scaled into TARGET_RANGE
    X_test: np.ndarray
    y_test: np.ndarray
    y_train_native: np.ndarray   # original GFD units, for reporting
    y_test_native: np.ndarray
    feature_names: list[str]
    n_qubits: int
    meta: dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"train {self.X_train.shape[0]:,} x {self.X_train.shape[1]}  |  "
            f"test {self.X_test.shape[0]:,}  |  qubits {self.n_qubits}"
        )


@dataclass
class Preprocessor:
    """The fitted transform chain. Kept so the cross-domain experiment can
    apply the SOURCE domain's transforms to the TARGET domain's rows -- which
    is what testing a trained model on new data means. Re-fitting on the target
    domain would quietly give the model information it would not have in
    deployment, and would make the generalization gap look smaller than it is.
    """

    imputer: SimpleImputer
    power: PowerTransformer | None
    scaler: MinMaxScaler
    pca: PCA | None
    y_log1p: bool
    y_scaler: MinMaxScaler
    feature_names: list[str]

    def transform_X(self, X: pd.DataFrame) -> np.ndarray:
        arr = self.imputer.transform(X[self.feature_names])
        if self.power is not None:
            arr = self.power.transform(arr)
        arr = self.scaler.transform(arr)
        if self.pca is not None:
            arr = self.pca.transform(arr)
        return np.asarray(arr, dtype=float)

    def transform_y(self, y: np.ndarray) -> np.ndarray:
        v = np.log1p(y) if self.y_log1p else y
        return self.y_scaler.transform(v.reshape(-1, 1)).ravel()

    def inverse_y(self, y_scaled: np.ndarray) -> np.ndarray:
        v = self.y_scaler.inverse_transform(np.asarray(y_scaled).reshape(-1, 1)).ravel()
        return np.expm1(v) if self.y_log1p else v


# ==========================================================================
# Loading
# ==========================================================================
def table_path(domain: str, freq_slug: str | None = None) -> Path:
    slug = freq_slug or mcfg.FREQ_SLUG
    return mcfg.PROCESSED_DIR / f"gfd_{domain}_{slug}.parquet"


def load_table(domain: str, freq_slug: str | None = None) -> pd.DataFrame:
    """Read one domain's processed table, with a readable error if it is absent."""
    path = table_path(domain, freq_slug)
    if not path.exists():
        csv = path.with_suffix(".csv")
        if csv.exists():
            df = pd.read_csv(csv)
        else:
            raise FileNotFoundError(
                f"{path} not found. Build it first:\n"
                f"    cd dataset-pipeline/src && python -m gfd_data.build\n"
                f"(set gfd_data.config.TIME_FREQ to match "
                f"gfd_model.mconfig.FREQ_SLUG = {freq_slug or mcfg.FREQ_SLUG!r})"
            )
    else:
        df = pd.read_parquet(path)

    df.attrs["source_path"] = str(path)
    meta_path = path.with_suffix(".meta.json")
    if meta_path.exists():
        df.attrs["build_meta"] = json.loads(meta_path.read_text())
    return df


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Every numeric column that is neither excluded nor the target."""
    cols = [
        c for c in df.columns
        if c not in mcfg.EXCLUDE_COLUMNS
        and c != mcfg.TARGET_COLUMN
        and pd.api.types.is_numeric_dtype(df[c])
    ]
    if not cols:
        raise ValueError(
            "no usable feature columns. Check EXCLUDE_COLUMNS against the "
            f"table's actual columns: {list(df.columns)}"
        )
    return cols


# ==========================================================================
# Splitting
# ==========================================================================
def _split_indices(
    df: pd.DataFrame, strategy: str, test_fraction: float, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = len(df)

    if strategy == "time":
        if "time" not in df.columns:
            raise ValueError("time-blocked split needs a 'time' column")
        periods = np.sort(pd.unique(df["time"].astype(str)))
        n_test = max(1, int(round(len(periods) * test_fraction)))
        test_periods = set(periods[-n_test:])
        mask = df["time"].astype(str).isin(test_periods).to_numpy()
        return np.where(~mask)[0], np.where(mask)[0]

    if strategy == "cell":
        cells = df[["lat", "lon"]].drop_duplicates().to_numpy()
        idx = rng.permutation(len(cells))
        n_test = max(1, int(round(len(cells) * test_fraction)))
        held = {tuple(c) for c in cells[idx[:n_test]]}
        mask = np.array([tuple(r) in held for r in df[["lat", "lon"]].to_numpy()])
        return np.where(~mask)[0], np.where(mask)[0]

    if strategy == "random":
        idx = rng.permutation(n)
        n_test = max(1, int(round(n * test_fraction)))
        return idx[n_test:], idx[:n_test]

    raise ValueError(f"unknown split strategy {strategy!r}")


# ==========================================================================
# Fitting
# ==========================================================================
def fit_preprocessor(
    train: pd.DataFrame, features: list[str], n_qubits: int
) -> Preprocessor:
    """Fit the whole chain on training rows only."""
    X = train[features]

    imputer = SimpleImputer(strategy="median").fit(X)
    arr = imputer.transform(X)

    power = None
    if mcfg.USE_POWER_TRANSFORM:
        # Yeo-Johnson handles zeros and negatives, unlike Box-Cox. Matches the
        # predecessor study.
        power = PowerTransformer(method="yeo-johnson", standardize=True).fit(arr)
        arr = power.transform(arr)

    scaler = MinMaxScaler(feature_range=(0.0, 1.0)).fit(arr)
    arr = scaler.transform(arr)

    pca = None
    if mcfg.USE_PCA:
        k = min(n_qubits, arr.shape[1], arr.shape[0])
        if k < n_qubits:
            print(f"  [data] PCA capped at {k} components "
                  f"(asked {n_qubits}; {arr.shape[1]} features, {arr.shape[0]} rows)")
        pca = PCA(n_components=k, random_state=mcfg.RANDOM_SEED).fit(arr)

    y = train[mcfg.TARGET_COLUMN].to_numpy(dtype=float)
    y_v = np.log1p(y) if mcfg.TARGET_LOG1P else y
    y_scaler = MinMaxScaler(feature_range=mcfg.TARGET_RANGE).fit(y_v.reshape(-1, 1))

    return Preprocessor(
        imputer=imputer, power=power, scaler=scaler, pca=pca,
        y_log1p=mcfg.TARGET_LOG1P, y_scaler=y_scaler, feature_names=features,
    )


def prepare(
    domain: str,
    freq_slug: str | None = None,
    n_qubits: int | None = None,
    max_rows: int | None = None,
    verbose: bool = True,
) -> tuple[Split, Preprocessor, pd.DataFrame]:
    """Load one domain and produce the within-domain split both models use."""
    n_qubits = n_qubits or mcfg.N_QUBITS
    df = load_table(domain, freq_slug)
    features = feature_columns(df)

    df = df.dropna(subset=[mcfg.TARGET_COLUMN]).reset_index(drop=True)
    if "time" in df.columns:
        df = df.sort_values("time").reset_index(drop=True)

    tr_idx, te_idx = _split_indices(
        df, mcfg.SPLIT_STRATEGY, mcfg.TEST_FRACTION, mcfg.RANDOM_SEED
    )
    train, test = df.iloc[tr_idx].copy(), df.iloc[te_idx].copy()

    if max_rows:
        # Subsample AFTER splitting -- subsampling first would let a training
        # row and its neighbour end up on opposite sides.
        rng = np.random.default_rng(mcfg.RANDOM_SEED)
        if len(train) > max_rows:
            train = train.iloc[np.sort(rng.choice(len(train), max_rows, replace=False))]
        n_test = max(8, max_rows // 4)
        if len(test) > n_test:
            test = test.iloc[np.sort(rng.choice(len(test), n_test, replace=False))]

    pre = fit_preprocessor(train, features, n_qubits)

    split = Split(
        X_train=pre.transform_X(train),
        y_train=pre.transform_y(train[mcfg.TARGET_COLUMN].to_numpy(float)),
        X_test=pre.transform_X(test),
        y_test=pre.transform_y(test[mcfg.TARGET_COLUMN].to_numpy(float)),
        y_train_native=train[mcfg.TARGET_COLUMN].to_numpy(float),
        y_test_native=test[mcfg.TARGET_COLUMN].to_numpy(float),
        feature_names=features,
        n_qubits=(pre.pca.n_components_ if pre.pca is not None else len(features)),
        meta={
            "domain": domain,
            "source_path": df.attrs.get("source_path"),
            "build_meta": df.attrs.get("build_meta"),
            "split_strategy": mcfg.SPLIT_STRATEGY,
            "n_rows_total": int(len(df)),
            "zero_target_share": float((df[mcfg.TARGET_COLUMN] == 0).mean()),
        },
    )

    if verbose:
        print(f"  [data] {domain}: {split.summary()}")
        print(f"  [data] zero-target share {split.meta['zero_target_share']:.1%} "
              f"-- compare any R^2 against the trivial baselines below")
        if pre.pca is not None:
            ev = pre.pca.explained_variance_ratio_.sum()
            print(f"  [data] PCA {len(features)} -> {pre.pca.n_components_} "
                  f"components, {ev:.1%} of variance retained")

    return split, pre, df


def prepare_cross_domain(
    source: str, target: str, pre: Preprocessor,
    freq_slug: str | None = None, max_rows: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply the SOURCE domain's fitted transforms to the TARGET domain.

    Returns (X, y_scaled, y_native) for every row of the target domain. No
    re-fitting: the model is being asked what it does on a climate it has never
    seen, with the preprocessing it was trained under.
    """
    df = load_table(target, freq_slug).dropna(subset=[mcfg.TARGET_COLUMN])

    missing = [c for c in pre.feature_names if c not in df.columns]
    if missing:
        raise ValueError(
            f"{target} table is missing features the {source} model was trained "
            f"on: {missing}. The two domains must be built with the same "
            f"feature set or the cross-domain test is meaningless."
        )

    if max_rows and len(df) > max_rows:
        rng = np.random.default_rng(mcfg.RANDOM_SEED)
        df = df.iloc[np.sort(rng.choice(len(df), max_rows, replace=False))]

    y_native = df[mcfg.TARGET_COLUMN].to_numpy(float)
    return pre.transform_X(df), pre.transform_y(y_native), y_native
