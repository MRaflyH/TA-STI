# DECISIONS.md

**Project-wide decision record, v2. Started 10 September 2026.**

Supersedes `DECISIONS-v1-archive.md`, which is archived and **not deleted** —
it holds 46 entries, twelve of which carry an honest "not recorded"
attribution that cannot be rebuilt.

Where this disagrees with `config.py`, **`config.py` wins**. That rule has
already earned its keep once: when `config.py` contradicted *itself* on `KX`,
fixing that came before anything else, because the rule was inert until it did.

Every choice in this project that a reader could reasonably have made
differently, with its reasoning, its cost and its provenance — so the thesis
can cite it by ID rather than re-deriving the argument in prose.

---

## How to read this file

**Six fields per entry:** what was decided, why, what it costs, how to reverse
it, which Bab it belongs in, and who decided it.

**The `Who` field is the one that cannot be reconstructed later.** Where it
says "not recorded" or "inherited", that is the accurate record and not a
placeholder for something tidier. **Do not reconstruct attribution.**

**Numbering is `D-N1`, `D-N2`, …** so a v2 ID can never be confused with a v1
ID sitting in an old code comment or an old chapter draft. When an entry
supersedes a v1 decision, the old ID is named explicitly.

**Chapters use the seven-chapter TA template scheme directly** — I Pendahuluan,
II Studi, III Analisis, IV Perancangan, V Implementasi, VI Evaluasi, VII
Penutup. The v1 record used a five-chapter scheme and its `Bab` fields need
translating; the mapping is in `components/05-paper.md` §5.2 and is not
one-to-one.

**Provenance tags on figures:**

- **[repo]** — stated in `config.py`, a `RUNBOOK.md`, or a source docstring
- **[derived]** — computed from repo values, with the arithmetic shown
- **[measured]** — counted or read directly from the built tables or files on
  disk, with the date

---

## Status

**Ten entries, all from the restructure conversation of 10 September 2026.**
The record grows through the week as each component reports back.

Every entry below carries a real attribution. That is a change from v1, where
twelve entries could not be attributed at all.

| ID | Subject | Supersedes |
|---|---|---|
| D-N1 | The model is a diagnostic; no lead time in the target | — |
| D-N2 | `AOD_55_ADJ` is dropped | D-24 |
| D-N3 | `KX` re-pull attempted, with a hard cutoff | D-01 |
| D-N4 | The gradient backend is decided by measurement, not argument | D-28, D-39 |
| D-N5 | GPU acceleration is deferred to Bab VII | — |
| D-N6 | Five components, nine contracts, v1 frozen as a fallback | — |
| D-N7 | PCA reduction is structural, not an ablation axis | D-40 |
| D-N8 | Feature selection is Spearman + MI + ablation, never Pearson | D-02 |
| D-N9 | Two freezes: raw on day 3, modelled features on day 4–5 | — |
| D-N10 | Record v2 policy: archive, carry-forward, scoped review | — |

---

# Bab I — Pendahuluan

## D-N1 — The model is a diagnostic with no lead time, and becomes a forecast when driven by forecast fields

**Decided.** The target stays `flash_count` **at the same hour** as the
predictor fields. No lead time is introduced. The thesis frames the model as a
**diagnostic** that maps a meteorological state onto the lightning occurring in
that state, and states that it becomes an operational forecast when driven by
forecast fields from an NWP system rather than by analysis fields.

**Why.** This is how operational lightning forecasting is actually built: an
NWP model forecasts CAPE, humidity and cloud water out to some horizon, and a
diagnostic maps those forecast fields onto lightning. ECMWF's own lightning
parameterisation has this shape. So a same-hour mapping is the correct object,
and the word *prediksi* in the judul survives without a lead time in the
target.

An earlier proposal in the restructure conversation was to shift the target to
t+1 / t+3 / t+6 so that "nowcasting" would be literally true. **That proposal
was wrong and was withdrawn.** It would have solved a problem the design does
not have, at the cost of skill and a rebuild.

