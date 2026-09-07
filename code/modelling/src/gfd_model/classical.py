"""The classical arm: the whole comparison ladder, floor to ceiling.

Five entries, and every one of them earns its place:

  baseline_trivial  predict the training mean, or the majority class. THE
                    FLOOR. Against a 94,30% / 97,00% zero target this already
                    explains most of the variance, so no R2 above it is
                    interpretable without it on the same page.
  ridge             linear reference. If the QNN cannot beat a linear model,
                    nothing else in the comparison matters.
  nn_matched        an MLP with the QNN's parameter count. Parity is solved
                    for, not guessed -- see solve_matched_hidden().
  nn_large          15 -> 64 -> 64 -> 1. The CEILING. The matched network is
                    deliberately crippled and a reviewer will say so; without
                    this arm there is no honest answer to "how good could a
                    classical model actually be".
  nn_full           nn_large trained on EVERY row rather than the QNN's
                    subsample. Not part of the matched comparison -- reported
                    separately and labelled as such.

On nn_full, and why it is in the ladder despite breaking parity
--------------------------------------------------------------
The NN trains on all 1.841.040 rows in under a minute; the QNN cannot exceed a
few thousand. Holding both to the same subsample is what makes D-09's
comparison meaningful, so the matched arms do exactly that. But "the classical
model can use 400x the data at a thousandth the cost" is a real finding about
where QNNs currently stand, and an examiner will ask about it whether or not
it was measured. Measure it, label it, and put it in Bab V.

Parameter parity is a weak currency here
----------------------------------------
The QNN's 45 weights act on a 32.768-dimensional Hilbert space. Forty-five
classical weights on 15 inputs buy a hidden layer of THREE units. The two are
not comparable in any deep sense, which is the argument for reporting the
whole ladder rather than a single matched pair.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from . import config as mcfg


# --------------------------------------------------------------------------
# Parameter parity
# --------------------------------------------------------------------------
def initial_bias(y: np.ndarray, stage: str) -> float:
    """Output bias that makes an untrained model predict the base rate.

    Without this, a model on a 5,79%-positive target burns its entire
    optimisation budget dragging the intercept from 0 to -2,79 and never
    reaches the features. Measured: at lr 0,01 with 16 steps per epoch, that
    move alone takes ~280 steps -- more than a 15-epoch run has.

    Applied to BOTH arms. Giving it only to the quantum model would hand it a
    head start and make D-09's comparison meaningless.
    """
    if stage != "occurrence":
        return float(np.mean(y))
    p = float(np.clip(np.mean(y), 1e-6, 1 - 1e-6))
    return float(np.log(p / (1.0 - p)))


def mlp_param_count(n_in: int, hidden: tuple[int, ...]) -> int:
    """Trainable parameters in an MLP with these layer widths."""
    total, prev = 0, n_in
    for h in hidden:
        total += prev * h + h
        prev = h
    return total + prev + 1                     # output layer


def solve_matched_hidden(n_in: int, target: int) -> tuple[int, ...]:
    """Single hidden width whose parameter count is closest to `target`.

    Solved rather than hand-picked, so that changing ANSATZ_REPS or the
    feature count cannot silently break parity. At 15 inputs and 47 target
    parameters this returns (3,) -- 52 parameters, the closest attainable.

    Exact parity is generally impossible: parameter count moves in steps of
    (n_in + 2) per hidden unit, which is 17 here. Report the actual counts of
    both models rather than claiming they are equal.
    """
    best, best_err = 1, None
    for h in range(1, 4 * target + 2):
        err = abs(mlp_param_count(n_in, (h,)) - target)
        if best_err is None or err < best_err:
            best, best_err = h, err
        elif mlp_param_count(n_in, (h,)) > target + best_err:
            break                               # counts only grow from here
    return (best,)


# --------------------------------------------------------------------------
# The neural network
# --------------------------------------------------------------------------
def _activation() -> nn.Module:
    if mcfg.NN_ACTIVATION == "tanh":
        # Bounded, like the quantum readout. Keeping the nonlinearity's range
        # comparable removes one more difference between the two arms.
        return nn.Tanh()
    if mcfg.NN_ACTIVATION == "relu":
        return nn.ReLU()
    raise ValueError(f"unknown NN_ACTIVATION: {mcfg.NN_ACTIVATION!r}")


class ClassicalModel(nn.Module):
    """An MLP with the same interface as QuantumModel.

    Same interface is the point: `training.fit` takes either without knowing
    which it has, which is what makes "the only difference is the layer"
    enforceable rather than aspirational.

    For stage "occurrence" the output is a LOGIT, matching QuantumModel --
    pair it with BCEWithLogitsLoss.
    """

    def __init__(self, n_features: int, hidden: tuple[int, ...],
                 stage: str = "count", seed: int = 0,
                 output_bias: float = 0.0):
        super().__init__()
        self.n_features = n_features
        self.stage = stage
        self.hidden = hidden

        torch.manual_seed(seed)
        layers: list[nn.Module] = []
        prev = n_features
        for h in hidden:
            layers += [nn.Linear(prev, h), _activation()]
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)

        # Start at the base rate -- see initial_bias(). The same treatment is
        # applied to QuantumModel's affine head, so neither arm is favoured.
        with torch.no_grad():
            self.net[-1].bias.fill_(output_bias)

    @torch.no_grad()
    def calibrate_output(self, X, y=None, max_rows: int = 256) -> dict:
        """The same treatment QuantumModel gets -- see its docstring.

        A standard-init MLP already produces O(1) outputs, so this changes
        little here. It is applied anyway because D-09 requires the two arms
        to differ only in their layer: a calibration step given to one and
        withheld from the other is exactly the kind of asymmetry that makes
        the comparison unanswerable at sidang.

        Rescaling the last layer is exact rather than approximate. With
        out = W.h + b, the map (out - m)/s + bias is reproduced by
        W' = W/s and b' = (b - m)/s + bias.
        """
        last = self.net[-1]
        xb = torch.as_tensor(np.asarray(X[:max_rows]), dtype=torch.float32)
        out = self.net(xb).squeeze(-1)

        o_mean, o_std = float(out.mean()), float(out.std())
        if not np.isfinite(o_std) or o_std < 1e-8:
            o_std = 1.0

        bias = float(last.bias.item())
        last.weight.div_(o_std)
        last.bias.fill_((bias - o_mean) / o_std + bias)
        return {"layer_mean": o_mean, "layer_std": o_std}

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)

    @property
    def n_trainable(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# --------------------------------------------------------------------------
# Non-gradient arms -- fitted in closed form, not through the shared loop
# --------------------------------------------------------------------------
class TrivialBaseline:
    """Predict the training mean (count) or the majority class (occurrence).

    THE FLOOR, and the most important number in the results table. On a target
    that is 94,30% zeros, "always predict zero" is already a strong-looking
    model by RMSE and by R2. Every other row in the ladder has to be read
    against this one.

    For occurrence it returns the training BASE RATE rather than a hard 0/1,
    so that AUC and log-loss stay defined and the comparison is not trivially
    degenerate.
    """

    def __init__(self, stage: str = "count"):
        self.stage = stage
        self.value = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TrivialBaseline":
        self.value = float(np.mean(y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.full(len(X), self.value, dtype=np.float64)


class RidgeModel:
    """Closed-form ridge regression, solved directly.

    Written out rather than imported so that the intercept handling and the
    regularisation of the bias term are visible -- the bias is NOT penalised,
    which sklearn also does but does not make obvious. Twelve lines is cheaper
    than a dependency whose defaults have to be checked.

    For the occurrence stage this fits the 0/1 labels as a linear probability
    model. Crude, but it is a reference point, not a contender.
    """

    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha
        self.coef: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeModel":
        A = np.hstack([X, np.ones((len(X), 1))])
        penalty = self.alpha * np.eye(A.shape[1])
        penalty[-1, -1] = 0.0                   # never penalise the intercept
        self.coef = np.linalg.solve(A.T @ A + penalty, A.T @ y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.coef is None:
            raise RuntimeError("fit() first")
        return np.hstack([X, np.ones((len(X), 1))]) @ self.coef


# --------------------------------------------------------------------------
# Assembling the ladder
# --------------------------------------------------------------------------
def build(name: str, n_features: int, stage: str, seed: int,
          qnn_params: int | None = None, output_bias: float = 0.0):
    """One rung of MODEL_LADDER, by name.

    `qnn_params` is required for "nn_matched" and comes from
    QuantumModel.n_trainable -- read off the actual model rather than
    recomputed here, so the two cannot drift apart.

    `output_bias` comes from initial_bias(y_train, stage) and goes to EVERY
    gradient-trained arm. The closed-form arms do not need it: they solve for
    the intercept directly.
    """
    if name == "baseline_trivial":
        return TrivialBaseline(stage=stage)

    if name == "ridge":
        return RidgeModel(alpha=1.0)

    if name == "nn_matched":
        if qnn_params is None:
            raise ValueError("nn_matched needs qnn_params for parity")
        hidden = mcfg.NN_MATCHED_HIDDEN or solve_matched_hidden(
            n_features, qnn_params
        )
        return ClassicalModel(n_features, hidden, stage=stage, seed=seed,
                              output_bias=output_bias)

    if name in ("nn_large", "nn_full"):
        return ClassicalModel(n_features, mcfg.NN_LARGE_HIDDEN, stage=stage,
                              seed=seed, output_bias=output_bias)

    if name == "qnn":
        from .qnn import QuantumModel
        return QuantumModel(n_features, stage=stage, seed=seed,
                            output_bias=output_bias)

    raise ValueError(f"unknown model: {name!r}")


def is_gradient_model(model) -> bool:
    """Does this go through the shared torch loop, or fit in closed form?"""
    return isinstance(model, nn.Module)


if __name__ == "__main__":
    from .qnn import QuantumModel, n_features_configured

    n = n_features_configured()
    q = QuantumModel(n, stage="count", seed=0)
    hidden = solve_matched_hidden(n, q.n_trainable)

    print(f"gfd_model.classical -- {n} features\n")
    print(f"  {'qnn':<18s} {q.n_trainable:>4d} params "
          f"({q.n_circuit_weights} circuit + affine head)")
    print(f"  {'nn_matched':<18s} "
          f"{mlp_param_count(n, hidden):>4d} params  hidden={hidden}")
    print(f"  {'nn_large':<18s} "
          f"{mlp_param_count(n, mcfg.NN_LARGE_HIDDEN):>4d} params  "
          f"hidden={mcfg.NN_LARGE_HIDDEN}")
    print(f"  {'ridge':<18s} {n + 1:>4d} params")
    print(f"  {'baseline_trivial':<18s} {1:>4d} param")
    print(f"\n  Parity is approximate: counts move in steps of {n + 2} per "
          f"hidden unit,\n  so report both numbers rather than claiming "
          f"they are equal.")
