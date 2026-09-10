# Component 4 — Training

**Owns:** backends, splits, the runs, metrics, evaluation.
**Does not own:** the circuit or the ladder's membership (C3), the feature set
(C2).
**Machine:** PC. **Config:** `code/modelling/src/gfd_model/config.py`.
**Hard dates:** Run A day 4 overnight, Runs B and C day 5.

---

## 4.1 — The backend question, and the three runs

The backend choice is **decided by measurement this week, not assumed**. Two
runs get one night each; the comparison is on equal wall-clock, which is the
practical question ("what does each buy me for a night"), not equal config.

| Run | Backend | Config | Cost | Purpose |
|---|---|---|---|---|
| **A** | Qiskit Aer + parameter-shift | reduced: ~6 qubits, 1 fold, 3 seeds, 1.000 rows | ~1 night | a fully-Qiskit result |
| **B** | PennyLane + adjoint | **identical to A** | ~15 min | backend equivalence |
| **C** | PennyLane + adjoint | full: 15 qubits, 3 folds, 3 seeds, 3.000 rows | ~1 night | full-scale result |

**A against C is the choice.** Equal time, best config each. **B is the
evidence** that the two backends produce the same numbers — without it you have
picked a backend with no proof they agree, and B is nearly free.

**Benchmark before committing a night.** Run Aer on the PC for ten minutes and
measure ms/sample before booking A's slot. The ~305 ms/sample figure is
`[repo]`, measured on a MacBook Air; the 9600X may land elsewhere.

**Where A's budget comes from** `[derived]` from `[repo]` figures:

| Change | Factor | Running total |
|---|---|---|
| Aer + parameter-shift, v1 config | — | ~236 h |
| 1 fold, 1 seed (4 fits, not 36) | 9× | ~26 h |
| 6 qubits → 18 weights → 36 circuits/sample | ~2,5× | ~10,5 h |
| `TRAIN_ROWS` 3.000 → 1.000 | 3× | ~3,5 h |

Three seeds at 6 qubits and 1.000 rows lands near 10,5 h. Parameter-shift needs
2 circuits per weight, so **cutting weights is the highest-leverage lever**.

**The cost of A's reduction, and it must be declared:** one fold means the
headline rests on one test year, in a record containing a triple-dip La Niña
(2020–2023) and a strong El Niño peaking in 2023–24. That is exactly what
rolling origin exists to avoid. Say it in Bab IV rather than let it be found.

**Do not reinstate SPSA.** Tested and rejected. Its estimate is rank-1 — one
random direction probing a 45-dimensional gradient — so the expected cosine
against the true gradient is ~1/√d = 0,149. Measured 0,137 ± 0,224 at k=1 and
0,277 at k=16, following the √k law exactly. Reaching a usable 0,7 needs k ≈ 84,
which costs **more** than parameter shift.

**Do not retry LinComb.** Expected to halve parameter-shift's cost; measured
**2,5× slower** (104,2 min per 10k-row epoch against 40,9). It builds a
controlled-gate circuit per parameter, and circuit construction dominates.

**GPU: deferred to Bab VII.** `qiskit-aer-gpu` and `lightning.gpu` ship Linux
wheels, so on Windows this means WSL2 plus CUDA plus a second environment
against a project whose NF-02 story is one pinned environment. The RTX 5070 is
Blackwell (sm_120), new enough that wheel support needs checking rather than
assuming. And the measured ceiling is low: Aer was expected to give 5–20× and
gave **1,34×**, because the bottleneck was Python-side circuit construction, not
simulation, and a GPU does not touch that. **The free win is using the PC as a
second CPU worker** — zero setup, genuinely doubles throughput.

---

## 4.2 — Splits

**Rolling origin.** Always train on the past, test on the future.

| Fold | Train | Test |
|---|---|---|
| 1 | 2018–2021 | 2022 |
| 2 | 2018–2022 | 2023 |
| 3 | 2018–2023 | 2024 |

Reported as mean ± sd across folds. Run A uses fold 3 alone; Run C uses all
three. **State the asymmetry.**

**Validation is the latest slice of the training window** (`VAL_FRACTION =
0.15`), never a random sample. A random validation set lets 2021 rows inform
the stopping decision for a model judged on 2022 — the same leak the
chronological split exists to prevent, one level down.

**Test rows are never reshaped** (contract C-4). Training rows may be
subsampled, stratified across cell and month so a subsample cannot come out all
Jakarta and all December. The train zero-ratio (natural / 75% / 50%) is a sweep
axis, not a default: a model trained at 50/50 believes lightning is roughly
twenty times more common than it is, and every count it produces is inflated.