**What it costs, and this must be declared.** ERA5 is a **reanalysis**: it
assimilates observations after the fact. Forecast CAPE at +6 h carries error
that analysis CAPE does not. **The skill measured here is therefore an upper
bound on operational skill**, and the gap is however wrong the driving NWP's
forecast fields are — an amount this thesis does not measure and does not
claim to. Declared, this is a strength. Discovered by an examiner, it is a
hole.

**How to reverse it.** A lead time is one line in target construction
(`make_target`), plus a rebuild is not required — the shift happens at
modelling time. Cheap to reverse; it was not taken because it is not needed.

**Bab.** I for the scope sentence; VI or VII for the reanalysis caveat.

**Who.** **Rafly**, restructure conversation, 10 September 2026. The reasoning
is his: the meteorological inputs are themselves predicted by another system,
so the model consumes predicted fields rather than producing a lead time
itself. The withdrawn lead-time proposal was the assistant's and was correctly
rejected.

---

# Bab III — Analisis

## D-N2 — `AOD_55_ADJ` is dropped from both domains

**Decided.** Aerosol optical depth is removed from the predictor set and from
`POWER_PARAMS`. It is not carried in the table as an excluded column; it is not
requested at all.

**Why.** `AOD_55_ADJ` arrives from NASA POWER as **one regional monthly request
per domain** and is broadcast across every hour of that month. At hourly
resolution it therefore carries **zero within-month variance** and cannot
inform an hourly prediction. Every row in a given month and domain holds the
same value.

**What it costs.** Aerosol loading has a real literature linking it to
lightning activity, so dropping it removes a physically plausible predictor.
The honest framing is that the *available product* is at the wrong temporal
resolution for this design, not that aerosols do not matter. An hourly aerosol
product would be a legitimate Bab VII *saran*.

It also retires the "AOD broadcast" limitation that v1 carried as a Bab IV
caveat under D-24 — one fewer thing to declare.

**How to reverse it.** Re-add to `POWER_PARAMS` and re-request; two regional
monthly requests per domain, cheap. The broadcast problem returns with it.

**Bab.** III for the exclusion; VI in the feature-selection subsection, as a
dropped candidate with a stated reason.

**Who.** **Rafly**, restructure conversation, 10 September 2026, on the
assistant's measurement of the broadcast.

**Supersedes.** v1 D-24 in part — the POWER acquisition decision stands, its
AOD limitation does not.

---

## D-N3 — The `KX` re-pull is attempted, with a hard cutoff at end of day 2

**Decided.** ~84 supplementary single-variable CDS requests for `k_index` over
the subtropis box, 2018–2024, launched on day 1. **If the data has not landed
by end of day 2, `KX` stays in `DROPPED_PREDICTORS` for both domains and the
cost is stated in Bab VI.** The decision is made by the date, not by
readiness.

**Why attempt it.** The gap is **diagnosed, not unknown** (v1 D-01, diagnosed
2026-09-06). The subtropis NetCDFs genuinely lack the variable under any short
name, so it is not an `ERA5_SHORTNAME_MAP` miss. A fresh six-variable request
for that box returns five variables. But `k_index` requested **alone** for the
same box returned `kx` cleanly, twice, in **84 and 27 seconds** **[repo]**. The
CDS will serve it; what fails is the six-variable request for this box
specifically.

Recovering it restores **14 base predictors** and with them the exact feature
set the predecessor study used, which repairs the cost v1 D-01 records against
the Bab VI comparison.

**Why the cutoff.** The CDS queues **per account, not per machine**, so the KX
requests compete with the new-parameter requests for the same queue. An
open-ended attempt would push against the day-3 raw freeze and stall every
downstream component.

**What it costs.** Two days of CDS queue priority that could have gone to new
parameters. Sequenced KX first because it is 84 short single-variable requests
and because it repairs a named cost.

**How to reverse it.** If it lands late, the data is on disk and a rebuild
recovers it — but not this week.

**Bab.** III for the acquisition record; VI for the feature set actually used
and, if the cutoff bites, the cost of the drop.

**Who.** **Rafly**, restructure conversation, 10 September 2026.

**Supersedes.** v1 D-01, which recorded the drop as settled. The drop is now
provisional pending the re-pull.

---

## D-N8 — Feature selection is Spearman, mutual information and leave-one-out ablation, never Pearson

