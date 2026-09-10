"""The quantum arm: a PennyLane circuit that is provably the Qiskit template.

WHY NOT QISKIT, when the thesis says "existing Qiskit templates"
---------------------------------------------------------------
The architecture IS the Qiskit template -- z_feature_map composed with
real_amplitudes, read out with a local Z observable. What changed is the
differentiation backend, and only because the measured cost left no choice.

MEASURED on this machine, 15 qubits / 45 weights / reps=2. Milliseconds per
sample, and hours for the 36-run final set:

    Qiskit  StatevectorEstimator + ParamShift    438,70      526,5 h
    Qiskit  Aer + ParamShift                    ~305        ~366   h
    Qiskit  Aer + SPSA (k=1)                      12,01       14,4 h  unusable
    PennyLane  lightning.qubit + adjoint           6,97        8,4 h  <-- chosen

qiskit-machine-learning 0.9.1 exposes no adjoint or backprop gradient; its
only exact method is parameter shift, which needs 2 circuits per weight -- 90
per sample here. The adjoint method needs ONE backward pass for all 45. That
is a change in scaling, not a constant factor.

SPSA looked like the escape and was not. Its estimate is rank-1: a single
random direction probing a 45-dimensional gradient, so the expected cosine
against the true gradient is ~1/sqrt(d) = 0,149. Measured 0,137 +/- 0,224 at
k=1 and 0,277 at k=16 -- the sqrt(k) law exactly. Reaching a usable 0,7 would
need k ~= 84, which costs MORE than parameter shift. Recorded so nobody
retries it.

`qml.from_qiskit` is deliberately NOT used. It needs the pennylane-qiskit
plugin, which pins its own Qiskit range and could drag this environment off
2.5.2 and break the pipeline. Instead `verify_against_qiskit()` proves the two
circuits return identical expectation values, which is a stronger claim than
a converter would give.

Bab III should state: architecture taken from the Qiskit template, executed
on a backpropagating simulator, equivalence verified numerically to 1e-10.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pennylane as qml
import torch
from torch import nn

from qiskit.circuit import QuantumCircuit
from qiskit.circuit.library import (
    efficient_su2, real_amplitudes, z_feature_map, zz_feature_map,
)
from qiskit.quantum_info import SparsePauliOp

from . import config as mcfg


# --------------------------------------------------------------------------
# The Qiskit side -- reference definition, and the source for Bab III figures
# --------------------------------------------------------------------------
def build_feature_map(n: int) -> QuantumCircuit:
    if mcfg.FEATURE_MAP == "z":
        return z_feature_map(n, reps=mcfg.FEATURE_MAP_REPS)
    if mcfg.FEATURE_MAP == "zz":
        return zz_feature_map(
            n, reps=mcfg.FEATURE_MAP_REPS,
            entanglement=mcfg.FEATURE_MAP_ENTANGLEMENT,
        )
    raise ValueError(f"unknown FEATURE_MAP: {mcfg.FEATURE_MAP!r}")


def build_ansatz(n: int) -> QuantumCircuit:
    if mcfg.ANSATZ == "real_amplitudes":
        return real_amplitudes(
            n, reps=mcfg.ANSATZ_REPS, entanglement=mcfg.ANSATZ_ENTANGLEMENT
        )
    if mcfg.ANSATZ == "efficient_su2":
        return efficient_su2(
            n, reps=mcfg.ANSATZ_REPS, entanglement=mcfg.ANSATZ_ENTANGLEMENT
        )
    raise ValueError(f"unknown ANSATZ: {mcfg.ANSATZ!r}")


def build_circuit(n: int) -> tuple[QuantumCircuit, list, list]:
    """The reference Qiskit circuit. Draw this for the thesis figure."""
    fm, ansatz = build_feature_map(n), build_ansatz(n)
    return fm.compose(ansatz), list(fm.parameters), list(ansatz.parameters)


def build_observable(n: int) -> SparsePauliOp:
    if mcfg.OBSERVABLE == "local_mean":
        return SparsePauliOp.from_sparse_list(
            [("Z", [i], 1.0 / n) for i in range(n)], num_qubits=n
        )
    if mcfg.OBSERVABLE == "single_z":
        return SparsePauliOp.from_sparse_list([("Z", [0], 1.0)], num_qubits=n)
    if mcfg.OBSERVABLE == "global_z":
        return SparsePauliOp("Z" * n)
    raise ValueError(f"unknown OBSERVABLE: {mcfg.OBSERVABLE!r}")


def n_weights(n: int) -> int:
    """(reps + 1) * n for real_amplitudes; twice that for efficient_su2."""
    per_layer = n if mcfg.ANSATZ == "real_amplitudes" else 2 * n
    return (mcfg.ANSATZ_REPS + 1) * per_layer


def weight_shape(n: int) -> tuple[int, int]:
    """Layer-major, matching Qiskit's parameter order exactly.

    Row r holds layer r's rotation angles. Flattened in C order this
    reproduces theta[0..n-1], theta[n..2n-1], ... which is how Qiskit
    enumerates a ParameterVector. Get this wrong and verify_against_qiskit()
    fails loudly, which is precisely why that function exists.
    """
    per_layer = n if mcfg.ANSATZ == "real_amplitudes" else 2 * n
    return (mcfg.ANSATZ_REPS + 1, per_layer)


# --------------------------------------------------------------------------
# The PennyLane side -- what actually runs
# --------------------------------------------------------------------------
def _entangling_pairs(n: int, kind: str) -> list[tuple[int, int]]:
    if kind == "linear":
        return [(i, i + 1) for i in range(n - 1)]
    if kind == "circular":
        return [(n - 1, 0)] + [(i, i + 1) for i in range(n - 1)]
    if kind == "full":
        return [(i, j) for i in range(n) for j in range(i + 1, n)]
    raise ValueError(f"unknown entanglement: {kind!r}")


def _apply_feature_map(x, n: int) -> None:
    """z_feature_map / zz_feature_map, gate for gate.

    Qiskit's ZFeatureMap applies H then P(2*x_i). RZ(2*x_i) differs from
    P(2*x_i) by a global phase only, which cannot affect an expectation
    value -- verified numerically rather than assumed.

    Indexing uses x[..., i] so the same code serves a single sample and a
    batched tensor without branching.
    """
    for _ in range(mcfg.FEATURE_MAP_REPS):
        for i in range(n):
            qml.Hadamard(i)
            qml.RZ(2.0 * x[..., i], i)

        if mcfg.FEATURE_MAP != "zz":
            continue

        # ZZFeatureMap's second-order terms: 2*(pi - x_i)*(pi - x_j) on each
        # entangled pair, conjugated by CNOTs.
        for i, j in _entangling_pairs(n, mcfg.FEATURE_MAP_ENTANGLEMENT):
            qml.CNOT([i, j])
            qml.RZ(2.0 * (np.pi - x[..., i]) * (np.pi - x[..., j]), j)
            qml.CNOT([i, j])


def _apply_ansatz(w, n: int) -> None:
    """real_amplitudes / efficient_su2: rotate, entangle, repeat, rotate."""
    pairs = _entangling_pairs(n, mcfg.ANSATZ_ENTANGLEMENT)

    for r in range(mcfg.ANSATZ_REPS + 1):
        for i in range(n):
            if mcfg.ANSATZ == "real_amplitudes":
                qml.RY(w[r, i], i)
            else:
                qml.RY(w[r, 2 * i], i)
                qml.RZ(w[r, 2 * i + 1], i)
        if r < mcfg.ANSATZ_REPS:
            for i, j in pairs:
                qml.CNOT([i, j])


def _observable(n: int):
    """The same operator as build_observable(), in PennyLane's algebra.

    "local_mean" keeps every term single-qubit, so the cost function stays
    local and the gradient does not vanish exponentially with n. The stock
    template's "global_z" concentrates toward zero as qubits grow -- kept as
    the ablation arm that demonstrates why it was not chosen.
    """
    if mcfg.OBSERVABLE == "local_mean":
        return qml.dot([1.0 / n] * n, [qml.Z(i) for i in range(n)])
    if mcfg.OBSERVABLE == "single_z":
        return qml.Z(0)
    if mcfg.OBSERVABLE == "global_z":
        return qml.prod(*[qml.Z(i) for i in range(n)])
    raise ValueError(f"unknown OBSERVABLE: {mcfg.OBSERVABLE!r}")


def make_qnode(n: int, interface: str = "torch", device: str | None = None,
               diff_method: str | None = None):
    """The QNode. Its first argument MUST be named `inputs` for TorchLayer."""
    dev = qml.device(device or mcfg.DEVICE, wires=n)

    @qml.qnode(dev, interface=interface,
               diff_method=diff_method or mcfg.DIFF_METHOD)
    def circuit(inputs, weights):
        _apply_feature_map(inputs, n)
        _apply_ansatz(weights, n)
        return qml.expval(_observable(n))

    return circuit


# --------------------------------------------------------------------------
# The torch module
# --------------------------------------------------------------------------
class QuantumModel(nn.Module):
    """Circuit + affine head, as a plain torch Module.

    Being a Module is the whole point. D-09 requires the ONLY difference
    between the quantum and classical arms to be the layer -- same optimizer,
    batch size, loss, early stopping and seeds. That is enforceable only if
    both go through one training loop, and they only can if both are Modules.

    The affine head is not decoration. A Pauli expectation lives in [-1, 1];
    a standardised log-count target does not. Without a trainable a*y + b the
    model is structurally unable to reach the target range, and the failure
    presents as "the QNN does not learn". The Qiskit tutorial omits it because
    its toy target is already in range.

    For stage "occurrence" the output is a LOGIT -- pair it with
    BCEWithLogitsLoss, which is stabler than sigmoid followed by BCE.
    """

    def __init__(self, n_features: int, stage: str = "count", seed: int = 0,
                 device: str | None = None, diff_method: str | None = None,
                 output_bias: float = 0.0):
        super().__init__()
        self.n_features = n_features
        self.stage = stage

        qnode = make_qnode(n_features, device=device, diff_method=diff_method)

        # Small-angle init. real_amplitudes at theta=0 is the identity, so
        # starting near zero starts the circuit near identity -- a region
        # where gradients are informative rather than exponentially small.
        torch.manual_seed(seed)
        self.layer = qml.qnn.TorchLayer(
            qnode, {"weights": weight_shape(n_features)},
            init_method=lambda t: nn.init.normal_(t, mean=0.0, std=0.1),
        )

        if mcfg.OUTPUT_AFFINE_HEAD:
            self.head = nn.Linear(1, 1)
            with torch.no_grad():
                self.head.weight.fill_(1.0)
                # Start at the base rate. An identity head puts initial
                # logits in [-1, 1] -> probabilities in [0,27, 0,73], while
                # the truth is 0,058. Reaching that intercept alone took the
                # whole 15-epoch budget, so the circuit never got to learn.
                # classical.ClassicalModel gets the identical treatment.
                self.head.bias.fill_(output_bias)
        else:
            self.head = nn.Identity()

    @torch.no_grad()
    def calibrate_output(self, X, y=None, max_rows: int = 256) -> dict:
        """Set the affine head so the UNTRAINED model matches the target's
        marginal distribution.

        Why this is necessary, measured. z_feature_map leaves every qubit on
        the Bloch equator, where <Z> = 0 exactly. Small-angle init tilts each
        one by ~0,1, and `local_mean` averages 15 of those with mixed signs,
        so the layer's output std lands near 0,03. The target has std 1,0. A
        head starting at weight 1,0 must therefore learn a weight near 30, and
        at lr 0,01 that takes thousands of steps -- more than the whole run.

        Symptom without it: the occurrence stage converges after 3 epochs to
        barely below the trivial floor, and the count stage is still
        descending at epoch 29 of 30. Two failure modes, one cause.

        classical.ClassicalModel implements the same method, so neither arm
        gets an advantage the other does not.
        """
        if not isinstance(self.head, nn.Linear):
            return {}

        xb = torch.as_tensor(np.asarray(X[:max_rows]), dtype=torch.float32)
        z = self.layer(xb)
        if z.dim() == 1:
            z = z.unsqueeze(-1)

        z_mean, z_std = float(z.mean()), float(z.std())
        if not np.isfinite(z_std) or z_std < 1e-8:
            z_std = 1.0                     # degenerate layer; leave the head

        bias = float(self.head.bias.item())
        w = 1.0 / z_std
        self.head.weight.fill_(w)
        self.head.bias.fill_(bias - w * z_mean)
        return {"layer_mean": z_mean, "layer_std": z_std, "head_weight": w}

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.layer(x)
        if z.dim() == 1:
            z = z.unsqueeze(-1)
        return self.head(z).squeeze(-1)

    @property
    def n_circuit_weights(self) -> int:
        return n_weights(self.n_features)

    @property
    def n_trainable(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# --------------------------------------------------------------------------
# Proof, not assumption
# --------------------------------------------------------------------------
def verify_against_qiskit(n: int, trials: int = 3, tol: float = 1e-10) -> dict:
    """Assert the PennyLane circuit equals the Qiskit template numerically.

    This is what lets Bab III claim the architecture is the Qiskit template
    while running on a different simulator. It raises rather than prints,
    because a mismatch invalidates every downstream result and a warning in a
    long run is a line nobody reads.

    It also catches the parameter-ordering hazard in weight_shape(): if the
    layer-major reshape does not match Qiskit's ParameterVector enumeration,
    the expectation values diverge and this fails.
    """
    from qiskit.primitives import StatevectorEstimator

    qc, _, _ = build_circuit(n)
    obs = build_observable(n)
    estimator = StatevectorEstimator()
    pl = make_qnode(n, interface="numpy", diff_method=None)

    rng = np.random.default_rng(0)
    diffs = []
    for _ in range(trials):
        x = rng.uniform(0.0, np.pi, n)
        w = rng.normal(0.0, 0.3, n_weights(n))

        job = estimator.run([(qc, obs, np.concatenate([x, w]))])
        q_val = float(job.result()[0].data.evs)
        p_val = float(pl(x, w.reshape(weight_shape(n))))
        diffs.append(abs(q_val - p_val))

    worst = max(diffs)
    if worst > tol:
        raise AssertionError(
            f"PennyLane and Qiskit disagree by {worst:.3e} (tol {tol:.0e}). "
            f"Check gate order in _apply_feature_map / _apply_ansatz and the "
            f"parameter reshape in weight_shape()."
        )
    return {"max_abs_diff": worst, "trials": trials, "qubits": n}


# --------------------------------------------------------------------------
# Cost, measured rather than predicted
# --------------------------------------------------------------------------
@dataclass
class CostEstimate:
    n_qubits: int
    n_weights: int
    seconds_per_sample: float

    def run_minutes(self, rows: int, epochs: int) -> float:
        return self.seconds_per_sample * rows * epochs / 60.0


def measure_cost(n: int, batch: int = 32, repeats: int = 3) -> CostEstimate:
    """Time a real torch forward+backward -- the actual training cost.

    Five performance predictions in this project turned out wrong (LinComb,
    Aer, the SPSA cosine, SPSA batch scaling, backprop). Measure, do not
    estimate.
    """
    model = QuantumModel(n, stage="count", seed=0)
    x = torch.rand(batch, n) * np.pi
    y = torch.randn(batch)
    loss_fn = nn.MSELoss()

    loss_fn(model(x), y).backward()          # warm up
    model.zero_grad()

    t = time.perf_counter()
    for _ in range(repeats):
        loss_fn(model(x), y).backward()
        model.zero_grad()
    elapsed = (time.perf_counter() - t) / repeats

    return CostEstimate(n, n_weights(n), elapsed / batch)


def project(cost: CostEstimate) -> None:
    """Print what the configured experiment matrix would actually cost."""
    n_final = 2 * 2 * len(mcfg.FOLDS) * len(mcfg.SEEDS)
    final = cost.run_minutes(mcfg.TRAIN_ROWS, mcfg.MAX_EPOCHS)
    total = final * n_final / 60

    print(f"  qubits {cost.n_qubits} | weights {cost.n_weights} | "
          f"{cost.seconds_per_sample * 1000:.2f} ms/sample")
    print(f"  sweep run  (1.000 x 15 ep)  ~{cost.run_minutes(1_000, 15):6.1f} min")
    print(f"  final run  ({mcfg.TRAIN_ROWS:,} x {mcfg.MAX_EPOCHS} ep)  ~{final:6.1f} min")
    print(f"  FINAL SET  ({n_final} runs)       ~{total:6.1f} h")
    if total > 12:
        print(f"  !! {total:.1f} h exceeds one night -- cut TRAIN_ROWS, "
              f"SEEDS or ANSATZ_REPS in config.py")


def n_features_configured() -> int:
    n = len(mcfg.BASE_FEATURES)
    if mcfg.HOUR_ENCODING == "cyclic":
        return n + 2
    if mcfg.HOUR_ENCODING == "raw":
        return n + 1
    return n


if __name__ == "__main__":
    n = n_features_configured()
    print(f"gfd_model.qnn -- {n} features -> {n} qubits")
    print(f"  {mcfg.FEATURE_MAP} feature map | {mcfg.ANSATZ} "
          f"reps={mcfg.ANSATZ_REPS} | {mcfg.OBSERVABLE} readout")
    print(f"  {mcfg.DEVICE} / {mcfg.DIFF_METHOD}\n")

    r = verify_against_qiskit(n)
    print(f"  equivalence vs Qiskit: max |diff| {r['max_abs_diff']:.2e} "
          f"over {r['trials']} trials -- PASS\n")

    project(measure_cost(n))

    m = QuantumModel(n, stage="count", seed=0)
    print(f"\n  trainable parameters: {m.n_trainable} "
          f"({m.n_circuit_weights} circuit + affine head)")
          