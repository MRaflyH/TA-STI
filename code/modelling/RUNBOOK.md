# Modelling runbook

Goes at `code/modelling/RUNBOOK.md`. Companion to `code/pipeline/RUNBOOK.md`:
that one records how the data was acquired, this one records how the models
were built, what they cost, and what went wrong on the way.

Design decisions live in `DECISIONS.md` and are cited here by ID. This file is
the record of what was actually executed and what it produced.

---

## 1. Environment

One virtualenv at the repo root, Python 3.13.7. Added for modelling:

    torch                2.14.0   (CPU wheel, download.pytorch.org/whl/cpu)
    pennylane            0.45.1
    pennylane-lightning  0.45.0

**`pennylane-qiskit` is deliberately NOT installed.** It pins its own Qiskit
range and could drag the environment off 2.5.2, breaking the pipeline. The
circuit is written natively in PennyLane and proved equal to the Qiskit
template numerically instead — see §3.

Commands in this file run from `code/modelling/src/`.

---

## 2. Why PennyLane, when the thesis says "Qiskit templates"

The architecture IS the Qiskit template: `z_feature_map` composed with
`real_amplitudes`, read out through a local Z observable. Only the
differentiation backend changed, and only because the measured cost left no
choice.

**Measured, 15 qubits / 45 weights / reps=2, on a MacBook Air.** Milliseconds
per sample, and projected hours for the 36-run final set:

| Backend | ms/sample | final set |
|---|---|---|
| Qiskit StatevectorEstimator + ParamShift | 438,70 | 526,5 h |
| Qiskit Aer + ParamShift | ~305 | ~366 h |
| Qiskit Aer + SPSA (k=1) | 12,01 | 14,4 h — gradient unusable |
| PennyLane lightning.qubit + adjoint | **6,97** | **8,4 h** |

`qiskit-machine-learning` 0.9.1 exposes no adjoint or backprop gradient. Its
only exact method is parameter shift, which needs 2 circuits per weight — 90
per sample here. Adjoint needs one backward pass for all 45. A change in
scaling, not a constant factor.

**Two backends that looked promising and were not:**

*LinComb* was expected to roughly halve ParamShift's cost and measured 2,5×
SLOWER (104,2 min per 10k-row epoch against 40,9). It builds a controlled-gate
circuit per parameter, and circuit construction dominates in the reference
primitive.

*Aer* was expected to give 5–20× on the exact gradient and gave 1,34×.
Simulation was never the bottleneck; Python-side circuit construction was, and
Aer does not touch it.

**SPSA, and why it must not be retried.** Its estimate is rank-1: one random
direction probing a 45-dimensional gradient, so the expected cosine against
the true gradient is ~1/sqrt(d) = 0,149.

| perturbations k | cosine vs ParamShift | ms/sample |
|---|---|---|
| 1 | 0,077 (0,137 ± 0,224 at 13 qubits) | 12,1 |
| 4 | 0,080 | 45,6 |
| 16 | 0,277 | 180,7 |

Exactly the sqrt(k) law. Reaching a usable 0,7 needs k ≈ 84, which costs MORE
than parameter shift. SPSA is strictly dominated once a usable gradient is
required.

**ParamShift cost surface**, measured, for 4.000 rows × 30 epochs × 36 runs.
Nothing fits a night; the cheapest configuration in the table is 19,4 h:

| qubits | reps | weights | ms/sample | set |
|---|---|---|---|---|
| 6 | 1 | 12 | 16,2 | 19,4 h |
| 8 | 1 | 16 | 27,4 | 32,9 h |
| 10 | 1 | 20 | 43,7 | 52,5 h |
| 13 | 1 | 26 | 102,1 | 122,6 h |
| 15 | 2 | 45 | 438,7 | 526,5 h |

Cost is brutally superlinear in qubits: 6→15 at reps=1 is a 14× jump for 2,5×
the features. Every qubit costs twice — more parameters to shift, and a
statevector twice as large to shift them through.

---

