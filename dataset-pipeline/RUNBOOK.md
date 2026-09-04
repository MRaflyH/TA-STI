# Data acquisition runbook

Four sources, two of them files you already have, two of them things you fetch.
Only one needs an account.

| Source | How you get it | Account? | Native grid | Notes |
|---|---|---|---|---|
| PLN Puslitbang LDS | Given to you as `.xlsx` | no | point strikes | one sheet or file per year |
| NASA MERLIN | Manual export from the KSC web archive | no | point strikes | 30-day cap per export → many files |
| NASA POWER | HTTP API, synchronous | **no** | 0.5° × 0.625° | 1 parameter per regional request |
| ERA5 | Copernicus CDS API, queued | **yes** | 0.25° × 0.25° | licence accepted **per dataset**, in the browser |

Everything lands in `data/raw/<source>/`, and `python -m gfd_data.build` turns
it into `data/processed/gfd_<domain>_<resolution>.*`.

Both domains cover **2018–2024**. That is final.

---

## Resolution switch — read this before any step

`config.TIME_FREQ` controls the whole pipeline.

```python
TIME_FREQ = "h"   # clock hour     (current)
TIME_FREQ = "D"   # calendar day
TIME_FREQ = "M"   # calendar month (original; the predecessor-comparable one)
```

It changes which POWER endpoint is called, which ERA5 product is downloaded and
whether it is collapsed, how strikes are binned, and how the target is
normalised. Raw files are named by resolution and processed tables go to
`gfd_<domain>_<hourly|daily|monthly>.*`, so all three can live on disk at once.

**Keep the monthly build.** It is the only resolution comparable with the
predecessor study, which aggregated monthly. Any claim that this TA improves on
it has to be made at matched resolution.

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
- `MIN_COVERAGE` — `0.9` below monthly, was `0.0`. See "Decisions".

---

## Step 0 — environment

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt truststore
```

`xarray`, `netcdf4` and `cdsapi` are only needed for ERA5. Steps 1–3 work
without them. `pyarrow` is no longer optional — parquet is the primary output
below monthly resolution.

Every command below runs from `dataset-pipeline/src/`, with the venv active.

---

## Step 1 — PLN Puslitbang (tropical lightning)

Drop every workbook into `data/raw/pln/`:

```
data/raw/pln/
    Data_Petir_Jabar_20182024_Repaired.xlsx     # 2024 only as of writing
    Data_Petir_Jabar_2018.xlsx                  # ...add the rest as they arrive
    ...
