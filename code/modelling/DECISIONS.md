# Modelling decisions

Goes at `code/modelling/DECISIONS.md`.

Every choice the modelling code makes that a reader could reasonably have made
differently, with its reason, its cost, and whether it can be undone. Cite these
by ID from the thesis rather than re-deriving the argument in prose.

Format: **what was decided**, **why**, **what it costs**, **how to reverse it**,
**where it belongs in the thesis**.

Pipeline facts referenced below come from `code/pipeline/RUNBOOK.md` and the
build of 2026-09-06. Where this file and `config.py` disagree, `config.py` wins
and this file is what needs fixing.

**Build of 2026-09-06, after the intensity patch:**

| | tropis | subtropis |
|---|---|---|
| Strikes | 2.242.100 | 5.301.491 |
| Cells | 30 | 56 |
| Cell-hours | 1.841.040 | 3.314.304 |
| Non-zero cell-hours | 104.955 | 99.273 |
| Zero share | 94,30% | 97,00% |
| Months covered | 84 | 81 |
| Day-coverage, mean (min) | 86% (13%) | 59% (3%) |
| Predictors | 14, `KX` present | 13, `KX` absent |
| Missing values | none | none |

No predictor in either table contains a NaN. **No imputation step is required
anywhere in the modelling package.** Say so in Bab III.

---

## D-01 — `KX` is dropped from both domains

**Decided.** No model uses the ERA5 K index. Both domains present 13 base
predictors: `lat`, `lon`, the six NASA POWER parameters, and five of the six
ERA5 variables.

**Why.** `KX` is present in the tropis build and absent from the subtropis
build. The cross-domain experiment fits on one domain and applies the fitted
model to the other, so a 14-feature source against a 13-feature target either
raises a shape error or gets silently intersected by the shared preprocessing
chain — dropping `KX` without recording it. Making the drop explicit is the
difference between a documented decision and an undocumented accident.

**Common misstatement to avoid.** `KX` is not a MERLIN field. MERLIN supplies
only lightning strikes. `KX` is ERA5, and it is missing from the *subtropis ERA5
download*. Diagnosed 2026-09-06: the NetCDFs genuinely lack the variable under
any short name, so it is not an `ERA5_SHORTNAME_MAP` miss; a fresh six-variable
request for the subtropis box returns five variables; but `k_index` requested
**alone** for that same box returns `kx` cleanly, twice, in 84 and 27 seconds.
The CDS will serve it. What fails is the six-variable request for this box
specifically.

**Cost.** `KX` is one of the fourteen predictors the predecessor study used. The
feature set no longer matches his, which weakens the Bab V comparison. This is
the real price and it should be stated, not buried.

**Reversible.** Yes, at ~84 supplementary single-variable CDS requests of ~750
fields each — faster-queuing than the original fetch. A time trade, not a
technical constraint.

**Thesis.** Bab IV, feature-selection subsection. State the cost.

---

## D-02 — Feature set is 13 base predictors, with the hour encoding as an axis

**Decided.** `cfg.FEATURE_COLUMNS` minus `KX` gives 13. On top of that,
`hour_of_day_local` is included by default, cyclically encoded as
`sin(2πh/24)`, `cos(2πh/24)` — so the default running configuration is **15
columns**. The encoding is a config value, and 13 / 14 / 15 is one of the
one-factor-at-a-time sweeps.

**Why.** Time bins are UTC (`TZ_MODE` is forced to `"utc"` at hourly
resolution). Without a local-hour feature, a model must learn the UTC-to-local
offset separately for each domain — precisely the domain-specific quirk the
cross-domain experiment exists not to measure. Leave it out and the
cross-domain gap is partly a measurement of a clock. Cyclic encoding is used
because hour 23 and hour 0 are adjacent and a raw integer asserts they are 23
apart.

**Cost.** The cyclic encoding spends two columns where one would do, and on the
QNN each column is a qubit. That is why it is a sweep axis rather than a silent
default — the 13/14/15 comparison measures whether the second qubit earns its
place.

**Never predictors, at any setting.** `year` (worse than useless under a
chronological split — every test row carries a value never seen in training),
`days_in_month` (bookkeeping), `flash_count`, `gfd_per_km2_per_day`,
`gfd_per_km2_per_year` (the target and deterministic functions of it), `domain`
(a free giveaway in the cross-domain experiment), `coverage`, `observed_days`
(see D-10), `area_km2`, `period_days`, and every column in `INTENSITY_COLUMNS`
(see D-08). Enforced by `cfg.EXCLUDE_COLUMNS`.