## 3. Equivalence to the Qiskit template

    python3 -m gfd_model.qnn

    equivalence vs Qiskit: max |diff| 2.71e-16 over 3 trials -- PASS
    qubits 15 | weights 45 | 7.25 ms/sample
    trainable parameters: 47 (45 circuit + affine head)

Machine epsilon. `verify_against_qiskit()` binds the same parameters to the
Qiskit circuit and the PennyLane QNode and compares expectation values; it
raises rather than warns, because a mismatch would invalidate everything
downstream.

It also guards the parameter-ordering hazard in `weight_shape()`: the
layer-major reshape must match Qiskit's ParameterVector enumeration exactly,
and this test is what proves it does.

**Bab III should state:** architecture taken from the Qiskit template,
executed on a backpropagating simulator, equivalence verified numerically to
1e-10.

---

## 4. The final run

    caffeinate -i nohup python3 -u run_final.py > ../final.log 2>&1 &

Started 2026-09-08 02:44, finished 10:26. **432 runs in 7,7 h**, against a
6,9 h projection. 36 QNN fits, 8,92 min mean, ~5,4 h of QNN time.

Output: `results/final_20260908_024452.jsonl`.

Configuration: `TASK="hurdle"`, 15 features (13 base + cyclic hour),
`TRAIN_ROWS=3_000`, `MAX_VAL_ROWS=1_000`, `TEST_DAYS=30`, `MAX_EPOCHS=30`,
patience 6, seeds (0,1,2), 3 rolling-origin folds, Adam at lr 0,01, batch 64.

`nn_full` was re-run three times afterwards as bugs 6–8 were found; the valid
file is `results/final_20260908_131242.jsonl`. Every other arm's numbers come
from the original 7,7 h run and are unaffected — they all use the shared
prep, so the fixes are no-ops for them.

### Occurrence, mean log loss over 3 folds × 3 seeds

| model | tropis_in | subtropis_in | tropis→sub | sub→tropis |
|---|---|---|---|---|
| baseline (floor) | 0,2353 | 0,1228 | 0,1352 | 0,2541 |
| ridge | 0,1923 | 0,1028 | 0,1908 | 0,3738 |
| **qnn** (47 par) | **0,1954** | **0,1054** | **0,1259** | **0,3192** |
| nn_matched (52 par) | 0,1692 | 0,0943 | 0,1006 | 0,2372 |
| nn_large (5.249 par) | 0,1645 | 0,0965 | 0,1384 | 0,2295 |
| nn_full (5.249 par, 2,4M rows) | 0,1607 | 0,0871 | 0,1308 | 0,1884 |

### Count, mean RMSE (standardised log space)

| model | tropis_in | subtropis_in | tropis→sub | sub→tropis |
|---|---|---|---|---|
| baseline (floor) | 1,0009 | 1,1271 | 1,3099 | 0,9294 |
| ridge | 0,9230 | 1,0933 | 1,3608 | 0,9083 |
| **qnn** | **0,9270** | **1,0700** | **1,3720** | **0,9467** |
| nn_matched | 0,9125 | 1,0659 | 1,3531 | 1,1142 |
| nn_large | 0,9238 | 1,0444 | 1,4369 | 0,9566 |
| nn_full | 0,9194 | 1,0404 | 1,4926 | 0,9291 |

### Cost

| model | training rows | mean wall-clock |
|---|---|---|
| qnn | 3.000 | 8,92 min |
| nn_full | 2.432.192 | 0,01 min |
| all others | 3.000 | 0,00 min |

**810× less data, 892× more time.**

### Readings for Bab IV and Bab V

1. **The QNN captures about half the achievable in-domain gain.** On
   `tropis_in` occurrence it closes 53% of the distance from the floor
   (0,2353) to the best classical model (0,1607); on `subtropis_in`, 49%.
   Consistent across domains.
