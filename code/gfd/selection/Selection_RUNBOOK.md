# RUNBOOK — `gfd.selection`

Built tables to a committed feature set. Reasoning lives in `DECISIONS.md`;
this is the sequence and what to expect from it.

Four modules, run in order. Each writes JSON to `data/processed/`; the last
also writes `code/gfd/dataset/modelled.json`, which is the output everything
downstream reads.

---

## 1. Before anything

Both tables must already be built — see the dataset RUNBOOK. `config.py` raises
on import if `data/raw/` is missing, and `selection/` raises if the parquets
are not there.

```
data/processed/
├── gfd_tropis_hourly.parquet       1 841 040 x 41
├── gfd_tropis_hourly.meta.json
├── gfd_subtropis_hourly.parquet    3 436 608 x 41
└── gfd_subtropis_hourly.meta.json
```

`dataset/features.py` must be the version carrying `modelled(domain, stage)`
and `modelled_shared(stage)`. The older single-list version cannot load what
`screen.py` writes, and the failure appears at training time rather than here.

```bash
python3 -c "from gfd.dataset import features as f; print(f.STAGES)"
```

Prints `('occurrence', 'count')` if the contract is current.

---

## 2. The sequence

```bash
python3 -m gfd.selection.description    # stage 1 — measure the table
python3 -m gfd.selection.diagnosis      # stage 2 — measure the problems
python3 -m gfd.selection.screen         # steps 2-5 — derive, exclude, rank, select
python3 -m gfd.selection.ablate         # step 6 — confirm
python3 -m gfd.selection.prepare        # the chain, for inspection
```

`prepare.py` owns the derived features and the scaling classes. It is the only
module here that changes a value, and `screen.py` and `ablate.py` import the
derivations from it rather than rebuilding them.

`ablate` imports from `screen` and re-derives the selection rather than reading
it from disk, so `screen` does not strictly have to run first — but it should,
because it is what writes `modelled.json`.

Each takes `--domain tropis` or `--domain subtropis` to run one, and `--no-json`
to print without writing. **`screen` needs both domains to write
`modelled.json`**, because the shared set is ranked on the two pooled; with
`--domain` it prints the per-domain ordering and skips the write.

---

## 3. `description` — stage 1

A few minutes. Writes `description_{domain}.json`.

Eight sections: contract and shape, duplicates, missingness, per-column
distributions, the target, coverage, predictor redundancy, and tails.

**Three things it raises rather than reports.** Rows not equal to cells × hours.
Any duplicate `(lat, lon, time)`. And meta drift — the table compared against
the `.meta.json` that built it, which catches a stale parquet that still
satisfies the column contract.

Expected:

| | tropis | subtropis |
|---|---|---|
| rows | 1 841 040 | 3 436 608 |
| cells × hours | 30 × 61 368 | 56 × 61 368 |
| zero share | 0,9430 | 0,9711 |
| dead cells | 6 | 0 |
| `CIN` missing | 0,2352 | 0,4638 |
| coverage, row-weighted | 0,8549 | 0,5710 |

Lines worth reading rather than skimming:

- `unclassified none` and `missing none`. These print even when empty, on
  purpose — a tripwire that only prints when it fires is one nobody knows is
  armed (O-9).
- `meta drift none`.
- The `mass` column in section D. `CRR` at 0,605 subtropis is the largest point
  mass in the table and its median is zero.
- Section H, the `n` columns. Every detached maximum is held by **one** row. A
  large `n` at an extreme would be a fill value, not an observation.

**Do not quote `mean_coverage` from a `.meta.json`.** It is wrong — 0,6907 and
0,5156, matching neither weighting. `dataset/` is frozen, so it is not
corrected. Section F has the right numbers.

---

## 4. `diagnosis` — stage 2

A few minutes; the zero-run computation sorts 5,3 million rows. Writes
`diagnosis_{domain}.json` and `diagnosis_cross_domain.json`.

Four sections: missingness against its partner variable, zero structure,
cross-domain maps, and temporal structure.

This module **may** put a predictor against the target, which stage 1 may not.
That is what it is for, and it is why the two are separate files (D-18).

Expected:

- `CIN` null rate falls monotonically down `CAPE`'s deciles — 0,9885 to 0,0001
  subtropis. The blank is a threshold on `CAPE`, not a data failure.
- A negative binomial predicts **more** zeros than observed: 0,9858 against
  0,9711 subtropis, 0,9639 against 0,9430 tropis. The target is not
  zero-inflated.
- Zero runs, median 20 h subtropis and 15 h tropis; 90,66% and 74,25% of zero
  rows inside runs longer than a day.
- Tropis 22 of 24 live cells diurnally dominated; subtropis 13 of 56, with peak
  hours spanning sixteen values and diurnal amplitude collapsing eastward.
- The bounded map beats min-max on cross-domain resolution in 35 of 36
  column-arm pairs.

---

## 5. `screen` — steps 2 to 5

The longest run: five seeds × two arms × two targets × two domains, plus the
shared pooled ranking. Mutual information by nearest neighbours on 200 000
sampled rows is the bulk of it. Allow ten minutes or so.

Writes `screen_{domain}.json`, `screen_shared.json`, and
**`code/gfd/dataset/modelled.json`**.

