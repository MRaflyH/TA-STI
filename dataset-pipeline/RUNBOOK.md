# Data acquisition runbook

Four sources, two of them files you already have, two of them things you fetch.
Only one needs an account.

| Source | How you get it | Account? | Native grid | Notes |
|---|---|---|---|---|
| PLN Puslitbang LDS | Given to you as `.xlsx` | no | point strikes | one sheet or file per year |
| NASA MERLIN | Manual export from the KSC web archive | no | point strikes | 30-day cap per export → many files |
| NASA POWER | HTTP API, synchronous | **no** | 0.5° × 0.625° | hourly is **point-only**; regional is daily/monthly and one parameter per request |
| ERA5 | Copernicus CDS API, queued | **yes** | 0.25° × 0.25° | licence accepted **per dataset**, in the browser |

Everything lands in `data/raw/<source>/`, and `python -m gfd_data.build` turns
it into `data/processed/gfd_<domain>_<resolution>.*`.

Both domains cover **2018–2024**, and both are now complete on disk:

| Domain | Source | Status |
|---|---|---|
| tropis | PLN Puslitbang LDS | **complete.** 2.242.100 CG strikes, 2018-01-01 .. 2024-12-31 |
| subtropis | NASA MERLIN | **complete.** 89 exports, ~4,3 juta strikes, ~557 MB |

The tropis figure is CG-only and post-filter — it is what `load_pln()` returns,
not the raw row count. Re-derive it rather than quoting it if a workbook is ever
added or replaced (step 1).

---

## Resolution — read this before any step

`config.TIME_FREQ` controls the whole pipeline, and it is **`"h"`**.

```python
TIME_FREQ = "h"   # clock hour — CURRENT AND INTENDED
TIME_FREQ = "D"   # calendar day
TIME_FREQ = "M"   # calendar month
```

Hourly is the project's decision, not a leftover. The `"D"` and `"M"` code paths
still work, but **nothing is currently built at either**, and neither should be
described as the project's resolution.

`"M"` exists for one purpose: the predecessor study aggregated monthly, so a
monthly build is the only artifact that could ever be set beside its numbers. If
that comparison is wanted, build it deliberately — do not assume it is there.

**Do not confuse `TIME_FREQ` with the `"M"` in `POWER_PARAM_FREQ`.** The latter
says NASA POWER publishes `AOD_55_ADJ` monthly and nothing finer. It is a fact
about the source, not a resolution setting, and it is the reason AOD is
broadcast rather than fetched hourly.

Changing `TIME_FREQ` changes which POWER endpoint is called, which ERA5 product
is downloaded and whether it is collapsed, how strikes are binned, and how the
target is normalised. Raw files are named by resolution and processed tables go
to `gfd_<domain>_<hourly|daily|monthly>.*`, so all three can coexist on disk.

The hourly and daily builds share their ERA5 downloads, so switching between
those two costs nothing once the fetch is done. Switching to or from monthly
means a fresh ERA5 download — different dataset, different licence.

Two settings only matter below monthly:

- `TZ_MODE` — **ignored and forced to `"utc"` at hourly**. At hourly the clock
  does not decide which storms land in which bin; it decides how the bin is
  *labelled*, and every source has to agree on the label or the join silently
  yields nothing. POWER's hourly endpoint offers local solar time, but LST is
  longitude-derived and is not Asia/Jakarta, so UTC is the only convention all
  four sources can honour. The diurnal cycle is carried by the
  `hour_of_day_local` column instead.
- `MIN_COVERAGE` — **`0.0`. The coverage gate is OFF.** See "Decisions".

---