2. **It loses to a 52-parameter MLP in 7 of 8 scenario-stage cells.**
   Individual gaps sit within one standard deviation (tropis_in occurrence is
   0,1954 ± 0,0335 against 0,1692 ± 0,0216), so the CONSISTENCY carries the
   claim, not any single comparison. Write it that way.
3. **Against ridge it is a tie** — better on both cross-domain occurrence
   arms, marginally worse elsewhere. A 15-qubit QNN buys roughly linear-model
   performance for ~900× the compute.
4. **Occurrence transfers; magnitude does not.** On `tropis_to_sub`
   occurrence, `nn_matched` (0,1006) beats the floor (0,1352). On
   `tropis_to_sub` count, EVERY model is worse than the floor (1,3099), with
   `nn_full` worst at 1,4926. This follows directly from D-08: MERLIN's
   amplitude distribution is truncated by detection efficiency in a way PLN's
   is not, so a model calibrated on Java counts cannot produce Florida counts.
5. **Smaller models transfer better.** On `tropis_to_sub` occurrence
   `nn_matched` (0,1006) beats `nn_large` (0,1384), reversing their in-domain
   order. Fewer parameters, less domain-specific overfitting.
6. **Ridge collapses on `sub_to_tropis` occurrence**: 0,3738 ± 0,2487, worse
   than the floor, standard deviation two-thirds of the mean. A linear
   probability model extrapolated across domains produces values outside
   [0, 1] that get clipped.
7. **D-12 confirmed by measurement.** Best count RMSE is 0,9125 against a
   1,0009 floor — about 9%, R² near 0,15. NF-01's R² > 0,9 was never
   reachable at hourly resolution.

---

## 5. The train_rows sweep — sample efficiency tested and not found

    python3 -u run_sweep.py > ../sweep.log 2>&1

18 runs per stage: 3 rungs (500 / 1.000 / 3.000 rows) x 3 seeds, on the sweep
fold (fold2, test 2024) with `TEST_DAYS=20` and `max_epochs=15`. Files
`results/sweep_train_rows_20260908_14*.jsonl` onward. ~80 min.

This is the axis the scientific argument was meant to rest on. QNNs are
claimed to be sample-efficient rather than asymptotically better, so "does the
gap close at small n" is the question this compute budget can actually answer.

### Occurrence, log loss

| rows | nn_matched | qnn | gap | pooled sd |
|---|---|---|---|---|
| 500 | 0,1691 ± 0,0105 | 0,1928 ± 0,0160 | +0,0237 | 0,0191 |
| 1.000 | 0,1519 ± 0,0137 | 0,1793 ± 0,0038 | +0,0274 | 0,0142 |
| 3.000 | 0,1374 ± 0,0073 | 0,1643 ± 0,0038 | +0,0269 | 0,0082 |

The gap **exceeds the pooled standard deviation at every rung**, and it does
not shrink across a 6x range of training data.

Both models improve at similar rates from 500 to 3.000 rows — QNN 0,0285
(0,1928 → 0,1643), nn_matched 0,0317 (0,1691 → 0,1374). The classical model
improves marginally FASTER, so the gap is flat to slightly widening. It is not
closing.

### Count, RMSE

| rows | nn_matched | qnn | gap | pooled sd |
|---|---|---|---|---|
| 500 | 0,9268 ± 0,0217 | 0,9322 ± 0,0465 | +0,0054 | 0,0513 |
| 1.000 | 0,9290 ± 0,0193 | 0,9357 ± 0,0213 | +0,0067 | 0,0287 |
| 3.000 | 0,9105 ± 0,0071 | 0,9313 ± 0,0158 | +0,0208 | 0,0173 |

Positive at every rung and WIDENING with data. Only the 3.000-row gap clears
the noise.

### A single-seed result that did not survive

The first sweep ran one seed and showed the count gap at −0,0111 (QNN AHEAD)
at 500 rows, −0,0003 at 1.000, +0,0138 at 3.000 — a textbook sample-efficiency
crossover. Three seeds erased it completely: the clean count gap is +0,0054,
+0,0067, +0,0208 — positive throughout and widening.