**The solar-cycle limitation, stated and not claimed.** 2018–2024 spans roughly
half a solar cycle monotonically (cycle 24 bottomed ~late 2019, cycle 25 climbed
to a maximum ~2024–25). No split resolves an 11-year period in a 7-year record,
and a monotonic solar trend is perfectly confounded with everything else
trending over the same window: ENSO phase, LDS network upgrades, urbanisation,
MERLIN sensor changes. Write it as *a possible source of interannual variability
this record cannot resolve*, not as established physics — reported effect sizes
are small and the literature is contested.

---

## 4.3 — Evaluation

**Occurrence stage.** Base rate is ~5%, so **ROC-AUC flatters**. Lead with:

- **average precision** (PR-AUC) — the right summary at a low base rate
- **Brier score** and a **reliability curve** — calibration, which matters more
  than ranking for a rare event
- **log loss**, with the trivial baseline's log loss beside it as the floor
- **skill score** against that floor

The meteorology-standard set is **POD, FAR, CSI, Brier skill score**. An
examiner in this field will expect them; add them alongside the ML metrics.

**Count stage.** RMSE in standardised log space, plus MAE. Invert with `expm1`
**before** aggregating (contract C-3) — summing `log1p` values and inverting
once gives a geometric mean, a silent wrong answer.

**Report the zero share beside every metric.** A number on a 94–97% zero target
means nothing without it.

**Reporting windows.** The model always predicts one cell-hour; windows
aggregate predictions afterwards. Measured zero share by window (v1 build):

| window | tropis | subtropis |
|---|---|---|
| 1 h | 94,30% | 97,00% |
| 3 h | 90,09% | 94,52% |
| 6 h | 85,40% | 91,35% |
| 24 h | 64,63% | 76,63% |

`PRIMARY_WINDOW_H = 6` is **a nomination for readability, not a derived
optimum**. Say so.

**NF-01 will not be met** (NRMSE < 0,1 and R² > 0,9) at hourly resolution.
State this in advance, in Bab III where the requirement is restated, rather
than reporting it as a failure in Bab VI.

**NF-02 is met in mechanism and untested end-to-end.** No full replay has ever
been run from a fresh environment. The requirement itself is weaker than the
repo attempts ("replicable, with documented results"), and the mechanisms —
exact pins, a lock file, a shared seed, per-run config snapshots — are unusually
thorough for a TA. Claiming more than they show wastes them.

---

## 4.4 — Training loop

**One loop, both models.** Same optimizer, batch size, loss, early stopping and
seed handling for the QNN and the NN. This is what makes the comparison mean
anything; if the two were trained differently, "the NN was trained differently"
is the first objection at sidang.

`adam`, lr 0,01, batch 64, `MAX_EPOCHS = 30`, patience 6, seeds (0, 1, 2).
Equal optimizer steps per epoch across arms.

`MAX_VAL_ROWS = 1_000` — the quantum layer costs ~7 ms/row on adjoint, so a
full 236.610-row validation set would cost 27 min **per epoch** against 7 s of
training. Validation drives early stopping only.

---

## Done-criteria

- [ ] Aer benchmarked on the PC before any night is booked
- [ ] Runs A, B, C complete, each with its config snapshot
- [ ] Backend chosen on measured grounds, recorded as a v2 entry
- [ ] B's equivalence result reported either way
- [ ] Metric set includes POD/FAR/CSI and a reliability curve
- [ ] Zero share and coverage distribution beside every table

---

## Carry-forward from v1

| Old ID | Subject | Verdict | Note |
|---|---|---|---|
| D-06 | Rolling origin across years | carried | Run A departs from it; declare |
| D-07 | Training rows reshapeable, test rows not | carried | |
| D-38 | Stratified, largest-remainder, stage-filtered sampling | carried | |
| D-36 | Every model carries its own scaler; cross-domain uses the source's | carried | |
| D-30 | Equal optimizer steps per epoch | carried | |
| D-37 | Sweep protocol: one fold, one seed, config mutated in place | carried | |
| D-12 | NF-01 will not be met, stated in advance | carried | |
| D-42 | NF-02 met in mechanism, untested end-to-end | carried | |
| D-29 | Compute budget and its two-tier split | **revisited** | new budget, two machines |
| D-28 | PennyLane over Qiskit for gradients | **revisited** | re-decided by Runs A/B/C |
| D-39 | Reduced Qiskit run for gradient-path agreement | **revisited** | absorbed into Run B |
| D-14 | Sample-efficiency advantage tested, not supported | carried | a result, not a null |
| D-05 | Spatial aggregation is supplementary | carried | |

---

## Open

- The `shots` sweep axis is **suspect and untested**.
- Four OFAT sweeps declared and unrun (`observable`, `ansatz_reps`,
  `feature_map`, `hour_encoding`).
- No end-to-end reproducibility replay has been run.