**Decided.** Features are selected in three stages, each producing a reportable
number:

1. **Candidate list** — literature, one citation per parameter, written into
   Bab II and frozen before any result is seen.
2. **Statistical screen** — **Spearman** rank correlation and **mutual
   information**, computed on the rebuilt table.
3. **Leave-one-feature-out ablation** — retrain without each feature and report
   the degradation. Run on **ridge**, not the QNN.

A feature-to-feature correlation matrix is reported alongside, to identify
redundant pairs.

**Why not Pearson.** Pearson detects only straight-line relationships. It would
discard a predictor like CAPE that matters chiefly above a threshold. Spearman
catches any consistently monotone relationship; mutual information catches any
relationship at all, including thresholds and non-monotone shapes.

**Why the QNN does not require linear relationships.** Under `FEATURE_MAP =
"z"` each feature enters as a bounded trigonometric function of its own scaled
value, which is already nonlinear per feature. What the `z` map does **not**
supply is feature *interaction* — that comes from entanglement in the ansatz.
So interaction questions are settled by ablation, not by inspecting a
correlation matrix.

**Why ablation on ridge rather than the QNN.** Seconds per fit against minutes.
The question is the feature's information content, not the model's capacity,
and running it on the QNN would consume a night that is already committed.

**What it costs.** The ablation measures information content for a *linear*
model. A feature that ridge cannot use but the QNN could would be discarded.
**State this limitation** rather than implying the ablation is model-agnostic.

**How to reverse it.** Each screen is independent and re-runnable in minutes
against the built table.

**Bab.** IV for the method; VI for the resulting table.

**Who.** **Rafly**, restructure conversation, 10 September 2026, on the
assistant's proposal. The requirement that every choice carry a justification
is the pembimbing's, from the bimbingan of 10 September 2026.

**Supersedes.** v1 D-02 in part — the feature set changes; the
pipeline-owns-the-list contract does not.

---

## D-N9 — Two freezes, not one: raw on day 3, modelled features on day 4–5

**Decided.** Two separate freeze dates.

- **Raw freeze, day 3.** No new CDS or POWER requests after this. Whatever has
  arrived enters the rebuild; whatever has not becomes Bab VII future work.
- **Modelled feature freeze, day 4–5.** Which columns the model actually reads.

**Why separate them.** The raw freeze gates a rebuild, which everything
downstream waits on, so it must be a hard date. The feature freeze is a config
change with no rebuild, so it can wait for the ablation to finish. Collapsing
them into one date would force the feature decision to be made before the
evidence for it exists.

This is what makes contract **C-1** work: the raw table may be wider than the
model. A 20-column table feeding an 8-qubit model is the normal case and is
what makes the ablation possible at all.

**What it costs.** Two dates to hold rather than one, and a discipline that a
column arriving on day 4 cannot be used however good it looks.

**How to reverse it.** Not reversible within this week. A missed raw freeze
cascades into every component.

**Bab.** III, in the acquisition and dataset-construction record.

**Who.** **Rafly**, restructure conversation, 10 September 2026.

---

# Bab IV — Perancangan

## D-N7 — PCA reduction is structural, not an ablation axis

**Decided.** `FEATURE_REDUCTION` moves from a sweep axis to a **designed part
of the pipeline**: standardise → PCA → min-max onto [0, π] → clip. The number
of retained components **is** the qubit count.

**Why.** `QUBITS_PER_FEATURE = 1`, so every feature is a qubit. Simulation cost
grows **exponentially** in qubits (statevector size 2ⁿ), and under
parameter-shift the circuit count per sample grows **linearly** in weights,
which themselves grow with qubits — `real_amplitudes` at reps=2 gives 3n
weights, so 45 at n=15 **[repo]**.

Under v1's 13-feature design, PCA was an optional reduction worth ablating.
Under a widened candidate set it becomes the only thing that reconciles a broad
literature-justified feature list with a tractable qubit budget. It is
therefore designed in, not swept.

**Why PCA rather than hand-rolled feature packing.** PCA is linear, citable,
and used in the predecessor's own references to reduce fourteen molecular
descriptors before a quantum feature map. Combining features by multiplication
or another ad-hoc rule has no such backing. Packing remains available as a
**variation** if time allows; PCA is primary.