**Thesis.** Bab III for the feature list, Bab IV for the sweep result.

---

## D-03 — The training target is `log1p(flash_count)`; reporting is in GFD units

**Decided.** Models are fitted on `log1p(flash_count)`. Predictions are inverted
with `expm1` and converted to GFD units for every reported number.

**Why.** At hourly resolution `gfd_per_km2_per_year` annualises a single hour,
so one flash becomes roughly 8.766× its per-hour rate. The column is a count
process wearing a density's units, and its non-zero values form a spike
distribution that no squared-error optimiser handles well. `flash_count` is the
honest hourly quantity. The log transform compresses a range that runs 1..2.391
in tropis and 1..11.777 in subtropis.

`gfd_per_km2_per_year` is retained for reporting so the thesis speaks in the
units the pembimbing and the predecessor study expect, and so the hourly, daily
and monthly builds remain unit-comparable.

**Cost.** One inversion step that must not be forgotten, and one failure mode
that is silent: **never sum in log space.** Summing `log1p` values and inverting
once gives a geometric mean, not a total. Always `expm1` first, then aggregate.
This matters directly for D-04.

**Reversible.** Yes — the transform is a config value.

**Thesis.** Bab III, preprocessing subsection.

---

## D-04 — Train hourly, aggregate the predictions to a reporting window

**Decided.** The model predicts one cell-hour. Reported results aggregate those
predictions to 1 h, 3 h, 6 h and 24 h windows. The window is a reporting choice
applied after inference, not a change to the dataset.

**Why.** The hourly build exists because ERA5 and NASA POWER are hourly, and
because the diurnal cycle is a first-order physical signal that aggregating the
*inputs* would destroy. Nothing forces the *reporting unit* to also be hourly.

**1. The zero problem softens; it does not dissolve.** MEASURED against the
build of 2026-09-06. This corrects an earlier estimate that assumed independent
hours and was badly wrong.

| Window | Tropis zeros | Subtropis zeros |
|---|---|---|
| 1 h | 94,30% | 97,00% |
| 3 h | 90,09% | 94,52% |
| 6 h | 85,40% | 91,35% |
| 24 h | 64,63% | 76,63% |

Under independent hours a 6-hour tropis window would be 70,33% zeros. It is
85,40%. Convection clusters in time: solving 0,943ᵏ = 0,8540 says a 6-hour
window behaves like **2,69 independent hours** in tropis and **2,97** in
subtropis; a 24-hour window like **7,43** and **8,74**.

Subtropis is measurably LESS clustered than tropis — Florida sea-breeze cells
fire and die inside the afternoon where West Java's convection persists. That
contrast is a physical difference between the domains rather than an
instrumental one, and it belongs in Bab IV as ballast alongside the
detection-efficiency problem.

The gain is real but modest: 24-hour tropis reaches 35,37% non-zero against
5,70% hourly, a factor of 6,2.

**Aggregation changes the REPORTING target only.** Training remains hourly and
remains 94,30% / 97,00% zeros. Do not claim otherwise. This is why D-13 exists.

**2. R² becomes interpretable at the wider windows**, where variance stops
being dominated by zeros. At 6 h it is still marginal.

**3. The window is a free test axis.** One trained model, four aggregations,
one skill-versus-reporting-window curve.

**4. The 24-hour tropis dataset is 76.710 rows** — small enough to hand a QNN
almost whole, which relaxes D-07's subsampling considerably.

**5. It matches the operational question.** "GFD over the next six hours for
this cell" is a statement a protection engineer can use. "GFD for the hour
beginning 14:00 UTC" is not.

**Cost, and it is real.** Summing predictions is unbiased only if the model is
calibrated. A model under-predicting by 10% per hour under-predicts the 6-hour
total by 10% — the error accumulates rather than cancelling. Report mean
predicted against mean observed, per window, beside every result.

**Rejected alternative.** Aggregating *before* training (building 6-hourly rows
by summing counts and averaging predictors) discards the within-window diurnal
structure the hourly build was paid for, and forces a choice of daily statistic
per predictor that hourly resolution otherwise removes from the thesis.

**Thesis.** Bab III for the mechanism, Bab IV for the window curve and the
clustering contrast.

---

## D-05 — Spatial aggregation is a supplementary result, not a second main axis

