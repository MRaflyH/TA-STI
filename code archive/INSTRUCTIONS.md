# Project instructions — root

Tugas Akhir, Muhammad Rafly (18222067), STI ITB — II4092. Ground flash density
prediction for a tropical domain (Jawa Barat, PLN Puslitbang LDS) and a
subtropical one (Florida, NASA MERLIN), comparing a variational QNN against a
classical ladder, plus the pipeline that builds the tables both read.

**Restructured 10 September 2026.** The project is being finished in one week
across two machines, in five components worked in parallel against a frozen
v1 dataset, with real inputs swapped in at fixed dates.

**This file does not describe the project state.** It carries the precedence
rule, the component map, the contracts that cross components, and the dates.
Everything else lives in a component brief or in the decision record.

---

## 1. Source precedence

When two sources disagree, this order decides:

| Rank | Source | Authoritative for | Not authoritative for |
|---|---|---|---|
| 1 | `config.py` (both) | parameter values — what is actually set | why, or whether it is finished |
| 2 | `DECISIONS.md` (v2) | reasoning, cost, reversal, chapter, attribution, status | current parameter values |
| 3 | `components/*.md` | who owns a decision, what a component's done-criteria are | parameter values; measured figures |
| 4 | source docstrings | what the code does | project state; comments drift |
| 5 | `RUNBOOK.md` × 2 | acquisition history, measured attempts, negative results | anything else |
| — | `README.md` | nothing. Known stale in two places, not being fixed this week. | — |

**Two configs, not interchangeable.** `code/pipeline/src/gfd_data/config.py`
owns acquisition, binning and the build. `code/modelling/src/gfd_model/config.py`
owns the experiment, and imports the pipeline's rather than copying it. Say
which one you mean.

**Never quote a figure from prose when a measured one exists.** Every figure in
the record is tagged `[repo]`, `[derived]` or `[measured]`. Use the tagged
figure; do not paraphrase from memory.

---

## 2. The five components

Each owns a set of decisions and nothing else. A fact that two components need
is a **contract** (§3) and lives here, once.

| # | Component | Brief | Owns | Machine |
|---|---|---|---|---|
| 1 | Data | `components/01-data.md` | acquisition, what exists on disk | Mac |
| 2 | Processing | `components/02-processing.md` | the build, zero handling, feature selection | Mac |
| 3 | Modelling | `components/03-modelling.md` | circuit, provenance, qubit budget, the ladder | either |
| 4 | Training | `components/04-training.md` | backends, splits, runs, metrics | PC |
| 5 | Paper | `components/05-paper.md` | the document, the bibliography, the chapter map | either |

**Parallel working method.** Every component develops against the **frozen v1
tables** and swaps in real inputs at the freeze dates. Two rules make this safe:

1. **Nothing hardcodes a feature count.** Not 13, not 14, not 20. Read the
   length from the config or from the table.
2. **A swap happens on a date, not on readiness.** Whatever has not arrived by
   the freeze becomes Bab VII future work.

---

## 3. Contracts

These cross component boundaries. Changing one is a decision entry, not an edit.

**C-1 — The raw table is wider than the model.** The pipeline may emit any
number of columns. Which the model reads is `FEATURE_COLUMNS` minus
`DROPPED_PREDICTORS`, in the pipeline config, imported by the modelling config.
The two halves must never define a feature set separately.

**C-2 — `EXCLUDE_COLUMNS` is owned by the pipeline and never bypassed.** It
covers the target and its deterministic functions, the five intensity
statistics, `year`, `days_in_month`, `coverage`, and `KX` where dropped.
`dataset.assert_no_leakage` raises rather than warns, deliberately.

**C-3 — The target is `flash_count`, at the same hour, no lead time.** Fit on
`log1p`, invert with `expm1` **before** any aggregation. `gfd_per_km2_per_year`
is for unit-consistent reporting only; it annualises a single hour, so one
flash becomes ~8,766× its rate. The model is a diagnostic to be driven by
forecast fields — see D-N1 in the record and the ERA5-reanalysis caveat.

**C-4 — Test rows are never reshaped.** The test set is the fold's held-out
year, whole, at its natural class ratio. Training rows may be subsampled and
rebalanced; that is a sweep axis.

**C-5 — `coverage` is reported, never acted on.** Not a filter, not a sample
weight. It correlates with the target through lightning activity itself.
Report its distribution beside every metric, and say which weighting (row or
month).

**C-6 — Every parameter tested in Bab IV is reviewed in Bab II, including the
ones that fail.** The candidate list is frozen and written up before the
ablation results are seen.