**What it costs.** Principal components are **not interpretable as
meteorological quantities**. A Bab VI statement that "CAPE mattered most" is
not available downstream of PCA. This is why D-N8's screen and ablation run on
the **raw features before reduction** — that is where interpretability lives,
and the two stages answer different questions.

**How to reverse it.** `FEATURE_REDUCTION = None` restores direct
one-qubit-per-feature encoding, at whatever qubit count the frozen feature set
implies.

**Bab.** IV for the design; VI for the component count actually used and the
interpretability limitation.

**Who.** **Rafly**, restructure conversation, 10 September 2026, on the
assistant's argument from the qubit budget.

**Supersedes.** v1 D-40, which wired PCA as a sweep axis.

---

# Bab V — Implementasi

## D-N4 — The gradient backend is decided by measurement, on equal wall-clock, not by argument

**Decided.** Three runs. The backend for the reported results is chosen from
their outcome, not assumed in advance.

| Run | Backend | Config | Budget | Purpose |
|---|---|---|---|---|
| **A** | Qiskit Aer + parameter-shift | reduced: ~6 qubits, 1 fold, 3 seeds, 1.000 rows | one night | a fully-Qiskit result |
| **B** | PennyLane `lightning.qubit` + adjoint | **identical to A** | ~15 min | backend equivalence |
| **C** | PennyLane `lightning.qubit` + adjoint | full: 15 qubits, 3 folds, 3 seeds, 3.000 rows | one night | full-scale result |

**A against C decides the backend**, on equal wall-clock — the practical
question is what each buys for one night, not what each does on a matched
config. **B is the evidence** that the two backends produce the same numbers;
without it a backend would be chosen with no proof of agreement, and B is
nearly free.

**Why this replaces the v1 position.** v1 D-28 settled on PennyLane from a
benchmark of the *then-current* configuration and reported the Qiskit cost as
526,5 h for the 36-run set — a sweep that does not happen. That figure is
correct for that config and **was wrongly treated as a floor**. It is not.
Reducing qubits cuts weights, which cuts circuits per sample linearly and the
statevector exponentially:

| Change | Factor | Running total |
|---|---|---|
| Aer + parameter-shift, v1 config | — | ~236 h |
| 1 fold, 1 seed (4 fits, not 36) | 9× | ~26 h |
| 6 qubits → 18 weights → 36 circuits/sample | ~2,5× | ~10,5 h |
| `TRAIN_ROWS` 3.000 → 1.000 | 3× | ~3,5 h |

**[derived]** from the `[repo]` figure of ~305 ms/sample for Aer +
parameter-shift, measured on a MacBook Air M4. Three seeds at 6 qubits and
1.000 rows lands near 10,5 h — one night, not an impossibility.

**Benchmark before booking the night.** The ~305 ms/sample figure is from the
MacBook Air; the Ryzen 5 9600X may land elsewhere. Ten minutes of measurement
decides whether Run A is real. **[unverified]** until that benchmark runs.

**What Run A buys beyond speed.** A result computed by Qiskit end to end
retires the "does *Framework Qiskit* survive the backend switch" question
outright, rather than defending it. That is worth a night on its own.

**What Run A costs, and it must be declared.** One fold means the headline
rests on **one test year**, in a record containing a triple-dip La Niña
(2020–2023) and a strong El Niño peaking in the 2023–24 boreal winter. That is
exactly what rolling-origin cross-validation exists to avoid. Say it in Bab VI
rather than let it be found.

**Settled negatives, carried forward and not to be retried:**

- **SPSA.** Rank-1 estimate — one random direction probing a 45-dimensional
  gradient — so expected cosine to the true gradient is ~1/√d = 0,149.
  Measured **0,137 ± 0,224 at k=1** and **0,277 at k=16** **[repo]**, following
  the √k law. Reaching a usable 0,7 needs k ≈ 84, costing more than
  parameter-shift.
- **LinComb.** Expected to halve parameter-shift's cost; measured **2,5×
  slower** (104,2 min per 10k-row epoch against 40,9) **[repo]**. It builds a
  controlled-gate circuit per parameter, and circuit construction dominates.