**Decided.** Predictions are aggregated over 2×2 cell blocks in both domains.
Whether 3×3 is available in subtropis depends on the grid shape — subtropis is
**56 cells**, not the 54 NASA POWER points; confirm the lat×lon dimensions
before claiming it.

**Why the arithmetic matters.** GFD is a density. Aggregating cells means
`sum(counts) / sum(areas)`, never the mean of the per-cell densities — cell
areas differ with latitude (`_cell_area_km2` accounts for meridian convergence)
so averaging densities is wrong.

**Why it is supplementary.** Tropis is 30 cells. A 5×5 block is very nearly the
whole domain, so 2×2 is about the limit. Temporal aggregation (D-04) has far
more headroom and carries the argument.

**Hazard.** Six tropis cells hold zero flashes across all seven years — 20% of
the grid. Any spatial block containing them scores well for the wrong reason.
See D-11.

**Thesis.** Bab IV, short subsection.

---

## D-06 — Rolling-origin cross-validation across years, not one held-out year

**Decided.** Three folds, always training on the past and testing on the future:

| Fold | Train | Test |
|---|---|---|
| 1 | 2018–2021 | 2022 |
| 2 | 2018–2022 | 2023 |
| 3 | 2018–2023 | 2024 |

Results are reported as mean ± standard deviation across folds. Rolling origin
is used for the default configuration and the headline QNN-versus-NN
comparison; the one-factor-at-a-time sweeps use fold 3 alone, to keep the
compute affordable. **State this asymmetry in Bab IV** — it is a defensible
allocation, but only if declared.

**Why, and what it does not fix.** A single held-out year makes the headline
number hostage to one year's climate state, and 2018–2024 is not climatically
uniform: it contains a triple-dip La Niña (2020–2023) and a strong El Niño
peaking in the 2023–24 boreal winter. ENSO is a first-order driver of tropical
convection over Indonesia, so 2024 alone is a poor summary of the record.

**The solar-cycle limitation, stated honestly.** An approximately 11-year
modulation of thunderstorm activity by the solar cycle — via sunspot number and
galactic cosmic ray flux — appears in the literature. This record cannot test
it. Solar cycle 24 bottomed out around late 2019 and cycle 25 climbed toward a
maximum around 2024–25, so 2018–2024 spans roughly **half a cycle,
monotonically**. Three consequences:

1. No split can resolve an 11-year period in a 7-year record. Rolling-origin CV
   does not fix this and is not claimed to.
2. A monotonic solar trend is perfectly confounded with everything else that
   trends monotonically over the same window — ENSO phase, LDS network
   upgrades, urbanisation, MERLIN sensor changes. Not separable by any method
   with this data.
3. 2024 sits at the extreme end of that trend, an additional reason not to rest
   the headline result on it alone.

Write this as *a possible source of interannual variability this record cannot
resolve*, not as established physics. Reported effect sizes for solar
modulation of lightning are small and the literature is contested;
overclaiming invites a question at sidang that cannot be answered from these
data.

**Cost.** 3× compute on the headline runs — the largest single compute cost in
the project.

**Thesis.** Bab III for the protocol, Bab IV for the limitation.

---

## D-07 — Training rows may be reshaped; test rows may not

**Decided.** The test set is the fold's held-out year, whole, at its natural
class ratio, never resampled. The training set is subsampled — uniformly at
random, stratified across cell and month so a subsample cannot come out all
Jakarta and all December. The zero-to-non-zero ratio of the *training* set
(natural / 75% / 50%) is one OFAT axis.

**Why subsample at all.** Tropis is 1.841.040 rows and subtropis 3.314.304. A
13-qubit `real_amplitudes` ansatz at 4 reps has 65 trainable parameters;
parameter-shift gradients cost 2 circuit evaluations per parameter per sample,
so 130 evaluations per sample per step. At an optimistic 1 ms per statevector
evaluation, one epoch over 10.000 samples is roughly 20 minutes — and the
matrix needs dozens of epochs across dozens of configurations across five
seeds. The full table is four orders of magnitude out of reach. A design
constraint, not a tuning problem.

**D-13 changes the arithmetic favourably.** Stage 2 trains on non-zero rows
only: 104.955 tropis and 99.273 subtropis. Both are within reach without
aggressive subsampling. Stage 1 still faces the full table.

