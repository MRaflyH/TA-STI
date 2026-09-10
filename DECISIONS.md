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

**Status.** `dataset/` is complete: `features.py`, `lightning.py`, `merlin.py`,
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

## Measured

Findings that correct something the archive asserts, or that the thesis will
need to quote. All `[measured]`, 2026-09-10.

- **The PLN export is entirely cloud-to-ground.** 2 242 100 CG strikes, 0
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
  against tropis's 2 242 100, yet 99 273 non-zero cell-hours against 104 955.
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

---

## Open

**O-1 — The calendar columns.** A proposal exists and is not yet written into
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

**The wrapping measurement makes this sharper.** Tropis latitude spans −7,75
to −5,75; subtropis 26,75 to 30,25. They do not overlap at all, so a
source-fitted min-max scaler maps **100% of the target domain's `lat` and `lon`
outside [0, π]** in both directions, where a rotation wraps rather than clips.
In the cross-domain arms those two features carry noise.

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

**O-4 — Tier 1 ERA5 additions.** Seven candidate variables are drafted and
their short names are in `era5.VARIABLE_SHORTNAME`, but `VARIABLES` still
requests six and `features.CANDIDATES` holds none of them. A one-month,
one-domain trial is written and waiting on the KX queue; it is also the first
request to mix analysis and forecast variables, and therefore the first to
exercise the ZIP branch. `mean_convective_precipitation_rate` is a mean rate
and would need a one-hour realignment; `convective_rain_rate` is the
instantaneous alternative and would not. Undecided.

**O-5 — `PRECTOTCORR` may have a unit or data problem. Unresolved.**
Maximum is 1076 (tropis) and 1194 (subtropis) against a column documented as
mm/hour. The world record for one-hour rainfall is roughly 305 mm, so these are
not possible as hourly rates. Either the unit annotation in `features.py` is
wrong — it was copied from the v1 archive and never verified against the NASA
POWER parameter definition — or the values are not what they appear. **Settle
this before the column appears in any chapter.** Check whether the extreme
values are a handful of rows or a smooth tail.

**O-6 — One model or two stages.** The dry-spell measurement supports v1's
`occurrence`/`count` split: median runs of 15–20 hours and two thirds of
subtropis zero rows inside week-long runs is switch-like behaviour rather than
a continuous process with many small values. No QML literature on zero-inflated
targets was found; the hurdle approach is classical. Undecided.

**O-7 — Skew must be fixed before min-max, for some predictors.** See the
squashing measurements. Under plain min-max the worst predictors are nearly
constant to the circuit. The likely order is: fix skew, z-score, then min-max
to [0, π]. Which transform, and which predictors need it, is undecided.