# Component 3 — Modelling

**Owns:** the circuit, its provenance, the qubit budget, the classical ladder.
**Does not own:** which backend computes gradients, or how anything is trained
or evaluated. That is Component 4.
**Config:** `code/modelling/src/gfd_model/config.py`.

The central deliverable here is not code — the code works. It is **a clear
statement of what is stock and what is ours**, which is what the dosen asked
for and what the predecessor's paper does well.

---

## 3.1 — Provenance: stock versus proposed

Bab III needs this as an explicit table, ideally beside a circuit diagram, in
the way Fadhil's paper presents the ZZ and BPS feature maps.

| Element | Source | Stock or ours |
|---|---|---|
| `z_feature_map` | Qiskit circuit library | **stock**, unmodified |
| `real_amplitudes` ansatz | Qiskit circuit library | **stock**, unmodified |
| Composition (map → ansatz) | standard VQC pattern | **stock** |
| Readout observable | `local_mean` of single-qubit Z | **ours** — the stock template uses global Z |
| Output affine head | trainable scale + shift on the expectation | **ours** — not in the template |
| Output-bias initialisation | set from the training base rate | **ours** |
| Feature scaling to [0, π] | — | **ours** |
| PCA reduction before encoding | — | **ours** |

**Two of these need their reasoning written out, because they are the
substantive contributions and both currently read as implementation detail:**

**The local readout.** The stock global Z-on-every-qubit saturates badly past a
handful of qubits and is a known barren-plateau accelerant. Local cost
functions are the standard mitigation and the proposal already commits to them.
`global_z` is kept as the ablation arm that demonstrates why it was not taken —
**run it**, so the claim is measured rather than asserted.

**The affine head.** A Pauli expectation lives in [−1, 1]; a standardised
log-count target does not. Without a trainable affine head the model is
structurally incapable of reaching the target range, which reads as "the QNN
does not learn". The stock tutorial omits this because its toy target is
already in range. This is a real finding about applying the template to a
real target and is worth a paragraph, not a footnote.

---

## 3.2 — The qubit budget

`QUBITS_PER_FEATURE = 1`. Every feature is a qubit. This is the constraint that
makes "add more features" expensive in a way that is not obvious:

- simulation cost grows **exponentially** in qubits (statevector size 2ⁿ)
- under parameter-shift, cost grows **linearly** in weights, and weights grow
  with qubits (`real_amplitudes` at reps=2 gives 3n weights: 45 at n=15)

So a wide candidate set and a Qiskit run are in direct tension, and PCA is what
resolves them. Under the v1 design PCA was an ablation axis
(`FEATURE_REDUCTION = None | "pca6" | "pca8"`). Under a widened feature set it
becomes **structural**: the pipeline is standardise → PCA → min-max → clip, and
the number of components is the qubit count.

**Say this in Bab III as a designed constraint, not a compromise.** The chain
literature → screen → ablation → PCA → qubits is the full justification the
dosen asked for, end to end.

**Variation worth an ablation if time allows:** packing more than one feature
per qubit by combining them before encoding. PCA already does this in a
citable, linear way, and Fadhil's own references use PCA to reduce fourteen
descriptors before a quantum feature map. A hand-rolled product of two features
does not have that backing. **Use PCA as primary; keep packing as a variation.**

---

## 3.3 — Architecture settings

| Setting | Value | Status |
|---|---|---|
| `FEATURE_MAP` | `z` | product encoding, no entanglement, shallow |
| `FEATURE_MAP_REPS` | 1 | **no recorded reasoning** |
| `FEATURE_MAP_ENTANGLEMENT` | `linear` | **no recorded reasoning** |
| `ANSATZ` | `real_amplitudes` | |
| `ANSATZ_REPS` | 2 | **no recorded reasoning**; declared sweep axis, unrun |
| `ANSATZ_ENTANGLEMENT` | `linear` | **no recorded reasoning** |
| `OBSERVABLE` | `local_mean` | argued; `global_z` is the ablation |
| `OUTPUT_AFFINE_HEAD` | True | argued |

`zz_feature_map` at `full` entanglement is 105 two-qubit blocks at 15 qubits
and very deep. If tried at all, use `linear` or `circular`.

**Seven hyperparameters have no recorded reasoning** across this component and
Component 4: `LEARNING_RATE`, `BATCH_SIZE`, `NN_LARGE_HIDDEN`, ridge `alpha`,
`VAL_FRACTION`, `FEATURE_MAP_REPS`, and linear entanglement on both map and
ansatz. **State this as a limitation in Bab VI. Do not write a justification
now** — a reconstruction is exactly what the record exists to prevent. The
pattern is itself the finding: the hyperparameters that shape the comparison
are the ones with the least justification behind them.

---

## 3.4 — The classical ladder

Six rungs, reported together. This is the only definition of the ladder.

| Rung | Role |
|---|---|
| `baseline_trivial` | the floor. Without it no metric on a 94–97% zero target means anything. |
| `ridge` | linear reference |
| `nn_matched` | hidden width solved to match the QNN's weight count (52 vs 47) |
| `qnn` | |
| `nn_large` | (64, 64), the unconstrained ceiling |
| `nn_full` | `nn_large` on **every** row, not the QNN's subsample. Breaks parity on purpose, reported separately. |

`NN_ACTIVATION = "tanh"` — bounded, like the quantum readout.

The parameter-matched NN alone is not enough: it is deliberately crippled to
the QNN's weight count and a reviewer will say so. The unconstrained NN is what
the QNN is really measured against.

**If the compute budget forces a cut, cut `nn_large` before `nn_full` and
`baseline_trivial` before neither** — all classical rungs together cost under a
minute, so there is no real saving here. Cut QNN configurations instead.

---

## Done-criteria

- [ ] Provenance table written, with a circuit diagram
- [ ] `global_z` ablation run, so the local-readout claim is measured
- [ ] Qubit count fixed by the PCA component count, and the chain from
      literature to qubits written out
- [ ] The seven unjustified hyperparameters listed as a stated limitation

---

## Carry-forward from v1

| Old ID | Subject | Verdict | Note |
|---|---|---|---|
| D-33 | `z` map, `real_amplitudes` reps=2, local readout | carried | reps=2 still has no argument behind it |
| D-32 | Trainable affine head | carried | promote to a written contribution |
| D-31 | Output-bias init and layer calibration, both arms | carried | |
| D-09 | PyTorch for both models via `TorchConnector` | carried | |
| D-34 | Six-rung ladder, parity 47 against 52 | carried | |
| D-40 | PCA reduction axis | **revisited** | ablation → structural |
| D-02 | Feature set and hour encoding | **revisited** | shared with C2 |

---

## Open

- `ansatz_reps` sweep, declared and never run. ~15 min per seed. Until it
  runs, the reps=2 choice rests on nothing.
- `observable`, `feature_map` and `hour_encoding` sweeps, all declared and
  unrun.
- Whether 3×3 spatial blocks exist for subtropis (needs the grid shape).
