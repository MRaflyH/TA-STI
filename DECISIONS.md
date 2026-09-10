## D-1 — One installable package, seven fixed subpackages

**Decided.** `code/` holds one package `gfd`, installed with
`pip install -e code/`, with seven subpackages whose names are fixed:
`dataset`, `selection`, `models`, `training`, `evaluation`, `experiments`, plus
a root `config.py`. Module layout inside each subpackage is free. v1's split
into `code/pipeline/src/gfd_data/` and `code/modelling/src/gfd_model/` is not
carried over.

**Why.** Three failures recorded in v1, each traceable to the two-package
layout:

- Commands only ran from `code/pipeline/src/`; from the repo root they raised
  `ModuleNotFoundError`. A `src/` layout with nothing installed contradicts the
  `python3 -m` replay rule it was supposed to satisfy.
- Two `config.py` files owned overlapping truths. The archive records the two
  layers disagreeing about whether `KX` was dropped, and the pipeline config
  citing a modelling decision by the wrong number.
- `experiments.py` fitted, owned the scalers, applied the smearing correction
  and evaluated cross-domain in one file. Both bugs recorded against it were
  coupling bugs across those four jobs.

Separating `models` / `training` / `evaluation` is not justified by those bugs
but by rate of change: the circuit, the optimiser, and the Bab VI tables change
for different reasons, and the tables will change repeatedly during writing.

**Cost.** A `pyproject.toml` and one install step before anything runs. Seven
subpackages is more structure than a one-person project strictly needs, and
`selection/` is being sized before any of it is written.

**Reversal.** Renaming a subpackage is a find-and-replace across `code/` plus
a RUNBOOK edit. Collapsing two subpackages into one is a file move and an
import fix. Neither touches `data/` or any built table. Reverting to the v1
two-package layout would mean re-splitting `config.py`, which is the thing this
decision exists to prevent.

**Bab.** V (Implementasi) carries the layout. III and IV reference `dataset/`
where the data preparation is described.

**Decided by.** Rafly, 2026-09-10.

**Status.** Layout decided 2026-09-10 when no file under `code/` existed.
Since then `config.py`, `dataset/features.py`, `dataset/lightning.py` and
`dataset/era5.py` are written and the package installs. `dataset/power.py` and
`dataset/build.py` are not. `selection/`, `models/`, `training/`,
`evaluation/` and `experiments/` are still names only.

---

## D-2 — Hourly only; the daily and monthly paths are deleted

**Decided.** One training row is one clock hour. v1's three-way `TIME_FREQ`
switch is gone, along with `ERA5_DAILY_STATS`, `_daily_partials`,
`_finalise_daily`, `fetch_year_monthly`, the monthly CDS product and
`TZ_MODE`. `TIME_FREQ` survives as a constant because filenames and log lines
read it; `FREQ_ORDER` survives only to decide whether a POWER parameter needs
broadcasting.

**Why.** Nothing was ever built at daily or monthly, and the branches were
roughly a third of the dataset layer. Every one of them was a path that could
go stale without anyone noticing, because nothing exercised it. `TZ_MODE` could
only ever hold `"utc"` once hourly was the only resolution, so it was a setting
with one legal value.

**Cost.** The predecessor study aggregated monthly, so a monthly build was the
only artifact that could ever have been set beside Fadhil Amri's numbers. That
comparison is now unavailable without writing the path back. Bab VI loses a
possible baseline table.

**Reversal.** Not a config change. Re-adding a resolution means restoring the
collapse functions in `era5.py`, the regional endpoints in `power.py`, the
period logic in `lightning.py`, and a branch in `build.py`. Half a day, and the
v1 versions are in `code archive/` to copy from.

**Bab.** III (why hourly), V (what the code does).

**Decided by.** Rafly, 2026-09-10.

---

## D-3 — The target is `flash_count`, not GFD

**Decided.** `cfg.TARGET = "flash_count"`. Fit on `log1p`, invert with `expm1`
before any aggregation. `gfd_per_km2_per_year` stays in the table as
`cfg.TARGET_REPORTING` — a reporting unit, never a fit target.

**Why.** At hourly resolution the annualised density is a count process wearing
a density's units: a single flash in one hour annualises to ~8766 times its
per-hour rate, producing a spike-or-zero distribution. v1 already printed a
warning saying exactly this on every hourly build while still carrying
`gfd_per_km2_per_year` as `TARGET_COLUMN`, so the code disagreed with itself.

**Cost.** Every reported number needs converting to GFD units for the thesis,
and the conversion has to happen after `expm1`, not before. One more place to
get an ordering wrong.

**Reversal.** A one-line config change, but it would reinstate the
distributional problem rather than solve it.

**Bab.** IV (what the model predicts), VI (units in every results table).

**Decided by.** Rafly, 2026-09-10. Follows INSTRUCTIONS §4.

---

## D-4 — KX is re-acquired by supplementary request. Supersedes v1 D-01

**Decided.** `k_index` is a candidate predictor for both domains. The 84
missing subtropis months are fetched by single-variable request
(`--supplement k_index --domain subtropis`) and merged in `load_era5`. v1's
D-01, which dropped KX from both domains for cross-domain symmetry, no longer
applies.

