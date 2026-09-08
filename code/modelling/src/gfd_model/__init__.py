"""Modelling half of the GFD project: QNN and NN, tropis and subtropis.

Read `DECISIONS.md` before changing anything here. Every
constant in `config.py` that a reader could reasonably have set differently
carries the decision ID that justifies it, and a config that disagrees with
the decision record is worse than either alone.

Layout mirrors `code/pipeline/src/gfd_data/`:

    config.py     one source of truth -- task, features, folds, models
    dataset.py    loading, leakage checks, folds, subsampling, scaling
    qnn.py        feature map + ansatz + observable -> EstimatorQNN
    classical.py  the comparison ladder
    training.py   the single shared loop both models go through
    metrics.py    window aggregation, GFD conversion, calibration
    experiments.py the matrix runner
"""

from __future__ import annotations

__all__ = ["config", "dataset"]