**Why the asymmetry.** Rebalancing training data is a legitimate technique.
Rebalancing test data produces a number evaluated against a world that does not
exist. Same mechanism as D-10: any reweighting correlated with the target
inflates apparent performance.

**Metrics that survive the imbalance.** RMSE alone is dominated by zeros.
Report MAE alongside, and report a zero/non-zero classification view
(precision, recall, F1, AUC) beside the regression metrics. Always report the
trivial baselines — predict-the-mean and predict-zero-everywhere — because
against a 94–97% zero target those already explain most of the variance and no
R² is interpretable without them.

**Thesis.** Bab III for the protocol, Bab IV for the ratio sweep.

---

## D-08 — Intensity is built into the pipeline, used later

**Decided.** `aggregate_gfd` emits `mean_peak_current_ka`, `positive_share`,
`median_abs_peak_current_ka`, `max_abs_peak_current_ka` and
`p95_abs_peak_current_ka`, and `build_domain` carries them into the processed
table. Whether they are modelled is a separate decision.

**Why build them now.** Recovering them later means a full rebuild of both
parquets. Building them cost tens of seconds. The first two were already
computed by `aggregate_gfd` and were being dropped by `build_domain`'s column
selection.

**Statistics chosen.** The signed mean is kept because polarity is physically
meaningful. The spread statistics use absolute value: a cell-hour holding one
+40 kA and one −40 kA strike has a mean near zero and a median magnitude of 40,
and the second number is the useful one. The median is the headline rather than
the mean because CG peak current is heavy-tailed and the mean of a handful of
strikes is dominated by the largest.

**They are leakage for the GFD task.** All five derive from the same strike
records as the target. They are in `cfg.EXCLUDE_COLUMNS` and must never be
predictors for GFD.

**The NaN structure defines the experiment.** They are NaN wherever
`flash_count == 0` — the mean intensity of no strikes is undefined, not zero.
Verified in the build: 0 zero-rows carry any intensity value, and 100% of
non-zero rows carry all five statistics, in both domains.

### RESOLVED 2026-09-06: MERLIN's `Signal Strength` is kA

The argument is the upper tail, not the median. Tropis maxes at 520 kA and
subtropis at 551,3. Peak CG current has a physical ceiling near 500 kA, and two
independently operated networks agreeing within 6% of it is not an artefact of
an arbitrary sensor unit. Same shape of argument as the one that settled the
PLN timezone: physics, not labelling.

### Which makes the median gap a detection-efficiency finding

Per-cell-hour median absolute peak current:

| | median | IQR | max |
|---|---|---|---|
| tropis | 19,5 kA | 13,5–27,5 | 299 |
| subtropis | 36,9 kA | 23,05–60,65 | 537 |

Tropis sits squarely in published negative-CG climatology. Subtropis is roughly
double. Florida CG is somewhat stronger than tropical average, not 2× stronger.
MERLIN loses low-amplitude strikes, truncating the bottom of the distribution
and dragging the median up — the same mechanism as the −0,955 distance
gradient. **Cross-domain intensity comparison therefore measures MERLIN's
sensitivity floor as much as Florida's meteorology.** State this before any
intensity result.

### `positive_share` is dominated by singleton cell-hours

Mean 0,195 tropis and 0,102 subtropis; medians 0,011 and 0,000; against
record-level figures of 14,1% and 5,7%. A cell-hour containing exactly one
positive strike scores 1,0. As an unweighted per-row target it is mostly noise
about how many strikes landed that hour. Weight by `flash_count` or apply a
minimum-count threshold before using it.

**Thesis.** Bab III for the columns, Bab IV for the units argument and the
detection-efficiency bias.

---

## D-09 — PyTorch for both models, via `TorchConnector`

**Decided.** The QNN is wrapped as a `torch.nn.Module` through
`qiskit_machine_learning.connectors.TorchConnector`. The classical NN is a
plain `torch.nn.Module`. Both train in one loop: same optimizer, same batch
size, same loss object, same early-stopping rule, same seed handling.

**Why not `MLPRegressor`.** scikit-learn's estimator owns its training loop.
You cannot make it use your optimizer, batch size, early-stopping rule or seed
handling, so every comparison drawn against it carries a confound, and "the NN
was trained differently" is the first objection an examiner will raise. The
only difference between the two models must be the layer.

