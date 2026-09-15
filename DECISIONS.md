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

**Status.** `dataset/` is complete and frozen (D-15): `features.py`, `lightning.py`, `merlin.py`,
`era5.py`, `power.py`, `build.py`, plus the root `config.py`. The package
installs and tropis builds end to end. `selection/`, `models/`, `training/`,
`evaluation/` and `experiments/` are still names only — no file exists in any
of them.

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

**Status.** Done. All 84 supplementary files present and merged; the subtropis
build reports `merging 84 [kx] files` and carries all six ERA5 columns
**[measured]**. Both domains now hold the same 13 predictors.

---

## D-5 — AOD_55_ADJ is dropped from the POWER request

**Decided.** `AOD_55_ADJ` is not requested and is not a candidate predictor.
The two already-downloaded regional files stay on disk.

**Why.** POWER publishes it monthly and nothing finer, so at hourly resolution
it is held constant across roughly 730 consecutive rows. A feature that cannot
vary hour to hour cannot explain hour-to-hour variance in the target.

**Not** because the data is thin. v1's config called it "(sparse!)" and never
checked; it is complete — 756 records, 9 points × 84 months, zero missing,
2018-01 to 2024-12 **[measured]**. Bab II should say resolution and not repeat
the sparsity claim.

**Cost.** One fewer aerosol-related variable, in a literature where aerosol
loading is argued to affect lightning. Bab II should say the variable was
considered and rejected on resolution grounds rather than omit it — a reviewer
who knows that literature will look for it.

**Reversal.** Add it back to `power.PARAM_FREQ` and to `features.POWER`; the
raw files are already there, so no re-download. The broadcast machinery is
deliberately kept for this reason and for whatever the literature step turns
up.

**Bab.** II (considered and rejected), IV.

**Decided by.** Rafly, 2026-09-10.

**Status.** Implemented. `power.PARAMS` and `features.POWER` both hold the same
five parameters.

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

**Decided.** The diurnal check becomes `lightning.check_diurnal`, the ERA5
variable check becomes `era5.check_variables`, and the POWER file inventory
becomes `power.check_files`. `smoke_power` and `smoke_build` are not carried
over as modules. Nothing is named `smoke_*`; each check lives in the module
that owns the concern, per INSTRUCTIONS §3.

**Why.** `smoke_power` and `smoke_build` existed to protect a download before
it happened. All four acquisitions are complete, so that job is finished. The
others are not tests — the diurnal histogram is the evidence that settled the
PLN clock and belongs in Bab III, and `check_variables` is what caught the KX
absence.

**Cost.** None outstanding. `smoke_build`'s key-overlap check was the one real
loss and it is rebuilt as `build._check_keys`, which **raises** on a dtype
mismatch or zero overlap and warns below 50%. It guards the failure v1
recorded: a left join whose right side has no matching keys returns an all-NaN
predictor block without raising.

**Reversal.** The v1 modules are in `code archive/`.

**Bab.** III (the diurnal validation), V.

**Decided by.** Not recorded — proposed during implementation and not
separately ratified.

---

## D-8 — `dataset/` keeps every month. Row and column selection is `selection/`

**Decided.** The built table is a complete grid: every configured month for
every cell, including months holding no strike records at all. Empty months
carry `observed_days = 0` and `coverage = 0`. `MIN_COVERAGE` stays at 0.0 and
`dataset/` never drops a row on coverage grounds. Removing months, filtering
rows and choosing columns are `selection/`'s job and get narrated there.

**Why.** A dropped row cannot be examined. Keeping it with `coverage = 0`
attached means the zero says of itself that it is an absence of observation
rather than an observation of absence — nothing is manufactured and nothing is
lost, and the filter becomes a decision made on a labelled column, on evidence,
in the place that owns row and feature selection.

It also makes the domains structurally comparable: both tables span the same 84
months whatever their detectors were doing.

**Cost.** The reported zero share now mixes observed zeros with unobserved
ones, so **zero share must be reported beside mean coverage**, or beside the
zero share over `coverage > 0` rows. Tropis is 94.30% zeros with all 84 months
observed; a subtropis figure computed the same way may not mean the same thing.
Rows at `coverage = 0` also carry real ERA5 and POWER values against a target
that was never observed — exactly the kind of row a model will happily fit.

**Reversal.** Raise `cfg.MIN_COVERAGE` above 0. That reinstates dropping inside
`dataset/` and requires a rebuild.

**Bab.** III (what the table contains), IV (how coverage is handled and
reported).

**Decided by.** Rafly, 2026-09-10. Stated as final.

**Measured cost.** Subtropis zero share moves from 97,00% to 97,11%. The
difference is exactly the three retained months: 56 cells x ~2 190 hours
removed from the denominator reproduces v1's 97,00% to two decimals. Same data,
same code, different figure — so any comparison against a v1 number has to say
which convention it used.

---

## D-9 — One module per source

**Decided.** `dataset/` holds `merlin.py`, `era5.py` and `power.py`, each
owning acquisition and loading for its source. `lightning.py` keeps the grid,
the target construction, the PLN loader and the diurnal check. v1's
`merlin_download.py` is ported into `merlin.py` along with the MERLIN loaders
that used to live in `lightning.py`.

**Why.** Reproducibility, not need — the MERLIN files are already on disk. But
they are *obtainable*, and a replay from a clean checkout could not obtain them
without this. PLN has no downloader because those records came through the
supervisors and are not public: a hole by circumstance, and one the RUNBOOK
should state rather than leave to be discovered.

**Cost.** `lightning.py` no longer defines `load_merlin`; `LOADERS` points at
`merlin.load`. Anything importing the old name breaks.

**Reversal.** A file move. §3 makes module layout inside a subpackage an
ordinary edit, so this is recorded for the convention it sets rather than
because it needed permission.

**Bab.** V.

**Decided by.** Not recorded — proposed during implementation.

**Status.** The token codec reproduces all seven captured tokens **[measured]**
and 89 windows cover 2018–2024. The HTTP path has never run in this codebase;
the existing files came from v1. Same for `power.fetch_point` and
`power.fetch_regional`. Say so in Bab V rather than claiming the acquisition
code "works".

---

## D-10 — `PRECTOTCORR` is mm/day. The values stay; the annotation is corrected

**Decided.** `PRECTOTCORR` remains a candidate predictor and its stored values
are unchanged. The unit annotation in `features.POWER` changes from
`# precipitation, mm/hour` to `mm/day`, and any chapter text repeating
`mm/hour` is corrected. O-5 closes.

**Why.** NASA POWER's hourly response declares the unit itself. Read as mm/day
the domain means give 2 886 and 1 246 mm/year and the maxima are 44.8 and
49.8 mm in an hour; read as mm/hour the same means give 69 319 and 29 933
mm/year, which are impossible. O-5 asked whether the extremes were a handful of
rows or a smooth tail — they are a smooth tail across every cell, so the column
is not corrupt and was never the problem. The v1 annotation was copied from the
archive and never checked, which is exactly what O-5 suspected.

**Cost.** Every stored value is 24× what its old label implied, so any figure
quoted from a pre-2026-09-11 draft is wrong by that factor and silently wrong.
Nothing downstream changes: the two readings differ by a constant, and Spearman,
mutual information, min-max onto [0, π] and leave-one-out ablation are all
invariant under a monotone rescaling. The measured squashing figure (7,4% /
3,2% of [0, π]) is unaffected.

**Not settled by this entry.** Whether each hourly value is a one-hour mean or
an instantaneous sample. The header does not say. MERRA-2's hourly
precipitation is time-averaged, which makes an hourly mean likely, but that is
**unverified** and Bab IV must label it so. If it is instantaneous, the
`crr` / `avg_cpr` finding in Measured applies here too and a one-hour
realignment would be owed.

**Reversal.** Dividing by 24 in `power.py` to store mm/hour would need a full
rebuild of both tables and would change every stored number for no modelling
gain. Not recommended; recorded so the option stays visible.

**Bab.** II (the variable, correctly described), IV (the unit, and the
unverified averaging convention).

**Decided by.** Rafly, 2026-09-11.

---

## D-11 — Each domain gets its own feature set, at the same width

**PARKED 2026-09-14 by D-17.** Not in force. Its content returns to the open
list as S-10. Text below is left as written.

**Decided.** `selection/` runs the screen and the leave-one-out ablation
**separately on each domain** and writes both rankings to disk as the Bab VI
evidence. `MODELLED` becomes two lists of **identical length N**, one per
domain. The `pooled` scenario uses the union of the two, truncated to N by
pooled ranking. N is one number, chosen once, and stated.

**Why.** The rankings disagree, and the disagreement is measured rather than
feared: `KX` ranks 1st in subtropis and 10th in tropis, `T2M` 6th and 18th,
`CAPE` 4th and 12th. `TCIW` is the only informative predictor that ranks the
same in both. A single list selected on either domain handicaps the other, and
one selected on the pooled table suits neither.

Fixing N is what makes the split safe. Identical width means identical qubit
count, identical ansatz weight count and identical compute per run, so
`tropis_in` against `subtropis_in` compares two models of the same capacity. A
model fitted on one domain and evaluated on the other is still well defined —
both tables carry all 37 columns, and a fitted model travels with its own
feature set and its own scaler — so the within-arm gap `tropis_in` minus
`tropis_to_sub` is exactly as clean as it would be under one shared list.

**Cost.** Three, and all three are declared rather than avoided.

- If the two ablations pick different sizes, forcing both to N means at least
  one domain runs at a width its own ablation did not choose. Bab VI must say
  which domain took that cost and how much skill it gave up.
- Per-domain selection is itself a mild form of domain adaptation: each domain
  picks its own inputs before training. The measured gap is therefore the gap
  **after** that adaptation, which is smaller than a zero-knowledge transfer
  gap. Bab IV must state which question is being answered — "how well does it
  transfer once each region has chosen its own predictors", not "how well does
  it transfer with no local information at all". Keeping a shared-set run as a
  comparison arm answers the harder question too, if the budget allows; that is
  not committed here.
- Selection must run on **training rows only**, and therefore per fold under
  the rolling origin. Selecting once on the whole table would choose the
  feature set with knowledge of the held-out year. This applies to a shared set
  as well; two selections make it easier to get wrong.

**Reversal.** Collapse the two lists into one and pick a rule — pooled ranking,
union or intersection. A `features.py` edit and a re-run of `selection/`; no
rebuild, and no re-fit of anything in `dataset/`.

**Bab.** IV (why the sets differ and what that does to the transfer claim),
VI (the two rankings side by side, and the shift table).

**Decided by.** Claude, proposed 2026-09-11 and accepted by Rafly without
separate ratification of the reasoning. Recorded as a judgement between
defensible options, not a measurement.

---

## D-12 — The calendar columns: `hour_sin` and `cos_sza`. Closes O-1

**PARKED 2026-09-14 by D-17.** Not in force. Its content folds into S-3, and
O-1 reopens with it. Text below is left as written.

**Decided.** Two calendar candidates, `hour_sin` and `cos_sza`. Everything else
calendar-derived moves to `EXCLUDE`: `month_of_year`, `day_of_year`,
`hour_of_day_utc`, `hour_of_day_local` and `hour_cos`. `hour_of_day_local`
stays in the built table as bookkeeping. No rebuild — `build.py` already emits
all seven columns.

**Why.**

*Redundancy forces most of it.* `month_of_year` and `day_of_year` are Spearman
0.997 / 0.996 — the same column. `hour_cos` and `cos_sza` are −0.989 / −0.964.
At one qubit per feature, keeping both of either pair is a wasted qubit.

*`month_of_year` is the single most dangerous column in the set.* Zero share by
calendar month is antiphase between the domains: tropis is quietest in July and
August (0.987) and most active in April (0.903); subtropis is quietest in
January (0.997) and most active in July (0.924). A model that learns "month 7
means quiet" from West Java predicts quiet in Florida's most active month.

*`hour_of_day_utc` versus `hour_of_day_local` cannot be settled by screening.*
Their mutual information is 0.1067 and 0.1062 — identical to within binning
noise, because MI is invariant under a bijective relabelling of bins and the
two columns are the same partition with different labels. Taken at face value
the screen ranks UTC hour 3rd in tropis, above local hour, `PS` and
`PRECTOTCORR`. It is the one column guaranteed to inject a domain-specific
offset into a cross-domain experiment. The choice between them is structural,
not informational.

*Why `hour_sin` and not the integer hour.* Hour 23 and hour 0 are adjacent and
an integer says they are 23 apart. `hour_sin` is also asymmetric about solar
noon, which matters: lightning peaks in the late afternoon, two to three hours
after peak insolation, because the boundary layer keeps accumulating
instability. `sin(2πh/24)` separates 09:00 from 15:00; a symmetric function
cannot.

*Why `cos_sza` and not `hour_cos`.* They carry nearly the same diurnal
information. `cos_sza` is preferred because it is **physically** comparable
across domains rather than only nominally: `hour_cos` asserts that noon in Java
in March and noon in Florida in January are the same state, and they are not.
`cos_sza` encodes actual solar elevation, which means the same thing in both
hemispheres.

**Cost, and an argument this entry does not make.** O-1 justified `cos_sza`ex
partly as carrying the seasonal cycle with the correct sign in both
hemispheres. That claim is now measured and does **not** survive as stated:
Spearman between `cos_sza` and `month_of_year` is 0.0094 (tropis) and −0.0360
(subtropis). The seasonal signal is present and correctly signed in the monthly
means — tropis peaks in January at +0.042 and troughs in July at −0.042,
subtropis mirrors it at −0.170 and +0.187 — but the column swings roughly −1 to
+1 every day, so a seasonal modulation of amplitude 0.09 (tropis) is swamped.
**`cos_sza` is chosen as a solar-elevation feature, not as a seasonal one.**
Season is therefore not represented in the modelled set at all. That is a
deliberate omission, on the antiphase grounds above, and Bab IV must say so.

Two qubits either way. Dropping the diurnal columns entirely would cost more in
tropis than anything else on the table: the diurnal cycle spans 15.91 points of
zero share there against `CAPE`'s 8.52 across its deciles.

**Not addressed here.** Over water the diurnal cycle is reversed — continental
lightning peaks in the afternoon, oceanic at night or in the morning. A large
part of the subtropis box is Atlantic, and one `hour_sin` / `cos_sza` pair
cannot separate land cells from sea cells. This is the strongest argument
available for the land/sea flag O-3 raises, and it stays open.

**Reversal.** A `features.py` edit and a re-run of `selection/`. No rebuild.
The dropped columns remain in both built tables.

**Bab.** II (the diurnal and seasonal mechanism, with the lag), IV (which
columns and why), VI (the tropis/subtropis diurnal asymmetry).

**Decided by.** Claude, proposed 2026-09-11 and accepted by Rafly without
separate ratification of the reasoning. The redundancy and antiphase parts
follow from measurements; the `cos_sza` over `hour_cos` choice is a judgement.

---

## D-13 — Temporal encoding moves to `selection/`. Supersedes part of D-12

**Decided.** `dataset/` emits raw time only — `year`, `month_of_year`,
`day_of_year`, `hour_of_day_utc`, `hour_of_day_local` — as a new
`features.RAW_TEMPORAL` list, which is neither `CANDIDATES` nor `EXCLUDE`.
`build.py` no longer computes `hour_sin`, `hour_cos` or `cos_sza`, and
`_cos_sza` is removed from it. `selection/` owns every temporal encoding.

D-12's *choice* stands — `hour_sin` and `cos_sza` remain the intended pair, on
the reasoning recorded there. What changes is where they are produced.

**Why.** Whether an hour becomes sin/cos, a spline basis, radial basis
functions, one-hot or an integer is a representation decision, and
`selection/` is the subpackage that owns representation. With the derivation in
`build.py`, trying a different encoding meant a full rebuild of 5,3 million
rows; it is now a function call. It also concentrated a decision that was split
across two files — `build.py` chose the encoding, `features.py` chose which
half survived — which is the same shape as the two-`config.py` failure D-1
exists to prevent.

**Cost.** The `.meta.json` sidecar no longer records the encodings as columns,
so the table is slightly less self-describing. `selection/` must reproduce them
before any model runs, and if it reproduces them differently from D-12 the
mismatch is silent. The `-0,989` correlation between `hour_cos` and `cos_sza`
that D-12 rests on was computed on columns that no longer exist in the table;
it needs recomputing in `selection/` if it stays load-bearing.

**Reversal.** Restore `_cos_sza` and the three derivations in
`_add_time_features`; the tested version is in the 2026-09-13 chat log. One
rebuild.

**Bab.** IV (where the encoding decision lives), V (what `dataset/` emits).

**Decided by.** Rafly, 2026-09-14.

---

## D-14 — The seven Tier 1 ERA5 variables become candidates. Closes O-4

**Decided.** `VIMDF`, `CRR`, `TOTALX`, `CIN`, `CBH`, `TCWV`, `D2M` join
`features.ERA5`. `CANDIDATES` is now 20: 2 spatial, 5 POWER, 13 ERA5. No
temporal columns, per D-13.

`mean_convective_precipitation_rate` is **not** among them. It was trialled and
dropped in favour of `convective_rain_rate`: every other predictor is
instantaneous, and correcting sub-hourly sampling for one variable out of
twenty while leaving nineteen uncorrected is harder to defend than one uniform
convention with a stated limitation. The two are not interchangeable — Spearman
0,684, Pearson 0,533 over one tropis month **[measured]** — so this is a real
loss, not the removal of a duplicate.

**Why.** The variables were acquired for this. Amri's fourteen are a monthly
feature set; an hourly problem admits process variables a monthly aggregation
cannot use.

**Cost.** Bab II owes a literature paragraph for each of the seven, per §5,
before the raw freeze. Two of them, `CIN` and `CBH`, carry informative
missingness that no other predictor has — see O-8.

**Reversal.** Remove from `features.ERA5`. The files stay on disk; no
re-download.

**Bab.** II (each variable reviewed), IV, VI.

**Decided by.** Rafly, 2026-09-14.

---

## D-15 — `dataset/` is frozen

**Decided.** The acquisition, gridding, join and column contract are complete.
Both tables are built with 20 candidate predictors and no missing values in
eighteen of them. Further changes to `dataset/` are reversals of a recorded
decision, not ordinary edits.

**What is frozen.** Four sources acquired and loadable; the 0,5° grid; hourly
UTC binning; `flash_count` on `log1p`; the left join onto the lightning
skeleton with `_check_keys`; every month kept at its measured coverage (D-8);
the three-list contract (D-13); 504 ERA5 files, 590 POWER files, 89 MERLIN
exports, one PLN workbook.

**What is not frozen and never was.** `selection/`, and everything downstream.
The open items O-2, O-3, O-6, O-7 and O-8 are all `selection/` decisions that
read the built tables; none requires `dataset/` to change.

**Cost.** A variable discovered in the literature step after this point costs a
supplementary CDS pass and a rebuild, not a config change. That is the point of
a freeze.

**Reversal.** Not a reversal — a new decision superseding this one, per §2's
raw freeze.

**Bab.** III, IV, V all describe the frozen state.

**Decided by.** Rafly, 2026-09-14.

**Amended.** Declared before D-16, which changed `load_pln`. The freeze dates
from the rebuild of 2026-09-14 that followed it, not from this entry.

---

## D-16 — PLN strikes are deduplicated in `dataset/`, not `selection/`

**Decided.** `load_pln` drops exact duplicate rows on
`(timestamp, lat, lon, peak_current_ka)` — the same key `merlin.load` has
always used. Both domains are now processed identically.