**C-7 — Decimal comma in the deliverable, decimal point in code and JSON.**
`0,943` and `0.943` are the same number; a copy-paste in either direction is
wrong and silent.

**C-8 — Bahasa Indonesia for deliverables, English for code and records.**

**C-9 — One D-number namespace, globally.** Splitting the decision record per
component is what caused the collision the September 2026 merge had to repair.

---

## 4. Dates

Day 1 is 10 September 2026. Both machines run throughout.

| Day | Mac (data) | PC (compute) | Writing |
|---|---|---|---|
| 1 | freeze v1; launch KX re-pull | benchmark Aer, 10 min | port `.bib`; Bab I |
| 2 | KX lands; launch new params | dry-run reduced Qiskit config | Bab I–II |
| 3 | **RAW FREEZE**; rebuild | — | Bab II, candidate list |
| 4 | correlation / MI / ablation | **Run A overnight** | Bab III |
| 5 | **FEATURE FREEZE** | Run B (15 min); Run C overnight | Bab IV–VI |
| 6 | — | rerun if needed | Bab VI–VII, abstrak |
| 7 | — | — | compile, read the log, buffer |

**Two freezes, not one.**

- **Raw freeze, day 3.** No new CDS or POWER requests after this. Hard date;
  everything downstream waits on the rebuilt parquet.
- **Feature freeze, day 4–5.** Which columns the model reads. A config change
  with no rebuild, so it waits for the ablation.

---

## 5. The decision record

**`DECISIONS.md` v1 is archived, not deleted**, as `DECISIONS-v1-archive.md`.
It holds 46 entries, twelve of which carry an honest "not recorded" attribution
that cannot be rebuilt. A new `DECISIONS.md` starts empty and is written this
week.

**Review method.** Each component brief carries a *carry-forward table* with
three verdicts against the old IDs:

| Verdict | Meaning |
|---|---|
| **carried** | still true, still ours. Re-verified against the config, dated. |
| **revisited** | the decision changes. New entry in v2, citing the old ID as superseded. |
| **dropped** | no longer applies. One line saying why. |

**Scope the review to entries the thesis cites.** A full 46-entry pass does not
fit in a week. Everything not reviewed keeps a banner: *last verified 8
September 2026, not re-checked in the v2 pass.* That is honest and cheap.

**Numbering.** v2 entries are `D-N1`, `D-N2`, … so a v2 ID can never be
confused with a v1 ID in an old comment or an old chapter draft.

---

## 6. Non-negotiables

1. **`Template Baskara/` is never written into.** It exists to diff against.
   Its `daftar-pustaka.bib` is dummy data and must never be cited.
2. **`data/raw/` is irreplaceable.** The PLN records came through the
   supervisors, are not public, and **must not be redistributed**.
   `data/processed/` is one command away and safe to delete.
3. **One environment**, `requirements.txt` at the root, Python 3.13.7,
   everything pinned exactly. Regenerate the lock after any change. A second
   environment for a GPU experiment is a documented exception, not a default.
4. **Cite decisions by ID, and open the entry first.** A D-number quoted from
   memory is worse than no citation.
5. **Do not reconstruct attribution.** "Not recorded" is the accurate record,
   not a gap to fill.
6. **Anything not verified is labelled unverified.** Say exactly that, not more.
7. **Say plainly when something does not exist yet.** Do not imply an
   implementation, a measurement or a decision that has not happened.

Commands run from `code/pipeline/src/` or `code/modelling/src/`, with the venv
active. From the repo root they raise `ModuleNotFoundError`.

---

## 7. Known stale, and not being fixed

Treat as wrong, do not act on, do not cite:

- **`README.md`** — the layout tree calls `code/modelling/` empty and being
  rebuilt, and claims the two domains do not present the same feature set.
  Both false. Line 117 is *not* stale.
- **`RUNBOOK.md` (pipeline)** — five known stale passages: step 1 on the
  `VERIFY with PLN` comment, step 2's window arithmetic, step 4e's three
  disproved `KX` hypotheses and its `*{dom}*.nc` glob bug (`subtropis`
  contains `tropis`), and both positions on the coverage gate.
- **Both RUNBOOKs' reasoning paragraphs generally.** Strip the reasoning, keep
  the measured findings and the negative results. The negatives are the
  expensive part — ERA5 yearly chunking refused by the CDS cost limit, LinComb
  measured 2,5× *slower* than parameter-shift, SPSA's rank-1 gradient. Deleting
  those means someone re-tries them.