**The comparison ladder.** Five entries, reported together: predict-the-mean
floor, ridge regression, parameter-matched NN (≈65 weights, roughly
`13 → 4 → 1`), the QNN, and an unconstrained NN (`13 → 64 → 64 → 1`). The
parameter-matched NN alone is not enough — it is deliberately crippled and a
reviewer will say so. The unconstrained NN is the performance ceiling the QNN
is really being measured against.

**Cost.** `torch` enters `requirements.txt` and `environment-lock.txt` is
regenerated — a change to the NF-02 story that must be recorded, not silent.
CPU-only torch is roughly a 200 MB install.

**To verify before relying on it.** That `TorchConnector` behaves as expected
against the pinned `qiskit-machine-learning==0.9.1`, and whether that version
exposes a reverse/adjoint estimator gradient. The second is the difference
between a QNN sweep finishing in an hour and finishing in a day, and should be
measured rather than assumed. STILL OPEN.

**Thesis.** Bab III, implementation subsection.

---

## D-10 — `coverage` is reported, never acted on

**Decided.** `MIN_COVERAGE` stays at 0,0. `coverage` is neither a filter nor a
sample weight. The distribution of `coverage` over the rows actually trained on
is reported in Bab IV beside the zero share.

**Why not filter.** A 0,9 gate would delete 56 of 81 subtropis months and 26 of
84 tropis — and it deletes *opposite halves of the year* in the two domains
(tropis thins through the JJAS dry season, subtropis through DJF winter). The
two training sets would no longer span comparable seasonal ranges, so any
cross-domain gap measured afterwards would be partly an artefact of the filter.

**Why not weight either.** `coverage` is correlated with the target through
lightning activity itself — the observation proxy is "a day with at least one
strike somewhere in the domain is a day the network was up", so a genuinely
quiet month and a dead detector look identical. Down-weighting low-coverage
rows preferentially removes low-activity periods and inflates apparent
performance. `coverage` is in `EXCLUDE_COLUMNS` for exactly this reason; using
it as a weight reintroduces the problem through a side door.

**The honest framing.** Observation coverage and target magnitude cannot be
separated with the data available. That is a limitation, not a preprocessing
step. The right instrument is a real observation record, which does not exist.

**Thesis.** Bab IV, as a limitation.

---

## D-11 — All-zero cells are identified before any split

**Decided.** Cells with zero flashes across all seven years are identified and
their handling is recorded. Under a cell-holdout split they must not fall
entirely into test.

**Why.** Six tropis cells — 20% of the 30-cell grid — hold zero flashes across
the whole record. The southern pair is Indian Ocean. The northern four are the
coast around Jakarta and Cirebon, which is not lightning-free, and the fifth
cell in that row does carry flashes; the likelier reading is that the snapped
box reaches past the LDS network's useful range, giving tropis an artificial
zero rim. Under a cell split these six could land entirely in test, where a
model would score perfectly on them for the wrong reason.

**A land mask would not fix the subtropis gradient.** 30,25 / −81,25 is over
land and carries 6.968 flashes against 437.287 at 28,75 / −81,25.

**Dropping all-zero cells is defensible preprocessing.** If taken, record it
here and in Bab III.

**Thesis.** Bab III if cells are dropped, Bab IV either way.

---

## D-12 — NF-01 will not be met at hourly resolution, stated in advance

**Decided.** NF-01 (NRMSE < 0,1 and R² > 0,9) is kept as written, reported as
not met at hourly resolution, and explained.

**Why.** NF-01 was written against a monthly GFD density. At hourly resolution
the target is a count process that is 94–97% zeros, and R² on such a target is
close to meaningless — predicting zero everywhere already explains most of the
variance. A category difference, not a modelling failure.

**What D-04 changes, and by how much.** Less than hoped. At 24 h the tropis
zero share is 64,63%, so R² becomes interpretable but the target is still
zero-dominated. Report NF-01 against every window in the D-04 curve; that is a
far stronger answer than either quietly missing it or quietly redefining it.

**Raise this with the pembimbing before Bab V, not in it.**

**Thesis.** Bab III when NF-01 is restated, Bab V in the evaluation.

---

## D-13 — The default task is a hurdle model, not single-model count regression

**Decided.** `TASK` is a config value taking `"hurdle"`, `"count"` or
`"occurrence"`, defaulting to `"hurdle"`.

- **Stage 1, occurrence.** Binary: did any lightning occur in this cell-window?
- **Stage 2, intensity-given-occurrence.** Regress `log1p(flash_count)` on
  non-zero rows only.