**Why it cannot wait for `selection/`.** This is the line between what
`dataset/` must do and what it must not, and it is sharper than "merge
everything, decide later". `aggregate_gfd` collapses strike rows into
`flash_count`. After that the individual strikes do not exist, so a duplicate
counted once is uncountable thereafter. Row filtering on coverage or on dead
cells operates on the aggregated table and can be deferred; deduplicating
strikes cannot.

`gfd_per_km2_per_day` and `gfd_per_km2_per_year` are computed from
`flash_count` in the same function, so they inherit the inflation — but the
count is what is wrong, not the conversion.

**Cost.** Reopens D-15's freeze and required a rebuild. Every tropis strike
count recorded before 2026-09-14 is the pre-dedup figure.

**Reversal.** Remove the three lines. The raw workbook is untouched.

**Bab.** III (what the source contains), V (what the loader does).

**Decided by.** Rafly, 2026-09-14, after working out that the aggregation makes
it irreversible.

---

## D-17 — The selection component is reset. Parks D-11 and D-12

**Decided.** Four things.

*One.* **D-11 and D-12 are parked.** Neither is in force. Their text stays in
the record and is not edited; a reader should be able to see what was decided
and that it stopped being binding. D-11's content returns to the open list as
S-10 (how many feature sets, and how wide). D-12's content folds into S-3.

*Two.* **The 2026-09-11 measurements are void for selection purposes.** Not
withdrawn — they were honest measurements of the table that existed that day —
but they describe a different object and must not be quoted in Bab III, Bab IV
or Bab VI, and must not be used to justify a handling step.

- *Predictor-side, all of it.* The squashing shares, the cross-domain
  saturation percentages, the mutual-information rankings, the redundancy
  pairs. Seven Tier 1 columns joined the table under D-14 after these were
  taken.
- *Target-side, most of it.* D-16 left the zero share and the active cell-hour
  count unchanged, but lowered counts *inside* already-active hours. So
  anything computed from `flash_count` **values** moved: the negative-binomial
  `P(0)`, the var/mean ratios, the non-zero skew, the coverage-against-mean-
  flash Spearman.
- *Surviving.* Findings about the zero/non-zero **pattern** rather than the
  values: the six dead tropis cells, the dry-spell run lengths, the diurnal and
  monthly zero-share spreads, and the non-overlapping coordinate ranges.

*Three.* **`description.py` was deleted, not amended.** Recorded so that its
absence reads as a decision rather than an accident.

*Four.* **Selection is worked in three stages.**

- **Stage 1 — generic description.** Neutral inventory of both tables. No
  interpretation, nothing dropped, nothing fitted. Stage 1 never measures a
  predictor against the target; that is the screen, and the screen is stage 3.
  Because of that line, stage 1 runs on the whole table with no leakage
  concern.
- **Stage 2 — targeted description.** Aimed at problems stage 1 surfaces.
  Something is stage 2 only if the default handling is **absent or actively
  wrong** *and* the choice moves a number the thesis reports. Each stage 2 item
  owes a literature pass, not just a measurement.
- **Stage 3 — standard steps.** Steps any pipeline needs, justified by the
  field default or by a paper: transform order, scaling to the encoding range,
  temporal encoding, the split, the screen, the ablation.

Two rules ride on this structure. **Stage 2's contents are an output of stage
1, not chosen in advance** — only the zero majority is nameable now, because
its share is already known and no standard handling for it has been found.
And **anything fitted is stage 3 by definition, and stage 3 measurements run on
training rows only.** A whole-table minimum is descriptive; a scaler is fitted.

**Why.** Both parked decisions were proposals accepted rather than argued out,
and both rest on a table that has been rebuilt twice since — D-14 added the
Tier 1 columns, D-16 forced the dedup rebuild. D-11's own text asserts that
both tables carry all 37 columns; they carry 41. D-12's redundancy argument was
computed on `hour_cos` and `cos_sza` as materialised columns, which D-13
removed from the table, and D-12's cost paragraph already conceded the number
would need recomputing.

A literature pass since (2026-09-14) separates the two. Cyclic hour-of-day
encoding has direct precedent and a published leave-one-out ablation in a
convective-occurrence model; solar zenith angle has no located precedent as a
lightning **predictor**, appearing in that literature only as a day/night
stratification threshold. So `hour_sin` may well survive re-argument and
`cos_sza` probably will not — but neither should be carried on the old
reasoning.

The deeper fault is ordering, and it is why the reset is structural rather than
two amendments. Handling steps were chosen before the measurements that justify
them existed. The three stages exist to make that impossible: describe, then
find what has no default, then act.

**Cost.** Everything selection-adjacent restarts. There is no modelled feature
set, no encoded temporal column, no scaler decision, and no ratified screen
method. The measurement work of 2026-09-11 is redone against the current
41-column tables.

§5's method — Spearman and mutual information, never Pearson, confirmed by
leave-one-out ablation on ridge — is reset with the rest, pending a revision of
`INSTRUCTIONS.md`. It survived its literature check: the pairing of mutual
information as primary criterion with a rank correlation as complement, chosen
because variational circuits are sensitive to input dimensionality and qubit
scaling, has 2026 precedent. It is reset for want of a written justification,
not for want of support.

The equal-width assertion in `features.modelled()` stays, and carries a comment
saying it enforces a parked decision. It cannot fire while `modelled.json` does
not exist. Leaving it uncommented is the exact shape of fault O-9.

**Reversal.** Unpark by writing a new entry that ratifies D-11 or D-12 against
measurements taken on the current tables. Nothing is deleted, so the
reversal is additive.

**Bab.** III (data understanding), IV (pipeline design), VI (the selection
result).

**Decided by.** Rafly, 2026-09-14, in discussion with Claude.

---

## D-18 — `selection/` declares the transform chain; `training/` executes it

**Decided.** `selection/` owns *what* the transform chain is — the temporal
encoding, the missingness handling, the skew transform, the scaler and its
range — and emits it as a declared spec. `training/` owns *when and on what*:
it fits the chain on the training rows of each fold and applies it to the rest.
Neither duplicates the other, and no third place transforms anything.

`selection/` holds five modules, one per stage:

    description.py   stage 1. Measures the table. Never puts a predictor
                     against the target.
    diagnosis.py     stage 2. Measures the problems. May use the target.
                     Still only measures.
    prepare.py       stage 3. Declares and builds the chain. The only module
                     in selection/ that changes a value.
    screen.py        ranks the candidates.
    ablate.py        leave-one-out; writes modelled.json.

Files are divided by **what the code does**, not by which question it answers.
A question is a function; a file is a stage. Questions multiply without limit.

**Why a spec rather than a function each side calls.** §3 assigns scaling to
`training/` and D-13 assigns temporal encoding to `selection/`, so the chain
was already split across two subpackages. But `screen.py` and `ablate.py` need
transformed data too, and if they build their own the screen measures a
different matrix from the one that trains — the fault §3 names about a
benchmark constructing its own circuit. A declared spec is the only
arrangement in which three consumers cannot disagree.

**Why description and diagnosis are two files, not two sections.** Stage 1's
guarantee is that it never puts a predictor against the target, and that
guarantee is what lets it run on the whole table with no leakage concern. In
one file it is a comment someone can violate without noticing. In two it is
checkable: `description.py` never names the target beside a candidate.

**Cost.** Indirection. Reading the chain end to end means reading a spec in
`selection/prepare.py` and an executor in `training/`. The alternative was one
subpackage reaching into the other, which is worse and harder to see.

`prepare.py`, `screen.py` and `ablate.py` do not exist yet.

**Reversal.** Collapse the spec into a function `training/` imports. Nothing is
lost but the guarantee that three consumers see one chain.

**Bab.** IV (pipeline design), V (implementation).

**Decided by.** Rafly, 2026-09-14, choosing between three seams Claude set out.

---

## D-19 — Structurally undefined predictors are dropped, not imputed. Closes S-4 and O-8

**Decided.** A candidate whose field is **undefined** — the physical quantity
does not exist, so there is no value that failed to be recorded — is dropped
from the modelled set rather than imputed. It is dropped from **both** domains
regardless of which domain triggered it, so the two arms carry the same
predictors.

Two candidates meet this: `CIN`, undefined where no parcel reaches a level of
free convection, and `CBH`, undefined where there is no cloud. The modelled set
is drawn from the remaining **18 candidates, with no imputed value anywhere in
either table.**

`CANDIDATES` is unchanged and stays at 20. §3 freezes it at the raw freeze and
§5 requires Bab II to review every variable tested including the ones that
fail. `CIN` and `CBH` are reviewed in Bab II and dropped in Bab VI **with this
reason stated** — a variable dropped in silence looks buried.

**Why a rule and not a judgement.** The requirement was a standardised handling
step, either the field default or backed by a paper, applied uniformly with no
per-feature exceptions. The field default is mean or median imputation, and it
is wrong here on measured grounds: the null means "no convective layer", and
the mean asserts a layer that did not exist. Rejecting a default on evidence is
part of the justification, not a gap in it.

Three alternatives were considered and set aside:

*Impute at the ceiling* — `CIN` to 1000, `CBH` to maximum, on the physical
reading that no LFC means unbounded inhibition. Defensible physically, but it
has no citation, it is a bespoke argument constructed for these two columns,
and it is exactly the per-feature exception the instruction forbids. It would
also create a 46% point mass in subtropis, so nearly half of Florida would
arrive at that qubit as one identical angle.

*Missing indicator* — the literature's answer for informative missingness, and
the conditions fit (low-dimensional, missingness allowed at deployment). Set
aside on two grounds: two qubits of fifteen, and the measurement in the
2026-09-14 diagnosis showing the blank is a threshold on `CAPE`, which is
already a candidate. The indicator would largely duplicate a feature the model
already has.

*A missingness percentage threshold* — rejected because `CIN` is 46,4% in
subtropis and 23,5% in tropis, so any threshold between those two drops it in
one domain and keeps it in the other. Asymmetric predictors across the two arms
would confound the comparison this thesis reports.

**Cost, and it is the highest-ranked feature in one domain.** Imputed `CIN`
ranks **1st** on mutual information in subtropis, 0,3470 against `KX`'s 0,2266.
This decision discards it. The defence is that the rank is not established as
new information: the blank is a `CAPE` threshold, so imputed-`CIN` may be a
better-shaped `CAPE` rather than a distinct signal, and the screen cannot tell
the two apart.

**That defence must be tested, not asserted.** Run the leave-one-out ablation
once on complete-case rows with `CIN` and `CBH` present, as a side measurement
outside the main pipeline, and report what their removal cost. A stated
limitation with a number beside it, rather than a gap.

**Second cost.** Complete-case rows are not a random sample. Subtropis
occurrence is 0,0289 over all rows and 0,0536 among complete ones, so the side
measurement above is itself computed on a convective sub-population and must
say so.

**Reversal.** Both columns remain in `CANDIDATES` and in both built tables.
Reversing means writing a new entry that chooses an imputation, with no rebuild.