**How to reverse it.** `DEVICE` and `DIFF_METHOD` are config values. Nothing is
committed until the runs report.

**Bab.** V for the implementation and the benchmark table; VI for whichever
result becomes the headline and for Run A's fold limitation.

**Who.** **Rafly**, restructure conversation, 10 September 2026. The framing on
equal wall-clock rather than equal config is his; the assistant had proposed a
matched-config comparison, which answers a different question. The assistant's
earlier claim that Qiskit-only was unavailable was an error and is corrected
above.

**Supersedes.** v1 D-28 (the PennyLane switch) and v1 D-39 (a reduced Qiskit
run for gradient-path agreement, which Run B absorbs).

---

## D-N5 — GPU acceleration is deferred to Bab VII

**Decided.** No GPU work this week. The RTX 5070 machine is used as a **second
CPU worker**, which needs no setup and genuinely doubles throughput across the
two machines.

**Why.** Three reasons, in order of weight:

1. **The measured ceiling is low.** Aer was expected to give 5–20× over
   `StatevectorEstimator` on the exact gradient and gave **1,34×** **[repo]**.
   The bottleneck was **Python-side circuit construction**, not simulation, and
   a GPU does not touch that.
2. **Windows.** `qiskit-aer-gpu` and `lightning.gpu` ship Linux wheels, so this
   means WSL2 plus a CUDA toolkit plus a second environment — against a project
   whose NF-02 story is one pinned environment at the repo root.
3. **The RTX 5070 is Blackwell (sm_120)**, new enough that wheel support needs
   **checking rather than assuming**. **[unverified]** — nobody has tried.

**What it costs.** An unmeasured possible speedup, and the honest position is
that it is unmeasured rather than absent. Bab VII states it as a *saran* with
the 1,34× figure attached, so a reader knows why it was not pursued.

**How to reverse it.** A documented second environment, which non-negotiable 3
permits as an exception rather than a default.

**Bab.** V for the environment; VII as future work.

**Who.** **Rafly**, restructure conversation, 10 September 2026.

---

# No chapter — process

## D-N6 — Five components, nine contracts, and v1 frozen as a fallback thesis

**Decided.** The project is worked in five components in parallel across two
machines — Data, Processing, Modelling, Training, Paper — each owning a
disjoint set of decisions. Facts that cross a boundary are **contracts C-1 to
C-9** in `INSTRUCTIONS.md` §3 and live there once. Every component develops
against the **frozen v1 tables** and swaps in real inputs at the freeze dates.

**The v1 state is tagged and preserved before anything changes**: the built
parquets, their `.meta.json` snapshots, and `results/final_20260908_024452.jsonl`
plus the valid `nn_full` rerun `final_20260908_131242.jsonl`.

**Why the freeze.** Every planned change — new parameters, a changed feature
count, a backend switch — invalidates the existing result set, which cost 7,7 h
of compute and 36 QNN fits. Tagging it means that if the re-pull stalls or Run A
overruns, **a complete and defensible thesis still exists**. The cost of the tag
is minutes; the cost of not having it is the project.

**Why five components rather than a serial plan.** The bottlenecks are
wall-clock, not effort: an ERA5 download is days, an overnight run is a night.
Working serially idles one machine and one person at every step. Two rules make
parallel work safe:

1. **Nothing hardcodes a feature count.** Not 13, not 14, not 20. Read the
   length from the config or from the table.
2. **A swap happens on a date, not on readiness.**

**What it costs.** Six documents to keep true instead of one, and a discipline
that a fact appearing in two briefs is a defect. The mitigation is the contract
list: anything shared lives in the root and is referenced, never restated.

**How to reverse it.** The briefs are documentation; abandoning the split costs
nothing technical. The v1 tag should never be deleted.

**Bab.** None. Process.

**Who.** **Rafly**, restructure conversation, 10 September 2026. The five-way
split is his; the contract mechanism and the freeze are the assistant's
proposals, accepted.

---

## D-N10 — Record v2 policy: archive rather than delete, carry-forward verdicts, review scoped to cited entries

