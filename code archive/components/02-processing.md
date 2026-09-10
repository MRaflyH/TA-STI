# Component 2 — Processing

**Owns:** the build, zero handling, and feature selection.
**Does not own:** acquisition (C1), the qubit budget (C3), the splits (C4).
**Machine:** Mac. **Config:** `code/pipeline/src/gfd_data/config.py`.
**Hard dates:** rebuild day 3, feature freeze day 4–5.

This is the component with the most revision. Develop everything against the
frozen v1 tables and re-run against the rebuilt ones on day 4.

---

## 2.1 — Zero handling

The target is 94,30% zeros (tropis) and 97,00% (subtropis) at hourly
resolution **[measured, 2026-09-06]**. That is the shape of the problem, not a
defect to engineer away.

**Three kinds of zero, and they are handled differently:**

| Kind | Meaning | Handling |
|---|---|---|
| true zero | quiet sky, network up | kept, explicit |
| censored zero | network down, sky unknown | **cannot be identified** — see below |
| structurally absent | no export at all | excluded, not filled |

**Do not fill zeros from other metrics.** That manufactures a target.

**The censored-zero problem, stated honestly.** The observation proxy is "a day
with at least one strike somewhere in the domain is a day the network was up",
so a genuinely quiet month and a dead detector look identical. Subtropis has 56
of 81 months below 90% day-coverage. Nothing in the dataset separates these.

The only instrument that would is an external observation record built from
METAR: a day when a station inside the box reports `TSRA` while the network
logged zero strikes is a day the network was not working. **If it is built it
must be built for both domains** — West Java has METAR stations too (Husein
Sastranegara, Soekarno-Hatta, Halim) — or it injects a domain-dependent
selection effect into the one comparison the TA exists to make.

**Not a week-of task.** It goes in Bab VI/VII as the named instrument for a
limitation that is stated rather than solved.

**Empty months.** The three fully-empty MERLIN months are excluded. C1 task 1.4
re-tests whether they are recoverable first. **Further study is agreed as
in-scope** — the question is whether the 56 low-coverage months should also be
excluded, and the answer cannot be "yes" without the instrument above, because
excluding low-coverage months preferentially removes low-activity periods and
inflates apparent performance the same way weighting would.

**What the literature offers, and what to cite.** Zero-inflated and hurdle
models are the standard treatment for this data shape. The current design is a
**hurdle**: stage 1 predicts occurrence (binary, all rows), stage 2 predicts
`log1p(flash_count)` on non-zero rows only (104.955 tropis, 99.273 subtropis).
Bab III should cite the hurdle/zero-inflated literature rather than presenting
this as an ad-hoc two-stage design.

---

## 2.2 — Feature selection

This is what answers the dosen's "justify every choice", and it has three
stages, each producing a number.

**Stage 1 — the candidate list (why N features).** Literature. Every candidate
has a citation, written into Bab II, drafted with Component 5, frozen day 3.
Includes candidates that later fail (contract C-6).

**Stage 2 — the statistical screen (why these survive).** Two measures, both
run against the rebuilt table:

- **Spearman rank correlation** — detects any consistently increasing or
  decreasing relationship, not only straight-line ones.
- **Mutual information** — detects any relationship at all, including
  thresholds and humps.

**Do not screen on Pearson.** It only detects straight-line relationships and
will discard a feature like CAPE that matters chiefly above a threshold. The
QNN does not require a linear relationship: with a `z` feature map each feature
enters as a bounded trigonometric function of its own scaled value, which is
already nonlinear per feature. What the `z` map does *not* give is feature
interaction — that comes from entanglement in the ansatz. So interaction
questions are settled by ablation, not by a correlation matrix.

**Stage 3 — leave-one-feature-out ablation (the strongest justification).**
Retrain without each feature and report how much worse the model gets. Run it
on **ridge**, not the QNN — it is seconds per fit rather than minutes, and the
question is about the feature's information content, not the model.