```

The loader reads **every sheet of every workbook** and concatenates, so it does
not matter whether the years arrive as separate sheets in one file or as
separate files. It keeps rows whose `Discrimination` starts with `CG` and
derives polarity from the `+`/`-` suffix.

```bash
python -c "from gfd_data.lightning import load_pln; d=load_pln(); print(d.shape, d.timestamp.min(), d.timestamp.max())"
```

Run that after every new workbook arrives and check the max timestamp actually
moved. The filename says `20182024`; the contents are what the loader reports.

**One thing to confirm with PLN before you write this up.** The loader assumes
`Date and time` is local Jakarta time (`Domain.tz = "Asia/Jakarta"` in
`config.py`). If the LDS actually writes UTC, change that field to `"UTC"`.

At monthly resolution this shifts a handful of strikes across month boundaries —
small, but the kind of thing an examiner asks about. **At hourly resolution it is
no longer small.** A seven-hour error puts every strike in the wrong bin and
moves the entire diurnal cycle, which is one of the strongest signals in the
hourly target. `TZ_MODE` being forced to UTC does not rescue you here: it fixes
the *label*, and this is about whether the source timestamps were correctly
interpreted before labelling. Get a definite answer from PLN, not an assumption.

---

## Step 2 — NASA MERLIN (subtropical lightning)

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

The archive caps each export at **30 days**, so 2018–2024 is **89 exports**
(~4,3 million strikes, ~557 MB). This is done. Do not rename the files: the
archive's own filenames are your provenance record, and the loader does not care
what they are called. Never merge them by hand — concatenation in code is
reproducible and a manual merge is not.

Access requires a device-level VPN with a US exit; the archive is geo-restricted.

```bash
python3 -m gfd_data.merlin_download --self-test     # check the URL codec
python3 -m gfd_data.merlin_download ... --dry-run   # list windows, fetch nothing
```

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

Two constraints from the POWER docs are already handled in the code, but know
they exist because they explain the loop:

- a **regional** request may ask for only **one parameter**, so the code issues
  one request per parameter and joins afterwards;
- a regional request is capped at a **4.5° × 4.5° box (100 grid points)**. Both
  domains fit. If you ever widen West Java or Florida past that, the request has
  to be tiled.

At hourly with the default monthly chunking this is 5 parameters × 84 months +
1 monthly AOD request = **421 requests per domain**. They are synchronous,
small, and paced 2 s apart; budget an hour or two. Anything already on disk is
skipped, so an interrupted run resumes for free. If a year-sized request works
by hand, set `POWER_HOURLY_CHUNK = "Y"` and cut this to 36.

New in hourly mode: `time-standard=UTC` is sent explicitly, and `start`/`end`
are `YYYYMMDD` (the monthly endpoint takes bare `YYYY`).

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
   the hourly dataset. If you expect to run both resolutions, accept both now.

Verify:

```bash
python3 -c "import cdsapi; cdsapi.Client(); print('CDS client OK')"
python3 -m gfd_data.smoke_era5          # --clean removes the scratch folder
```

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
| `"M"`, year-chunked | 14 (7 per domain) | `fetch_year_monthly`; minutes each |
| `"h"`, month-chunked | **168** (84 per domain) | current default |
| `"h"`, `ERA5_HOURLY_CHUNK = "Y"` | 14 (7 per domain) | try one by hand first |

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

That is CDS fair-share scheduling demoting you for sustained recent usage, and it
had not levelled off. Extrapolated over 168 sequential requests it is a
**multi-day** run, not an overnight one. Two consequences:

1. Prefer `ERA5_HOURLY_CHUNK = "Y"` if a year-sized request is accepted. Twelve
   times the data per request, one twelfth the queue penalties. Verify by hand
   first: a year of hourly single-level data is 8 760 timesteps × 6 variables ≈
   53 000 fields, which should sit inside the CDS per-request field cap, but
   confirm rather than assume. Two years in one request will not.
2. Files cache by name and the domains are fetched in sequence, so killing the
   run costs you nothing already on disk. If you decide mid-run to switch to
   year chunking, do it at a domain boundary.

Transient `502 Bad Gateway` responses are normal; `cdsapi` retries them
automatically after 120 s and they do not need intervention.

**4d. The instantaneous-versus-interval caveat.** ERA5 hourly fields are
instantaneous values at the top of the hour; a target row counts every flash
*inside* the hour. This pipeline pairs the predictor at time T with strikes in
[T, T+1h) — the atmospheric state at the opening of the interval, predicting what
happens during it. That belongs in Bab III. Daily and monthly aggregation used
to hide the question; hourly does not.

One thing hourly makes *simpler*: there is no daily statistic to choose, so the
daily-max-CAPE-versus-mean argument disappears from the thesis entirely.

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

**Parquet is now the primary output.** The CSV mirror is skipped above 500 000
rows; pass `--force-csv` if you really want it.

**The time key column is `time`, not `month`** — `2024-07-15 14:00` at hourly.
Any notebook reading `df["month"]` needs updating. `year`, `month_of_year`,
`day_of_year`, `hour_of_day_utc` and `hour_of_day_local` are provided separately.
The remaining columns are `domain, lat, lon,` the six POWER features, the six
ERA5 features, then `flash_count, area_km2, period_days, gfd_per_km2_per_day,
gfd_per_km2_per_year`.

**`hour_of_day_local` is the feature that matters most here.** Bins are UTC, so
without it a model has to learn the offset separately per domain — exactly the
kind of domain-specific quirk the cross-domain experiment is trying not to
measure. Consider encoding it cyclically (sin/cos of 2πh/24) before modelling,
since hour 23 and hour 0 are adjacent and a raw integer says they are 23 apart.
That doubles a column against a scarce qubit budget, so decide it in the
modelling code and record the choice.

The join is a **left join onto the lightning grid**, so a cell-period the
meteorological sources do not cover appears as a NaN row rather than vanishing.

Read the build report every time, not just the file list:

- `zero-target share` — printed to two decimals, because it will be well above
  99% at hourly.
- the `!! at hourly resolution the target is a COUNT process` warning.
- `NO DATA for N months` / `dropping N months below 90% coverage` — periods
  excluded rather than filled with false zeros.
- `months covered` — day-coverage per month; low values mean detector gaps.
- `N native points -> M cells` — regridding; `0% still empty` is what you want.
- `!! N of M cells have ZERO flashes` — usually sea or beyond detector range.
- `missing-value share by feature` — read before modelling.

---

## Data on disk

```
dataset-pipeline/data/
├── raw/            source files, never edited
│   ├── pln/        PLN Puslitbang .xlsx (obtained via supervisors — not public)
│   ├── merlin/     KSC archive .csv exports
│   ├── power/      NASA POWER .json responses
│   └── era5/       Copernicus CDS .nc downloads
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
the pembimbing, not a silent config change. Set `TIME_FREQ` back to `"M"` to
reproduce the original behaviour exactly.

**Coverage is still judged monthly, and the guarantee is weaker than it was.**
The observation proxy — "a day with at least one strike somewhere in the domain
is a day the network was up" — is sound over a month and useless over anything
shorter, because at sub-monthly resolution the thing it cannot distinguish is
exactly the thing being predicted. A quiet 3 a.m. hour and an offline detector
look identical, and calling the quiet hour *unobserved* would delete nearly the
entire dataset. So the gate stays monthly: a month passes on its day-coverage,
and every hour inside it becomes a row. State the residual weakness in the
thesis: the gate can certify the network was up on 90% of a month's *days*, never
that it was up for all 24 hours of any one of them.

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
