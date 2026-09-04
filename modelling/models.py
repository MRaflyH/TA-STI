"""The QNN and the classical NN, plus the metrics both are scored with.

THE QNN IS STOCK QISKIT ON PURPOSE. Every component below is an unmodified
function from ``qiskit.circuit.library`` or a class from
``qiskit_machine_learning``, used the way the official regression tutorial uses
it. Nothing here is a bespoke circuit. That is a defensible position to write
in Bab III and not an admission: the variable under study is the climate
domain, so the circuit is a control, and a standard well-characterised circuit
is the right control. A novel ansatz would add a confound to the one
comparison the TA exists to make.

References for the thesis (verified against qiskit 2.5 / qiskit-machine-learning 0.9):
  - qiskit.circuit.library.zz_feature_map / z_feature_map
    https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.circuit.library.zz_feature_map
  - qiskit.circuit.library.real_amplitudes / efficient_su2
  - qiskit_machine_learning.neural_networks.EstimatorQNN
  - qiskit_machine_learning.algorithms.regressors.NeuralNetworkRegressor
    https://qiskit-community.github.io/qiskit-machine-learning/tutorials/02_neural_network_classifier_and_regressor.html

Note the API era: circuit-library constructors are snake_case FUNCTIONS in
Qiskit 2.x (efficient_su2, not EfficientSU2), the primitives are V2, and every
circuit is transpiled to an ISA circuit through a preset pass manager before it
reaches an Estimator. Any tutorial you find that says otherwise predates 2.0.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from qiskit.circuit.library import (
    efficient_su2, real_amplitudes, z_feature_map, zz_feature_map,
)
from qiskit.primitives import StatevectorEstimator
from qiskit.quantum_info import SparsePauliOp
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_aer import AerSimulator
from qiskit_machine_learning.algorithms.regressors import NeuralNetworkRegressor
from qiskit_machine_learning.neural_networks import EstimatorQNN
from qiskit_machine_learning.optimizers import COBYLA, L_BFGS_B
from qiskit_machine_learning.utils import algorithm_globals
from sklearn.neural_network import MLPRegressor

from . import mconfig as mcfg


# ==========================================================================
# Metrics
# ==========================================================================
def _rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))


def _r2(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    ss_res = float(np.sum((y - p) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def score(y_true, y_pred, y_train_ref) -> dict:
    """RMSE / NRMSE / MAE / R^2, plus the baselines that keep them honest.

    NRMSE IS NORMALISED BY THE RANGE OF THE TARGET AND THE SCALE IS RECORDED.
    NF-01 asks for NRMSE < 0,1 without saying on what; an RMSE on a
    min-max-scaled target and an RMSE on raw GFD are different numbers with the
    same name. Whichever is quoted in the thesis, quote the scale beside it.

    The two baselines are not decoration. On a zero-inflated target, predicting
    the training mean everywhere already scores an R^2 near zero and an RMSE
    that a weak model will struggle to beat -- so a model that fails to beat
    `baseline_mean_rmse` has learned nothing, whatever its R^2 says.
    """
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    y_train_ref = np.asarray(y_train_ref, float)

    rng = float(y_true.max() - y_true.min())
    rmse = _rmse(y_true, y_pred)

    return {
        "rmse": rmse,
        "nrmse_range": rmse / rng if rng > 0 else float("nan"),
        "nrmse_mean": rmse / abs(float(y_true.mean())) if y_true.mean() else float("nan"),
        "mae": float(np.mean(np.abs(y_true - y_pred))),
        "r2": _r2(y_true, y_pred),
        "baseline_mean_rmse": _rmse(y_true, np.full_like(y_true, y_train_ref.mean())),
        "baseline_mean_r2": _r2(y_true, np.full_like(y_true, y_train_ref.mean())),
        "beats_mean_baseline": bool(rmse < _rmse(y_true, np.full_like(y_true, y_train_ref.mean()))),
        "target_min": float(y_true.min()),
        "target_max": float(y_true.max()),
        "n": int(len(y_true)),
    }


# ==========================================================================
# QNN
# ==========================================================================
def build_circuit(n_qubits: int):
    """Feature map + ansatz, both straight from qiskit.circuit.library."""
    fm_fn = {"zz": zz_feature_map, "z": z_feature_map}[mcfg.FEATURE_MAP]
    feature_map = fm_fn(
        feature_dimension=n_qubits,
        reps=mcfg.FEATURE_MAP_REPS,
        entanglement=mcfg.FEATURE_MAP_ENTANGLEMENT,
        parameter_prefix="x",
    )

    az_fn = {"real_amplitudes": real_amplitudes, "efficient_su2": efficient_su2}[mcfg.ANSATZ]
    ansatz = az_fn(
        num_qubits=n_qubits,
        reps=mcfg.ANSATZ_REPS,
        entanglement=mcfg.ANSATZ_ENTANGLEMENT,
        parameter_prefix="theta",
    )

    qc = feature_map.compose(ansatz)
    return qc, feature_map, ansatz


def _estimator_and_pm(n_qubits: int):
    """The V2 Estimator and the pass manager that produces the ISA circuit.

    statevector: exact expectation values, no sampling noise, deterministic.
                 The right default while the science is being settled -- any
                 variance you see is the model, not the shots.
    aer:         shot-based. Slower and noisier; run it before claiming the
                 result would survive on hardware.
    """
    if mcfg.ESTIMATOR_BACKEND == "statevector":
        estimator = StatevectorEstimator(seed=mcfg.RANDOM_SEED)
        backend = AerSimulator()
    elif mcfg.ESTIMATOR_BACKEND == "aer":
        from qiskit_aer.primitives import EstimatorV2 as AerEstimator
        backend = AerSimulator(seed_simulator=mcfg.RANDOM_SEED)
        estimator = AerEstimator(options={"default_shots": mcfg.SHOTS})
    else:
        raise ValueError(f"unknown ESTIMATOR_BACKEND {mcfg.ESTIMATOR_BACKEND!r}")

    pm = generate_preset_pass_manager(
        optimization_level=mcfg.OPTIMIZATION_LEVEL,
        backend=backend,
        seed_transpiler=mcfg.RANDOM_SEED,
    )
    return estimator, pm


@dataclass
class QNNResult:
    model: NeuralNetworkRegressor
    n_weights: int
    depth: int
    n_qubits: int
    fit_seconds: float
    loss_curve: list = field(default_factory=list)


def build_qnn(n_qubits: int) -> tuple[EstimatorQNN, dict]:
    """EstimatorQNN over the composed circuit, with an explicit observable."""
    qc, feature_map, ansatz = build_circuit(n_qubits)
    estimator, pm = _estimator_and_pm(n_qubits)

    # Global Z-parity. A LOCAL observable (Z on one qubit, i.e. "Z" + "I"*(n-1))
    # is the agreed barren-plateau mitigation and is one line away -- swap it in
    # and record which was used. Global cost functions are exactly what the
    # barren-plateau literature warns about as qubit count grows.
    observable = SparsePauliOp.from_list([("Z" * n_qubits, 1.0)])

    qnn = EstimatorQNN(
        circuit=qc,
        observables=observable,
        input_params=list(feature_map.parameters),
        weight_params=list(ansatz.parameters),
        estimator=estimator,
        pass_manager=pm,          # rule 3: ISA circuit before any primitive
        input_gradients=False,
    )
    info = {
        "n_qubits": n_qubits,
        "n_weights": len(ansatz.parameters),
        "n_inputs": len(feature_map.parameters),
        "circuit_depth": qc.decompose().depth(),
        "observable": str(observable.paulis[0]),
        "feature_map": f"{mcfg.FEATURE_MAP}_feature_map(reps={mcfg.FEATURE_MAP_REPS},"
                       f" entanglement={mcfg.FEATURE_MAP_ENTANGLEMENT!r})",
        "ansatz": f"{mcfg.ANSATZ}(reps={mcfg.ANSATZ_REPS},"
                  f" entanglement={mcfg.ANSATZ_ENTANGLEMENT!r})",
        "estimator_backend": mcfg.ESTIMATOR_BACKEND,
    }
    return qnn, info


def fit_qnn(X, y, n_qubits: int, max_iter: int | None = None, verbose: bool = True):
    """Train the QNN. Returns (QNNResult, info dict)."""
    algorithm_globals.random_seed = mcfg.RANDOM_SEED
    max_iter = max_iter if max_iter is not None else mcfg.MAX_ITER

    qnn, info = build_qnn(n_qubits)

    losses: list[float] = []

    def callback(weights, loss):
        losses.append(float(loss))
        if verbose and len(losses) % 25 == 0:
            print(f"      iter {len(losses):4d}  loss {loss:.5f}", flush=True)

    optimizer = (
        COBYLA(maxiter=max_iter) if mcfg.OPTIMIZER == "cobyla"
        else L_BFGS_B(maxiter=max_iter)
    )

    # Identity-block-style initialisation: weights near zero leave the ansatz
    # close to the identity, which is the agreed mitigation against starting on
    # a barren plateau. A small spread breaks the symmetry that exact zeros
    # would impose.
    rng = np.random.default_rng(mcfg.RANDOM_SEED)
    initial_point = rng.normal(0.0, 0.05, size=info["n_weights"])

    model = NeuralNetworkRegressor(
        neural_network=qnn,
        loss="squared_error",
        optimizer=optimizer,
        initial_point=initial_point,
        callback=callback,
    )

    t0 = time.perf_counter()
    model.fit(np.asarray(X, float), np.asarray(y, float).reshape(-1, 1))
    elapsed = time.perf_counter() - t0

    return QNNResult(
        model=model, n_weights=info["n_weights"], depth=info["circuit_depth"],
        n_qubits=n_qubits, fit_seconds=elapsed, loss_curve=losses,
    ), info


def predict_qnn(result: QNNResult, X) -> np.ndarray:
    return np.asarray(result.model.predict(np.asarray(X, float))).ravel()


# ==========================================================================
# Classical NN
# ==========================================================================
def matched_hidden_width(n_features: int, n_qnn_weights: int) -> int:
    """Hidden width giving an MLP roughly the QNN's trainable-parameter count.

    An MLP with one hidden layer of width h has h*(n_features+1) + (h+1)
    parameters. Solve for h. The baseline exists to be a fair reference, not to
    be beaten -- an unmatched 100-unit MLP against a 12-parameter QNN would
    make the comparison in Bab V worthless in either direction.

    Report the classical model's parameter count in the thesis next to the
    quantum one. If the two differ by an order of magnitude, say so.
    """
    h = max(2, int(round((n_qnn_weights - 1) / (n_features + 2))))
    return h


@dataclass
class NNResult:
    model: MLPRegressor
    n_weights: int
    hidden: tuple
    fit_seconds: float
    loss_curve: list = field(default_factory=list)


def fit_nn(X, y, n_qnn_weights: int | None = None, max_iter: int | None = None,
           verbose: bool = True):
    X = np.asarray(X, float)
    y = np.asarray(y, float).ravel()
    max_iter = max_iter if max_iter is not None else mcfg.NN_MAX_ITER

    if mcfg.MATCH_PARAM_COUNT and n_qnn_weights:
        hidden = (matched_hidden_width(X.shape[1], n_qnn_weights),)
    else:
        hidden = tuple(mcfg.NN_HIDDEN_SIZES)

    model = MLPRegressor(
        hidden_layer_sizes=hidden,
        activation=mcfg.NN_ACTIVATION,
        solver="lbfgs",          # deterministic given the seed, good for small n
        alpha=mcfg.NN_ALPHA,
        max_iter=max_iter,
        random_state=mcfg.RANDOM_SEED,
    )

    t0 = time.perf_counter()
    import warnings
    from sklearn.exceptions import ConvergenceWarning
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        model.fit(X, y)
    elapsed = time.perf_counter() - t0

    n_weights = int(sum(c.size for c in model.coefs_) +
                    sum(b.size for b in model.intercepts_))
    if verbose:
        print(f"      hidden {hidden}, {n_weights} parameters, {elapsed:.2f}s")

    return NNResult(model=model, n_weights=n_weights, hidden=hidden,
                    fit_seconds=elapsed,
                    loss_curve=list(getattr(model, "loss_curve_", [])))


def predict_nn(result: NNResult, X) -> np.ndarray:
    return np.asarray(result.model.predict(np.asarray(X, float))).ravel()
