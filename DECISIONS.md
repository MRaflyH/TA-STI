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

## S-2 — `lat`, `lon`, and the six dead cells

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

## S-3 — How to encode time

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

## S-4 — `CIN` and `CBH` missingness

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

## S-5 — Whether to transform skew before scaling

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

## S-6 — Scaler and range

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

## S-7 — One model or two stages

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

## S-9 — Screening and ablation

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

## S-10 — How many feature sets, and how wide

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