**Bab.** II (both reviewed as candidates), IV (the rule), VI (dropped, with the
reason and the ablation's price).

**Decided by.** Rafly, 2026-09-14, after rejecting Claude's impute-at-ceiling
recommendation for failing the standardised-handling requirement.

---

## D-20 — Five temporal candidates, decided by ablation rather than in advance. Narrows S-3

**Decided.** `selection/` builds five temporal features and all five enter the
ablation as candidates: `hour_sin`, `hour_cos`, `doy_sin`, `doy_cos`,
`cos_sza`. Which survive is the ablation's answer, not this entry's. They are
built in `selection/` per D-13 and are not materialised in either table.

`month_sin` and `month_cos` are excluded. Month is a coarsened day-of-year, the
two pairs are near-collinear, and day-of-year is the form with precedent. Their
screen ranks were close to the day-of-year pair in both domains, so nothing is
lost by taking the citable one.

**Why all five rather than a choice now.** The screen and the literature point
different ways on one feature, and neither is strong enough to settle it.

*The literature favours sine-cosine pairs.* Cyclical encoding of hour-of-day is
the documented standard — an integer hour puts 23:00 and 00:00 23 apart, and
the sine-cosine pair removes the discontinuity. Pacey et al. (2026) confirm it
by ablation in a convective-occurrence model: their cosine time-of-day
predictor was key to reproducing the diurnal cycle, while removing `CAPE` was
not. Cosine of day-of-year has its own precedent as a seasonal predictor in
ensemble postprocessing.

*The screen favours `cos_sza`,* which ranks 5th in tropis complete-case and 8th
in subtropis, beating `hour_sin` by twelve places in the domain whose signal is
seasonal. That is physically coherent: solar elevation carries hour and season
in one column, where `hour_sin` carries only hour.

*But the disagreement is weaker than it looks.* **No study found `cos_sza`
useless for lightning. None tested it.** Absence of precedent is a gap in the
literature, not a result against the measurement. And a screen rank is a
candidate for testing, not a finding — `lat` ranks 2nd on mutual information in
tropis, and that is dead-cell leakage scoring well.

So there is no result here that contradicts the literature yet. There is a
hint, and §5 names the instrument for turning a hint into a result.

**What each option would have cost.** `cos_sza` alone is one qubit and carries
both cycles, but solar elevation is symmetric about solar noon and the
lightning cycle is not — peaks run 15:00-17:00 local in both domains, two to
three hours after peak insolation, so `cos_sza` cannot express the lag.
`hour_sin` supplies exactly that asymmetry. Both pairs complete is four qubits,
27% of a fifteen-qubit budget spent on time.

**Cost.** Five temporal columns during the ablation against the 18 meteorological
candidates of D-19. Temporary — only the survivors are modelled — but it
lengthens the ablation and, if several survive, it competes directly with
meteorology for qubits.

**What Bab II owes.** A paragraph for each of the five, and the `cos_sza`
paragraph must state that its precedent is in solar-irradiance forecasting and
that no lightning study was located using it as a predictor. §5 requires every
tested variable reviewed, and an unprecedented one is reviewed by saying so.

**What Bab VI owes.** Which survived and what each cost. A well-supported
feature that fails is reported as failing. `cos_sza` surviving would be a small
original finding; `cos_sza` failing closes a gap nobody had checked.

**Reversal.** Remove a name from the temporal candidate list in `selection/`.
No rebuild, nothing materialised.

**Bab.** II (five paragraphs), IV (encoding lives in `selection/`), VI (the
ablation result).

**Decided by.** Rafly, 2026-09-14, choosing to test rather than to pick.

---

## D-21 — The selection pipeline. Six steps, one rule each. Narrows S-9

**Decided.** Selection is one fixed sequence. Every feature goes through every
step and no feature gets an argument of its own.

| | step | the rule |
|---|---|---|
| 1 | **Start** | `CANDIDATES`, 20, frozen at the raw freeze |
| 2 | **Derive** | admissible derived features are added as candidates |
| 3 | **Exclude** | two rules, below |
| 4 | **Rank** | mRMR, per domain, on training rows only |
| 5 | **Select** | top N, N stated once |
| 6 | **Confirm** | leave-one-out ablation, reported in Bab VI |

**Step 2 — what may be derived.** A derived feature is admissible if it is a
function of existing columns or of a stated external source, it has a physical
or cited motivation, and it is given a Bab II paragraph like any other
candidate. It then enters the ranking on equal terms and gets **no protection**
— a derived feature that ranks badly is dropped like any other.

The Bab II paragraph is the brake. Under §5 every tested variable must be
reviewed, so each derivation costs a paragraph and the list cannot inflate
quietly. The five temporal encodings of D-20 are one instance of this step, not
a special case.

**Step 3 — two exclusion rules, applied before ranking.**

*Structurally undefined* (D-19): the field has no value because the quantity
does not exist. `CIN`, `CBH`.

*Location-identifying*: a predictor that identifies **where** a row is rather
than describing **what the weather was** is excluded. This is not a redundancy
rule and no correlation method can find it — a cell identifier is both highly
relevant and not redundant with anything, so mRMR would keep it.

The measurement that forces this rule: `lat` contributes 0,0147 PR-AUC in the
tropis ablation, 4th of 23, with a Spearman of -0,0446. It is not that lower
latitudes flash more; it is that six cells never flash, and `lat` names them.
That skill cannot transfer to Florida, and in the cross-domain arms `lat` and
`lon` deliver **0,0000 effective resolution** — two constants occupying two
qubits.

`PS` is the ambiguous case. It ranks 2nd in the tropis ablation at 0,0244, and
it is nearly static per cell because it is terrain, so it may be acting as a
cell identifier by another route. But surface pressure is also a real
meteorological variable. **Not resolved here.** It needs its own entry.

**Step 4 — why mRMR rather than ranking by relevance.** Ranking on relevance
alone tends to select redundant features, because it never considers the
feature-to-feature relationship. That is measured here: `KX` and `TCWV` correlate
at 0,914 in subtropis and 0,903 in tropis, and both rank in the screen's top
five. mRMR subtracts a redundancy penalty, so once one is selected the other's
score falls.

The formulation is Peng, Long & Ding (IEEE TPAMI, 2005), maximising mean
relevance minus mean pairwise redundancy over the selected set. Relevance by
mutual information, redundancy by Spearman — the pairing §5 already requires,
combined by a standard algorithm instead of read off two tables side by side.

**Step 6 — why the ablation moves from selecting to confirming.**
Leave-one-out systematically undervalues correlated features: remove one and its
partner absorbs the job. The 2026-09-14 ablation shows this at scale — in
subtropis the largest single contribution is 0,0098 of a 0,2912 baseline, and
eleven of 23 features score negative. That is not 23 useless features, it is
collinearity. So leave-one-out cannot be the selector. It remains the
confirmation §5 asks for, and Bab VI must state this limitation rather than let
an examiner find it.

**Cost.** Step 5 needs an N that is chosen rather than derived, and mRMR gives
no principled stopping point. Step 3's second rule is a judgement about what a
diagnostic model may use, not a measurement, and `PS` sits on its boundary.

**Reversal.** Any step is replaceable in `selection/`; nothing is materialised.

**Bab.** IV (the pipeline), VI (the result and the leave-one-out limitation).

**Decided by.** Rafly, 2026-09-14, requiring a standardised sequence with no
per-feature exceptions.

---

## D-22 — Two feature sets, one per domain, equal width at N = 10. Closes S-10

**Decided.** Each domain gets its own modelled set, selected by the D-21
pipeline on its own training rows. The two sets are **not** constrained to
differ or to overlap — whatever mRMR returns is what they are. On the
2026-09-14 ordering they share ten of twelve, which is an outcome, not a rule.

Both sets are **N = 10**. The same ten features feed the quantum and classical
arms in a given domain: a QNN-against-classical gap must not be a feature-count
gap.

**Why per-domain rather than shared.** The mRMR ordering weakened D-11's
premise considerably — most of the apparent disagreement between domains was
the two of them selecting different members of one redundant cluster. But
weakened is not refuted, and `KX` and `TCIW` in subtropis against `PS` and
`cos_sza` in tropis are real differences that a shared set would suppress in
both directions. Selecting per domain lets the pipeline answer rather than
being told.

**Why equal width.** One feature, one qubit. Sets of different size are
circuits of different size, and a tropis-subtropis performance gap would then
confound domain difficulty with model capacity — which is the number this
thesis reports.

**Why 10.** Three considerations, none of them a derivation.

*Stability.* Across five seeds, ranks above 10 are stable at 1,00 while ranks
11 and 12 wobble — `hour_cos` and `PRECTOTCORR` at 0,80 in subtropis, `WS2M`
and `TCLW` at 0,80 and 0,20 in tropis. A feature that moves between seeds is a
weak selection, and 12 would import several.

*The zero crossing is not used as the rule.* mRMR scores go negative at rank 9
subtropis and 8 tropis. That is suggestive but partly mechanical: the
redundancy penalty is a mean over a growing set, so something goes negative
eventually regardless. Taking 8 would read more into it than it carries.

*Cost.* Statevector simulation is 2^n. Ten against the archive's fifteen is
roughly an eighth of the state, and the parameter-shift circuit count falls
with the parameter count too.

**mRMR has no principled stopping rule.** That is a property of the method, not
a gap in this analysis, and D-21 already records that step 5 takes a chosen
number. Bab IV must say so plainly: N was set at 10 because ranks above it are
seed-stable and ranks below are not, and because a larger circuit costs
exponentially more to simulate.

**Considered and dropped: pricing N by running 8, 10 and 12.** Affordable
classically — the ablation is ridge and logistic regression, minutes per run —
but not quantumly, where the archive's 432 runs would triple. A
classical-only sensitivity check was then rejected on its own merits: the
classical ladder being flat across 8 to 12 says little about whether a circuit
is, since capacity scales differently, so it would have bought a footnote
carrying its own caveat.

**Cost.** N is the weakest link in the pipeline and stays weak. And the two
sets differing at all means the **cross-domain arm has no defined input** — a
tropis-trained model reads qubit 2 as `cos_sza` where subtropis has `KX`, and
feeding one into the other is not a weak result but a meaningless one. D-11
never resolved this and its `pooled` gesture did not either. **Left open** as
S-11; the ten-feature intersection is the obvious candidate but it is a
separate decision.

**Reversal.** Change N or the per-domain flag in `selection/`. No rebuild.

**Bab.** IV (the rule and the choice of N), VI (the two tables).

**Decided by.** Rafly, 2026-09-14. Per-domain and unconstrained overlap his;
N = 10 on Claude's recommendation.

---

## D-23 — `lat` and `lon` are ordinary candidates. Removes D-21 step 3's second rule. Closes S-2 in part

**Decided.** The location-identifying exclusion rule is **withdrawn**. `lat`
and `lon` go through the D-21 pipeline like every other candidate: ranked by
mRMR, confirmed or rejected by the ablation, kept if they earn a place. Step 3
now holds one rule only — structurally undefined columns are dropped (D-19).

`PS` ceases to be an ambiguous case, because there is no longer a boundary for
it to sit on. The `*` flag comes out of `selection/screen.py`.

**Why the rule was wrong.** It rested on calling `lat`'s contribution leakage.
It is not. Leakage is test information reaching training, and the test set here
is **the same cells in a different year**. A model that learns from 2018-2023
that a particular cell never flashes, and applies that to 2024, has learned a
spatial prior — which is legitimate, and is what a diagnostic model over a
fixed grid is entitled to do. It would be leakage only if the test cells were
unseen, and they are not.

So `lat` entering 4th in the tropis ordering on relevance 0,1174 with redundancy
0,0286 is the method working, not failing. And the literature supports a spatial
effect: M. Zhou et al. (2023) find latitude correlates with flash density along
the China-Laos railway, Soriano et al. (2002) find linear correlation with both
coordinates across Iberia, and the predecessor carried both columns.

**What was actually measured, stated narrowly.** `lat` and `lon` deliver
**0,0000 effective resolution in the cross-domain arms** — the domains do not
overlap in either coordinate and no monotone map repairs that, so every target
row pins to one bound. That is a transfer limitation, not a validity problem,
and it is the kind of thing the ablation should report rather than a rule
should pre-empt.

**Why that makes the withdrawal the better position.** It converts a claim into
a measurement. "Features that contribute within a domain and contribute nothing
across domains" is a finding for Bab VI, and arguably a more interesting one
than a clean result — it isolates what a transfer experiment can and cannot
carry.

**Cost.** If both are selected in both domains, the cross-domain arms spend 2
of 10 qubits on constants: 20% of the circuit doing nothing. That is now a
measured outcome rather than a prevented one, and it bears directly on S-11.
Bab VI must report it.

**Also simpler.** One exclusion rule instead of two, and the remaining one is
a property of the data rather than a judgement about what a model may use.
That is the standardisation this pipeline was rebuilt for.

**Still open.** The six dead tropis cells — 368 208 rows, 20% of the domain,
guaranteed zero. That is a question about **rows**, not features, and belongs
to S-1.

**Reversal.** Reinstate `EXCLUDE_LOCATION` in `selection/screen.py`.

**Bab.** IV (one exclusion rule), VI (what the coordinates cost across domains).

**Decided by.** Rafly, 2026-09-14, rejecting Claude's leakage framing.

---

## D-24 — N = 15, superseding D-22's width. Closes the reopened part of S-10

**Decided.** The modelled sets are **15 features wide**, not 10. Everything else
in D-22 stands: two sets, one per domain, overlap unconstrained, equal width,
and the same set feeding the quantum and classical arms in a given domain.

**Why 15, and why not 18.** The width sweep is the knee, and it is sharp.

| N | tropis occ | subtropis occ | tropis count | subtropis count |
|---|---|---|---|---|
| 8 | 0,2741 | 0,2240 | 0,1144 | 0,0321 |
| 10 | 0,2871 | 0,2240 | 0,1178 | 0,0308 |
| 12 | 0,3344 | 0,2448 | 0,1215 | 0,0477 |
| **15** | **0,3620** | **0,2637** | **0,1277** | **0,0655** |
| 18 | 0,3714 | 0,2712 | 0,1429 | 0,0672 |

10 to 15 buys +26% relative on tropis occurrence, +15% on subtropis
occurrence, +113% on subtropis count. 15 to 18 buys +2,6%, +2,8% and +2,6% on
those three curves for **8x the statevector**. Only tropis count is still
climbing at 18, and that is the curve with a visible noise floor.

**And 15 is the proven number, not a projection.** The archive completed 432
runs at 15 qubits on 8 September 2026. Feasibility here is measured rather than
estimated, which is the strongest argument available for a cost this large.

**Where D-22 reasoned wrongly, and it is worth stating.** D-22 stopped at 10
because seed stability falls off at ranks 11 and 12. That reads the stability
column backwards. A feature that moves in and out across seeds means **several
features are near-equivalent at that rank**, not that the chosen one is
worthless — swapping one near-equivalent for another should cost little, and
the curve confirms it, since skill keeps climbing well past the point where
stability drops. Instability is a caveat about *which* features Bab VI names,
not evidence that the eleventh is dead weight.

D-22 also recorded that pricing N was affordable classically but not
quantumly, and then declined to do the classical check on the grounds that it
would say little about a circuit. That was wrong twice over: the check cost
minutes, and it revealed a 26% gap that no amount of reasoning about seed
stability would have surfaced.

**Cost.** 2^15 against 2^10 is **32x the statevector**, and the parameter-shift
circuit count rises with the parameter count. The archive proves this is
survivable, not that it is cheap.

The curve is ridge and logistic regression. A circuit's capacity scales
differently from a linear model's, so the 26% classical gain **may not
transfer**, and Bab IV must say the width was chosen on classical evidence.

Features 11 to 15 are the unstable ones. Bab VI reports the seed stability
beside the selection rather than presenting fifteen equally confident choices.

**Reversal.** Change N in `selection/`. No rebuild. Both this entry and D-22
stay readable, so the revision is visible rather than tidied away.

**Bab.** IV (the width and how it was chosen), VI (the sets, with stability).

**Decided by.** Rafly, 2026-09-14, on the width sweep.

---

## D-25 — Two stages: a hurdle. Closes S-7

**Decided.** The model is a **hurdle**. Stage 1 predicts whether the hour
flashed at all, on every training row. Stage 2 predicts how many, on `log1p`,
**trained on flashing hours only**. Each stage gets its own feature set from the
D-21 pipeline and its own circuit. Both arms of the comparison — QNN and
classical — are built the same way, so the comparison stays clean.

**Why two.** Three reasons, strongest first.

*The two questions want different features, and that is measured.* In the
subtropis meteorology arm the two stages agree on only **6 of 10**: occurrence
selects cloud and ice (`TCIW`, `TCLW`, `VIIWD`), count selects temperature and
instability (`T2M`, `TOTALX`, `dewpoint_depression`). Whether it flashes
depends on whether there is a storm; how much depends on how strong. One model
with one input set serves both badly.

*The zeros are switch-like, not merely frequent.* Median consecutive zero run
within a live cell is 20 hours subtropis and 15 tropis; 90,66% and 74,25% of
zero rows sit inside runs longer than a day. A process that stays off for
stretches and then turns on is what a hurdle describes.

*The predecessor architecture matches.* v1 ran `TASK = "hurdle"` by default,
which keeps the comparison to Amri's work on one axis fewer.

**The argument against, stated rather than buried.** The target is **not
zero-inflated**: a negative binomial at the observed moments predicts 0,9858
and 0,9639 zeros against 0,9711 and 0,9430 observed — a *negative* excess in
both domains. Overdispersion alone over-explains the zeros.

That rules out a zero-inflated **mixture**, and it does not rule out a hurdle.
The distinction, already recorded under O-6: a ZI mixture claims two processes
generate the zeros; a hurdle is a **factorisation**, P(y) = P(y>0) · P(y | y>0),
which is valid whatever produces them. The justification here is the feature
divergence and the persistence, not an excess of zeros — and Bab IV should say
so, because "94-97% zeros, therefore a hurdle" is the reasoning a reader will
assume and it is not the reasoning used.

**Scoring, and this is where v1 was wrong.** The count stage **trains** on
flashing rows only, which §4 permits — training rows may be subsampled. The
composed model is **scored on the whole held-out year at its natural class
ratio**. Scoring the count stage on non-zero test rows alone reshapes the test
set, which §4 forbids; v1 did exactly that. A per-stage score on flashing test
rows may be reported as a diagnostic, labelled as one, never as the headline.

Composition follows §4's ordering rule: invert with `expm1` before any
aggregation, never after.

**Cost.** Two circuits per domain per arm, so roughly double the run matrix
against a single-stage design. Two 15-qubit circuits, not one 30-qubit one, so
the statevector cost is 2 x 2^15 rather than 2^30 — cheap relative to the
alternative, expensive relative to one stage.

Stage 2 trains on far fewer rows: 89 917 tropis and 85 073 subtropis flashing
hours against 1,58 and 2,94 million. Seed stability is already measurably worse
in the count rankings for this reason, and Bab VI should report it.

**A contract consequence that is not yet handled.** §3 and `features.py` define
`MODELLED` as one list per domain. This decision makes it **two** — occurrence
and count. `features.modelled()` and its equal-width assertion both assume the
single-list shape. That needs an edit before `modelled.json` is written, and
the equal-width rule of D-22 should be read as applying **within a stage**: the
two stages need not be the same width as each other, only the two domains
within a stage.

**Reversal.** Train one model on `log1p(flash_count)` over all rows and take
one feature set per domain. No rebuild; a `selection/` and `training/` change.

**Bab.** IV (the architecture and why, including the not-zero-inflated point),
V (two stages in the code), VI (composed scores, per-stage diagnostics
labelled).

**Decided by.** Rafly, 2026-09-14, on Claude's recommendation.

---

## D-26 — `full` is the model; `meteorology` is a reported comparison

**Decided.** The models are built from the **`full` pool** — all 25 candidates,
so `lat`, `lon` and the temporal encodings compete like anything else (D-23).
The `meteorology` pool, which excludes those seven, is **not a model that gets
built**. It is a second run of the D-21 ranking whose score is reported in
Bab VI beside the `full` score.

This takes the selection from eight sets to **four**: occurrence and count, per
domain, which is what `modelled.json` holds.

**Why `full` is the product.** D-23 settled that the coordinates and the clock
are legitimate predictors — the test set is the same cells in a different year,
so a model learning a spatial or diurnal prior has learned something real, not
leaked anything. And `full` scores higher in tropis at every width tested.

**Why `meteorology` is still reported, and it is not a formality.** §4 says the
model becomes a forecast when driven by forecast fields from an NWP system. Run
that substitution: the meteorological variables are replaced by forecast
values, and `lat`, `hour_sin`, `doy_sin` and the rest **do not change** — they
are the same numbers in 2030 as in 2018.

So the `meteorology` arm's score is the **operational** number: what the model
would achieve when the only thing genuinely known about a future hour is the
forecast weather. The `full` score is an upper bound that includes knowing
where and when.

At N = 15: tropis 0,3620 full against 0,2637 meteorology; subtropis 0,2712
against 0,2851. Read operationally — in Florida the model is genuinely
meteorological, and in West Java about a quarter of its occurrence skill is
knowing the hour, which is real skill that a climatological lookup table also
has.

That is the answer to the strongest question an examiner can ask of a
diagnostic model, and without the second arm the answer is a guess.

**Composition at N = 15**, measured 2026-09-14: **nine meteorological and six
climatological in all four `full` sets.** `hour_cos` is excluded from every set
— last in both domains at redundancy 0,988 and 0,993 once `hour_sin` and
`cos_sza` are chosen — and the remaining six climatological features survive.
At N = 10 the split was four and six; the five extra slots had only meteorology
left to fill them.

**A category quota was considered and rejected.** Requiring a minimum number of
meteorological or temporal features would be a protection, and D-21 step 2
gives derived features none. The threshold would be arbitrary, it would force a
knowingly worse set whenever the ranking disagreed with it, and the two-arm
comparison already *measures* the climatology share rather than legislating it.

**Cost.** One extra ranking and one extra ablation per domain, both classical
and both cheap. One more column in the Bab VI table. No extra circuits.

**Reversal.** Drop the `meteorology` arm from `selection/screen.py`. The
product is unchanged; Bab VI loses the operational number.

**Bab.** IV (which pool the model uses), VI (both scores, with the operational
reading).

**Decided by.** Rafly, 2026-09-14, after questioning why an arm that is not
shipped should be reported.

---

## D-27 — Per-domain sets within, a shared set across. Closes S-11

**Decided.** Two kinds of feature set, for two different questions.

*Within-domain.* Each domain's own model uses its own 15 features from the D-21
pipeline, per D-22 and D-24. `tropis_in` and `sub_in` are the headline models
and answer "how well can lightning be predicted in this domain".

*Cross-domain.* The transfer arms use a **shared set**, ranked once on both
domains' training rows pooled, 15 wide, identical and in identical order for
both directions. `tropis_to_sub` and `sub_to_tropis` are trained on this set
and answer "do the two domains share a mapping from weather to lightning".

This means **two extra models per domain per stage**, trained on the shared set
purely so the transfer test is well posed.

**Why a transfer arm cannot read a per-domain set.** A trained circuit is 15
rotations bound to 15 named variables in a fixed order. Tropis occurrence puts
`cloud_water` on the first qubit; subtropis puts `KX` there. Feeding a Florida
vector into the West Java model sends `KX` values into a rotation trained on
`cloud_water`. The arithmetic completes and returns a number that means
nothing. There is no correct way to align two different lists, so the only
options were to share a set or to abandon transfer.

**Why this is not the shared-set-everywhere option.** Making all four arms use
the pooled set would make every number directly comparable, but the two
headline models would then run on a set neither domain's own ranking chose.
Per-domain selection is one of this thesis's results — the two domains choose
differently, and that difference is the cross-domain claim's main evidence.
Modelling on a set neither chose would report a finding the models do not use.

**What it costs, and it must be declared.** `tropis_in` and `tropis_to_sub` no
longer use the same features, so the gap between them mixes a feature change
with a domain change. Bab VI must therefore compare **`tropis_to_sub` against
`sub_to_tropis`, and each against a shared-set within-domain baseline** trained
on the same shared set — not against `sub_in`. Comparing a transfer arm to a
per-domain arm would attribute a feature difference to a domain difference.

So the shared set yields **four** trained models per stage, not two: a
within-domain and a transfer model on the shared set, per domain.

**`lat` and `lon` are excluded from the shared set.** They measure **0,0000
effective resolution across domains** — the domains do not overlap in either
coordinate, so every target row clips to one bound and the qubit arrives as a
constant. Three of fifteen qubits dead on arrival would make a poor transfer
score unattributable: a model that transfers badly because the domains differ
and one that transfers badly because a fifth of its circuit is frozen produce
the same number. The purpose of the transfer arm is to make degradation
*mean* something, so features that cannot carry information across domains are
excluded from it. They remain in the within-domain sets, where they are
legitimate (D-23).

`cos_sza` is computed from latitude and is therefore partly affected. Its
cross-domain resolution should be measured before the shared ranking is
trusted; **not resolved here.**

**Why transfer at all, given the claim.** The purpose is not to build a
transferable model. It is to use degradation as evidence that the two domains
are physically different — a model that transfers poorly says the weather-to-
lightning mapping is not shared. That inverts the usual reading of a transfer
result, and Bab IV must say so, or a reader will take a poor number as a
failure rather than as the finding.

**Cost.** Roughly double the run matrix: two stages x two domains x
{within-domain set, shared set}. Both arms of the QNN-against-classical
comparison must be built the same way.

**Reversal.** Drop the transfer arms and rest the cross-domain claim on the
feature selections alone, which was considered and is a coherent thesis. Or
move every arm onto the shared set.

**Bab.** IV (two set types and why), VI (transfer results, compared against
shared-set baselines and not against the per-domain models).

**Decided by.** Rafly, 2026-09-14.

---

## D-28 — Two scaling classes: physical bounds, else `arctan(x / IQR)`. Closes S-6

**Decided.** Every predictor is scaled by one of two rules, and which rule
applies is a property of the variable rather than a judgement.

*A variable with a definitional bound* is scaled by that bound. `RH2M` is
[0, 100] by definition; the cyclic temporal encodings are [-1, 1] by
construction. No fitted parameter, and the same map in every domain and every
future domain.

*Everything else* goes through `arctan((x - median) / IQR)`, with the median
and IQR fitted on **training rows only**, then mapped onto the rotation range.

`selection/prepare.py` declares this; `training/` fits and applies it per fold
(D-18).

**Why bounded rather than min-max.** The measured cross-domain resolution is
0,0959 for min-max on extremes, 0,1846 for min-max on p1/p99, and 0,2390 for
`arctan`. But resolution is not the deciding argument — this is:

*Nothing clips.* Under any min-max rule, every value above the upper bound
becomes the same number. `arctan` is monotone on the whole real line, so an
unseen `CAPE` of 30 000 still maps above 22 396 — compressed, but ordered and
distinguishable. That is the property Rafly's Jawa Tengah question asked for,
and it survives even though the scale here is fitted: a wrong scale compresses,
a wrong bound erases.

*This project has a variable that matters above a threshold.* `VIIWD` ranks
top-three on mutual information in both domains with a Spearman near zero —
informative, non-monotone, with the signal in the tail. Clipping that tail
destroys the part that carries it. `VILWD` and `VIMDF` are weaker instances.

**The two-class split is the literature's, not an invention.** Quantum
reinforcement-learning encodings separate finite-range state variables, scaled
by their known bounds, from infinite-range ones passed through `arctan` onto a
finite interval before scaling (Kölle et al., arXiv:2401.07043). Lockwood & Si
(arXiv:2008.07524) state the trade-off directly: scaled encoding preserves
magnitude but requires bounded inputs. `arctan` as a phase map is a named
encoding variant rather than an improvisation. Peer-review status unverified.

**What was rejected, and why the reasoning changed twice.**

*min-max on extremes* — the standard recommendation, and the worst measured
option. Two fitted parameters, each a single observation: `CAPE` 22 396 is one
row of 3,4 million and it sets the denominator for all of them.

*min-max on p1/p99* — recommended by Claude, then withdrawn. It is a documented
default, it is one uniform rule, and it recovers roughly two thirds of the
available resolution. The withdrawal rests on two corrections Claude made to
its own argument: the "twenty scale constants" objection was aimed at a
physical-constant variant that was never tested, where `arctan(x/IQR)` is one
uniform rule; and the artefact critique applies only to the within-domain
column, not to the cross-domain one that actually distinguishes the options.
It remains a defensible choice and Bab IV should say it was considered.

**Costs, stated.**

*The scale is fitted, so this is not parameter-free.* A third domain gets
compressed rather than clipped, which is better but not free. The
physical-constant version — `arctan(x/s)` with `s` chosen per variable from
domain knowledge — would be parameter-free and was rejected as twenty
judgements to defend individually.

*`arctan` is non-linear inside the bulk*, so it distorts spacing where a
min-max rule preserves it. Whether that costs anything is untested.

*It does nothing about point masses.* `CRR` holds one value on 60,5% of
subtropis rows before and after. S-5 owes that a separate answer, and no
monotone map is it.

*The within-domain resolution figures for `arctan` are not comparable* to the
other two maps and must not be quoted — see the Measured block.

**Reversal.** One function in `selection/prepare.py`. Nothing is materialised
and no table changes.

**Bab.** IV (the two classes and the encoding requirement), VI (what the choice
cost, if the ablation is rerun under it).

**Decided by.** Rafly, 2026-09-14, on Claude's recommendation after Claude
reversed it once.

---

## D-29 — No transform beyond D-28's scaling. The point masses stand. Closes S-5

**Decided.** No skew transform is applied. Predictors are scaled as D-28 says —
physical bound where one exists, `arctan((x - median) / IQR)` otherwise — and
nothing else. The large point masses at zero are left intact and declared.

**Why the skew half of this question is already answered.** S-5 began as
"transform skew before scaling", on the measurement that most predictors
squash badly under plain min-max. `arctan` is a bounded monotone map that
handles a heavy tail without a separate transform, so under D-28 the tail
problem does not arise. Adding Yeo-Johnson or a log on top would be a second
transform solving a problem the first one already solved, and Yeo-Johnson fits
its lambda from data, which would reintroduce a fitted parameter D-28 was
chosen partly to avoid.

**What is left is the point masses, and no monotone map touches them.** Share
held by the single most frequent value (subtropis / tropis): `CRR` **0,605 /
0,393** — its subtropis median *is* zero — `TCIW` 0,269 / 0,097,
`PRECTOTCORR` 0,222 / 0,066, `CAPE` 0,180 / 0,038, `TCLW` 0,058 / 0,002. So
60,5% of Florida rows send `CRR` to the circuit as one identical angle.

**Why nothing is the right answer.**

*The mass is a property of the atmosphere, not an artefact.* All five variables
mean the same thing at zero: the process was absent. No convective rain, no
cloud ice, no instability. A model that maps identical physical states to
identical angles is correct. Engineering the mass away would manufacture
structure that is not there — the same objection §4 makes about filling zeros
from other metrics.

*Zero already is the indicator.* A binary "is it zero" column would spend a
qubit restating what the value carries. That is the objection D-19 made against
a missingness indicator for `CIN`, and it applies unchanged.

*`CRR` earns its place with the mass present.* It ranks 10th and 11th in three
of the four selected sets, measured under mRMR, which penalises redundancy and
had every opportunity to demote it.

**A quantile transform is specifically wrong here**, not merely unnecessary: it
would spread 2,08 million tied subtropis zeros across the output range on
tie-breaking alone, inventing an ordering among rows that are physically
identical.

**Considered and not run: a zero-indicator on `CRR` as a test.** Rejected
because it would not settle the question. The worry is that a *shallow circuit*
may not learn a zero-versus-non-zero split from an angle sitting at the
boundary, the way a tree learns it from a threshold. The available ablation is
ridge and logistic regression, which are linear, so the test would answer an
adjacent question and cost a round trip.

**Cost, and it is the honest weakness of this entry.** That circuit-behaviour
worry is untested and stays untested. If the QNN underperforms the classical
ladder specifically on the domain with the larger masses, this is the first
thing to look at — subtropis carries 0,605 against tropis's 0,393 on `CRR`, and
larger masses on all five variables.

Bab IV states the masses as a property of the data with this caveat attached,
rather than reporting a clean pipeline and leaving an examiner to find them.

**Reversal.** Add a transform or an indicator in `selection/prepare.py`. No
rebuild, nothing materialised.

**Bab.** III (the masses, measured), IV (the decision and the caveat), VI (if
the QNN-classical gap differs by domain, this is a candidate explanation).

**Decided by.** Rafly, 2026-09-14, on Claude's recommendation.

---

## D-30 — The two scaling classes produce different angular spreads. Kept, and declared

**Decided.** D-28's two classes are kept as they are. A bounded feature's
middle 50% occupies roughly 0,70 of the rotation range; a fitted one occupies
roughly 0,29. The asymmetry is reported in `prepare.py`'s output and stated in
Bab IV rather than equalised.

**What was measured.** Fitted on all training rows, share of [0, pi] the middle
50% occupies: `hour_sin` 0,7071, `doy_sin` and `doy_cos` 0,7052, `cos_sza`
0,5769 subtropis and 0,6918 tropis — against `KX` 0,2836, `TCIW` 0,2626,
`CRR` 0,2500, and roughly 0,29 for every other fitted feature.

So a temporal feature reaches about **2,5 times the angular dynamic range** of
a meteorological one, and that follows from the scaling class rather than from
anything about the variables.

**Why it is not a defect.** A sinusoid spends most of its time near its
extremes and little near zero, so its middle half genuinely spans most of
[-1, 1]. The bounded number is the honest one. The ~0,29 that `arctan` returns
for nearly every fitted feature is the manufactured one — `arctan(x/IQR)` maps
the interquartile range to a fixed output width by construction, which is the
same artefact recorded against its within-domain resolution figures.

Equalising the two would impose a uniformity the data does not have.

**Why it matters anyway, and this is the reason for the entry.** The feature
map is periodic in the data, so a feature's phase span sets how much of the
model's frequency response it can reach — a variational model is a partial
Fourier series whose accessible frequencies are fixed by the encoding (Schuld,
Sweke & Meyer, Phys. Rev. A 103, 032430). A feature spanning 0,71 pi reaches
more of that response than one spanning 0,29 pi.

`hour_sin` is already worth 0,0817 of a 0,2871 tropis occurrence baseline —
28% of the model — measured under **ridge**, where scaling was uniform. Under
D-28 it also receives the widest angular range of any feature in the set. If
the QNN comes back more time-dominated than the classical ladder, those two
facts are not separable after the fact.

**So this entry makes a prediction rather than a hedge.** If the QNN leans on
the temporal features harder than the classical arm does, **the encoding range
is the first thing to check**, and the remedy is known: scale every feature to
an equal spread, or move the bounded class onto `arctan` as well.

**Considered and rejected: testing the options now.** The available ablation is
ridge and logistic regression, and a linear model is indifferent to angular
range — it learns a proportionally different weight and fits identically. All
three options would return the same numbers and tell us nothing, because the
concern is specific to a periodic encoding. The only real test is the circuit,
which is the expensive thing. This is the same reasoning D-29 used in declining
to test a zero-indicator on `CRR`.

**A second asymmetry, smaller and in the other direction.** `RH2M` is the
narrowest feature in every set it appears in — 0,1481 subtropis and 0,1195
tropis — because its definitional bound is [0, 100] while the data runs from
about 13 to 100, leaving the bottom eighth of the range empty. A definitional
bound the data only partly occupies costs resolution. This is the same
trade-off that keeps `lat` and `lon` out of the bounded class, at a much milder
setting: `RH2M` occupies 87% of its bound where a tropis latitude would occupy
1,1% of the planet's.

**Amends D-28.** D-28 says a variable with a definitional bound uses it.
`prepare.py` applies a narrower rule: **a definitional bound is used only where
the data can actually occupy it.** `RH2M` reaches exactly 100 on 56 512
subtropis rows and the cyclic encodings span [-1, 1] by construction, so both
qualify. `lat` and `lon` are bounded by the planet and do not, so they take the
fitted map. Recorded here because it was an implementation judgement Claude
made while writing `prepare.py`, not something D-28 said.

**Reversal.** One rule change in `selection/prepare.py`. Nothing is
materialised.

**Bab.** IV (both asymmetries and the narrower bound rule), VI (if the arms
differ on the temporal features, this is a candidate explanation).

**Decided by.** Rafly, 2026-09-14, on Claude's recommendation.

---

## Measured

Findings that correct something the archive asserts, or that the thesis will
need to quote.

**Void for selection purposes, per D-17.** Everything dated 2026-09-10 or
2026-09-11 was measured on a 37-column table with 17 candidates. It is not
withdrawn — it was honest measurement of the table that existed — but it
describes a different object, and must not be quoted in Bab III, Bab IV or
Bab VI, or used to justify a handling step. Specifically:

- **All predictor-side figures are void**: the squashing shares, the
  cross-domain saturation percentages, the mutual-information rankings, the
  redundancy pairs. Seven Tier 1 columns joined under D-14 after these were
  taken.
- **Target-side figures computed from `flash_count` values are void**: the
  negative-binomial `P(0)`, the var/mean ratios, the non-zero skew, the
  coverage-against-mean-flash Spearman. D-16 left the zero share and the
  active cell-hour count unchanged but lowered counts inside already-active
  hours.
- **Findings about the zero/non-zero pattern survive**: the six dead tropis
  cells, the dry-spell run lengths, the diurnal and monthly zero-share
  spreads, the non-overlapping coordinate ranges.

The 2026-09-13/14 blocks below are unaffected.

All `[measured]`, 2026-09-10.

- **The PLN export is entirely cloud-to-ground.** 2 242 100 CG rows as
  exported, 0
  non-CG dropped, and `Discrimination` is present in the workbook so the
  loader's `"CG"` fallback never fired. `positive_share` spans 0 to 1, so
  polarity reads correctly from the same field. v1 left this uncounted and
  warned against generalising from 2024 alone.
- **All six ERA5 variables are `instant`**, checked against `GRIB_stepType`.
  Downloads are not ZIPs, so `_open_members`' archive branch has never
  executed. The archive's claim that VIIWD and VILWD are time-averaged is
  wrong, and no one-hour realignment is owed on the existing six.
- **POWER hourly has no missing values.** 0 of 8 760 hours are sentinel across
  all five parameters in the sampled point-year, and `load_power` reports 0%
  empty across all 211 tropis files. The `-999` in the file is the header's
  declared `fill_value`, not data.
- **POWER's longitude grid is coarser than the project grid in both domains.**
  One collision each — tropis 6 cells on 5 POWER points, subtropis 7 on 6.
  Roughly symmetric, so it is a resolution limitation for Bab IV rather than a
  cross-domain asymmetry.
- **Tropis: 1 841 040 rows, 30 cells × 61 368 hours, 94.30% zeros**, 104 955
  cell-hours with at least one flash. Matches v1's figure exactly.
- **Tropis coverage**: mean 0.855, median 0.967, min 0.129; 31.2% of rows below
  0.9. A 0.9 gate would delete nearly a third of the tropical dataset.
- **6 of 30 tropis cells have zero flashes in all 61 368 hours** — 368 208 rows
  of guaranteed zero, 20% of the domain. See O-3.
- **The intensity target is complete where defined**: all 104 955 non-zero
  tropis cell-hours and all 99 273 subtropis cell-hours carry all five
  statistics.
- **Subtropis: 3 436 608 rows, 56 cells x 61 368 hours, 97,11% zeros**,
  99 273 cell-hours with at least one flash.
- **The MERLIN record is complete; three months are genuinely empty.** All 89
  download windows covering 2018–2024 are present, and 2021-03, 2022-12 and
  2024-02 contain no CG flashes. Those are the three quietest calendar slots
  (December 2 734, February 4 440, March 8 495 strikes on the seven-year mean,
  against 209 597 in July). Not a gap — a climatological absence.
- **`coverage` is not comparable across domains.** Tropis mean 0,855, median
  0,967, 31,2% of rows below 0,9. Subtropis mean 0,571, median 0,567, **70,1%
  below 0,9**. The proxy counts a day with no lightning anywhere in the box as
  unobserved, and Florida's winter is far quieter than West Java's dry season,
  so the gap is climatology rather than instrumentation. A uniform threshold
  would delete 70% of Florida and 31% of West Java for reasons unrelated to
  detector uptime. This is the measurement that makes D-8's "reported, never
  acted on" the only defensible position.
- **Florida has more strikes but fewer active cell-hours.** 5 301 491 strikes
  against tropis's 2 236 390 (post-dedup, D-16), yet 99 273 non-zero
  cell-hours against 104 955.
  Subtropical lightning is more concentrated in space and time.
- **MERLIN export overlap is negligible**: 3 duplicate strikes dropped across
  89 windows. All three come from the *same* file each time, so the cause is
  repeated rows in the archive, not window overlap.
- **ERA5 variables are all instantaneous.** 14 distinct short names checked
  against `GRIB_stepType` across every file on disk; 13 are `instant`. The one
  exception, `avg_cpr`, was dropped (O-4). The configured feature map is
  `FEATURE_MAP = "z"`, encoding data as `RZ(2x)`.
- **Two ERA5 short names were wrong in the request map.**
  `vertical_integral_of_divergence_of_moisture_flux` arrives as `vimdf`, not
  `viwvd`; `mean_convective_precipitation_rate` as `avg_cpr`, not `mcpr`. Both
  were dropped silently until `--check` surfaced them.
- **`total_totals_index` is the second variable absent from a multi-variable
  subtropis request**, after KX. Requested alone for the same box, it arrives.
  Same behaviour, different variable — a property of the CDS for this box, not
  a one-off.
- **`crr` and `avg_cpr` are not interchangeable**: Spearman 0,684, Pearson
  0,533 over one tropis month. Medians differ by a factor of nine and `crr`'s
  25th percentile is exactly zero. The instantaneous rate frequently samples a
  dry moment inside an hour that produced rain.
- **`log1p` is validated, not assumed.** Non-zero target skew falls from 8,35
  to 0,92 (tropis) and 12,99 to 0,87 (subtropis). Non-zero counts reach 2 391
  and 11 777; the top 1% of rows hold 20,0% and 26,9% of all flashes.
- **Coverage is a weather filter, not a data-quality filter.** Spearman between
  monthly coverage and mean flash count is 0,838 (tropis) and 0,915
  (subtropis). Months below 25% coverage average 0,008 flashes; months above
  90% average 1,72. A coverage gate would remove quiet months.
- **Dry spells are long enough to be switch-like.** Median consecutive
  zero-flash run within a live cell: 15 hours (tropis), 20 (subtropis). p90:
  50 and 164 hours. 40,6% and 66,6% of zero rows sit inside runs longer than
  seven days. Never-flashing cells excluded from these figures.
- **Zeros are structured in time.** Tropis zero share ranges 83,52% at 16:00
  local to 99,43% at 09:00, a 15,9-point spread; subtropis 93,67% at 15:00 to
  98,71% at 02:00. By month, tropis spans 8,5 points and subtropis 7,3.
- **Most predictors squash badly under plain min-max.** Share of [0, π] the
  middle 98% would occupy: `PRECTOTCORR` 7,4%/3,2%, `VIIWD` 3,8%/6,8%,
  `VILWD` 6,9%/4,3%, `TCIW` 19,9%/20,2%, `TCLW` 20,7%/19,0%, `CAPE`
  35,0%/17,3% (tropis/subtropis). Six of thirteen predictors fall below 25% in
  tropis, seven in subtropis.

Added 2026-09-11. All `[measured]` unless marked otherwise.

- **`PRECTOTCORR` is mm/day, not mm/hour.** The NASA POWER hourly response
  declares `"units": "mm/day"` in its own `parameters` block. The four other
  POWER parameters match `features.py` exactly — `PS` kPa, `T2M` C, `RH2M` %,
  `WS2M` m/s — so this is one wrong annotation, not a systematic problem. One
  sampled point-year sums to 960.97 mm; the domain means of 7.9077 and 3.4147
  give 2 886 and 1 246 mm/year `[derived]`. The maxima of 1075.77 and 1194.43
  are 44.8 and 49.8 mm in an hour. See D-10.
- **The column is not corrupt.** Zero nulls in either table. The tail is smooth
  to the 0.99999 quantile (tropis 0.5=2.640, 0.99=79.780, 0.999=221.730,
  0.9999=439.453). The 699 tropis rows above 305 span all 30 cells and 281
  distinct hours; the 286 subtropis rows span 41 of 56 cells and 122 hours.
  Neither of O-5's two hypotheses survives.
- **Zero-inflation is ruled out. The target is overdispersion, not a mixture.**
  A method-of-moments negative binomial implies P(0) = 0.9638 (tropis) and
  0.9852 (subtropis) against observed 0.9430 and 0.9700 — a *negative* excess
  of 2.08 and 1.52 points. var/mean is 170.59 and 633.77. A Poisson implies
  0.2959 and 0.2325 and is not a candidate. Caveats that belong with the
  figure: method of moments rather than maximum likelihood, a *marginal* rather
  than conditional fit, and dominated by the extreme tail. Indicative, not
  precise. What it rules out is a ZI mixture; it does not argue against a
  hurdle, which is a factorisation and valid either way.
- **There is no clean occurrence gate.** Zero share, `coverage > 0` rows, under
  progressively harder conditioning (tropis/subtropis): unconditional
  94.30%/97.00%; top CAPE decile 91.29%/91.01%; top decile CAPE and KX
  89.87%/81.04%; top decile CAPE, KX and TCIW 74.20%/70.90%; same cell flashed
  within ±3 h 65.71%/69.01%; domain active *and* same cell active within ±3 h
  **56.29%/64.93%**. It never collapses. Sampling zeros are irreducible at
  0.5° / 1 h — a cell is larger than a storm and an hour longer than a flash
  gap. Stage 1's ceiling is set by resolution, not by the model.
- **Hour of day out-discriminates CAPE in the tropics, and not in the
  subtropics.** Tropis: CAPE deciles span 8.52 points of zero share, the
  diurnal cycle 15.91 `[derived]` from the two measurements. Subtropis: CAPE
  8.98, diurnal 5.04. The same feature set carries different information in
  each domain, which is itself a Bab VI finding.
- **`coverage == 0` occurs only in subtropis, and only in the three empty
  MERLIN months.** 122 304 rows = 56 cells × 2 184 hours = 91 days =
  2021-03 (31) + 2022-12 (31) + 2024-02 (29). Tropis has none. Excluding them
  gives 97.0047%, reproducing v1's convention exactly, as D-8 predicted. So a
  zero here means climatological absence, not detector downtime.
- **Roughly 20% of subtropis rows have CAPE at or near zero.** The bottom two
  deciles merged at 665 735 rows, CAPE ≤ 0.375. A point mass that size breaks
  both min-max and quantile transforms in different ways. Carry it into O-7.
- **The built tables emit seven calendar columns, not four.** `hour_sin`,
  `hour_cos` and `cos_sza` are present in both tables and appear in neither
  `CANDIDATES` nor `EXCLUDE`, which `check_against_table` reports in both
  domains. `cos_sza` therefore already exists; O-1 describes computing it as a
  proposal. All 17 declared candidates are present in both tables; 37 columns
  each. Nothing else is missing or unclassified.
- **`mean_coverage` in the meta files contradicts this section.** meta.json
  records 0.6907 (tropis) and 0.5156 (subtropis); the bullets above record
  0.855 and 0.571. The minima agree (0.129). Both are `[measured]`, so one is
  from a different build, denominator or weighting. **Unresolved** — do not
  quote either in a chapter until it is settled.
- **The screen ranks features differently in each domain.** Normalised mutual
  information against occurrence, `coverage > 0` rows, largest rank shifts:
  `T2M` 18th tropis / 6th subtropis, `lat` 9th/19th, `hour_of_day_local`
  4th/14th, `KX` 10th/1st, `CAPE` 12th/4th. `TCIW` is the only informative
  predictor ranking identically (2nd/2nd); `lon` is last in both (20th/20th).
  See D-11.
- **`VIIWD` is the case §5 predicts.** Spearman 0.0226 / 0.0219 — near zero,
  discarded by any correlation screen — but MI ranks it 8th and 5th. A variable
  that matters above a threshold with no monotone relationship. `VILWD` is a
  weaker instance. This is the concrete example Bab VI should lead the
  screening section with.
- **Spearman against the count and against occurrence agree to three decimals**
  on every predictor in both domains. The screen does not distinguish the two
  stages, so it need not be run twice.
- **`lat` is informative only where the dead cells are.** 9th in tropis, 19th
  in subtropis; `lon` 20th in both. The asymmetry is the O-3 shortcut appearing
  in the screen. The predecessor reports `LAT` as his most influential feature
  in **both** datasets while his own heatmap gives LAT–LIGHTNINGCOUNT 0.11
  (PLN) and −0.01 (MERLIN) `[repo]`. Correcting this is a Bab VI result.
- **Calendar redundancy.** `month_of_year` ~ `day_of_year` 0.997 / 0.996;
  `hour_cos` ~ `cos_sza` −0.989 / −0.964; `hour_of_day_local` ~ `hour_sin`
  −0.746 in both. See D-12.
- **`cos_sza` does not carry season as a column.** Spearman against
  `month_of_year` is 0.0094 (tropis) and −0.0360 (subtropis). The seasonal term
  is present in the monthly means and correctly signed — tropis +0.042 January
  to −0.042 July, subtropis −0.170 January to +0.187 June — but the daily swing
  is roughly −1 to +1, so an amplitude of 0.09 (tropis) or 0.37 (subtropis) is
  swamped. Corrects the assumption in O-1.
- **The antiphase, measured on the target itself.** Zero share by calendar
  month: tropis 0.933 Jan, 0.903 Apr, 0.987 Jul, 0.926 Dec; subtropis 0.997
  Jan, 0.977 Apr, 0.924 Jul, 0.995 Dec. Spreads of 8.4 and 7.3 points, matching
  the strike-total figures already recorded.
- **Monthly aggregation destroys the cross-domain comparison. Evidence for
  D-2.** Aggregating the hourly tables to cell-months reproduces the
  predecessor's table exactly — tropis 2 520 rows, 30 cells — and conditions the
  target well: zero share falls to 29.37% / 17.94% and `log1p` skew to −0.12 /
  −0.06. But the predictors change sign between domains. Spearman against the
  monthly count: `CAPE` **−0.040 tropis against +0.680 subtropis**; `T2M`
  −0.507 against +0.602; `TCLW` +0.705 against +0.029. At hourly the same
  predictors agree in sign (`CAPE` +0.128/+0.187, `T2M` −0.062/+0.172).
  Monthly averaging replaces the instantaneous physical relationship with a
  seasonal climatology, and the two climatologies are antiphase, so a
  cross-domain model at monthly resolution transfers an inverted climatology
  rather than physics. **This is the justification for hourly, and it belongs
  in Bab III.** The aggregation is a groupby on the existing parquets, so a
  monthly comparison arm against the predecessor's numbers remains available
  without touching `dataset/`; nothing is committed here.
- **Monthly zeros are mostly already-known effects.** Tropis: 6 dead cells × 84
  months = 504 of 740 zero cell-months `[derived]`, leaving 11.7% over live
  cells. Subtropis: 3 empty MERLIN months × 56 cells = 168 of 844 `[derived]`;
  the remaining 676 are winter, with mean coverage 0.1949 against 0.6517
  elsewhere — so at monthly resolution "quiet" and "unobserved" are harder to
  separate than at hourly, not easier.
- **Lightning is autocorrelated, but the model does not use it.** Zero share
  falls from 94.30%/97.00% to 65.71%/69.01% conditioned on the same cell having
  flashed within ±3 h. §4 makes the model a diagnostic — predictors and target
  at the same hour, no lags — so this persistence is measured and deliberately
  unexploited. Say so in Bab IV rather than letting it read as an oversight.

- **A note on this file's decimal convention.** §6 puts decimal points in code
  and records and commas in the thesis. The bullets above 2026-09-11 mix both.
  Entries from 2026-09-11 use points. The older bullets are left as written
  rather than silently normalised.

---

### 2026-09-13/14 — Tier 1 acquisition and the final build

- **Two ERA5 short names in the request map were wrong**, and both were dropped
  silently until a trial file was read column by column.
  `vertical_integral_of_divergence_of_moisture_flux` arrives as `vimdf`, not
  `viwvd`; `mean_convective_precipitation_rate` as `avg_cpr`, not `mcpr`.
  `2m_dewpoint_temperature` is `d2m`, not `2d` as the candidate note had it.
- **The multi-variable CDS behaviour is systematic, not intermittent.**
  `total_totals_index` is absent from **all 84** subtropis `tier1` files and
  present in all 84 tropis ones. Requested alone for the same box it arrives,
  as `k_index` did. Two variables, two for two, 84 for 84. Cause unknown.
- **The ZIP branch of `_open_members` executed for the first time**, on the
  eight-variable trial. `avg_cpr` has stepType `avg` while the other seven are
  `instant`, and the mixed request came back archived. With `avg_cpr` dropped,
  all thirteen ERA5 variables are `instant` and the branch does not fire.
- **ERA5 longitudes arrive on −180..180, not 0..360.** Measured directly:
  −82,0 to −78,5 for the subtropis box. The conversion in `parse_netcdf` has
  therefore never changed a value. v1's smoke test carried this as a warning,
  and it was carried forward into comments and a Bab IV draft as though it were
  an observed cause of failure. It is not.
- **`CIN` and `CBH` carry informative missingness — the only predictors that
  do.** `CIN` is missing on 23,5% of tropis rows and 46,4% of subtropis rows;
  `CBH` on 1,2% and 8,4%. The missingness is structural: `CIN` is absent on
  99,6% / 99,8% of rows where `CAPE` is zero, and `CBH` on 94,3% / 96,0% of
  rows where cloud water is zero. Critically, it barely touches rows that
  matter — `CIN` is missing on only 4,6% of tropis and 0,9% of subtropis rows
  that recorded a flash. A residual 20,6% / 34,6% of rows with positive `CAPE`
  still lack `CIN`, and that part is unexplained. See O-8.
- **`CIN` availability differs by domain** — 23,5% missing against 46,4%. The
  first predictor whose availability, not just its distribution, is asymmetric
  across the two domains.
- **PLN rows are flashes, not strokes.** The export carries a `Multi.`
  (multiplicity) column reporting how many return strokes the network grouped
  into each row, so `flash_count` as a row count is correct for ground flash
  density. Had rows been strokes, every GFD figure would be inflated by the
  mean multiplicity.
- **The final build:** 504 ERA5 files, none zero-byte. Tropis 1 841 040 rows,
  subtropis 3 436 608, unchanged by the seven new columns. Key overlap 100% for
  both POWER and ERA5 in both domains. Eighteen of twenty predictors complete.


### 2026-09-14 — PLN duplicates

- **The PLN export contains 5 710 duplicate rows, all inside the 2020 sheet.**
  Pairs, never triples: 11 420 rows in 5 710 groups of two. Every pair agrees
  on all thirteen source columns including `Multi.` and `Sensors nb.`, so they
  are repeated rows rather than two detections sharing a key. 0,25% of the
  export.
- **The two sources are not comparable on this.** MERLIN has 3 duplicates in
  5 301 491 rows — 0,00006% — scattered across three files in three different
  years. PLN has 5 710 in 2 242 100, all in one year's sheet. Same fix, not
  the same phenomenon.
- **After deduplication: 2 236 390 tropis strikes.** The zero share stays at
  94,30% and the active cell-hour count at 104 955, both unchanged, because a
  duplicated flash was always inside a cell-hour that already held a real one.
  Only counts within already-active hours fell.
- **The final tables.** Tropis 1 841 040 rows x 41 columns; subtropis
  3 436 608 x 41. Twenty candidate predictors, eighteen complete. Five raw
  temporal columns, five intensity statistics at 94,3% / 97,1% missing by
  construction, and bookkeeping.


### 2026-09-14 — stage 1 generic description

First run of `selection/description.py` against the current 41-column tables,
after the D-16 rebuild. All `[measured]`. These supersede the void 2026-09-10
and 2026-09-11 figures for every quantity they cover.

**Both tables verified.** Rows equal cells x hours exactly in both domains
(56 x 61 368 and 30 x 61 368). Zero duplicate cell-hours on
`(lat, lon, time)`. 20 of 20 candidates present, no unclassified columns, and
no drift between either table and the `.meta.json` that built it.

**No sentinels anywhere, and no second `PRECTOTCORR`.** Every detached maximum
in the table is held by exactly one row: `PRECTOTCORR` 1194 (n=1), `CAPE`
22 396 (n=1), `KX` -121,6 (n=1). Nothing repeats, so no fill value survived
into any candidate.

The extremes are also coherent in space and time, which a fill value is not.
The two largest subtropis `PRECTOTCORR` rows are the same timestamp in adjacent
cells; the tropis maximum is 15:00 and 16:00 in one cell on consecutive hours;
`VIIWD`'s subtropis maximum and minimum are one hour apart on 2021-04-11 with
26 and 7 flashes, which is divergence reversing across a storm. 2024-06-12
appears independently in subtropis `PRECTOTCORR`'s upper tail and `VIMDF`'s
lower tail — one convective event in two variables.

`CAPE` 22 396 is offshore Atlantic in July, where ERA5 produces its largest
values. `KX` -121,6 has a populated left tail (detachment 0,6), so it is not
floating free of the distribution. Both stand as ERA5 output.

**`mean_coverage` in the meta files is wrong; the record's bullets were right.**
Row-weighted 0,8549 tropis and 0,5710 subtropis; cell-month-weighted 0,8560 and
0,5697. The two weightings differ by under 0,002, so weighting was not the
source of the disagreement. The meta's 0,6907 and 0,5156 match neither.
`dataset/` is frozen, so the field is not corrected — **do not quote
`mean_coverage` from a `.meta.json`.**

**122 304 subtropis rows carry coverage 0** — 2 184 hours x 56 cells, exactly
the 91 days of the three empty MERLIN months. They are present as rows, not
absent. Tropis has none.

**The point masses are larger than the quantiles suggest** (share held by the
single most frequent value, subtropis / tropis): `CRR` 0,605 / 0,393 — its
subtropis median *is* zero; `TCIW` 0,269 / 0,097; `PRECTOTCORR` 0,222 / 0,066;
`CAPE` 0,180 / 0,038; `TCLW` 0,058 / 0,002. A monotone transform does not
touch a point mass, so this is a separate problem from the tails.

**The divergence variables are the most compressed columns in the table.**
Tropis `VIIWD`: interquartile range 8,1e-07 against a full range of 9,2e-04, so
the middle half would occupy **0,088% of the rotation range** under plain
min-max, and the maximum is ~2 900x p75. Subtropis `VIIWD` 0,058%. `VILWD` and
`VIMDF` are the same shape in both domains. This is a stronger case for a
bounded transform than `CAPE` is.

**`RH2M` hits its definitional ceiling often** — exactly 100 on 56 512
subtropis and 9 289 tropis rows. A bound that is physical rather than sampled.

**Target, post-dedup.** Tropis 94,30% zeros, 104 955 non-zero cell-hours,
2 236 390 flashes, var/mean 170,77, `log1p` skew 6,03, non-zero median 4 and
max 2 391, 6 dead cells (368 208 rows). Subtropis 97,11% zeros, 99 273 non-zero
cell-hours, 4 834 772 flashes, var/mean 633,82, `log1p` skew 8,47, non-zero
median 7 and max 11 777, no dead cells. On coverage > 0 rows only, the
subtropis zero share is 97,00%; tropis is unchanged.

**Redundancy, Spearman, whole table, no threshold applied.** Strongest pairs
subtropis: `KX`-`TCWV` 0,914, `CAPE`-`D2M` 0,880, `TCWV`-`D2M` 0,879. Tropis:
`KX`-`TCWV` 0,903, `T2M`-`RH2M` -0,774, `CAPE`-`D2M` 0,735. `KX`-`TCWV` is the
top pair in both. Anything dropped on this basis must have it recomputed on
training rows only.

**Unresolved, small.** Subtropis `CIN` maxes at exactly 1000,0 and tropis at
999,5, both with detachment 0,0 — the distribution runs to that value and
stops. Either coincidence or a ceiling in the ERA5 field. Worth settling before
the `CIN` handling is decided.

---

### 2026-09-14 — stage 2 diagnosis, first pass

`selection/diagnosis.py`, missingness and zero structure. All `[measured]`.
Recorded, not acted on: three S-items move and none is decided here.

**The `CIN` residual is a threshold, not a mystery. S-4's blocker is closed.**
The null rate decays monotonically down `CAPE`'s deciles — subtropis 0,9885 in
the bottom decile to 0,0001 in the top; tropis 0,9581 to 0,0004. The residual
rows carry a median `CAPE` of 10,81 subtropis and 16,47 tropis. `CIN` is
undefined when `CAPE` is **negligible**, not only when it is exactly zero, and
the physical story holds with that correction. `CBH` is the same shape against
cloud water: residual medians 0,00032 and 0,00049.

**And that weakens the missing-indicator case.** If the blank is a threshold on
`CAPE`, then `CIN_missing` is a thresholded copy of a variable already in the
candidate set, and it would cost a qubit to encode information `CAPE` carries.
The missing-indicator literature in S-4 assumes the indicator supplies
information not otherwise present. Here it demonstrably does not. `CIN`'s
**value** where present is a separate matter — it appears in neither domain's
top-15 Spearman pairs with `CAPE`.

**A domain asymmetry to declare.** Subtropis `CIN`-null rows are 99,95% zero
and carry 0,25% of all flashes. Tropis nulls are 98,89% zero and carry
**2,31%** — roughly 51 700 flashes. The same blank means "no lightning" in
Florida and does not quite mean it in West Java.

**`CIN` is capped at 1000.** Subtropis max exactly 1000,0 with one row on it
and 363 within 1%; tropis 999,469 with 25 within 1%. A real ceiling that almost
nothing reaches, so it does not distort the distribution — but it is the
direction a physically-motivated imputation would point, since no LFC means
effectively unbounded inhibition. Imputing 0 asserts the opposite.

**The target is not zero-inflated, and this overturns the standing assumption
behind S-7.** A negative binomial at the observed mean and variance predicts
**more** zeros than are observed: subtropis 0,9858 predicted against 0,9711
observed, tropis 0,9639 against 0,9430. The excess is negative in both domains.
The overdispersion alone over-explains the zeros. A Poisson would give 0,2449
and 0,2968, so the target is emphatically not Poisson — but the gap that a
hurdle or zero-inflated model exists to close is not there.

**Stated as a limitation of the test**: this is a marginal moment fit, and
conditional zero-inflation given the predictors is a different question that
this does not answer. It is a yardstick, not a proof. The direction is the
opposite of what 94-97% zeros invites, which is why it is worth reporting
either way.

**What does support two stages is persistence, not inflation.** Zero runs
within live cells: median 20 hours subtropis and 15 tropis, p90 164 and 50,
p99 1 184 and 338. **90,66% of subtropis zero rows and 74,25% of tropis sit
inside runs longer than 24 hours**; 66,59% and 40,62% inside runs longer than a
week. That is switch-like behaviour, and it is a different argument for the
same architecture. S-7 should lead with it.

**Tropis is diurnally driven; subtropis is seasonally driven.** Zero-share
amplitude, tropis: **15,9 points** diurnal (0,835 at 16:00 local, 0,994 at
09:00) against 8,4 points seasonal. Subtropis: 5,0 points diurnal (0,937 at
15:00, 0,987 at 02:00) against **7,3 points** seasonal (0,924 July, 0,997
January). The diurnal signal is three times stronger in West Java than in
Florida, and in Florida the seasonal signal is the larger of the two.

This bears on S-3, which inherited from the parked D-12 a choice of `hour_sin`
with `month_of_year` excluded — a choice that suits tropis and underserves
subtropis. It also bears on S-10: if the two domains need different *kinds* of
temporal feature rather than different weights on one, equal width is a harder
constraint than it looked.

**Non-zero counts.** Share of non-zero cell-hours equal to exactly 1: 0,1931
subtropis, 0,2863 tropis. Non-zero var/mean 586,53 and 150,68.

**S-items moved, none decided.** S-4 (blocker closed, indicator weakened),
S-7 (justification replaced), S-3 (new constraint), S-5 (a further point mass
if `CIN` is imputed), S-10 (equal width harder to defend).

---

### 2026-09-14 — stage 2 diagnosis, second pass

Cross-domain maps and temporal structure. All `[measured]`. Recorded, not acted
on. This closes the measuring phase.

**A bounded map beats min-max on cross-domain resolution, by about four times,
in 35 of 36 column-arm pairs.** Averaged over the eighteen non-coordinate
candidates, the target domain's middle 50% occupies roughly **7% of the output
range under source-fitted min-max and 27% under a bounded map**. The one
exception is `TCWV` subtropis-to-tropis, 0,1812 against 0,1546.

Worst individual cases, min-max then bounded: `CRR` tropis-to-subtropis 0,0007
to 0,0582 — under min-max the middle half of two million rows occupies 0,07% of
the rotation range. `PRECTOTCORR` subtropis-to-tropis 0,0066 to 0,3817.
`TCIW` subtropis-to-tropis 0,0172 to 0,3629.

**This reframes O-3. The transfer problem is compression, not saturation.**
`outside`, the share of target rows beyond the source's range, is 0,0000 for
almost every non-coordinate candidate in both directions. Rows are not falling
out of range. One Florida `CAPE` value of 22 396 crushes the whole West Java
distribution into the bottom 2,4% of the dial without a single row clipping.
Min-max's fragility is real and is exactly its two fitted parameters being
single observations — but the damage arrives as crushing, inside the range.

**Stated limitation of this measurement.** The bounded map used the **source
interquartile range** as its scale, which is a fitted quantity. So this
establishes that bounding helps, and by how much; it does **not** validate a
parameter-free map. The open question in S-6 moves from *whether* to bound to
*where the scale comes from*.

**No monotone map rescues the coordinates.** `lon` scores 0,0000 resolution
under both maps in both directions, with 100% of target rows pinned at an
output extreme — the domains are on opposite sides of the meridian. `lat`
scores 0,0004. S-2's case for dropping coordinates now has a number in both
directions.

**Tropis is one coherent diurnal signal; subtropis is not one signal at all.**
Tropis: **22 of 24 live cells diurnal-dominant**, per-cell ratio median 1,64,
peak hours clustered at 15:00-17:00 local in every high-flash cell. Per-cell
diurnal amplitude reaches 0,42 against a pooled 0,159 — pooling across cells
with slightly different peaks smears the cycle and understates it.

Subtropis: **13 of 56 diurnal-dominant**, median ratio 0,69, and per-cell peak
hours spanning **sixteen distinct values from 00:00 to 22:00** against tropis's
eight.

**And the subtropis spread is spatially organised, not noise.** Diurnal
amplitude collapses eastward into the Atlantic at fixed latitude: 28,75/-81,25
0,1615, 28,75/-80,75 0,1158, 28,75/-80,25 0,0407. Same at 28,25. The nocturnal
peak hours in the cell list (0, 1, 6, 7) are the offshore cells. This is the
land-sea contrast Pan et al. (2013) describe — land a single afternoon peak,
ocean bimodal with a nocturnal maximum — appearing inside one domain.

So **no single temporal feature serves subtropis**, for a physical and citable
reason. This is the strongest evidence yet for the land/sea flag S-2 lists
from `gow2021ELSF`.

**S-items moved, none decided.** S-2 (coordinates, now measured both
directions; land/sea flag strengthened), S-3 (subtropis needs more than one
temporal feature), S-6 (bounding established, scale source now the question),
S-5 (compression is the mechanism, not saturation), S-10 (equal width harder
still if the domains need different kinds of feature).

**Measuring stops here.** Every S-item has its evidence.

---

### 2026-09-14 — provisional screen

`selection/screen.py`, 27 features per domain: the 20 candidates plus seven
temporary temporal encodings built in memory and discarded. All `[measured]`.
**Provisional** — the split is S-8, the `CIN`/`CBH` handling is S-4, the
temporal features are S-3. Nothing is selected.

Train 2018-2023, 2024 held out and not read. Spearman against the count on all
training rows; normalised mutual information against occurrence on 200 000
sampled rows, filtered for completeness before sampling.

**`CIN` ranks 1st imputed and 13th complete-case, in subtropis.** MI 0,3470
against `KX` 0,2266 — 53% ahead of the next feature — when the blanks are
filled at the ceiling; 0,0531 when the blank rows are dropped. Same column,
same domain, rank 1 or rank 13 depending only on whether the missingness is
kept. Tropis: 3rd imputed (0,1205), 10th complete-case (0,0554).

**The information is in the missingness, not the value.** Which also means
imputing at the ceiling and adding a missing indicator are the same operation
by two routes — the ranking cannot distinguish them.

**Unresolved by the screen, and only the ablation can settle it.** The blank is
a threshold on `CAPE`, so imputed-`CIN` may carry information `CAPE` lacks, or
may simply be a better-shaped `CAPE`. `CAPE` itself ranks 6th subtropis and
12th tropis imputed. Drop `CIN` with `CAPE` present and see what moves.

**Two reading caveats.**

*Complete-case ranks a sub-population, not a domain.* Subtropis occurrence rate
is 0,0289 over all training rows but **0,0536** among complete rows — where
`CIN` is defined, the atmosphere is convective and lightning is nearly twice as
likely. Tropis 0,0570 against 0,0708. The complete-case block answers "among
hours where `CIN` exists, what matters", which is a real question and not S-4's.

*Do not compare MI values between the two blocks, only ranks.* Every subtropis
imputed MI is roughly double its complete-case counterpart across all 27
features. That is the lower occurrence rate raising normalised MI uniformly,
not 27 features each becoming more informative.

**The domains rank the meteorology very differently** (subtropis / tropis,
imputed): `KX` 2 / 13, `TCWV` 4 / 17, `CAPE` 6 / 12, `T2M` 10 / 25, `D2M`
14 / 26, against `TCLW` 16 / 1 and `TCIW` 3 / 2. Spearman's top three barely
overlap. This is D-11's premise, re-measured on the current table, and much
sharper than the void 2026-09-11 version.

**The temporal split holds, and `cos_sza` outperforms expectation.**
`hour_sin` ranks 6th tropis and 24th subtropis imputed; `month_cos` 14th tropis
and 9th subtropis. Diurnal matters in West Java, seasonal in Florida, as the
diagnosis predicted.

But `cos_sza` ranks **5th in tropis complete-case** and 8th subtropis, above
`hour_sin` in subtropis by twelve places. This is evidence **against** the
2026-09-14 literature note in S-3, which found no precedent for solar zenith
angle as a lightning predictor and concluded `cos_sza` was the weaker half of
D-12. On this ranking it is the better temporal feature in the domain whose
signal is seasonal — which is physically coherent, since solar elevation
carries hour and season together where `hour_sin` carries only hour. D-12 may
survive re-argument better than the note suggested.

**`lat` ranks 2nd on MI in tropis complete-case with a Spearman of -0,0446.**
Strongly informative, not monotone — which is the dead-cell leakage appearing
as a good score, exactly as S-2 predicts. `PS` at 1st is terrain, and probably
a relative of the same effect. Contrast `VIIWD`, 4th on MI in subtropis with
Spearman 0,0202: the same high-MI, near-zero-rank signature, but physically
sensible, since ice divergence matters in both signs. **A high MI rank is not
a recommendation, and these two cases are why.**

**S-items moved, none decided.** S-4 (both handlings priced; the `CAPE`
confound is now the open question), S-3 (`cos_sza` strengthened, the diurnal /
seasonal split confirmed), S-2 (leakage visible in the ranking), S-10 (the
domains disagree sharply), S-9 (method demonstrated end to end).

---

### 2026-09-14 — mRMR ordering, D-21 steps 2 to 4

`selection/screen.py`. 23 features per domain after step 3, five seeds, 2024
held out. All `[measured]`. Nothing selected.

**The domains agree far more than every earlier method said. Ten of the top
twelve are shared.** Only `KX` and `TCIW` are subtropis-only; only `PS` and
`cos_sza` are tropis-only.

Every prior ranking said the opposite. The relevance-only screen had `KX` 2nd
subtropis and 13th tropis, `TCWV` 4th and 17th. The ablation had `TCIW` 1st and
12th, and `PS` dead in subtropis but 2nd in tropis.

**The explanation is redundancy, and it matters for S-10.** `KX`, `TCWV`,
`CAPE`, `TOTALX`, `T2M` and `D2M` all measure one warm-moist-unstable axis. The
two domains were selecting **different members of a single redundant cluster**,
which reads as disagreement until something penalises redundancy. mRMR takes
one member and suppresses the rest, and most of the disagreement disappears.

So D-11's premise — that the domains need different feature sets — rested on
rankings that had not controlled for redundancy. It is substantially weaker
now, and a single shared set is a live option for the first time.

**A derived feature won, and another failed.** `cloud_water` (`TCLW` + `TCIW`)
ranks **1st in tropis**, ahead of both parents — `TCLW` 13th, `TCIW` 17th — and
10th in subtropis. The phase-agnostic sum beats either phase alone.
`dewpoint_depression` **failed**: 22nd and 16th, relevance 0,017 and 0,015,
below both parents. A physically motivated derivation that did not pay, which
is worth reporting in Bab VI — it shows step 2 is not free.

**`lat` and `lon` confirm D-21's second exclusion rule empirically.** In the
comparison pass, `lat` enters **4th in tropis** with relevance 0,1174 and
redundancy 0,0286: highly relevant, redundant with nothing, and therefore
exactly what mRMR is built to select. A correlation method cannot see that the
relevance is six dead cells being memorised. Including the pair displaces `KX`,
`TCIW` and `TOTALX` from the tropis top twelve.

**The divergence variables dominate, and the ablation had missed them.**
`VIIWD`, `VILWD` and `VIMDF` are all top-nine in both domains. The ridge
ablation put them 13th to 19th. This is the linear under-valuation D-21 step 6
warns about, now measured: mutual information sees them, ridge cannot, and a
circuit may. Bab VI should report both and the disagreement between them.

**Stability across five seeds.** Most features are 1,00 — always in or always
out. The unstable ones are `cos_sza` in subtropis (0,20), `TCLW` and `TOTALX`
in tropis (0,20), `hour_cos` and `PRECTOTCORR` (0,80). An unstable feature is a
weak selection and should be reported as one rather than presented as chosen.

**On reading the score column.** The printed score is the greedy criterion at
the moment of the pick, and it is **not monotone down the list**. Redundancy is
the *mean* correlation against the chosen set, so admitting a member that is
nearly uncorrelated with a waiting candidate lowers that candidate's average
and raises its score. Subtropis rank 4 outscoring rank 3 is this, not an error:
`doy_sin` was penalised against {`KX`, `VIIWD`} at step 3, then `hour_cos`
joined at |rho| about 0,06 and pulled its mean down. Claude first reported this
as a bug; it is a property of the mean-based formulation.

**S-items moved, none decided.** S-10 (a shared set is now viable; D-11's
premise weakened), S-2 (the leakage mechanism measured directly), S-9 (mRMR
demonstrated end to end).

---

### 2026-09-14 — mRMR with multivariate redundancy, two targets, two arms

Third and final form of `selection/screen.py`. All `[measured]`. Nothing
selected. Supersedes the earlier 2026-09-14 mRMR block for every quantity it
covers; that block used pairwise redundancy and ranked against occurrence only.

**Pairwise redundancy had a hole, and it was visible in the output.** Mean
absolute Spearman against each chosen feature cannot see dependence involving
three or more variables. `cos_sza` is a function of day-of-year, hour and
latitude, so its correlation with any one of them is modest and mRMR admitted
all four as independent — four columns of time in a set of ten.

Redundancy is now the **rank R-squared of the candidate regressed on the
already-chosen set**: how much of it the set can already explain. With one
chosen feature this is exactly rho-squared, so the pairwise form is the special
case. Still rank-based, so still invariant to S-5 and S-6.

It works. `hour_cos` redundancy is now 0,988 subtropis and 0,993 tropis — with
`hour_sin` and `cos_sza` chosen, the set explains essentially all of it — and it
falls to last in both domains.

**Two targets are ranked, not one.** Occurrence, on all training rows; count on
`log1p`, on flashing hours only (85 073 subtropis, 89 917 tropis). §4 names the
target as `flash_count`, and ranking only against occurrence measures half of
it. Count relevance is normalised by the largest value in its own ranking,
since continuous-target MI has no entropy to divide by — **ranks are comparable,
magnitudes are not**, and not across domains either.

**Two arms are reported, and this is the finding.** `full` is all 25 candidates.
`meteorology` removes `lat`, `lon` and the five temporal encodings: seven
features that are known in advance for any date, forever, and that no NWP
system would supply. §4 calls the model a diagnostic that becomes a forecast
when driven by forecast fields; a set built largely on these is a
**climatology**, predicting the average lightning for a place and time of year.
Real skill, and the same answer every year regardless of the weather.

**The meteorology arm recovers the instability indices completely.** Subtropis
count goes from `lat`, `lon`, `cos_sza`, `doy_sin` to **`T2M`, `KX`, `TOTALX`,
`WS2M`, `CRR`, `PS`**. `T2M` moves 21st to 1st, `TOTALX` 12th to 3rd. Tropis
count: `PS`, `cloud_water`, `VIIWD`, `CRR`, `TCIW`, `WS2M`, with `CAPE` at 9th
and 6th.

So those variables were never uninformative. The calendar was explaining them
away, correctly — `CAPE` at 15:00 in July at 28°N is largely predictable from
15:00, July and 28°N. That is the mechanism behind every earlier ranking in
which the meteorology sat at the bottom.

**Correction: `dewpoint_depression` did not fail.** The earlier block recorded
it 22nd and 16th and called it a derivation that did not pay. In the
meteorology arm it is **8th in subtropis count with relevance 0,8638**, the
second-highest raw relevance in that ranking. Both its parents are heavily
climatological; remove the calendar and their difference becomes one of the
strongest count predictors in Florida. The earlier reading was an artefact of
the full arm, and the negative result recorded there should not be quoted.

**The two stages diverge once climatology is gone.** In subtropis meteorology
they agree on only **6 of 10**: occurrence wants cloud and ice (`TCIW`, `TCLW`,
`VIIWD`), count wants temperature and instability (`T2M`, `TOTALX`,
`dewpoint_depression`). Whether it flashes depends on whether there is a storm;
how much depends on how strong. That is support for a two-stage model, and it
was invisible until the calendar was removed.

**Caveats.** Redundancy stays high throughout the meteorology arm — `TCWV`
0,92, `T2M` 0,96 in tropis occurrence — because sixteen variables measure a few
physical quantities, and no selection method removes that. Seed stability is
worse in the count arm (several at 0,60 and 0,80): fewer rows, noisier MI.

**S-items moved, none decided.** S-7 (the hurdle has measured support now),
S-3 (`hour_cos` is redundant given `hour_sin` and `cos_sza`), S-11 (four
candidate sets per domain, not two).

---

### 2026-09-14 — ablation on the selected sets, and the climatology gap

`selection/ablate.py`, D-21 step 6. Four sets per domain at N = 10, ridge and
logistic regression, 2024 held out whole. All `[measured]`. **Provisional**: the
split is S-8, the scaling S-5/S-6. Nothing selected; `modelled.json` not written.

**In subtropis the meteorology arm beats the full arm.** Occurrence PR-AUC
0,2547 against 0,2295; count R² **0,0626 against 0,0308 — double**. Removing
`lat`, `lon` and the calendar made Florida better, and by a wide margin.

Tropis runs the other way: occurrence 0,2871 full against 0,2577 meteorology
(share 0,898), count 0,1178 against 0,0797 (share 0,676). Climatology carries
about 10% of occurrence skill and 32% of count skill in West Java.

**This is not a bug, and the framing matters.** The two arms are not one model
with features removed — they are **two different selections of ten**. The full
arm spends six of its ten slots on space and time; the meteorology arm spends
all ten on weather. So in Florida, ten meteorological variables beat four
meteorological plus six climatological ones.

The correct statement is therefore **not** "removing climatology helps". It is:
**at a fixed budget of ten, climatological features are a poor use of the budget
in subtropis and a mildly good one in tropis.** mRMR admitted them because they
are mutually non-redundant, not because they earn a slot — a known consequence
of relevance-minus-redundancy scoring, which has no notion of opportunity cost.

**The diurnal asymmetry is confirmed at full strength.** `hour_sin` is worth
0,0817 of a 0,2871 tropis occurrence baseline — **28% of the model's entire
skill in one feature** — and 0,0411 of 0,1178 on count. The largest single
subtropis contributor is `KX` at 0,0717, and its diurnal features are worth
about 0,02. Every earlier measurement said West Java is diurnally driven and
Florida is not; this is the strongest form of it.

**N = 10 is expensive, and D-22 did not know that.** The 23-feature ablation
earlier the same day scored 0,2912 subtropis and 0,3855 tropis on occurrence.
The ten-feature full arm scores 0,2295 and 0,2871. Restricting to ten costs
roughly 0,06 and 0,10 of PR-AUC in the two domains. D-22 fixed N on seed
stability and simulation cost without this figure in front of it. **Not
reopened here** — recorded so the choice is revisited on evidence rather than
inherited.

**Per-feature notes.** `PS` is the largest single contributor in three of the
four tropis sets (0,0472 and 0,0456 on occurrence, 0,0189 on meteorology
count), which is consistent with it standing in for terrain. `VIIWD` is
negative or near zero in six of eight sets despite ranking top-three on mutual
information in both domains — the linear under-valuation D-21 step 6 warns
about, and the clearest case for reading the ablation beside the screen rather
than instead of it. `dewpoint_depression` contributes 0,0012 in subtropis
meteorology count, small but positive, against the earlier full-arm reading
that it failed.

**S-items moved, none decided.** S-7 (the two stages are measured separately
for the first time), S-10 (N = 10 has a measured cost now), S-11 (four candidate
sets per domain, and the arms differ).

---

### 2026-09-14 — the climatology gap across widths

`selection/ablate.py` swept at N = 8, 10, 12, 15, 18. All `[measured]`.
Provisional on S-8 and S-5/S-6. This separates the two explanations the N = 10
result could not distinguish, and **they separate by domain**.

**Subtropis: the budget was the constraint, mostly.** The count share collapses
as N grows — 2,031 at N=10, then 1,916 / 1,423 / 1,092 / 1,058 at 8, 12, 15,
18. Occurrence: 0,987 / 1,110 / 1,124 / 1,083 / 1,051. At 15 and 18 the two
arms are within 6% of each other.

So Florida's dramatic N = 10 result was largely artefact: at ten slots the full
arm had four left for weather and could not fit what it needed. **The earlier
block's reading — that climatological features are a poor use of the budget in
subtropis — is correct only at a tight N and must not be quoted without the
curve.**

The residual is real but small. At every width tested the subtropis meteorology
arm is at or above the full arm, ending at 1,051 and 1,058. Consistent
direction, never large once N is adequate. Physically coherent: Florida's
signal is seasonal, and `doy_sin` / `doy_cos` are a crude proxy for what `T2M`
and `TOTALX` measure directly.

**Tropis: the climatological features genuinely earn their slots.** Share stays
between 0,590 and 0,811 at every width and does not trend toward 1. At N = 15
the full arm scores 0,3620 against the meteorology arm's 0,2678 — **the
climatological features are worth 26% of occurrence skill**, and more room does
not erode it.

`hour_sin` is the reason: worth 0,0817 of a 0,2871 baseline alone, and no
meteorological variable substitutes, because the West Java diurnal cycle is a
15,9-point swing in zero share that the weather columns do not carry.

**The headline is a contrast, not a verdict.** In West Java, knowing the hour is
worth about a quarter of the model. In Florida, knowing the calendar is worth
nothing once there is enough weather. Same method, same budget, opposite
answers, and each with a physical explanation already measured. That is a
better Bab VI result than either domain alone.

**N = 10 costs real skill, and D-22 did not have this curve.** Tropis
occurrence: 0,2871 at N=10, 0,3620 at 15, 0,3714 at 18 — a 26% relative gain
from 10 to 15. Subtropis occurrence gains 18% over the same range. Count gains
are larger still in subtropis, 0,0308 to 0,0672.

**A noise floor to respect.** Tropis occurrence share runs 0,791, 0,740, then
back up to 0,811 at N = 18. Non-monotone, so differences in share below roughly
0,05 should not be read as signal.

**S-items moved.** S-10 is **reopened** — D-22 fixed N = 10 on seed stability
and simulation cost, and the measured cost of that choice is now on the record.
S-7 unchanged; S-11 unchanged.

---

### 2026-09-14 — the selected sets. `modelled.json` written

`selection/screen.py` at N = 15, D-21 steps 2 to 5. All `[measured]`. Six sets
written to `dataset/modelled.json` and read straight back through
`features.py`: occurrence and count per domain from the `full` arm (D-26), plus
the shared pair for the transfer arms (D-27). **This is the committed output of
selection**, and §2 step 4 is complete.

**Composition is nine meteorological to six climatological in all four
per-domain sets.** `hour_cos` is excluded from every one — last in both domains
at redundancy 0,988 and 0,993 once `hour_sin` and `cos_sza` are chosen — and
the remaining six climatological features survive. At N = 10 the split was four
and six; the five extra slots of D-24 had only meteorology left to fill them.
The concern that the sets would be dominated by time is answered by the
arithmetic: there are only seven climatological candidates, so N = 15 forces at
least eight meteorological.

**The two stages agree less in the `full` arm than in the `meteorology` arm.**
Subtropis 11 of 15 full against 14 of 15 meteorology; tropis 13 of 15 against
**15 of 15**. Without the calendar the two questions want nearly the same
weather; with it they diverge. So the stage divergence that supported D-25 is
partly a climatology effect — the hurdle's justification rests on the
persistence measurement and on the full-arm divergence, and Bab IV should not
overstate it.

**The pooled shared set resembles neither domain.** `TCIW` leads the shared
occurrence ranking while ranking 12th in subtropis and 18th in tropis
individually; `KX` falls to 17th despite leading subtropis. The pooling is
unweighted, so it carries 2 944 704 subtropis rows against 1 577 520 tropis —
roughly 2:1 toward Florida — and that interacts with the redundancy penalty.
This is the design working as intended: the transfer arms train on a compromise
set, which is what makes the two directions comparable. It is also the reason
D-27 requires transfer results to be compared against shared-set baselines
rather than against the per-domain models.

**The shared set's last slots are unsettled, and this must be reported.**
Seed stability in the shared occurrence ranking: `TCLW` 0,60, `cloud_water`
0,40 — the latter with a mean position of 11,8 despite ranking 19th on averaged
relevance, so it lands inside the top fifteen in two runs of five and outside
in three. Shared count: `TCWV` 0,60, `WS2M` 0,40. The per-domain sets are far
more stable — everything 1,00 except `WS2M` / `CAPE` at 0,80 / 0,20 at tropis
rank 15, which is one swap.

**Unmeasured, and it bears on D-27.** `cos_sza` is in both shared sets and is
computed from latitude. D-27 excluded `lat` and `lon` from the shared set
because they carry 0,0000 effective resolution across domains. Whether
`cos_sza` inherits that has **not been measured**, and it should be before any
transfer result is trusted.

**Contract.** `features.py` now holds three sets per stage — `modelled(domain,
stage)` and `modelled_shared(stage)` — with the equal-width check applying
within a stage (D-24, D-25) and an assertion that `lat` and `lon` never appear
in the shared set (D-27). `screen.py` reads the file back through the contract
after writing it, so a file the contract cannot load fails at write time rather
than at training time.

---

### 2026-09-14 — three encoding maps compared

`selection/diagnosis.py` section 3, rewritten. Replaces the two-map comparison
recorded in the second-pass block, which did not test quantile bounds. All
`[measured]`. Fitted on the source domain only, reported both within domain and
across.

**Mean resolution over all 20 candidates** — the share of the output range a
domain's middle 50% occupies:

| | min-max | quantile (p1/p99) | arctan(x/IQR) |
|---|---|---|---|
| within domain | 0,1350 | 0,2251 | 0,2883 |
| cross domain | 0,0959 | 0,1846 | 0,2390 |

**Quantile bounds recover most of the gap from one rule change.** 67% of the
way from min-max to arctan within domain, 62% across, with no per-variable
constant. The worst cases improve most: `CRR` within subtropis 0,0006 to
0,0065; `VIIWD` 0,0006 to 0,0085.

**arctan's within-domain column is an artefact and must not be quoted.**
Nearly every variable scores 0,294-0,295 — `arctan(x/IQR)` maps the
interquartile range to a fixed output width by construction, so the number
measures the transform rather than the feature. `CRR`'s 60% point mass is
untouched by it; the tied value simply sits at 0,5 instead of 0,0.

**The cross-domain column is not an artefact.** There the scale is fitted on
the source and applied to the target, so the target's share is free to vary,
and it does: 0,0004 to 0,4423 across candidates. arctan's cross-domain
advantage over quantile — 0,2390 against 0,1846, about 29% — is real.

**`PS` is the one variable quantile bounds make worse across domains**, 0,5714
to 0,1000 subtropis-to-tropis and 0,0349 to 0,0000 the other way. The two
domains barely overlap in surface pressure, so tightening the bounds pushes the
other domain outside them entirely.

**The physical bound works as intended.** `RH2M` scores identically under
min-max and quantile — 0,1494 and 0,1191 — because [0, 100] overrides both
fitted rules.

**A correction to the second-pass block.** It recorded that a bounded map beats
min-max "by about four times, in 35 of 36 column-arm pairs". That comparison
was against min-max fitted on the **extremes**. Against min-max fitted on
quantiles the advantage is about 1,3x. The earlier figure is not wrong, but it
overstates the case for bounding by comparing against the weakest possible
fitting rule, and should not be quoted without saying so.

---

### 2026-09-14 — the two owed measurements

Both obligations the record carried are discharged. All `[measured]`.

**`cos_sza` does not inherit latitude's cross-domain failure. D-27 stands.**
D-27 excluded `lat` and `lon` from the shared transfer set because they carry
0,0000 effective resolution across domains, and flagged that `cos_sza` is
computed from latitude and might behave the same way. It does not. Cross-domain
resolution under the bounded map: **0,3438** subtropis-to-tropis and 0,2515
the other way, against `lat` 0,0004 and `lon` 0,0000. Latitude enters `cos_sza`
only through the declination term; the hour angle does the work, and it is
identical in both domains. No amendment to D-27 is owed.

**Dropping `CIN` cost real skill, and D-19's defence does not survive.**
D-19 dropped `CIN` and `CBH` as structurally undefined and argued that imputed
`CIN`'s first-place mutual-information rank might be a better-shaped `CAPE`
rather than distinct information — recording that the claim "must be tested,
not asserted". The test is the complete-case ablation, on rows where both are
defined, with `CAPE` in the set and nothing imputed.

Occurrence PR-AUC: subtropis **0,2651 without against 0,2893 with**, a cost of
+0,0242, about 9% relative. Tropis 0,3717 against 0,3933, +0,0216, about 6%.

And it is `CIN` alone. Leave-one-out inside the larger set gives `CIN` +0,0197
and +0,0145; `CBH` -0,0003 and +0,0002, indistinguishable from zero. **Dropping
`CBH` was free; dropping `CIN` was not.**

**Count behaves differently.** Subtropis -0,0001, tropis +0,0062. `CIN` helps
decide whether an hour flashes and barely helps decide how many, which is
physically coherent — inhibition governs whether convection initiates, not how
large the storm becomes.

**This does not reverse D-19.** The rule was that a structurally undefined
column is dropped rather than imputed, and that holds whatever the value is
worth where it is defined: there is no non-arbitrary value to put in the 46,4%
of subtropis rows where no convective layer exists. What the measurement does
is convert "a stated limitation" into "a stated limitation with a number", which
is what D-19 said it owed. Bab VI reports the figure rather than the argument.

**Two caveats that travel with it.** The rows are filtered, so the test set is
reshaped — §4 forbids that for anything reported as a result, and this is a side
measurement. And complete-case rows are a convective sub-population: subtropis
occurrence is 0,0600 on them against 0,0289 over all test rows, tropis 0,0719
against 0,0571. Lightning is about twice as likely where `CIN` is defined. That
is the only population on which the column can be priced at all.

**From the same run, at N = 15.** Tropis `hour_sin` is worth **0,0979 of a
0,3620 occurrence baseline — 27% of the model** — so the figure recorded at
N = 10 was not a small-budget artefact. And `VIIWD` scores negative or near zero
in six of the eight ablated sets while ranking top-three on mutual information
in both domains: the clearest case in the project for Bab VI reporting the
screen and the ablation together rather than either alone.

---

## Open

**O-1 to O-9 are superseded by the S-list below, 2026-09-14.** They are kept
because §7 says a record is not edited to look tidier, but the S-list is what
`selection/` works from. O-2 is the exception — it concerns the environment,
not selection, and stays live.


**O-1 — CLOSED 2026-09-11 by D-12.** `hour_sin` and `cos_sza` are the two
candidates; the other five calendar columns move to `EXCLUDE`. The `cos_sza`
seasonal claim below did not survive measurement — see D-12 and Measured. The
land/sea question D-12 raises stays open under O-3. Original text kept below.

**O-1 (original) — The calendar columns.** A proposal exists and is not yet written into
`features.py`: `hour_of_day_local` as a candidate, encoded sin/cos rather than
as an integer; `cos_sza` as a new candidate, computed from lat, longitude, day
of year and hour rather than downloaded, carrying season with the correct sign
in both hemispheres; `month_of_year` and `day_of_year` tested against `cos_sza`
rather than assumed; `hour_of_day_utc` as bookkeeping.

`cos_sza` does not replace `hour_of_day_local`. SZA is symmetric about solar
noon, so 09:00 and 15:00 are near-identical (0.724 against 0.681
**[measured]**) while lightning peaks in the afternoon. Both are needed.

Surface shortwave radiation (ERA5 `ssrd`, POWER `ALLSKY_SFC_SW_DWN`) is **not**
a substitute: its value is suppressed by the storm clouds that are the
prediction target, making it an observation of the outcome rather than a
predictor of the conditions.

The seasonal argument against `month_of_year` and `day_of_year` is now
measured rather than assumed: subtropis strikes by calendar month average
209 597 in July against 2 704 in January, a factor of ~78, peaking in JJA;
tropis peaks in the wet season. The two cycles are close to antiphase, so a
model trained on one domain learns a month-to-activity mapping that is wrong in
the other.

`build.py` already emits all seven columns, so this is a `features.py` edit
with no rebuild. Blocked on the literature step.

**Updated 2026-09-11. No longer blocked, and more urgent than it reads.**
`hour_sin`, `hour_cos` and `cos_sza` are present in both built tables and are
in **neither `CANDIDATES` nor `EXCLUDE`** — `check_against_table` reports this
in both domains. `cos_sza` is described above as a proposal to compute; it
already exists. Three unclassified numeric columns is exactly the hazard the
check's own message names: any "everything numeric" selection in `selection/`
picks them up without a decision having been made. **This must close before
`selection/` reads a column list.**

Evidence for keeping `hour_of_day_local`, now measured rather than argued: in
tropis the diurnal cycle spans 15,91 points of zero share against CAPE's 8,52
across its deciles — the clock discriminates nearly twice as well as the single
most-cited convective predictor. In subtropis it reverses, CAPE 8,98 against
diurnal 5,04. That asymmetry is itself a Bab VI finding.

The literature offers weak support for including calendar columns regardless of
screening outcome: one forecast post-processing study force-includes prediction
time, month and hour whatever its three selection methods return (arXiv
2604.19340, metadata unverified). It does not address the antiphase problem.

**O-2 — Whether the lock is one file or two.** `requirements.txt` holds both
the pins and the reasoning, so regenerating it with `pip freeze` destroys the
comments — which has already happened once. The alternative is a
generated-only `environment-lock.txt` beside it. v1's D-41 was caused by two
files disagreeing after one was hand-edited, not by there being two.

**O-3 — Permanently dead cells, and `lat`/`lon` cannot transfer at all.** 6 of 30
tropis cells never flash in 61 368 hours; **0 of 56 subtropis cells**
**[measured]**. All six sit in the two extreme latitude rows, none in the
interior — consistent with `snapped_bbox` rounding the box outward past the
extent the strike data covers.

`lat` and `lon` are candidate predictors, so a model can learn "this coordinate
is always zero" and score well on tropis without learning any meteorology:
368 208 rows, 20% of the domain, guaranteed correct. There is no equivalent
rule to transfer to Florida, so it inflates one side of the comparison and does
nothing for the other — and the cross-domain gap is the number this thesis
reports.

**The range measurement makes this sharper.** Tropis latitude spans −7,75
to −5,75; subtropis 26,75 to 30,25. They do not overlap at all, so a
source-fitted min-max scaler maps **100% of the target domain's `lat` and `lon`
outside [0, π]** in both directions.

**Corrected 2026-09-11.** This paragraph previously said the rotation *wraps
rather than clips* and that the two features *carry noise*. Both are wrong
against the archive `[repo]`: `CLIP_TEST_FEATURES = True`, and `Scaler.transform`
clips to [0, 1] before mapping onto [0, π] — the archive makes the same aliasing
argument and already prevents it. The correct statement is **saturation, not
aliasing**: every target-domain `lat` and `lon` value clips to exactly 0.0 or
exactly π. In the cross-domain arms those are not noisy features, they are two
constants occupying two of fifteen qubits. That is a larger and more measurable
cost than "noise", and it applies only to the cross-domain arms — the number
this thesis reports.

The same mechanism, milder, applies to `PS`: 36,37% of subtropis rows collapse
onto a single boundary value in `sub_to_tropis`.

Whether the new code clips at all is itself a decision, not an inheritance.

So dropping `lat` and `lon` as predictors addresses both problems at once: the
dead-cell shortcut and the fact that a coordinate cannot mean anything in the
other hemisphere. `gow2021ELSF` uses a binary land/sea flag alongside
coordinates, which captures what the coordinates proxy for in a form that does
transfer.

Other predictors also wrap, less severely: `PS` at 36,37% of subtropis rows
outside the tropis range and 25,92% the other way, `T2M` 2,62%, `KX` 1,11%.
Everything else is under 1%.

Distinct from the zero-hour question §4 settles: a quiet hour in an active cell
is a real observation; a cell with no flash in seven years probably is not
observed at all. Options: exclude such cells, exclude `lat`/`lon` as
predictors, or keep both and declare the effect. This is a `selection/`
decision, not a `dataset/` one.

**O-4 — CLOSED 2026-09-14 by D-14.** All seven acquired and promoted to candidates; `mean_convective_precipitation_rate` dropped in favour of `convective_rain_rate`. Original text below.

**O-4 (original) — Tier 1 ERA5 additions.** Seven candidate variables are drafted and
their short names are in `era5.VARIABLE_SHORTNAME`, but `VARIABLES` still
requests six and `features.CANDIDATES` holds none of them. A one-month,
one-domain trial is written and waiting on the KX queue; it is also the first
request to mix analysis and forecast variables, and therefore the first to
exercise the ZIP branch. `mean_convective_precipitation_rate` is a mean rate
and would need a one-hour realignment; `convective_rain_rate` is the
instantaneous alternative and would not. Undecided.

**Updated 2026-09-11.** The seven are named in `era5.VARIABLE_SHORTNAME` and are
`VIMDF`, `TOTALX`, `CIN`, `CBH`, `TCWV`, `D2M`, `CRR` — `convective_rain_rate`,
the instantaneous option, is the one in flight. The download is still running;
the built tables measured on 2026-09-11 are the **pre-tier-1 baseline**, 37
columns and six ERA5 variables, and `check_against_table` should be re-run
against that baseline when the seven land.

Two things to check on arrival, neither assumed:

- **`CBH` may be undefined in clear-sky hours.** If ERA5 returns NaN there it is
  the first candidate to break "no missing values". Unverified.
- **Run `--check` before trusting the files.** These are the first request to
  mix analysis and forecast variables, so the first that can return a ZIP, and
  Measured records that `_open_members`' archive branch has never executed.

**A Bab II point this settles.** Recent lightning-ML work identifies the
700–500 hPa lapse rate and a moist-static-energy ratio as dominant predictors
(western-US CG-lightning CNNs, PMC11583119, metadata unverified). Neither is a
standalone column here, and a true lapse rate **cannot** be: it needs
`reanalysis-era5-pressure-levels`, a different dataset and therefore a second
acquisition job, which §2 forbids after the freeze. But the ingredient is
present — total totals is (T850−T500)+(Td850−T500) and K index is
(T850−T500)+Td850−(T700−Td700), so both carry a mid-level lapse-rate term
inside them. Bab II should say the contribution enters through KX and TOTALX
rather than standalone, and name the dataset constraint. That is a stated
limitation, not a gap.

**O-5 — CLOSED 2026-09-11.** The unit annotation was wrong; the data is fine.
NASA POWER declares mm/day. The tail is smooth and spans every cell, so neither
of the two hypotheses this item offered survives. See D-10 and Measured. Two
code edits are outstanding: the `mm/hour` comment in `features.POWER`, and any
chapter text repeating it.

**O-6 — One model or two stages. Narrowed 2026-09-11; still undecided.**
The dry-spell measurement supports v1's `occurrence`/`count` split: median runs
of 15–20 hours and two thirds of subtropis zero rows inside week-long runs is
switch-like behaviour rather than a continuous process with many small values.

Two measurements now bound the question:

- **A zero-inflated mixture is ruled out.** The negative binomial already
  over-predicts the zeros in both domains, so there is no surplus for a
  structural-zero component to explain. This does *not* rule out a hurdle: a
  hurdle is the factorisation P(y) = P(y>0)·P(y | y>0), which is valid whatever
  produces the zeros. ZI makes a claim about the world; a hurdle makes a claim
  about how the prediction is decomposed.
- **The gate is not clean.** Under maximal conditioning the zero share is still
  56,29% and 64,93%. Whatever is chosen, stage 1 has a resolution-imposed
  ceiling and Bab VI must declare it rather than let it read as a weak
  classifier.

v1 already ran `TASK = "hurdle"` by default, on measured grounds this record
does not carry: at a 6-hour reporting window the target is still 85,40% /
91,35% zeros `[repo]`, so a single count regressor stays badly conditioned no
matter how wide the window gets.

The remaining choice is between a hurdle whose stages are composed and scored on
the whole held-out year at natural ratio, a hurdle whose count stage is scored
on non-zero test rows only (v1's practice, which reshapes the test set and
violates §4), and a single model on all rows. No QML literature on zero-inflated
targets was found; the hurdle approach is classical.

**O-7 — Skew must be fixed before min-max, for some predictors.** See the
squashing measurements. Under plain min-max the worst predictors are nearly
constant to the circuit. The likely order is: fix skew, z-score, then min-max
to [0, π]. Which transform, and which predictors need it, is undecided.

**Sharpened 2026-09-11 — this is a fairness condition, not a preprocessing
preference.** `_apply_feature_map` is Hadamard then `RZ(2x)` `[repo]`, so the
encoding has period π in x and [0, π] is exactly one full period rather than an
arbitrary convention. A predictor occupying 7,4% of that range is evaluated over
a phase arc of roughly 0,46 rad, where a sinusoid is close to linear — so the
circuit's response to it is approximately affine no matter how many ansatz reps
are added. The loss is in the encoding, before any trainable parameter.

A classical MLP fed the same squashed column simply learns a larger weight and
loses nothing. **So a bad transform degrades one arm of the comparison and not
the other**, and the gap between the arms is the number this thesis reports.

Theoretical support: Schuld, Sweke & Meyer, *Effect of data encoding on the
expressive power of variational quantum-machine-learning models*, Phys. Rev. A
103, 032430 (2021), arXiv:2008.08605 — a quantum model is a partial Fourier
series in the data whose accessible frequencies are set by the encoding gates.
Practical support for pre-scaling to [0, π]: Sammartino, arXiv:2606.05387
(preprint, not peer-reviewed).

Two complications the transform choice has to survive:

- **Roughly 20% of subtropis rows have CAPE ≤ 0,375.** Min-max leaves that mass
  at one end; a quantile transform spreads it across a wide output range purely
  on tie-breaking, inventing structure that is not there.
- **A rank-based transform is not a fix for O-3.** Quantile transforms map
  unseen out-of-range values to the *bounds*, so a source-fitted quantile
  transform collapses the whole target domain's `lat` onto one value. That is a
  different failure, not a solution.

The literature frames the trade-off as min-max preserving distribution shape but
not being robust to outliers, against quantile transformation being robust but
destroying shape entirely. McCarter, *The Kernel Density Integral
Transformation*, arXiv:2309.10194, interpolates between them with one parameter.
Metadata unverified.

**O-8 — Informative missingness in `CIN` and `CBH`. New 2026-09-14.**
Both are undefined rather than absent: `CIN` where there is no convective layer
to inhibit, `CBH` where there is no cloud. The NaN carries the information "no
layer here", which for a lightning model is a strong negative signal, so mean
imputation would both destroy it and insert a plausible-looking value into
hours that physically had none.

Options: a sentinel plus a missingness indicator, which costs a qubit per
indicator against a 15-qubit budget; imputing the value that means "no
inhibition" (0 for `CIN`) and relying on `CAPE = 0` to carry the same
information, which is defensible given they co-occur 99,6% of the time; or
dropping both and letting the ablation price it.

Before deciding, explain the residual — 20,6% of tropis and 34,6% of subtropis
rows have positive `CAPE` and still no `CIN`, which the "undefined without
CAPE" story does not cover.

A `selection/` decision. Also a Bab IV declaration: `CIN` is available twice as
often in West Java as in Florida, and a predictor whose availability differs by
domain is a confound in a cross-domain experiment.

**O-9 — `build.py` silently dropped unclassified columns. Fixed 2026-09-14;
recorded because the class of fault matters.**
Column ordering selected only columns the contract named, and
`check_against_table` ran afterwards — so the check inspected its own output
and could never fail. Seven acquired ERA5 columns were merged, reported in the
build log, then discarded before writing, and the contract check reported
"table matches". Found only by counting uppercase columns in the parquet.

Fixed: the check runs before the reorder, and the reorder appends unknown
columns rather than dropping them, satisfying §3's "the built table is wider
than the model". Verified on a synthetic table — 16 columns in, 16 out.

Kept open as a note, not a task. Three faults this week had the same shape:
something downstream kept comparing against a definition that had moved
(`expected_files` after AOD left `PARAM_FREQ`; `--check` after
`SHORTNAME_MAP` grew; this). Worth checking for whenever a list changes.

---

# Selection — the decisions to make

A clean list, replacing O-1..O-9. Each item is one decision, what is already
measured about it, and the options. Nothing here is decided. When one is
decided it becomes a numbered `D-` entry and drops off this list.

**Staged per D-17.** Stage 1 is generic description and holds no decisions —
it produces the evidence the rest of this list needs. Stage 2 is targeted, and
its membership is an output of stage 1 rather than a choice made now; only the
zero majority (S-1, S-7) can be named in advance. Stage 3 holds the steps any
pipeline needs (S-3, S-5, S-6, S-8, S-9) plus S-2, which is a leakage and
transfer argument rather than a description finding. S-4 is a stage 1
consequence.

**Every figure quoted under these items that is dated 2026-09-10 or
2026-09-11 is void per D-17** and is retained only to show what was previously
believed. Nothing on this list may be decided on those numbers.

Order matters a little: S-1 and S-2 change which rows and columns exist, so
they come before S-5 and S-6, which measure what is left.

---

## S-1 — Which rows to train on

Every month is in the table, including three subtropis months with no lightning
at all (D-8). Nothing has been filtered.

**Measured.** `coverage` is a weather filter, not a data-quality filter:
Spearman 0,838 tropis and 0,915 subtropis against mean flash count. Months
below 25% coverage average 0,008 flashes; months above 90% average 1,72. A
uniform 0,9 gate would delete 31% of West Java and 70% of Florida, for
climatic reasons rather than detector reasons.

**Options.** No filter at all. Drop only `coverage = 0` rows, which are
unambiguously unobserved. Some other gate, argued from something other than
coverage.

**Constraint.** §4: test rows are never reshaped. Whatever is dropped is
dropped from training only, and the held-out year stays whole.

---

## S-2 — `lat`, `lon`, and the six dead cells — PART CLOSED 2026-09-14 by D-23

The coordinates are ordinary candidates and that part is settled. What remains
is the six dead tropis cells — 368 208 rows, guaranteed zero — which is a
question about rows, not features, and moves to S-1.

**Measured.** 6 of 30 tropis cells never flash in 61 368 hours — 368 208 rows,
20% of the domain. Subtropis has none. All six sit in the two outermost
latitude rows.

The domains do not overlap in either coordinate. A scaler fitted on one maps
**100%** of the other's `lat` and `lon` outside the encoded range, in both
directions.

**So there are two problems, and one fix covers both.** A model can learn
"this coordinate never flashes" and score well on tropis without meteorology,
and that rule cannot transfer. And in the cross-domain arms the coordinates
carry noise regardless.

**Options.** Drop `lat` and `lon`. Keep them and drop the dead cells. Keep
both and declare the effect. Replace them with a land/sea flag, which is what
`gow2021ELSF` uses and which transfers.

---

## S-3 — How to encode time — NARROWED 2026-09-14 by D-20

The candidate list is settled: `hour_sin`, `hour_cos`, `doy_sin`, `doy_cos`,
`cos_sza`. What remains is which survive the ablation, and the unresolved
land-sea spread in subtropis, where sixteen distinct per-cell peak hours mean
no single temporal column serves the domain. That part is S-2's to answer.

`dataset/` emits raw time only (D-13): `year`, `month_of_year`, `day_of_year`,
`hour_of_day_utc`, `hour_of_day_local`. `selection/` builds whatever it needs.

**Fully open.** D-12 chose `hour_sin` and `cos_sza`; D-17 parked it. The
`-0,989` correlation it rested on was measured on columns that no longer exist.

**Literature, 2026-09-14.** Cyclic hour-of-day encoding has direct precedent
and a published leave-one-out ablation: Pacey et al. (2026) find their
cosine-transformed time-of-day predictor is key to reproducing the diurnal
cycle of convective cells, while removing CAPE leaves that cycle largely
intact. Against that, a September 2026 downscaling study reports an MLP given
no explicit temporal input at all reproducing the diurnal cycle from
environmental variables alone, with roughly a two-hour peak delay — so whether
a time feature is needed is itself an open ablation question.

Solar zenith angle has **no located precedent as a lightning predictor**. Where
it appears in convection ML it is a day/night stratification threshold, not a
model input; as a feature it belongs to solar-irradiance forecasting, a
different problem. `cos_sza` would need its own defence.

Pan et al. (2013), WWLLN and LIS/OTD: land shows a single diurnal peak at
1400–1900 LT, ocean a two-peak cycle with an early-morning maximum at
0100–0300 LT. One hour feature cannot serve both, and much of the subtropis box
is Atlantic. This bears on S-2 as much as on S-3.

Cosine-of-day-of-year has precedent as a seasonal feature in ensemble
postprocessing. It does not address the antiphase problem below.

All four citations are 2026-or-earlier preprints or papers whose peer-review
status is **unverified**; check before any enters Bab II.

**Measured.** Lightning peaks at 16:00 local in tropis and 15:00 in subtropis,
inside the 1400–1800 LST band the literature reports for continental land. The
seasonal cycles are close to antiphase: subtropis averages 209 597 strikes in
July against 2 704 in January.

**Watch for.** `hour_sin` alone is ambiguous — 03:00 and 09:00 share a value.
D-12 relies on `cos_sza` supplying the missing dimension. That holds if
`cos_sza` behaves like a cosine of hour angle, which it does in the tropics but
may not in Florida winter when the sun stays low all day. Check before
committing.

---

## S-4 — `CIN` and `CBH` missingness — CLOSED 2026-09-14 by D-19

**Re-measured 2026-09-14.** `CIN` missing on 23,52% of tropis rows and 46,38%
of subtropis; `CBH` on 1,22% and 8,44%. **The missingness is seasonal, and the
two domains are antiphase.** Subtropis `CIN` null share runs 0,855 in January
to 0,017 in July; tropis runs 0,090 in January to 0,595 in August. Stable
year to year, so nothing broke in one year. `CBH` is largely a subset:
88,3% of subtropis and 76,5% of tropis `CBH` nulls are also `CIN` null, while
the reverse is 16,1% and 4,0%. Only 1 808 830 of 3 436 608 subtropis rows
(52,6%) have every candidate present; tropis 76,2%.

**Row deletion is out, on §4.** The test set is a held-out year and the nulls
are seasonal, so deleting them before the split silently removes most of one
season from whichever year becomes the test year. It also entangles with S-1:
`CIN`-null rows are overwhelmingly non-flash, so deleting them is zero-removal
by a back door, non-random and differently sized in each domain. Handle at the
column, never at the row.

**Literature, 2026-09-14.** The governing distinction is that missing data
should be handled differently for prediction than for description or causal
explanation (Sperrin, Martin, Sisk & Peek 2020) — most advice against missing
indicators comes from causal inference, and this is prediction. Within the
prediction literature, the missing-indicator method improves performance for
linear models and neural networks when missingness is informative, and harmed
performance only in high-dimensional settings where uninformative indicators
caused overfitting. A clinical-prediction simulation (Sisk et al. 2023) found
indicators harmful specifically when missing data are **not** allowed at
deployment. Both caveats miss this case: 18-20 features is low-dimensional, and
future ERA5 hours will also have undefined `CIN`. So the indicator is the
better-supported option, at one qubit each. Peer-review status of the 2023
simulation is verified; the rest unverified.

**Superseded figures below.** The following were measured pre-Tier-1 and are
void per D-17, retained for what they claimed. Structural, not lost: `CIN` is absent on 99,6% / 99,8%
of rows with zero `CAPE`, `CBH` on 94,3% / 96,0% of rows with no cloud water.
Only 4,6% / 0,9% of rows that actually recorded a flash lack `CIN`.

So the NaN means "no convective layer here", which is a signal, not a gap. Mean
imputation would destroy it and insert a plausible value into hours that had
none.

**Options.** Sentinel plus a missingness indicator, at one qubit per indicator.
Impute 0 for `CIN` and rely on `CAPE = 0` to say the same thing. Drop both.

**Unexplained.** 20,6% of tropis and 34,6% of subtropis rows have positive
`CAPE` and still no `CIN`. Explain that before choosing.

---

## S-5 — Whether to transform skew before scaling — CLOSED 2026-09-14 by D-29

**Re-measured 2026-09-14, all 20 predictors.** The compression is worst in the
divergence variables, not `CAPE`. Tropis `VIIWD` has an interquartile range of
8,1e-07 against a full range of 9,2e-04 — the middle half would occupy 0,088%
of the rotation range under plain min-max, and the maximum is ~2 900x p75.
Subtropis `VIIWD` 0,058%. `VILWD` and `VIMDF` are the same shape in both
domains.

**A transform does not fix a point mass, and the point masses are large.**
Share held by the single most frequent value, subtropis / tropis: `CRR` 0,605 /
0,393, `TCIW` 0,269 / 0,097, `PRECTOTCORR` 0,222 / 0,066, `CAPE` 0,180 / 0,038.
`CRR`'s subtropis median is zero. Any monotone transform leaves these ties
intact, so this needs a separate answer from the tail question — and a quantile
transform is the wrong one, since it would spread 2,08 million tied zeros
across the output range on tie-breaking alone.

**No sentinels.** Every detached maximum is held by exactly one row, so none of
the ranges above is set by a fill value.

**Superseded figures below, void per D-17.** Under plain min-max to
[0, π], the middle 98% of each predictor would occupy: `PRECTOTCORR` 7,4% /
3,2% of the range, `VIIWD` 3,8% / 6,8%, `VILWD` 6,9% / 4,3%, `TCIW` ~20%,
`TCLW` ~20%, `CAPE` 35,0% / 17,3%. Six of thirteen below 25% in tropis, seven
in subtropis.

Below that, the feature is nearly constant to the circuit — min-max is set by
the two extreme values, so one outlier takes most of the angle range.

**Options.** Log or Box-Cox on the worst offenders, then scale. A quantile
transform. Nothing, and accept the compression.

**Do first.** Re-run the measurement on all 20 predictors. `CRR` is a
precipitation rate like `PRECTOTCORR`, which was the worst.

---

## S-6 — Scaler and range — CLOSED 2026-09-14 by D-28

**From the literature.** Angle encoding needs features inside the rotation
range, and min-max to [0, π] is the standard recommendation. For this circuit
it is not a recommendation but a requirement: the feature map is
`RZ(2·x)`, which is periodic with period π in the data, so anything above π
wraps to a different value with no error raised.

Common practice is two stages — z-score on training statistics, then min-max to
the rotation range. **Scaler parameters come from the training set only.**

**The trap.** The cross-domain arms apply the source scaler to target rows,
deliberately, because refitting would leak. Any target value outside the
source's range therefore wraps. Measured on 13 predictors: `PS` puts 36,4% of
subtropis rows outside the tropis range and 25,9% the other way; `T2M` 2,6%;
`KX` 1,1%; `lat` and `lon` 100%. A poor cross-domain result could be this
rather than a physical finding.

**A fifth option, raised by Rafly 2026-09-14 and not yet argued.** Min-max has
two fitted parameters, both set by single extreme observations in one sample,
so it cannot be correct for a domain that has not been seen — a third domain
(Jawa Tengah was the example) has an unknown maximum, and the model finds out
by saturating.

The QML encoding literature treats this as two classes of variable. Bounded
variables are scaled by their **known physical bound** rather than the sample
extremes; unbounded variables are mapped through a bounded function first and
then scaled. In quantum reinforcement learning the split is explicit — CartPole
position and pole angle have finite ranges and are scaled by those, while cart
velocity and angular velocity have infinite ranges and are passed through
`arctan` onto a finite interval before scaling (Kölle et al., arXiv:2401.07043).
Lockwood & Si (arXiv:2008.07524) state the trade-off directly: scaled encoding
preserves magnitude but requires bounded inputs, so CartPole cannot use it.
`arctan` is not an improvisation but a named encoding variant — angle rotation
encoding maps x to `arctan(x)` or `arctan(x²)` before using it as the phase.

**Why it addresses O-3 where min-max cannot.** `arctan` has **no fitted
parameter**. An unseen `CAPE` of 30 000 still maps above 22 396, still
monotone, still distinguishable. Min-max with clipping makes them identical.
The scale inside it, `arctan(x/s)`, would be a stated physical constant, not
a sample statistic.

**Two costs.** `arctan` compresses the bulk unless `s` is chosen well, and `s`
is a judgement. And it does nothing about the point masses in S-5. Note also
that Yeo-Johnson fits λ from data, so Amri's route has the same generalisation
weakness as min-max — if cross-domain transfer is the point, parameter-free
transforms are the more defensible family, and that belongs in Bab IV.

Peer-review status of both preprints unverified.

**Options.** Clip to the source range. Widen the scaler deliberately. Physical
bounds for bounded variables plus a parameter-free bounded map for unbounded
ones. Declare it as a limitation. Some combination.

---

## S-7 — One model or two stages — CLOSED 2026-09-14 by D-25

**Measured.** Median run of consecutive zero-flash hours within a live cell:
15 hours tropis, 20 subtropis. p90: 50 and 164 hours. 40,6% and 66,6% of zero
rows sit inside runs longer than a week. That is switch-like behaviour.

Zeros are also structured in time, so they are partly predictable: tropis zero
share runs 83,52% at 16:00 local to 99,43% at 09:00.

**Options.** One model on `log1p(flash_count)`. Two stages, occurrence then
count, as v1's `experiments.py` had. 

**Note for Bab II.** No QML literature on zero-inflated targets was found. The
hurdle approach is classical. If that gap survives checking, it is worth
claiming.

---

## S-8 — The split

**Constraints already fixed.** §4: the test set is the held-out year, whole, at
its natural class ratio. Training rows may be subsampled. D-11: each domain
gets its own feature set, at equal width.

**To decide.** Which year is held out, and whether the same year in both
domains. Whether validation comes from a further split or from cross-validation
within the training years. What subsampling, if any, on the 94–97% zeros.

---

## S-9 — Screening and ablation — NARROWED 2026-09-14 by D-21

The method is mRMR: relevance by mutual information, redundancy by Spearman,
per domain, on training rows only. Leave-one-out moves from selecting to
confirming. What remains is N (S-10) and whether `PS` falls under step 3's
location-identifying rule.

The last step, and the one that writes `features.MODELLED`.

**No longer fixed by §5.** D-17 reset the method with the rest of the
component, and §5 was revised to match: the screen is unratified until it is
argued here and written into a `D-` entry.

**The method that was reset, and what supports it.** Screen on Spearman and
mutual information, not Pearson — Pearson finds only straight lines and would
discard a variable that matters above a threshold. Confirm with leave-one-out
ablation. This survived its literature check: pairing mutual information as
the primary criterion with a rank correlation as complement, justified by
variational circuits' sensitivity to input dimensionality and qubit scaling,
has 2026 precedent, and that same work reports the low-rank-correlation /
high-MI pattern seen here in `VIIWD`. It was reset for want of a written
justification, not for want of support.

**What the field usually does instead.** Reduce to the qubit budget with PCA.
The distinction that matters for Bab VI: feature selection preserves
interpretability while feature extraction destroys it, and PCA preserves
directions of maximum variance rather than maximum target relevance. Amri ran
PCA and therefore never asked which variable matters. **Do not borrow the
standard NISQ justification** — fewer qubits, less hardware noise. This project
runs on a simulator; the cost here is 2^n statevector growth and
parameter-shift circuit count. State the real reason.

**Supporting evidence already measured.** Amri reports no strong linear
correlation between any feature and the target, plus multicollinearity, from a
Pearson heatmap on monthly aggregates. That is the argument for rank and
information measures here — and a reminder that his figures are monthly and
yours are hourly, so they are not comparable quantities.

**Blocked by.** S-1 through S-6. Screening a feature set that is about to
change is wasted work.

---

## S-10 — How many feature sets, and how wide — CLOSED by D-22 and D-24

D-22's per-domain and equal-width decisions stand. **N is reopened.** It was
fixed at 10 on seed stability and simulation cost, before the width sweep
measured what that costs: tropis occurrence gains 26% relative going from 10
to 15, subtropis 18%. The decision is not wrong, but it was taken without
this figure and should be retaken with it.

Was D-11; parked by D-17 and returned here.

**The decision.** Whether each domain screens and ablates separately and keeps
its own `MODELLED` list, or both share one list. If separate, whether the two
lists must be the same length N, and what N is.

**Why width matters if the sets are separate.** One feature, one qubit. A
12-feature model and a 9-feature model are different-sized circuits, so a
tropis-subtropis performance gap would confound domain difficulty with model
capacity — and that gap is the number the thesis reports. Equal width removes
the confound; it does not remove the difficulty of choosing N.

**Confirmed with Rafly, 2026-09-14.** If the sets are per-domain, they are
equal width. The assertion enforcing this already exists in
`features.modelled()` and carries a comment saying it enforces a parked
decision.

**What D-11 rested on, now void.** A mutual-information ranking taken
2026-09-11 on the 17-candidate table, in which `KX` ranked 10th in tropis and
1st in subtropis, `T2M` 18th and 6th, `CAPE` 12th and 4th. Those columns are
not the current columns and the ranking must be retaken.

**Interacts with.** S-9 (the screen produces the rankings), and the `pooled`
scenario, which under D-11 took the union of the two lists truncated to N.

**Blocked by.** Stage 1, then S-9.

---

## S-11 — What the cross-domain arm reads — CLOSED 2026-09-14 by D-27

Opened by D-22. Two per-domain sets of equal width mean the transfer arms have
no defined input: a tropis-trained model reads qubit 2 as `cos_sza`, and a
subtropis feature vector has `KX` there. Feeding one into the other produces a
meaningless number, not a weak one.

**Measured.** The 2026-09-14 mRMR ordering shares ten of twelve between
domains. `KX` and `TCIW` are subtropis-only; `PS` and `cos_sza` tropis-only.

**Options.** The intersection, which on current evidence is close to ten and
would make transfer trivial but forces N to be an output rather than a choice.
A pooled set ranked on the combined training rows and used by every arm. Source
features throughout, with the target domain's values read into the source's
slots. Or train the transfer arms separately on a shared set, and report
per-domain arms on per-domain sets.

**Blocks.** Every cross-domain result. Does not block the within-domain arms,
which can proceed on D-22's sets.