- **Reporting.** Expected count = P(occurrence) × E[count | occurrence],
  converted to GFD units per D-03.

**Why.** The measured window curve in D-04 killed the assumption that a wide
reporting window would make single-model count regression well-conditioned. At
6 hours the target is still 85,40% / 91,35% zeros.

**What it buys.** Stage 1 at a 24-hour window is a 35/65 split in tropis — the
first well-conditioned learning problem in this project. Stage 2 runs on
104.955 tropis and 99.273 subtropis rows, both QNN-tractable without aggressive
subsampling. Stage 1 yields F1 and AUC, which unlike RMSE and R² are not
hostage to the zero share. A hurdle model is the standard treatment for
zero-inflated counts, so it needs no defending.

**Cost.** Two models per configuration instead of one, so the experiment matrix
doubles. `"count"` remains available so the single-model comparison is still
runnable if a reviewer asks for it.

**Thesis.** Bab III for the formulation, Bab IV for the stage-wise results.

---

## D-14 — Sample efficiency was tested and is not supported

**Decided.** The thesis does not claim a low-data advantage for the QNN. It
reports that one was looked for, with adequate replication, and not found.

**What was measured.** `train_rows` at 500 / 1.000 / 3.000, three seeds, on
fold 2. QNN minus parameter-matched NN:

| rows | occurrence (log loss) | count (RMSE) |
|---|---|---|
| 500 | +0,0237 (sd 0,0191) | +0,0054 (sd 0,0513) |
| 1.000 | +0,0274 (sd 0,0142) | +0,0067 (sd 0,0287) |
| 3.000 | +0,0269 (sd 0,0082) | +0,0208 (sd 0,0173) |

Positive is worse. On occurrence the gap exceeds the pooled standard deviation
at every rung and does not shrink across a 6x range of data. On count it is
positive everywhere and widens, clearing the noise only at 3.000.

Improvement over the range: QNN 0,0285, nn_matched 0,0317. The classical model
improves marginally faster, so the gap is flat to slightly widening.

**Why this is a result and not a null.** The constant-offset shape is
informative: if the QNN were data-limited the gap would shrink with n, and if
it were capacity-limited relative to the classical model the gap would grow.
Neither happens on occurrence. The deficit is in representational fit — what
this circuit can express about these features — not in how efficiently it
learns from examples.

**The single-seed near-miss, recorded deliberately.** The first sweep used one
seed and produced a textbook crossover: QNN ahead by 0,0111 on count at 500
rows, behind by 0,0138 at 3.000. Three seeds erased it — the replicated count
gap is +0,0054, +0,0067, +0,0208. The seed-to-seed sd on
that arm is 0,0396, roughly four times the apparent effect. This is what D-06's
replication requirement is for, and it is worth a sentence in Bab IV — a
single-seed quantum-advantage claim is not evidence.

**Cost.** ~80 min for 18 runs per stage.

**Limitation to state.** 500–3.000 rows is a narrow window and all of it small.
An advantage below 500, or a crossover above 3.000, would not appear.
Extending to 10.000 is ~30 min per fit and affordable at one seed.

**Thesis.** Bab IV for the curve, Bab V for the finding and its limitation.

---

## Still open

1. **RESOLVED.** qiskit-machine-learning 0.9.1 has no adjoint gradient; the
   work moved to PennyLane `lightning.qubit` + `adjoint` at 6,97 ms/sample.
   See `RUNBOOK.md` §2 for the full cost surface and D-09.
2. **Subtropis grid dimensions.** D-05. 56 cells; the lat×lon shape decides
   whether 3×3 spatial blocks exist.
3. **Whether the six all-zero tropis cells are dropped.** D-11.
4. **2022-12 and 2024-02.** 2021-03 is a proven MERLIN instrument gap — Iowa
   Environmental Mesonet METAR shows `+TSRA` at KCOF and `LTGICCG OHD` at
   Daytona while MERLIN returned zero CG strikes for the month. The other two
   missing months have not been checked the same way. All three are excluded,
   not filled.
5. **CG/IC composition of the MERLIN export.** MERLIN is 5,7% positive against
   PLN's 14,1% on signed peak current over the full record; low-amplitude
   positive fractions are close (3,1% vs 2,6%). IC contamination raises the
   positive fraction, and MERLIN sits well below the CG-only reference —
   suggestive that the export is CG-only, not conclusive. Confirm against
   archive documentation before Bab III.
