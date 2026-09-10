#!/usr/bin/env python3
"""Verify the D-40 FEATURE_REDUCTION wiring.

TWO MODES, AND THE ORDER MATTERS.

    python3 verify_pca_wiring.py --capture    # BEFORE any edit
    ... apply the D-40 edits ...
    python3 verify_pca_wiring.py --check      # AFTER

`--capture` records hashes of the prepared arrays produced by the CURRENT
code. `--check` recomputes them and asserts equality. A check that only exists
after the edit cannot prove the edit changed nothing -- it can only prove the
new code agrees with itself.

Run from code/modelling/src/ with the venv active.

WHAT --check ASSERTS

  1. FEATURE_REDUCTION = None reproduces the captured arrays EXACTLY.
     Hash equality on X_train, X_val and X_test, not metric similarity.
     This is the one that must be green before anything else is believed.

  2. The three sweep values produce three different feature counts:
     15 / 8 / 6. This is the defect -- before D-40 all three gave 15.

  3. The three produce different DATA, not just different widths.
     Distinct X_train hashes across the three settings.

  4. The qubit count follows, and the parity chain recomputes:
        None  15 qubits  47 QNN params  52 nn_matched  (steps of 17)
        pca8   8 qubits  26 QNN params  21 nn_matched  (steps of 10)
        pca6   6 qubits  20 QNN params  17 nn_matched  (steps of 8)
     Note the parity gap INVERTS: matched is larger than the QNN at 15 and
     smaller at 8 and 6. See DECISIONS.md D-40.

  5. _config_snapshot() carries feature_reduction and n_qubits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASELINE = Path(__file__).with_name("pca_wiring_baseline.json")

# One fixed cell. Small and deterministic; prepare() seeds its own rng.
DOMAIN = "tropis"
STAGE = "occurrence"
SEED = 0
TRAIN_ROWS = 500


def _hash(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a, dtype=np.float64).tobytes()).hexdigest()


def _prepare(reduction):
    """Prepare one fold under a given FEATURE_REDUCTION, restoring config after."""
    from gfd_model import config as mcfg
    from gfd_model import dataset as ds

    saved = mcfg.FEATURE_REDUCTION
    mcfg.FEATURE_REDUCTION = reduction
    try:
        df = ds.load(DOMAIN)
        fold = ds.folds()[mcfg.SWEEP_FOLD]
        return ds.prepare(df, fold, STAGE, seed=SEED, train_rows=TRAIN_ROWS)
    finally:
        mcfg.FEATURE_REDUCTION = saved


def _fingerprint(prep) -> dict:
    return {
        "n_features": int(prep.X_train.shape[1]),
        "shape_train": list(prep.X_train.shape),
        "shape_val": list(prep.X_val.shape),
        "shape_test": list(prep.X_test.shape),
        "X_train": _hash(prep.X_train),
        "X_val": _hash(prep.X_val),
        "X_test": _hash(prep.X_test),
    }


def _param_chain(n: int) -> dict:
    """Realised parameter counts at n qubits, read off the real code."""
    from gfd_model import config as mcfg
    from gfd_model.classical import mlp_param_count, solve_matched_hidden
    from gfd_model.qnn import QuantumModel

    q = QuantumModel(n, stage="count", seed=0)
    hidden = mcfg.NN_MATCHED_HIDDEN or solve_matched_hidden(n, q.n_trainable)
    return {
        "n_qubits": n,
        "qnn_circuit": int(q.n_circuit_weights),
        "qnn_trainable": int(q.n_trainable),
        "matched_hidden": list(hidden),
        "nn_matched": int(mlp_param_count(n, hidden)),
        "parity_step": n + 2,
    }


# --------------------------------------------------------------------------
def capture() -> int:
    print("CAPTURE -- run this BEFORE applying the D-40 edits.\n")
    prep = _prepare(None)
    fp = _fingerprint(prep)

    from gfd_model import config as mcfg
    if mcfg.FEATURE_REDUCTION is not None:
        print(f"!! config.FEATURE_REDUCTION is {mcfg.FEATURE_REDUCTION!r}, "
              f"expected None. Baseline is meaningless unless the default "
              f"is the unreduced path.")
        return 1

    BASELINE.write_text(json.dumps(fp, indent=2), encoding="utf-8")
    print(f"  features   : {fp['n_features']}")
    print(f"  X_train    : {fp['shape_train']}  {fp['X_train'][:16]}...")
    print(f"  X_val      : {fp['shape_val']}  {fp['X_val'][:16]}...")
    print(f"  X_test     : {fp['shape_test']}  {fp['X_test'][:16]}...")
    print(f"\nwrote {BASELINE.name}. Apply the edits, then run --check.")
    return 0


def check() -> int:
    if not BASELINE.exists():
        print(f"!! {BASELINE.name} not found. Run --capture on the code as it "
              f"was BEFORE the edit; a baseline taken afterwards proves "
              f"nothing.")
        return 1

    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    failures = []

    # -- 1. the unreduced path is unchanged ------------------------------
    print("1. FEATURE_REDUCTION = None reproduces the captured arrays")
    now = _fingerprint(_prepare(None))
    for key in ("n_features", "X_train", "X_val", "X_test"):
        ok = now[key] == base[key]
        print(f"   {'OK  ' if ok else 'FAIL'} {key}")
        if not ok:
            failures.append(f"unreduced path changed: {key}")
            print(f"        was {base[key]}")
            print(f"        now {now[key]}")

    # -- 2 and 3. widths and data differ ---------------------------------
    print("\n2. three settings give three feature counts")
    prints = {}
    for spec, want in (None, 15), ("pca8", 8), ("pca6", 6):
        fp = _fingerprint(_prepare(spec))
        prints[spec] = fp
        ok = fp["n_features"] == want
        print(f"   {'OK  ' if ok else 'FAIL'} {str(spec):5s} -> "
              f"{fp['n_features']:2d} features (want {want})")
        if not ok:
            failures.append(f"{spec}: {fp['n_features']} features, want {want}")

    print("\n3. three settings give three DIFFERENT X_train")
    hashes = {k: v["X_train"] for k, v in prints.items()}
    ok = len(set(hashes.values())) == 3
    print(f"   {'OK  ' if ok else 'FAIL'} {len(set(hashes.values()))} distinct "
          f"of 3")
    if not ok:
        failures.append("settings produced identical data -- the defect is "
                        "that they don't differ")

    # -- 4. the parity chain ---------------------------------------------
    print("\n4. qubit count follows, parity recomputes")
    expect = {15: (47, 52), 8: (26, 21), 6: (20, 17)}
    for n, (want_q, want_m) in expect.items():
        chain = _param_chain(n)
        ok = chain["qnn_trainable"] == want_q and chain["nn_matched"] == want_m
        rel = "matched >  qnn" if want_m > want_q else "matched <  qnn"
        print(f"   {'OK  ' if ok else 'FAIL'} {n:2d} qubits: "
              f"qnn {chain['qnn_trainable']:3d}  "
              f"nn_matched {chain['nn_matched']:3d}  "
              f"hidden {tuple(chain['matched_hidden'])}  "
              f"step {chain['parity_step']:2d}   {rel}")
        if not ok:
            failures.append(f"parity at {n} qubits: got "
                            f"{chain['qnn_trainable']}/{chain['nn_matched']}, "
                            f"want {want_q}/{want_m}")

    # -- 5. the snapshot records it ---------------------------------------
    print("\n5. _config_snapshot carries the reduction and the qubit count")
    from gfd_model import experiments as X
    snap = X._config_snapshot(6)
    for key in ("feature_reduction", "n_qubits"):
        ok = key in snap
        print(f"   {'OK  ' if ok else 'FAIL'} {key} present")
        if not ok:
            failures.append(f"_config_snapshot missing {key}")
    if snap.get("n_qubits") != 6:
        failures.append("_config_snapshot did not record the qubit count given")

    # -- verdict -----------------------------------------------------------
    print()
    if failures:
        print(f"FAILED -- {len(failures)} problem(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED.")
    print("The unreduced path is bit-for-bit unchanged, the three settings")
    print("now differ in width and in data, and the parity chain recomputes.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--capture", action="store_true",
                   help="record baseline hashes from the CURRENT code")
    g.add_argument("--check", action="store_true",
                   help="assert against the baseline after the edits")
    args = ap.parse_args()
    return capture() if args.capture else check()


if __name__ == "__main__":
    sys.exit(main())