Recorded because it is a good illustration of why D-06 requires seed
replication, and because a single-seed crossover is exactly the kind of result
that is tempting to report. The seed-to-seed sd on the QNN count arm is 0,0396
at 500 rows, roughly four times the effect that appeared to exist.

An earlier draft of this section reported the two models improving by
"exactly 0,0319" each. That was an artefact of pooling the exploratory file,
which repeated seed 0 and gave 4 runs per cell instead of 3. Corrected above.
The lesson generalises: check the run count per cell before quoting a mean.

### The finding, for Bab V

> No sample-efficiency advantage was detectable. Across 500 to 3.000 training
> rows the parameter-matched classical network held a lead on the occurrence
> task that exceeded seed-to-seed variance at every rung and did not narrow
> with data, and a lead on the count task that widened. Both models improved
> at similar rates over the range (0,0285 and 0,0317 in log loss), indicating
> that the QNN's deficit lies in representational fit rather than in data
> efficiency.

This contradicts the usual expectation for QML in the low-data regime, it was
measured rather than assumed, and the constant-offset shape is the evidence
for the "representational fit" reading rather than merely a restatement of it.

**Caveat to state.** 500–3.000 rows is a narrow window and all of it is small.
An advantage below 500 rows, or a crossover above 3.000, would not appear
here. `TRAIN_ROWS=10_000` is ~30 min per QNN fit on the adjoint backend, so
one further rung at a single seed is affordable if the curve needs extending.

**Provenance of the numbers above.** Six files from the replicated batch
(`sweep_train_rows_20260908_143003` onward), 3 seeds per cell, 36 runs. The two
exploratory files from the first single-seed sweep are EXCLUDED — they repeat
seed 0 and would give 4 runs per cell.

---

## 6. Bugs found, and what they cost

Recorded because several are methodological findings rather than defects, and
because the same traps will be there for anyone who rebuilds this. Roughly
half belong in Bab III as justified design choices.

**1. The model spent its whole budget learning the intercept.**
*Symptom:* QNN occurrence converged after 3 epochs to 0,2028, barely under the
0,2044 floor. *Cause:* an identity output head puts initial logits in [-1, 1],
so probabilities start near 0,5 while the truth is 0,058. Reaching a logit of
−2,79 at lr 0,01 with 16 steps/epoch takes ~280 steps; a 15-epoch run gives
240. *Fix:* `classical.initial_bias()` initialises the output bias to the
base-rate logit, applied to BOTH arms. *Bab III material.*

**2. The quantum layer's output was 40× too small.**
*Symptom:* occurrence converged to nothing; count was still descending at
epoch 29 of 30. Two failure modes, one cause. *Cause:* `z_feature_map` leaves
every qubit on the Bloch equator where ⟨Z⟩ = 0 exactly. Small-angle init tilts
each by ~0,1 and `local_mean` averages 15 with mixed signs, giving output std
0,0258 (measured) against a target std of 1,0. The head starting at weight 1,0
needed to reach 38,8 — ~3.800 steps against the ~470 available. *Fix:*
`calibrate_output()` does data-dependent output init on both arms. Result:
occurrence 0,2028 → 0,1784, count 0,9341 → 0,9322. *Bab III material.*

**3. Validation cost more than training.**
*Symptom:* a run that should have taken minutes had not finished after an
hour. *Cause:* validation ran as one forward pass over 236.610 rows at ~7 ms
each — 27 min per epoch against 7 s of training. *Fix:* `MAX_VAL_ROWS` cap
plus chunked evaluation. Validation only drives early stopping; 1.000 rows
decides it.

**4. The count stage validated on 112 rows.**
*Cause:* `prepare()` capped validation to 2.000 rows and THEN applied the
non-zero stage filter. *Fix:* filter first, cap second.