Feature counts per arm: `full` 25, `meteorology` 18, `shared` 23.

Expected at N = 15:

- **Nine meteorological to six climatological** in all four per-domain sets.
  `hour_cos` is in none of them — redundancy 0,988 and 0,993 once `hour_sin`
  and `cos_sza` are chosen.
- Stage agreement: subtropis 11 of 15 full, 14 of 15 meteorology; tropis 13 of
  15 and 15 of 15.
- `[check] modelled.json loads through features.py, all six sets`. The module
  reads its own output back through the contract after writing. A file the
  contract cannot load is worse than no file, because nothing downstream would
  notice until it ran.

**Read the stability column.** `in top-k` is the share of five seeds placing a
feature inside the top N. The per-domain sets are 1,00 almost throughout. The
**shared** set is not: `cloud_water` at 0,40 and `TCLW` at 0,60 in occurrence,
`TCWV` 0,60 and `WS2M` 0,40 in count. Those last slots are genuinely unsettled
and Bab VI reports them as such.

**The score column is not monotone down the list**, and that is not a bug.
Redundancy is measured against the chosen set, so admitting a near-uncorrelated
feature lowers a waiting candidate's penalty and raises its score.

---

## 6. `ablate` — step 6

Fits the full model then refits once per feature, for four sets per domain, at
N = 15 and then at each swept width. Several minutes. Writes
`ablation_{domain}.json`.

`--sweep 8 12 15 18` by default; `--sweep 15` alone shortens it to the chosen
width, which is what to use once the curve is recorded. 18 is the ceiling
because the `meteorology` arm has only 18 features.

A final section prices `CIN` and `CBH` on rows where both are defined — the
side measurement D-19 owed. It reshapes the test set deliberately and reports
on a convective sub-population, and says so; it is never a headline number.

Two outputs. The per-feature deltas, where `<-` marks a feature whose removal
left the model equal or better. And the **climatology gap**, `full` against
`meteorology` on the same rows with the same estimator — how much of the skill
survives when nothing knowable in advance of the weather is allowed.

Expected at N = 15: tropis occurrence 0,3620 full against 0,2637 meteorology;
subtropis 0,2712 against 0,2851.

**Read the gap across widths, never a single N.** At N = 10 the subtropis
meteorology arm beats the full arm by a wide margin, and that is a budget
artefact — the full arm spends six of ten slots on space and time. The share
falls from 2,031 to 1,058 as N grows. A single-width reading of that number is
wrong.

**Ridge and logistic regression stand in for the QNN.** They under-value
non-monotone features: `VIIWD` ranks top-nine on mutual information in both
domains and 13th–19th here. Read the ablation beside the screen, not instead of
it.

---

## 7. What the output means

`modelled.json`:

```json
{"within": {"tropis":    {"occurrence": [...15...], "count": [...15...]},
            "subtropis": {"occurrence": [...15...], "count": [...15...]}},
 "shared":               {"occurrence": [...15...], "count": [...15...]},
 "meta":   {"n": 15, "arm": "full", "test_year_held_out": 2024, ...}}
```

Read it through `features.py`, never by parsing it directly:

```python
from gfd.dataset import features as feat
feat.modelled("tropis", "occurrence")   # the within-domain model's inputs
feat.modelled_shared("count")           # the transfer arms' inputs
```

Both check leakage. `modelled` also enforces equal width across domains within
a stage (D-24); `modelled_shared` raises if `lat` or `lon` appear (D-27).

A modelled name need not be a table column. `cloud_water`, `hour_sin` and the
rest are derived in `selection/` under D-21 step 2, and `prepare.py` is what
will build them for training.

---

## 8. Provisional, and what has never run

Stated because it should not be claimed otherwise.

- **The split is provisional.** 2024 is held out because it is the most
  representative year in both domains and because training on the past and
  testing on the future matches deployment — but S-8 is open and the validation
  scheme is undecided.
- **The ablation's scaling is provisional.** Features are standardised on
  training rows; S-5 and S-6 are open. The mRMR **ordering** is not affected —
  relevance and redundancy are both rank-based and survive any monotone
  rescaling — but the ablation deltas are.
- **`selection/prepare.py` exists and declares the chain** (D-18, D-28, D-29,
  D-30). `training/` has not been written, so nothing executes it per fold yet;
  the parameters `prepare.py` prints come from all training years at once and
  are for inspection only.
- **Both owed measurements are done.** `cos_sza` does not inherit latitude's
  cross-domain failure — 0,3438 and 0,2515 against `lat`'s 0,0004 — so D-27
  stands. And the complete-case ablation priced `CIN` at +0,0242 and +0,0216
  PR-AUC on rows where it is defined, with `CBH` worth nothing. D-19 is not
  reversed; the limitation now carries a number.

---

## 9. A failure that has happened three times

A module was edited, copied into the repo, run — and produced the previous
version's output, because the copy had not landed. It is not obvious from the
output unless you know what changed.

If a run looks like the last one:

```bash
grep -c "<a string only the new version has>" code/gfd/selection/<module>.py
python3 -c "from gfd.selection import screen; print(screen.__file__)"
```

The first tells you whether the file on disk is the new one; the second tells
you which file Python is actually importing.
