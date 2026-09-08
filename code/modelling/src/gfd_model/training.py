"""One training loop, both arms.

This file is the operational content of D-09. The claim that the QNN and the
NN differ only in their layer is only true if one function trains both, with
the same optimizer, batch size, loss object, early-stopping rule and seed
handling. Two loops -- however carefully matched -- leave "the NN was trained
differently" available as an objection at sidang, and it is not an objection
that can be answered after the fact.

So `fit()` takes an nn.Module and does not ask which kind it is.

Two details that are easy to get wrong and expensive to discover late:

  * Early stopping restores the BEST weights, not the last ones. Without the
    restore, patience epochs of overfitting are baked into every reported
    number.
  * The occurrence stage uses BCEWithLogitsLoss, so both models emit LOGITS
    and neither applies a sigmoid internally. Sigmoid followed by BCE is
    mathematically identical and numerically worse.

Batch size is not a speed lever here. lightning.qubit loops internally rather
than broadcasting -- measured 6,97 ms/sample batched against 8,68 single, so
batching buys 1,24x, not 32x. BATCH_SIZE is therefore purely an optimisation
choice, and it is held equal across arms because it is one more thing that
would otherwise differ.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from . import config as mcfg
from .classical import is_gradient_model


# --------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------
@dataclass
class TrainResult:
    model: object
    train_loss: list[float] = field(default_factory=list)
    val_loss: list[float] = field(default_factory=list)
    best_epoch: int = 0
    best_val: float = float("inf")
    epochs_run: int = 0
    seconds: float = 0.0
    stopped_early: bool = False

    def summary(self) -> str:
        return (f"{self.epochs_run:>3d} ep  best@{self.best_epoch:<3d} "
                f"val {self.best_val:.5f}  {self.seconds / 60:5.1f} min"
                f"{'  (early)' if self.stopped_early else ''}")


# --------------------------------------------------------------------------
# Loss
# --------------------------------------------------------------------------
def make_loss(stage: str) -> nn.Module:
    """Loss for a stage. Both models emit logits for the occurrence stage.

    BCEWithLogitsLoss fuses the sigmoid into the loss, which keeps gradients
    stable when the logit is large -- a real risk here, since the affine head
    on the quantum arm can push a bounded expectation value well outside
    [-1, 1] once it starts fitting a 94%-zero target.
    """
    if stage == "occurrence":
        return nn.BCEWithLogitsLoss()
    if stage == "count":
        return nn.MSELoss()
    raise ValueError(f"unknown stage: {stage!r}")


def make_optimizer(model: nn.Module) -> torch.optim.Optimizer:
    if mcfg.OPTIMIZER == "adam":
        return torch.optim.Adam(model.parameters(), lr=mcfg.LEARNING_RATE)
    if mcfg.OPTIMIZER == "sgd":
        return torch.optim.SGD(model.parameters(), lr=mcfg.LEARNING_RATE,
                               momentum=0.9)
    raise ValueError(f"unknown OPTIMIZER: {mcfg.OPTIMIZER!r}")


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------
def fit(
    model,
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    stage: str = "count",
    seed: int = 0,
    max_epochs: int | None = None,
    verbose: bool = False,
) -> TrainResult:
    """Train any model in the ladder. Quantum and classical take one path.

    Non-gradient arms (TrivialBaseline, RidgeModel) fit in closed form and
    return immediately with an empty history -- they have no epochs, and
    inventing some to make the table uniform would be dishonest.
    """
    started = time.perf_counter()

    if not is_gradient_model(model):
        model.fit(X_train, y_train)
        return TrainResult(model=model, seconds=time.perf_counter() - started)

    torch.manual_seed(seed)
    np.random.seed(seed)

    Xtr = torch.as_tensor(X_train, dtype=torch.float32)
    ytr = torch.as_tensor(y_train, dtype=torch.float32)
    Xva = torch.as_tensor(X_val, dtype=torch.float32)
    yva = torch.as_tensor(y_val, dtype=torch.float32)

    loader = DataLoader(
        TensorDataset(Xtr, ytr), batch_size=mcfg.BATCH_SIZE, shuffle=True,
        generator=torch.Generator().manual_seed(seed),
    )
    loss_fn = make_loss(stage)

    # Data-dependent output init, BEFORE the optimizer is built so its state
    # starts from the calibrated weights. Both arms implement this; see
    # qnn.QuantumModel.calibrate_output for why it is not optional.
    if hasattr(model, "calibrate_output"):
        model.calibrate_output(X_train, y_train)

    opt = make_optimizer(model)

    result = TrainResult(model=model)
    best_state = copy.deepcopy(model.state_dict())
    since_improved = 0
    epochs = max_epochs or mcfg.MAX_EPOCHS

    # Equal OPTIMIZER STEPS per epoch, not equal passes over the data.
    #
    # Without this, nn_full (1,8M rows) takes ~28.000 steps in a single epoch
    # while the matched arms (3.000 rows) take ~47. Early stopping only acts
    # at epoch boundaries, so nn_full had already run 35x the total training
    # of every other arm before validation was first checked -- at a learning
    # rate tuned for the small ones. It scored worse than the trivial floor on
    # subtropis occurrence as a result, which reads as "more data hurts" and
    # is really "the shared loop was unfair to the large-data arm".
    #
    # Capping steps makes the budget identical across arms; a large-data arm
    # simply draws each batch from a bigger pool, and the shuffle means it
    # still sees new rows every epoch. That is the comparison D-09 wants:
    # same budget, more data.
    max_steps = max(1, -(-mcfg.TRAIN_ROWS // mcfg.BATCH_SIZE))

    for epoch in range(epochs):
        model.train()
        running, seen = 0.0, 0
        for step, (xb, yb) in enumerate(loader):
            if step >= max_steps:
                break
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
            running += loss.detach().item() * len(xb)
            seen += len(xb)
        result.train_loss.append(running / max(seen, 1))

        model.eval()
        with torch.no_grad():
            # Chunked. The quantum layer costs ~7 ms per row, so validation is
            # a first-order cost rather than a rounding error -- an uncapped
            # 236.610-row set would spend 27 min PER EPOCH against 7 s of
            # training. cfg.MAX_VAL_ROWS caps the size; this caps the memory.
            preds = [model(Xva[i:i + 512]) for i in range(0, len(Xva), 512)]
            v = float(loss_fn(torch.cat(preds), yva))
        result.val_loss.append(v)

        if v < result.best_val - 1e-6:
            result.best_val, result.best_epoch = v, epoch
            # Restore-best, not last. Without this, `patience` epochs of
            # overfitting end up in every reported number.
            best_state = copy.deepcopy(model.state_dict())
            since_improved = 0
        else:
            since_improved += 1

        if verbose:
            print(f"    ep {epoch:>3d}  train {result.train_loss[-1]:.5f}  "
                  f"val {v:.5f}{'  *' if since_improved == 0 else ''}")

        if since_improved >= mcfg.EARLY_STOPPING_PATIENCE:
            result.stopped_early = True
            break

    model.load_state_dict(best_state)
    result.epochs_run = len(result.val_loss)
    result.seconds = time.perf_counter() - started
    return result


# --------------------------------------------------------------------------
# Inference
# --------------------------------------------------------------------------
def predict(model, X: np.ndarray, stage: str = "count",
            batch_size: int = 512) -> np.ndarray:
    """Predictions on the model's own scale.

    For "occurrence" the sigmoid IS applied here, so callers get calibrated
    probabilities -- the logits exist for the loss function's benefit, not the
    caller's. For "count" the output is still in standardised log space;
    inverting it is `dataset.Scaler.inverse_y` then `dataset.invert_target`,
    in that order, and never before aggregating (D-03).

    Batched because the quantum layer holds a statevector per sample and the
    test year is a quarter of a million rows.
    """
    if not is_gradient_model(model):
        out = model.predict(X)
        # TrivialBaseline and RidgeModel already return probabilities on the
        # occurrence stage -- only the torch models emit logits. Applying a
        # sigmoid here mapped the 5,79% base rate to 0,514 and made the FLOOR
        # look like a coin flip, which would have flattered every rung above
        # it. Clip instead: ridge is a linear probability model and can
        # predict outside [0, 1].
        return np.clip(out, 0.0, 1.0) if stage == "occurrence" else out

    model.eval()
    chunks = []
    with torch.no_grad():
        for i in range(0, len(X), batch_size):
            xb = torch.as_tensor(X[i:i + batch_size], dtype=torch.float32)
            out = model(xb)
            if stage == "occurrence":
                out = torch.sigmoid(out)
            chunks.append(out.numpy())
    return np.concatenate(chunks) if chunks else np.empty(0)


# --------------------------------------------------------------------------
# D-13. The two stages, combined
# --------------------------------------------------------------------------
def hurdle_predict(
    p_occurrence: np.ndarray,
    count_given_occurrence: np.ndarray,
) -> np.ndarray:
    """Expected count = P(occurrence) * E[count | occurrence].

    Both inputs must already be on the RAW count scale -- the second one
    inverted out of log space first. Multiplying a probability by a log-count
    is meaningless, and it fails silently rather than raising, which is why
    this function exists instead of the multiplication being written inline
    wherever it is needed.
    """
    if p_occurrence.shape != count_given_occurrence.shape:
        raise ValueError(
            f"shape mismatch: {p_occurrence.shape} vs "
            f"{count_given_occurrence.shape}. Both stages must predict the "
            f"same test rows, in the same order."
        )
    return p_occurrence * count_given_occurrence
