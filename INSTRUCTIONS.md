# Project instructions

Tugas Akhir, Muhammad Rafly (18222067), STI ITB — II4092. Ground flash density
prediction for a tropical domain (Jawa Barat, PLN Puslitbang LDS) and a
subtropical one (Florida, NASA MERLIN), comparing a variational QNN against a
classical ladder.

**One instruction file. One decision record.** No component briefs, no contract
numbering, no parallel document system. If a rule is not in this file, it is
not a rule.

---

## 1. Layout

One repository. The code is one installable package; the data and the paper
sit beside it.

```
.
├── INSTRUCTIONS.md       this file
├── DECISIONS.md          the record
├── requirements.txt      ONE environment, pinned exactly
├── data/                 NOT in git
│   ├── raw/              irreplaceable — see below
│   └── processed/        one command away, safe to delete
├── code archive/         v1. READ-ONLY. Reference only.
├── code/                 the new code — one package, see §3
└── paper/
    ├── Rafly TA/             the thesis being written (II4092)
    ├── Rafly Final Proposal/ submitted proposal (II4091) — 60 real bib entries
    └── Template Baskara/     pristine ITB STI template, reference only
```

**`code archive/` is read-only. Never write into it, never import from it.**
It holds a working pipeline, two built tables, and 432 runs of real results
from 8 September 2026. If this week fails, that is what gets submitted. Read it
to see how something was done; retype what you need into `code/`.

**`data/` sits at the repo root, not inside `code/`**, so no package rename can
move it out from under its gitignore rule.

- `data/raw/` is **irreplaceable.** The PLN records came through the
  supervisors, are not public, and must not be redistributed. Back it up
  outside the repo before anything else.
- `data/processed/` is rebuilt by one command.

**What carries over from the archive:** the proposal's `daftar-pustaka.bib`
(60 verified entries), and the **measured findings and negative results** from
the old RUNBOOKs. Not their reasoning paragraphs.

**What does not:** the old decision record, README, RUNBOOK prose, or any loose
script.

---

## 2. Order of work

**Nothing downloads until the variable list exists.** The CDS queues per
account, so a second request queued behind a first is two sequential downloads.
One list, one job.

| # | Step | Produces |
|---|---|---|
| 1 | **Literature** — candidate meteorological variables, one citation each | the Bab II parameter review, and the download spec |
| 2 | **One acquisition job** — every candidate, both domains, `k_index` among them | `data/raw/` |
| 3 | **Build** — merge to hourly cell tables | two parquets |
| 4 | **Feature selection** — Spearman, mutual information, redundancy, leave-one-out ablation on ridge | the Bab VI table, and the modelled feature set |
| 5 | **Model and train** | results |
| 6 | **Write** | the document |

Steps 1 and 6 need no compute. Bab I and II get written while step 2 runs.

**Two freezes.** No new acquisition after the raw freeze. The modelled feature
set freezes after the ablation, and is a config change with no rebuild.

---

## 3. Code

**One installable package.** `code/` holds one package, `gfd`, with one
`pyproject.toml`. Install it once with `pip install -e code/`. Every command is
`python3 -m gfd.<subpackage>` and runs from anywhere in the repo — no directory
is special, and a replay from a clean checkout is install-then-run.

```
gfd/
├── config.py      shared truths: paths, domains, grid, time key, target
├── dataset/       acquisition, gridding, the join, the column contract
├── selection/     step 4 — screening and ablation
├── models/        estimator definitions only — never fits, never scores
├── training/      folds, subsampling, scaling, the one shared loop
├── evaluation/    metrics, aggregation, the thesis tables
└── experiments/   the matrix runner
```

**The seven names are fixed. The files inside them are not.** A new module
inside a subpackage is an ordinary edit. A new subpackage, a rename, or moving
a concern from one subpackage to another is a `DECISIONS.md` entry. See D-1.

**No loose scripts at any level.** A new capability is a function in the module
that owns the concern, reachable through its subpackage's entry point. A
supplementary ERA5 request belongs inside `dataset/era5.py`, not in a file
beside it. Anything invisible to `python3 -m` is invisible to a replay.

**A constant lives in `gfd/config.py` if two subpackages disagreeing about it
would be silent; otherwise it lives beside the code that uses it.** CDS request
shapes and ansatz reps are local. Paths, the grid, the time key and the target
are not.