**Report redundancy too.** A feature-to-feature correlation matrix identifies
pairs carrying the same information; the ablation shows which of a redundant
pair to keep.

**Output:** the Bab IV feature-selection table. Its shape is known in advance;
only its contents wait on the run.

---

## 2.3 — Build

`python3 -m gfd_data.build`, from `code/pipeline/src/`. Produces per domain a
parquet and a `.meta.json` config snapshot.

**Checks after the rebuild:**

- [ ] no NaN in any predictor (v1 had none in either table; if the new
      parameters introduce any, that is a decision, not a fix)
- [ ] `!! absent features:` line reports nothing unexpected
- [ ] row counts match cells × hours
- [ ] zero share re-measured and recorded — the v1 figures are void once the
      table changes
- [ ] `coverage` distribution re-measured, and **say which weighting**. The v1
      row-weighted figures were tropis mean 0,8549 min 0,1290; subtropis mean
      0,5921 min 0,0323 **[measured]**. An earlier month-weighted version gave
      tropis 86%.

**Time key is `time`, not `month`.** Anything reading `df["month"]` is stale.

**Trap.** `year` and `days_in_month` are numeric columns that are **not**
predictors. Anything selecting features as "every numeric column that is not
the target" picks them up. That is what `EXCLUDE_COLUMNS` exists for
(contract C-2).

---

## 2.4 — Intensity columns

Kept in the table, excluded from modelling. Two traps if the output ever
changes to intensity:

1. They are in `EXCLUDE_COLUMNS` and `assert_no_leakage` **raises**. Switching
   is a deliberate config change, not a flag.
2. **The units are not comparable across domains.** PLN's is labelled kA;
   MERLIN's is not the same quantity. An intensity target is not
   cross-domain-portable as things stand.

Also: they are NaN wherever `flash_count == 0`, which is correct — the mean
intensity of no strikes is undefined, not zero.

---

## Done-criteria

- [ ] Both tables rebuilt from the day-3 raw freeze
- [ ] Spearman, MI, redundancy and ablation tables produced
- [ ] Modelled feature set frozen and written into the pipeline config
- [ ] Zero share and coverage distribution re-measured and recorded
- [ ] Every dropped feature has a stated reason

---

## Carry-forward from v1

| Old ID | Subject | Verdict | Note |
|---|---|---|---|
| D-15 | 0,5° grid, boxes snapped outward | carried | |
| D-16 | Bin labelling UTC, forced, at hourly | carried | |
| D-19 | Empty cells filled with explicit zeros | carried | |
| D-20 | Zero inflation carried and reported | carried | cite hurdle/ZI literature this time |
| D-13 | Default task is a hurdle model | carried | |
| D-03 | Fit `log1p(flash_count)`; report in GFD units | carried | invert **before** aggregating |
| D-08 | Intensity built in, used later | carried | units caveat above |
| D-18 | Coverage gate off, `MIN_COVERAGE = 0.0` | carried | Rafly's call over an objection |
| D-10 | `coverage` reported, never acted on | carried | contract C-5 |
| D-11 | All-zero cells identified before any split | carried | six tropis cells, 20% of the grid |
| D-02 | 13 base predictors, hour encoding as an axis | **revisited** | feature count changes |
| D-35 | Min-max onto [0, π], clipped, fitted on train alone | carried | |
| D-40 | Standardise → PCA → min-max → clip | **revisited** | PCA becomes structural, not an ablation — see C3 |
| D-24 | The AOD broadcast | **dropped** | AOD removed entirely |

---

## Open

- Whether the 56 low-coverage subtropis months are excluded. Needs the METAR
  instrument, which does not exist.
- Whether the six all-zero tropis cells are dropped. `DROP_ALL_ZERO_CELLS =
  False`, off by default so the choice stays visible. Dropping is defensible;
  keeping is defensible. What is not defensible is letting them fall entirely
  into a test fold under a cell-holdout split.
- Subtropis grid shape. 56 cells; the lat×lon dimensions decide whether 3×3
  spatial blocks exist. One line to read off the table.