## Step 0 — environment

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt truststore
```

`xarray`, `netcdf4` and `cdsapi` are only needed for ERA5. Steps 1–3 work
without them. **`pyarrow` is required, not optional** — parquet is the primary
output at hourly resolution and the CSV mirror is skipped above 500 000 rows.

Every command below runs from `dataset-pipeline/src/`, with the venv active.
Running them from the repo root gives `ModuleNotFoundError: No module named
'gfd_data'`.

---

## Step 1 — PLN Puslitbang (tropical lightning)

**Status: complete.** All workbooks are in `data/raw/pln/`.

The loader reads **every sheet of every workbook** and concatenates, so it does
not matter whether the years arrive as separate sheets in one file or as
separate files. It keeps rows whose `Discrimination` starts with `CG` and
derives polarity from the `+`/`-` suffix.

```bash
cd dataset-pipeline/src
python -c "from gfd_data.lightning import load_pln; d=load_pln(); print(d.shape, d.timestamp.min(), d.timestamp.max())"
```

Current output:

```
(2242100, 6) 2018-01-01 08:49:31.517000+00:00 2024-12-31 16:44:59.251000+00:00
```

Timestamps print in UTC because the loader localises the source clock and
converts. Re-run this after any change to `data/raw/pln/` and check the shape
and the span; the filename says `20182024`, the contents are what the loader
reports.

**The one thing still unconfirmed with PLN.** The loader assumes `Date and time`
is local Jakarta time (`Domain.tz = "Asia/Jakarta"` in `config.py`). Nothing in
the export states its clock. If the LDS actually writes UTC, change that field
to `"UTC"`.

At monthly resolution this shifted a handful of strikes across month boundaries.
**At hourly resolution it is not small.** A seven-hour error puts every tropis
strike in the wrong bin and moves the entire diurnal cycle, which is one of the
strongest signals in the hourly target. `TZ_MODE` being forced to UTC does not
rescue you: that fixes the *label*, and this is about whether the source
timestamps were correctly interpreted before labelling.

The check is physical, and it costs nothing:

```bash
python3 -m gfd_data.smoke_lightning --domain tropis
```

Convection over West Java peaks in the local mid-to-late afternoon, so the flash
count by local hour should show a clear afternoon maximum. Florida is the
control: same physics, and MERLIN really is UTC, so its local-hour peak should
land in the afternoon too. A tropis peak in the small hours means the timezone
is wrong. Run it before building anything hourly; get a definite answer from PLN
rather than trusting the smoke test alone.

---

## Step 2 — NASA MERLIN (subtropical lightning)

**Status: complete.** 89 CSV exports in `data/raw/merlin/`.

```bash
ls dataset-pipeline/data/raw/merlin/*.csv | wc -l    # 89
```

Export from <https://kscweather.ksc.nasa.gov/wxarchive/MerlinCloudToGround> and
drop every CSV into `data/raw/merlin/` unchanged. The loader globs the folder,
concatenates, and drops exact-duplicate strike records where two exports overlap
at a boundary.

```
data/raw/merlin/
    merlin-cloud-to-ground-export-20264427104454.csv
    merlin-cloud-to-ground-export-...csv
    ...
```

The archive caps each export at **30 days**, so 2018–2024 took **89 exports**
(~4,3 juta strikes, ~557 MB). Do not rename the files: the archive's own
filenames are your provenance record, and the loader does not care what they are
called. Never merge them by hand — concatenation in code is reproducible and a
manual merge is not.

Access requires a device-level VPN with a US exit; the archive is geo-restricted.

```bash
python3 -m gfd_data.merlin_download --self-test     # check the URL codec
python3 -m gfd_data.merlin_download ... --dry-run   # list windows, fetch nothing
```

`--dry-run` over 2018–2024 lists 86 windows at the default 30-day step, against
89 files on disk. The difference is manual re-pulls and boundary retries, not a
gap — the loader globs the folder and de-duplicates, so it does not matter. Do
not "fix" it by deleting files.

**Two schema facts that bite, and are not optional reading:**

- **`Date` is US `MM/DD/YYYY`**, and `Time` is a separate `HH:MM:SS.fffffff`
  string. Join them and parse with an explicit `format=`, then assert the result
  falls inside the window named in the file. A naive parse mislabels months
  across all 89 files and produces a seasonal signal that is pure artefact.
- **There is no CG/IC discrimination column and no multiplicity column.** PLN has
  both. Until the CG question is settled with the archive, every subtropis result
  is provisional and must say so. See §6.2 of the project instructions.

---

## Step 3 — NASA POWER (PS, PRECTOTCORR, T2M, RH2M, WS2M, AOD_55_ADJ)

No key, no queue, no registration.

**3a. Availability smoke test — mandatory, not optional.**

```bash
python3 -m gfd_data.smoke_power
```

Probes every parameter at the resolution `TIME_FREQ` asks for, using one short
window each, and prints OK or UNAVAILABLE. POWER does not publish everything
hourly; a parameter that fails should be demoted in `config.POWER_PARAM_FREQ` to
`"D"` or `"M"`, where it is fetched at its own resolution and broadcast across
the finer periods.

The raw payload is always written to disk before parsing, so a parse failure
never costs you a re-download.

`AOD_55_ADJ` is already set to `"M"` for exactly this reason. Understand what
that means at hourly resolution: it is **constant across ~730 consecutive
rows**. It cannot explain hour-to-hour variance in the target, and it will rank
near zero in any feature-importance analysis for that reason alone rather than
because aerosol loading is unimportant. Against a qubit budget this tight,
seriously consider dropping it — and either way, say which in Bab IV.

**3b. Fetch:**

```bash
python3 -m gfd_data.power
```

**The hourly endpoint is point-only.** `/api/temporal/hourly/regional` does not
exist and returns a bare 404. So the hourly fetch loops over NASA POWER's own
native grid points — MERRA-2 geometry, latitudes on multiples of 0.5 and
longitudes on multiples of 0.625 — and issues one request per point, carrying
every hourly parameter at once (the point endpoint takes up to 15). Requesting
POWER's points rather than the project's 0.5° cell centres is deliberate:
several project cells share one POWER longitude cell, and the docs warn that
repeatedly requesting the same underlying location can get you blocked.

The two domains hold **84 native POWER points**: 6 lat × 5 lon = 30 for tropis,
9 lat × 6 lon = 54 for subtropis. That count is the multiplier, not the number
of parameters.

| setting | hourly point requests | + AOD regional | total |
|---|---|---|---|
| `POWER_HOURLY_CHUNK = "ALL"` | 84 (one per point, whole span) | 2 | **86** |
| `POWER_HOURLY_CHUNK = "Y"` | 588 (one per point per year) | 2 | **590** ← current |

`"Y"` is set. It is slower, but a failure costs one year of one point rather
than seven, and the cache is finer grained so an interrupted run resumes closer
to where it stopped. Requests are synchronous, small, and paced 2 s apart;
budget several hours. Anything already on disk is skipped.

`AOD_55_ADJ` is the exception in every sense: monthly, and therefore fetched
through the **regional** endpoint, one request per domain for the whole span.
Two regional constraints apply to it and to nothing else in the current config:
one parameter per request, and a 4.5° × 4.5° box cap. Both domains fit; widening
West Java or Florida past that would need the request tiled.

Also hourly-specific: `time-standard=UTC` is sent explicitly, `start`/`end` are
`YYYYMMDD` (the monthly endpoint takes bare `YYYY`), and hourly `PRECTOTCORR` is
mm/hour where the monthly product is mm/day — **the units are not comparable
across resolutions.** Say so in Bab IV if an hourly and a monthly build are ever
put side by side.

---

## Step 4 — ERA5 (CAPE, KX, TCIW, TCLW, VIIWD, VILWD)

This is the only source with real setup friction. Do it in this order.

**4a. Account, token, licence.**

1. Register at <https://cds.climate.copernicus.eu/> and log in.
2. Open <https://cds.climate.copernicus.eu/how-to-api> and copy the two lines
   shown there into `~/.cdsapirc` (on Windows: `C:\Users\<you>\.cdsapirc`):

   ```
   url: https://cds.climate.copernicus.eu/api
   key: <YOUR-PERSONAL-ACCESS-TOKEN>
   ```

   The key is a **single token** now. Older tutorials show `url: .../api/v2` and
   `key: <UID>:<APIKEY>` — that is the retired format and it will fail.
3. **Accept the licence on the dataset you are actually going to use.** Licences
   are accepted per dataset, and sub-monthly mode uses a different dataset from
   monthly mode:

   | `TIME_FREQ` | dataset |
   |---|---|
   | `"h"`, `"D"` | ERA5 hourly data on single levels (`reanalysis-era5-single-levels`) |
   | `"M"` | ERA5 monthly averaged data on single levels (`reanalysis-era5-single-levels-monthly-means`) |

   Open its *Download* tab and accept. This is the step everyone skips; without
   it every request returns `403 … required licences not accepted`, regardless of
   how correct your token is. Accepting the monthly licence does **not** cover
   the hourly dataset. `"h"` is what this project runs, so that is the one that
   must be accepted; accept the monthly one too only if you intend to build the
   predecessor-comparable table.

Verify:

```bash
python3 -c "import cdsapi; cdsapi.Client(); print('CDS client OK')"
python3 -m gfd_data.smoke_era5          # --clean removes whatever the test wrote
```

By default `smoke_era5` writes into `data/raw/era5/` under the normal filename,
so the real fetch reuses it rather than re-requesting. `--scratch` isolates it in
`data/interim/` instead.

**4b. Confirm the two flux-divergence variable names before the first run.**

Four of the six names in `config.ERA5_VARIABLES` are stable and I am confident
in them: `convective_available_potential_energy`, `k_index`,
`total_column_cloud_ice_water`, `total_column_cloud_liquid_water`.

The other two — `vertical_integral_of_divergence_of_cloud_frozen_water_flux`
(VIIWD) and `vertical_integral_of_divergence_of_cloud_liquid_water_flux` (VILWD)
— are a best reconstruction, not something verified against the current CDS
catalogue. Confirm them the reliable way: on the dataset's *Download* tab, tick
the six variables you want, then press **"Show API request"**. The CDS prints the
exact Python dict, including the exact variable strings. Paste those into
`config.ERA5_VARIABLES` and you are guaranteed to match.

Do this on the **hourly** dataset page while `TIME_FREQ = "h"`. Variable naming
is not guaranteed identical across the two products.

Do the same check for `ERA5_SHORTNAME_MAP` after your first download — that maps
the *short* names inside the NetCDF (`cape`, `kx`, `tciw`, …) onto your column
names. `parse_era5_netcdf` prints any column it does not recognise, so one run
tells you if a key is off.

**4c. Fetch:**

```bash
python3 -m gfd_data.era5
```

`download_format: "unarchived"` is set deliberately — without it the CDS hands
back a `.zip` and the NetCDF reader fails on what looks like a corrupt file.

Request count depends on resolution and chunking:

| mode | requests | notes |
|---|---|---|
| `"h"`, month-chunked | **168** (84 per domain) | current default, and the only tested hourly path |
| `"h"`, `ERA5_HOURLY_CHUNK = "Y"` | 14 (7 per domain) | **rejected — exceeds the CDS cost limit** |
| `"M"`, year-chunked | 14 (7 per domain) | `fetch_year_monthly`; only if you build the monthly table |

`"Y"` was tested by hand (`era5.fetch_chunk_hourly(cfg.TROPIS, 2018)`) and
refused: a year is ~53.000 fields and the CDS gives very large requests very low
priority or declines them outright. This is a settled negative result. Leave
`ERA5_HOURLY_CHUNK = "M"`.

A **quarterly** chunk is the untested middle ground — ~13.000 fields against a
month's ~4.500 — and would cut 168 requests to 56. The cost threshold is
somewhere between those two numbers and only the ends have been probed. Adding
it means a `"Q"` branch in `fetch_chunk_hourly` *and* a matching glob in
`_files`; the filename pattern has to stay consistent or `load_era5` picks up
the wrong set.

**Budget this honestly — the cost is queue time, not bandwidth.** Each hourly
month is only ~1,3 MB over a box this small, and the CDS takes a consistent
~6 minutes to actually produce it. What grows is the wait between `accepted` and
`running`. Measured over one continuous 168-request run:

| request # (approx) | queue wait | wall time per month |
|---|---|---|
| 1–50 | 15–40 s | 6–10 min |
| 55 | 8 min | 12 min |
| 56 | 22 min | 29 min |
| 57 | 33 min | 39 min |
| 58 | 41 min | 47 min |
| 59 | 53 min | 59 min |

**Two explanations fit that, and they are not equivalent.** The CDS schedules on
the user profile, the request type and the expected request cost, and caps
simultaneous requests per user — so this could be fair-share demotion for
sustained usage. But the degradation began at 13:20 WIB, which is 06:20 UTC, and
that is when European working hours start. General CDS load fits the data at
least as well as a personal penalty, and it predicts the queue recovers on its
own after about 18:00 UTC each day. **Neither has been established; do not assert
either one in the thesis.**

Under the load model the useful window is roughly **01:00–13:00 WIB**: ~100
requests in the fast half of the day against ~12 in the slow half, so 168
requests is about a day and a half rather than four days. Check the queue waits
at 02:00 WIB before assuming the worst.

Three practical notes:

1. **Restarting the client does nothing.** The scheduling is server-side and
   per-account; killing the process and resuming puts the next request in the
   same queue position. Files cache by name, so an interrupt costs nothing
   already on disk, but it buys nothing either.
2. **Check your account's concurrent-request limit** on the CDS profile page. The
   cap is per user, not per process, but it is not necessarily 1 — if it allows
   two or three, running the two domains in separate processes overlaps the
   queue waits instead of serialising them.
3. Transient `502 Bad Gateway` responses are normal and `cdsapi` retries them
   automatically after 120 s. They are not the problem.

**4d. The instantaneous-versus-interval caveat.** ERA5 hourly fields are
instantaneous values at the top of the hour; a target row counts every flash
*inside* the hour. This pipeline pairs the predictor at time T with strikes in
[T, T+1h) — the atmospheric state at the opening of the interval, predicting what
happens during it. That belongs in Bab III. Daily and monthly aggregation used
to hide the question; hourly does not.

One thing hourly makes *simpler*: there is no daily statistic to choose, so the
daily-max-CAPE-versus-mean argument (`ERA5_DAILY_STATS`, live only at
`TIME_FREQ = "D"`) does not belong in this thesis at all.

---

## Step 5 — build the modelling tables

```bash
python3 -m gfd_data.build
```

Produces, per domain:

```
data/processed/gfd_tropis_hourly.parquet
data/processed/gfd_tropis_hourly.meta.json      # config snapshot, for F-05 replay
data/processed/gfd_subtropis_hourly.parquet
data/processed/gfd_subtropis_hourly.meta.json
```

Use `--no-power --no-era5` to build the lightning half alone while you are still
waiting on downloads.

**Parquet is the primary output.** The CSV mirror is skipped above 500 000 rows;
pass `--force-csv` if you really want it.

**The time key column is `time`, not `month`** — `2024-07-15 14:00` at hourly.
Any notebook reading `df["month"]` needs updating.

Full column list, in order:

```
domain, time,
year, month_of_year, day_of_year, hour_of_day_utc, hour_of_day_local,
lat, lon,
PS, PRECTOTCORR, T2M, RH2M, WS2M, AOD_55_ADJ,        # NASA POWER
CAPE, KX, TCIW, TCLW, VIIWD, VILWD,                  # ERA5
flash_count, area_km2, days_in_month, observed_days, coverage, period_days,
gfd_per_km2_per_day, gfd_per_km2_per_year
```

Note what that means downstream: **`year` and `days_in_month` are numeric
columns that are not predictors.** Anything selecting features as "every numeric
column that is not the target" will pick both up. `days_in_month` is pure
bookkeeping. `year` is worse than useless under a chronological train/test
split, because every test row carries a `year` value the model never saw in
training. Exclude both explicitly in the modelling config.

**`hour_of_day_local` is the feature that matters most here.** Bins are UTC, so
without it a model has to learn the offset separately per domain — exactly the
kind of domain-specific quirk the cross-domain experiment is trying not to
measure. Consider encoding it cyclically (sin/cos of 2πh/24) before modelling,
since hour 23 and hour 0 are adjacent and a raw integer says they are 23 apart.
That doubles a column against a scarce qubit budget, so decide it in the
modelling code and record the choice.

The join is a **left join onto the lightning grid**, so a cell-period the
meteorological sources do not cover appears as a NaN row rather than vanishing.

**Before the full build, run the one-month end-to-end test:**

```bash
python3 -m gfd_data.smoke_build                  # tropis, most recent January
python3 -m gfd_data.smoke_build --no-fetch       # use only what is on disk
```

It exists to catch the failure a left join will not raise on: zero key overlap
between the lightning skeleton and a predictor frame, which returns a full table
with every predictor column NaN and looks like a successful build. Three causes,
all invisible in the per-source smoke tests — a dtype mismatch on the time key,
a clock-convention offset, and ERA5 longitudes on 0..360 against lightning
longitudes on -180..180 (which fails silently for Florida only, since West Java
is positive either way).

With `--fetch` it pulls one month for one domain: 30 POWER point requests for
tropis (54 for subtropis), 1 regional AOD request, and 1 ERA5 request — so
roughly 32, not the ~590 a full POWER fetch costs.

Read the build report every time, not just the file list:

- `zero-target share` — printed to two decimals, because it will be well above
  99% at hourly.
- the `!! at hourly resolution the target is a COUNT process` warning.
- `NO DATA for N months` — months with no records at all, excluded rather than
  zero-filled. **There is no "dropping N months below coverage" line**, because
  `MIN_COVERAGE = 0.0` switches that filter off entirely. See "Decisions".
- `months covered` — day-coverage per month; low values mean detector gaps, and
  with the gate off they are kept.
- `N native points -> M cells` — regridding; `0% still empty` is what you want.
- `!! N of M cells have ZERO flashes` — usually sea or beyond detector range.
- `missing-value share by feature` — read before modelling.

---

## Data on disk

```
dataset-pipeline/data/
├── raw/            source files, never edited
│   ├── pln/        PLN Puslitbang .xlsx (obtained via supervisors — not public)
│   ├── merlin/     KSC archive .csv exports (89 files)
│   ├── power/      NASA POWER .json responses
│   └── era5/       Copernicus CDS .nc downloads
├── interim/        smoke-test scratch (--scratch)
└── processed/      gfd_<domain>_<resolution>.parquet + .meta.json
```

Nothing under `data/` is committed. The PLN records were obtained through the
supervisors and are not to be redistributed. Downloads cache by filename, so
re-running skips whatever already succeeded.

---

## Decisions this pipeline makes for you, and why

**Hourly, not monthly.** Every row is one cell-hour. This *departs from the
proposal*, which committed to temporal aggregation as the mitigation for
satellite sparsity — so it needs a sentence in Bab III and a conversation with
the pembimbing, not a silent config change. `TIME_FREQ = "M"` reproduces the
original behaviour exactly if the predecessor comparison is ever wanted.

**The coverage gate is OFF, and this is the pipeline's largest open exposure.**
`MIN_COVERAGE = 0.0`, so `aggregate_gfd` skips the filter and every month
holding at least one strike record contributes rows, however thin.

The underlying observation proxy — "a day with at least one strike somewhere in
the domain is a day the network was up" — is sound over a month and useless over
anything shorter, because at sub-monthly resolution the thing it cannot
distinguish is exactly the thing being predicted. A quiet 3 a.m. hour and an
offline detector look identical, and calling the quiet hour *unobserved* would
delete nearly the entire dataset. So the gate could only ever have been monthly:
a month passes on its day-coverage, and every hour inside it becomes a row.

With the gate at 0.0 it does not even do that. A month observed on 6 of 31 days
still emits 744 hourly rows, and the ~600 hours inside the 25 unobserved days
become rows asserting "no lightning here" — absences of observation wearing a
zero, against a target that is already >99% zeros.

Two things follow, and neither is optional:

1. `coverage` and `observed_days` are on **every row** of the processed table.
   Filter or weight on `coverage` at modelling time and record the threshold in
   the experiment config (F-05).
2. Report the distribution of `coverage` over the rows actually trained on, in
   Bab IV, beside the zero share.

Raising the gate to 0.9 would move the error rather than remove it: a 90% gate
preferentially deletes quiet months, and quiet months are the low-target
examples the model most needs. There is no setting that avoids both. Run
`python3 -m gfd_data.smoke_lightning` to see the per-month coverage table and
which trade you would actually be making.

**Empty cells are kept as zeros.** `aggregate_gfd(fill_empty_cells=True)` inserts
explicit `flash_count = 0` rows. Dropping them would quietly train the model on
"periods that had lightning", which raises the mean of the target and makes R²
look better than it is.

**The target is now a count process wearing a density's units.** At 0,5° cells,
the overwhelming majority of cell-hours contain no lightning at all, and the
non-zero ones hold small integers. Three consequences:

1. `gfd_per_km2_per_year` annualises a single hour, so one flash becomes ~8 766×
   its per-hour rate. The column is kept so the three resolutions share a unit
   for reporting, but **`flash_count` is the honest hourly target** — or a log /
   Anscombe transform of it. The build prints this warning at run time.
2. R² is close to meaningless on this target. Predicting zero everywhere scores
   well. Report the zero share beside every R², and beat a trivial baseline —
   the cell's climatological hourly rate — before claiming the model learned
   anything.
3. NF-01 (R² > 0,9) was already in tension with the only comparable published
   result at *monthly* resolution. Hourly puts it further out of reach, and not
   because of the model. This is now a target-renegotiation conversation with the
   pembimbing, not a modelling problem.

**Hourly GFD is arguably a different problem statement.** *Ground flash density*
conventionally means flashes per km² per year; an hourly cell-count is lightning
*occurrence*, a well-studied task with its own conventional metrics (POD, FAR,
CSI, Brier score) designed for exactly this kind of rare-event target. If the
hourly build is what the TA reports, the title and Bab I scope need to say so,
and the evaluation section should probably carry occurrence metrics alongside
RMSE and R².

**Sample size grows, but not in the way that helps.** Millions of rows against
`AerSimulator` means subsampling, and a subsample of a 99%-zero target is mostly
zeros — you end up with a few thousand training rows again, drawn from a noisier
distribution. Design the sampling deliberately (stratify on non-zero rows) and
record it in the experiment config.

**GFD normalisation.** `gfd_per_km2_per_year = flash_count / area_km2 /
period_days × 365,25`, where `period_days` is 1/24 for an hour, 1 for a day, and
the number of *observed* days for a month. Cell area comes from the cosine of
latitude, so a Florida cell is correctly smaller than a West Java one.

Note that the predecessor paper reports its target as km⁻¹day⁻¹, which is not a
density unit — a flash density is per area per time. Use the conventional unit
and define it explicitly in Bab III; `gfd_per_km2_per_day` is also in the output
if you want to compare numbers directly against theirs. Any such comparison must
be run at `TIME_FREQ = "M"`.

**Ocean cells are included.** The Florida bounding box covers a lot of Atlantic
and Gulf. MERLIN detects over water, but detection efficiency and the physics
both differ offshore — and at cell-hour granularity that difference dominates,
because the unit is small enough that a single missed flash flips a row from
non-zero to zero. This is exactly the kind of thing that shows up as an
unexplained cross-domain generalization gap. Decide deliberately whether to apply
a land mask, and record the decision.

---

## Still unverified — carry these into the thesis, not into a footnote

1. **The PLN source clock.** `Domain.tz = "Asia/Jakarta"` is an assumption. See
   step 1. This is the single most consequential unverified item in the build.
2. **CG/IC in MERLIN.** No discrimination column. If the KSC export includes
   intracloud strokes, the subtropis target is not ground flash density.
3. **Flash versus stroke.** PLN groups strokes into flashes via `Multi.`; MERLIN
   does not. Comparing raw MERLIN rows against flash-grouped PLN rows compares
   stroke density to flash density. Harmonise on one side or the other and record
   which.
4. **The two ERA5 flux-divergence variable names.** Step 4b.
5. **Detection efficiency.** MERLIN is ~10 sensors around the Cape, not a
   Florida-wide network. An uncorrected GFD field will show a spurious radial
   gradient centred on KSC. The two domains come from different networks, so a
   cross-domain generalization gap may be measuring instrument rather than
   climate — the biggest threat to the validity of the core experiment.
6. **The CDS queue explanation.** Fair-share demotion or European daytime load.
   Both fit; neither is established.