**`dataset/features.py` owns the column contract, and nothing else defines
one.** Three lists: `EXCLUDE`, never a predictor, covering the target and its
deterministic functions, the intensity statistics, `year`, `days_in_month` and
`coverage`; `CANDIDATES`, everything acquired, frozen at the raw freeze;
`MODELLED`, what survives the ablation. `selection/` writes `MODELLED`,
`models/` reads it, nothing counts it. The leakage assertion raises rather than
warns, and is never bypassed.

**The built table is wider than the model.** `dataset/` may emit any number of
columns; the model reads `MODELLED`. **Nothing hardcodes a feature count** —
not 13, not 14, not 20. Read the length from the contract or from the table.

**A fitted model carries its own scaler.** `training/` returns the model and
the scaler it was fitted with, together. `evaluation/` scores what it is handed
and has no way to reach for a different one.

**Never rebuild something the package already defines.** A benchmark that
constructs its own circuit can measure a different circuit from the one that
trains. Import the real builder.

**One environment.** `requirements.txt` at the root, Python 3.13.7, pinned
exactly, plus `pip install -e code/`. Regenerate the lock after any change.

---

## 4. The target

`flash_count`, hourly, at the same hour as the predictors — no lead time. Fit
on `log1p`; invert with `expm1` **before** any aggregation, never after.

The model is a **diagnostic**: it maps a meteorological state onto the
lightning in that state, and becomes a forecast when driven by forecast fields
from an NWP system. ERA5 is a reanalysis, so measured skill is an upper bound
on operational skill. Say so in the thesis.

The target is 94–97% zeros at hourly resolution. That is the shape of the
problem, not a defect to engineer away. **Do not fill zeros from other
metrics** — that manufactures a target. Report the zero share beside every
metric.

`coverage` is **reported, never acted on.** Not a filter, not a sample weight;
it correlates with the target through lightning activity itself.

**Test rows are never reshaped.** The test set is the held-out year, whole, at
its natural class ratio. Training rows may be subsampled.

---

## 5. Justification

The dosen's requirement, and it shapes the document:

- **Bab II** establishes the candidate list from literature. That answers *why
  these N variables*.
- **Bab VI** measures them. That answers *why the M that survived*.
- **Bab II must cover every variable tested, including the ones that fail.** A
  variable in the results table but absent from Bab II looks arbitrary; one
  reviewed and then dropped in silence looks buried.

So the candidate list is frozen and written up **before** the ablation results
are seen.

Screen on **Spearman and mutual information**, not Pearson — Pearson detects
only straight-line relationships and would discard a variable that matters
above a threshold. Confirm with **leave-one-out ablation**, which is the
strongest justification available and what Bab VI should lead with.

---

## 6. Writing

Bahasa Indonesia for the deliverable, English for code and records. **Decimal
comma in the thesis, decimal point in code and JSON** — the same number, and a
copy-paste in either direction is wrong and silent.

Seven chapters: I Pendahuluan, II Studi, III Analisis, IV Perancangan,
V Implementasi, VI Evaluasi, VII Penutup.

`Template Baskara/` is **never written into**. It exists to diff against, and
its `daftar-pustaka.bib` is dummy data that must never be cited.

**Never trust a compile that "worked" without reading the log** — and read the
log in the directory you compiled, not the template's own.

**Declare rather than let an examiner discover.** Each of these is defensible
only if stated outright: subtropis results are provisional until the MERLIN
CG/IC question is settled; hyperparameters with no recorded reasoning are a
stated limitation, not a gap to fill; ERA5 is a reanalysis; the
detection-efficiency falloff with distance from the Cape is a confound that
MERLIN alone cannot separate from climatology.

---

## 7. Records

**One `DECISIONS.md`.** A decision gets an entry when it is made: what was
decided, why, what it costs, how to reverse it, which Bab, and who decided it.
Numbered `D-1`, `D-2`, … in one global namespace.

**Do not reconstruct attribution.** "Not recorded" is the accurate record.

**Never quote a figure from prose when a measured one exists.** Tag every
figure `[repo]`, `[derived]` or `[measured]`. A derived estimate that
contradicts a measurement is wrong, and the measurement is usually already in
the file.

**Say plainly when something does not exist yet.** Do not imply an
implementation, a measurement or a decision that has not happened. Anything
unverified is labelled unverified — exactly that, and no more.