**Decided.** `DECISIONS.md` v1 is archived as `DECISIONS-v1-archive.md`, not
deleted. This file starts fresh with `D-N` numbering. Each component brief
carries a **carry-forward table** with three verdicts against the old IDs:

| Verdict | Meaning |
|---|---|
| **carried** | still true, still ours. Re-verified against the config, dated. |
| **revisited** | the decision changes. New v2 entry, citing the old ID as superseded. |
| **dropped** | no longer applies. One line saying why. |

**The review is scoped to entries the thesis cites.** A full 46-entry
re-verification does not fit in a week. Everything not reviewed keeps a banner:
*last verified 8 September 2026, not re-checked in the v2 pass.*

**Why archive rather than restart clean.** Twelve v1 entries carry a "not
recorded" attribution that is the accurate record and cannot be rebuilt. Two
entries invert the assumption a reader would otherwise make about who decided
what — `MIN_COVERAGE = 0.0` was Rafly's call over an objection, and so was
hourly resolution. Deleting the archive destroys findings, not clutter.

**Why one D-number namespace across all five components.** Splitting the record
per component is precisely what produced the collision the September 2026 merge
had to repair: three files sharing one namespace, with the modelling record's
`D-14` colliding with batch 1's. Contract **C-9**.

**Why `D-N` prefixes.** Old code comments, old chapter drafts and the archive
all cite bare numbers. A `D-N4` can never be mistaken for a `D-04`.

**What it costs.** Two records to consult rather than one, and a banner on
unreviewed entries that an examiner could read as untidiness. It is honest and
it is cheap.

**How to reverse it.** Not reversible in the deletion direction, which is the
point.

**Bab.** None. Process.

**Who.** **Rafly**, restructure conversation, 10 September 2026, on the
assistant's proposal. Rafly's framing: the old record is *"hey, we used to do
this, do we still want to do this or change?"*

---

# Open questions carried into v2

Not re-verified in this pass. Each keeps its v1 banner: *last verified 8
September 2026.*

**Gating the thesis:**

- **The MERLIN CG/IC question.** Half-resolved. No discrimination column
  exists. MERLIN is 5,7% positive against PLN's 14,1% on signed peak current
  over the full record; IC contamination *raises* the positive fraction, and
  MERLIN sits well below the CG-only reference, which question 5 verified as
  genuinely CG-only at source in all seven years. Settled only by the KSC
  Weather Archive's documentation for the MerlinCloudToGround product, **not by
  further analysis**. Needed before Bab III. **Until then every subtropis
  result is provisional and must say so.**
- **The two title questions.** Is an hourly cell-count still "ground flash
  density", and does "Framework Qiskit" survive the backend choice. **One
  pembimbing conversation, not two.** D-N4's Run A retires the second if it
  succeeds.
- **`data/raw/` backup.** The only permanent-loss risk on the list, and not a
  documentation task.

**Open and not closing this week:**

- Whether the 56 low-coverage subtropis months are excluded. Needs a METAR-based
  observation record, which does not exist and **must be built for both domains
  if built at all**, or it injects a domain-dependent selection effect into the
  one comparison the TA exists to make.
- Whether the six all-zero tropis cells are dropped. `DROP_ALL_ZERO_CELLS =
  False`, off by default so the choice stays visible.
- Subtropis grid shape — 56 cells; the lat×lon dimensions decide whether 3×3
  spatial blocks exist. One line to read off the table.
- Four OFAT sweeps declared and unrun: `observable`, `ansatz_reps`,
  `feature_map`, `hour_encoding`. Until `ansatz_reps` runs, reps=2 rests on
  nothing.
- The `shots` sweep axis is **suspect and untested**.
- No end-to-end reproducibility replay has ever been run.
- **Seven hyperparameters have no recorded reasoning**: `LEARNING_RATE`,
  `BATCH_SIZE`, `NN_LARGE_HIDDEN`, ridge `alpha`, `VAL_FRACTION`,
  `FEATURE_MAP_REPS`, and linear entanglement on both map and ansatz. **A
  justification written now would be a reconstruction, which is what this
  record exists to prevent.** They stay unrecorded, and the pattern is recorded
  instead: the hyperparameters that shape the comparison are the ones with the
  least justification behind them.