**5. The trivial floor was scored through a sigmoid.**
*Symptom:* `baseline_trivial` reported log loss 0,7188 where 0,216 was
correct, making every model look strong. *Cause:* `predict()` applied a
sigmoid on the occurrence stage, but `TrivialBaseline` and `RidgeModel`
already return probabilities — only the torch models emit logits. Sigmoid maps
0,058 to 0,514. *Fix:* clip instead of sigmoid for the closed-form arms.

**6. `nn_full` trained on 3.000 rows.**
*Symptom:* identical numbers to `nn_large` in all 432 rows of the first run.
*Cause:* `train_rows=None` means "use the config default" in `prepare()`, not
"use everything". *Fix:* pass `10**9`, which makes `subsample()` a no-op.

**7. `nn_full` got 35× the training budget of every other arm.**
*Symptom:* after fix 6, `nn_full` scored WORSE than the trivial floor on
subtropis occurrence (0,2867 against 0,1228) — reading as "more data hurts".
*Cause:* 2,4M rows at batch 64 is ~38.000 optimizer steps in ONE epoch, while
the 3.000-row arms take 47. Early stopping only acts at epoch boundaries, so
`nn_full` had run far past its optimum before validation was first checked, at
a learning rate tuned for the small arms. *Fix:* cap steps per epoch so every
arm gets an equal budget; a large-data arm simply draws each batch from a
bigger pool. **This is the comparison D-09 wants: same budget, more data.**
*Bab III material.*

**8. `nn_full` was trained and tested through different scalers.**
*Symptom:* after fix 7 it was still erratic — validation losses healthy at
0,08–0,22 but test log loss 0,2867. *Cause:* `fit_models` built a separate
`Prepared` for `nn_full`, fitting its min-max scaler on 2,4M rows, while
`evaluate` used the shared 3.000-row prep's scaler and `X_test`. Different
ranges, so every test feature was shifted. *Fix:* keep each model's own
`Prepared` and use it at evaluation. Result: `nn_full` went from worst to best
in 5 of 8 cells.

**9. Retransformation bias made every GFD number ~2,5× too low.**
*Symptom:* mean predicted 6-hour GFD was 0,37–0,45 of observed across the
WHOLE ladder — every model, so it was the transform and not the model.
*Cause:* fitting MSE on `log1p(count)` gives the conditional mean in LOG
space; `expm1` of that is median-like and sits below the mean count (Jensen).
D-04's summation multiplies the error rather than cancelling it. *Fix:*
`metrics.smearing_factor()`, the one-parameter Duan smearing estimator, fitted
on VALIDATION only. Corrected `cal_ratio` on `tropis_in` 6 h: 0,37–0,45 →
1,20–1,34. *Bab III material.*

**On the residual over-correction.** Corrected ratios land at ~1,2–1,3 rather
than 1,0 because the factor is fitted on late-2023 validation rows and applied
to 2024, which has more activity. Same interannual gap as D-06. Reportable as
a finding, not a defect. If it needs tightening, fit the factor on train ∪ val
rather than val alone.

---

## 7. Still unverified

1. **Four OFAT sweeps remain**: `ansatz_reps`, `observable`, `feature_map`
   and `hour_encoding`. `train_rows` is done (§5). Each is ~15 min per seed.
   `observable` is the most interesting of the four — it contains the
   `global_z` ablation that demonstrates why the local readout was chosen.
2. **The architecture is otherwise single-configuration.** reps=2,
   `z_feature_map`, `local_mean`, linear entanglement, exact statevector.
   Whether the QNN's constant deficit (§5) closes under a different ansatz is
   untested, and it is the obvious next question.
3. **The `pooled` scenario is defined in config but not in `run_final`'s
   plan.** Only the four one-source scenarios ran.
4. **Shot noise has never been enabled.** `SHOTS=None` throughout, so every
   number is from an exact simulator and none of it speaks to hardware.
5. **The intensity target (D-08) has not been modelled at all.** The columns
   are in the tables; no model has read them.
6. **The QNN's 3.000-row limit was never pushed.** With the adjoint backend a
   10.000-row run is ~30 min per fit, which is affordable for a single
   configuration and would show whether the gap is data-limited.