**Why.** The asymmetry was real and is confirmed rather than assumed:
`--check` on the files shows tropis carrying all six short names and subtropis
five, with nothing unmapped alongside, so it is not a short-name miss. But the
CDS serves `k_index` for the subtropis box when it is asked for alone. Dropping
a variable that can be obtained is worse than spending 84 requests, and K index
is one of the fourteen predictors the predecessor used, so dropping it also
weakened that comparison.

**Cost.** 84 CDS requests, queued. A second file naming convention in
`data/raw/era5/`, and a merge step in `load_era5` that has to stay correct.
Breaks the raw freeze in the sense of §2 — but the freeze had not yet been
declared, because the candidate list is still moving.

**Reversal.** Delete the `_kx` files and put `"KX"` back in `EXCLUDE`. Nothing
downstream needs rebuilding, because the modelled set is read from
`features.MODELLED`, not counted.

**Bab.** II (K index reviewed as a candidate), IV (why the feature set is
symmetric across domains).

**Decided by.** Rafly, 2026-09-10.

**Status.** Download running at the time of writing. **Not yet verified that
the supplementary files actually contain `kx`.**

---

## D-5 — AOD_55_ADJ is dropped from the POWER request

**Decided.** `AOD_55_ADJ` is not requested and is not a candidate predictor.
The two already-downloaded regional files stay on disk.

**Why.** POWER publishes it monthly and nothing finer, so at hourly resolution
it is held constant across roughly 730 consecutive rows. A feature that cannot
vary hour to hour cannot explain hour-to-hour variance in the target.

**Cost.** One fewer aerosol-related variable, in a literature where aerosol
loading is argued to affect lightning. Bab II should say the variable was
considered and rejected on resolution grounds rather than omit it — a reviewer
who knows the aerosol literature will look for it.

**Reversal.** Add it back to the POWER parameter list; the raw files are
already there, so no re-download. The broadcast machinery is deliberately kept
for this reason and for whatever the literature step turns up.

**Bab.** II (considered and rejected), IV.

**Decided by.** Rafly, 2026-09-10.

**Status.** **Decided, not implemented.** `features.POWER` still lists it and
`power.py` does not exist yet.

---

## D-6 — `config.py` raises on a missing `data/raw`, never creates it

**Decided.** Import-time `mkdir` covers `data/interim` and `data/processed`
only. A missing `data/raw` raises, and the message prints the resolved
`PROJECT_ROOT`.

**Why.** v1 created all six directories at import. A wrong repo root then built
an empty tree, and the first visible error was "no ERA5 files — run
fetch_domain() first", which reads as *you have not downloaded yet* when the
truth is *you are looking in the wrong place*. With 583 MB of irreplaceable
data sitting elsewhere on disk, that is a believable lie. The move of `data/`
from `code/pipeline/data/` to the repo root is exactly the change that would
have triggered it.

**Cost.** A fresh clone cannot import `gfd` until the raw data is restored from
backup. That is intended, but it means the package is not importable for
someone who only wants to read the code.

**Reversal.** One line.

**Bab.** V.

**Decided by.** Not recorded — proposed during implementation and not
separately ratified.

---

## D-7 — Two of v1's four smoke modules survive, as validations

**Decided.** The diurnal check becomes `lightning.check_diurnal`, and the
ERA5 variable check becomes `era5.check_variables`. `smoke_power` and
`smoke_build` are not carried over. No module is named `smoke_*`; each check
lives in the module that owns the concern, per INSTRUCTIONS §3.

**Why.** `smoke_power` and `smoke_build` existed to protect a download before
it happened. All four acquisitions are complete, so that job is finished. The
other two are not tests — the diurnal histogram is the evidence that settled
the PLN clock and belongs in Bab III, and `check_variables` is what caught the
KX absence.

**Cost.** `smoke_build`'s key-overlap check is lost, and it guarded a real
failure: a left join whose right side has no matching keys returns an all-NaN
block without raising. That check should be rebuilt inside `build.py` rather
than left out.

**Reversal.** The v1 modules are in `code archive/`.

**Bab.** III (the diurnal validation), V.

**Decided by.** Not recorded — proposed during implementation and not
separately ratified.

---

## Open

**O-1 — The calendar columns.** `hour_of_day_local` has a clear physical
reading and points the same way in both domains. `month_of_year` and
`day_of_year` carry seasonal phase, which is inverted between the domains and
could inject a domain artefact into the cross-domain transfer number.
`hour_of_day_utc` is `hour_of_day_local` shifted by a constant. Deferred until
the literature step; `build.py` emits all of them regardless, so the decision
is a `features.py` edit with no rebuild.

**O-2 — Whether the lock is one file or two.** `requirements.txt` currently
holds both the pins and the reasoning, so regenerating it with `pip freeze`
destroys the comments — which has already happened once. The alternative is a
generated-only `environment-lock.txt` beside it. v1's D-41 was caused by two
files disagreeing after one was hand-edited, not by there being two.