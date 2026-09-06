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
| subtropis | NASA MERLIN | **complete.** 89 exports, 5.301.491 strikes, 2018-01-03 .. 2024-12-31, 583 MB |

The tropis figure is CG-only and post-filter — it is what `load_pln()` returns,
not the raw row count. Re-derive it rather than quoting it if a workbook is ever
added or replaced (step 1).

The subtropis figure is post-deduplication: three exact-duplicate strike records
across overlapping export boundaries are dropped on load. Note the span begins
2018-01-03, not 2018-01-01 — the first export window starts there. **Five of the
89 exports returned nothing usable and three months are consequently missing
entirely; see step 2.**

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

**One environment for the whole project, at the repo root.** The pipeline and
the modelling code used to have separate `requirements.txt` files; installing
Qiskit could otherwise disturb a download mid-flight. All four acquisitions are
complete, so that reason has expired, and the asymmetry it left behind — the
modelling side pinned exactly with a lock, this side on open ranges with none —
was an NF-02 gap in its own right.

```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Verified on Python 3.13.7; 3.10 is the floor, because `qiskit-machine-learning`
0.9 dropped 3.9. Everything is pinned exactly, and `environment-lock.txt` at the
root records the full resolved set — regenerate it with `pip freeze` after any
change.

`truststore` is now in `requirements.txt` rather than appended to the install
command. It lets `requests` use the macOS keychain; without it
`merlin_download` raises `CERTIFICATE_VERIFY_FAILED` where `curl` succeeds.

`xarray`, `netCDF4` and `cdsapi` are only *used* by ERA5 — steps 1–3 do not need
them — but they are installed regardless now that there is one environment.
**`pyarrow` is required, not optional** — parquet is the primary output at
hourly resolution and the CSV mirror is skipped above 500 000 rows.

Every command below runs from `code/pipeline/src/`, with the venv active.
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
cd code/pipeline/src
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

**The PLN clock — checked, and the assumption holds.** The loader treats `Date
and time` as local Jakarta time (`Domain.tz = "Asia/Jakarta"` in `config.py`).
Nothing in the export states its clock, so this was an assumption. It has now
been tested physically.

At monthly resolution a seven-hour error shifted a handful of strikes across
month boundaries. **At hourly resolution it would not be small.** It puts every
tropis strike in the wrong bin and moves the entire diurnal cycle, which is one
of the strongest signals in the hourly target. `TZ_MODE` being forced to UTC does
not rescue you: that fixes the *label*, and this is about whether the source
timestamps were correctly interpreted before labelling.

The check is physical, and it costs nothing:

```bash
python3 -m gfd_data.smoke_lightning --domain tropis
```

Run 2026-09-06, over all 2.242.100 strikes:

```
  16:00 local    431,544  ########################################  <-- peak
  17:00 local    379,375  ###################################
  15:00 local    356,536  #################################
  04:00 local     13,753  #
  peak local hour : 16:00 (Asia/Jakarta)
```

A clean afternoon convective maximum. The argument is tighter than "that looks
plausible": the loader localises the raw field as Jakarta and the smoke test
converts back, so the histogram above is the raw field's own hour. If the export
were actually UTC, true West Java local time would be raw + 7 and the peak would
fall at 23:00 — a midnight maximum for tropical convection, which is not
physical. The field is local.

Florida is the control and behaves the same way: MERLIN really is UTC, and its
local-hour peak lands at 15:00.

Still worth written confirmation from PLN through the pembimbing, but this is a
validation result now rather than a blocker, and it belongs in Bab III as one.
`config.py` still opens its `TROPIS` definition with "THE OPEN QUESTION IN THIS
FILE" and carries `tz="Asia/Jakarta",   # VERIFY with PLN Puslitbang` — keep the
reasoning, change the verdict.

---

## Step 2 — NASA MERLIN (subtropical lightning)

**Status: complete.** 89 CSV exports in `data/raw/merlin/`.

```bash
ls code/pipeline/data/raw/merlin/*.csv | wc -l    # 89
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
(5.301.491 strikes after de-duplication, 583 MB). Do not rename the files: the
archive's own filenames are your provenance record, and the loader does not care
what they are
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

### Empty and truncated exports — five files, three lost months

Five of the 89 exports returned nothing usable. Four are well-formed CSVs with a
header and zero data rows; one returned a single row for a 29-day window.

| File | Window | Rows |
|---|---|---|
| `merlin_20210306_20210403.csv` | 6 Mar – 3 Apr 2021 | 0 |
| `merlin_20221204_20230101.csv` | 4 Dec 2022 – 1 Jan 2023 | 1 |
| `merlin_20230102_20230130.csv` | 2 – 30 Jan 2023 | 0 |
| `merlin_20231019_20231116.csv` | 19 Oct – 16 Nov 2023 | 0 |
| `merlin_20240212_20240311.csv` | 12 Feb – 11 Mar 2024 | 0 |

**These are not transport failures.** `fetch_window` validates the response with
`looks_like_csv()` and writes a non-CSV body to `FAILED_<dates>.html` without
saving a CSV at all, so a VPN drop or a geo-block could not have produced them.
The archive answered, correctly formed, with nothing in it.

Three months consequently hold no strike record at all and are absent from the
processed table: **2021-03, 2022-12, 2024-02**. Every day of 2018–2024 was
requested by some export, so this is not a gap in what was asked for.

**2021-03 is a proven instrument gap.** METAR observations from stations around
the Cape, fetched from the Iowa Environmental Mesonet ASOS archive, show
thunderstorms during a month MERLIN recorded as empty:

```
2021-03-31 20:54Z  KCOF ... +TSRA BKN021 24/20 ... TSB54
2021-03-06 15:53Z  KDAB ... -TSRA ... OCNL LTGICCG OHD-NW-N TS OHD-NW-N MOV E
2021-03-06 15:57Z  KDAB ... +TSRA ... OCNL LTGICCG OHD-NW-N
```

`+TSRA` at KCOF is a heavy thunderstorm **at Patrick SFB**, one of the three
sites where the MERLIN sensors are installed. `LTGICCG OHD` at Daytona is
in-cloud *and cloud-to-ground* lightning directly overhead at 29,2°N −81,1°W,
inside the domain box. MERLIN returned zero CG strikes for the whole month.

2022-12 and 2024-02 have not been checked the same way. Do that before treating
either as a genuine zero:

```bash
python metar_check.py --month 2022-12 --raw     # see merlin-crosscheck/
```

The bar is `TSRA` or `LTGICCG OHD` at a station inside the box. `LTG DSNT SW` or
a bare `VCTS` proves nothing — lightning visible on the horizon may have been
outside the box or beyond useful sensor range.

**Current handling: all three months are excluded, not filled.** That is
`aggregate_gfd`'s default and no code was changed for it. Filling them would
assert ~40.000 cell-hour rows of confident zero per month, which for 2021-03 is
now known to be false. Revisit if the other two are checked and come back clean.

**Nothing was deleted.** The five files remain in `data/raw/merlin/`. Re-pulling
them is untried; `fetch_window` skips a window whose file already exists unless
`--overwrite` is passed, so a naive re-run prints `cached` and fetches nothing.

The wider question — whether MERLIN downtime is confined to these five windows
or runs through the whole record — is open. See "Still unverified" item 7.

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

**On disk: 591 files, 482 MB.** 378 subtropis point files (54 points × 7 years,
exact) and 211 tropis (30 × 7 = 210, plus one), plus the 2 regional AOD files.
The extra is point `m006p500_p106p250`, which has 8 files where every other point
has 7 — a duplicated year window from a re-pull. The loader globs and the build
reported 100% key overlap, so it is harmless, but it has not been examined.

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

**4e. KX is absent from the subtropis build — unexplained.**

On disk: **168 files, 258 MB**, exactly as budgeted. But the build reports
`!! absent features: ['KX']` for subtropis. Tropis carries all 14 predictors;
subtropis carries 13. The column is not null — it never arrives.

The cause has not been diagnosed. Three possibilities, in decreasing order of
cost: the subtropis download requested a different variable list (84 CDS requests
to fix), a subset of files failed (fewer), or the variable carries a different
short name in the subtropis files and `ERA5_SHORTNAME_MAP` misses it — a code fix
with no download at all. That last one is plausible enough to check first:

```bash
python3 -c "
import xarray as xr
from gfd_data import config as cfg
for dom in ['tropis','subtropis']:
    files = sorted(cfg.RAW_ERA5_DIR.glob(f'*{dom}*.nc'))
    seen = {}
    for f in files:
        with xr.open_dataset(f) as ds:
            for v in ds.data_vars: seen[v] = seen.get(v, 0) + 1
    print(dom, len(files), sorted(seen.items()))
"
```

**Why it matters beyond one column.** `run_cross` fits on one domain and applies
that model to the other, so a 14-feature source against a 13-feature target
either raises a shape error or gets silently intersected by the shared
preprocessing chain — dropping KX from both domains without recording it. K index
is also one of the fourteen predictors the predecessor used, so losing it means
the feature set no longer matches theirs. If KX is dropped, drop it from **both**
domains explicitly in `config.py` and say so in Bab IV.

Deferred, not resolved. The modelling package is being rewritten, so this can be
settled against the new feature-selection code.

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

- `zero-target share` — printed to two decimals. **Measured: 94,30% tropis,
  97,00% subtropis.** Earlier drafts of this file, of `README.md` and of
  `config.py` estimated ">99%"; that was too high, and should be corrected
  wherever it still appears. The conclusion does not change — predicting zero
  everywhere still explains most of the variance — but the project has ~105.000
  non-zero tropis cell-hours and ~99.000 subtropis, which is more usable signal
  than ">99% zeros" implies.
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
code/pipeline/data/
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
zero, against a target that is 94,30% zeros in tropis and 97,00% in subtropis.

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

**The built tables make that trade concrete, and it is worse than it sounds.** A
0,9 gate would delete **56 of 81 subtropis months and 26 of 84 tropis** — about
70% of Florida. Worse, it deletes *opposite halves of the year* in the two
domains: tropis thins in the JJAS dry season, subtropis in DJF winter. The two
training sets would no longer span comparable seasonal ranges, and any
cross-domain generalization gap measured afterwards would be partly an artefact
of the filter. **The gate stays at 0.0. It is the wrong lever** — `coverage`
conflates a quiet sky with a dead detector, and at 0,9 the quiet skies vastly
outnumber the dead detectors, so the filter discards hundreds of real
observations to remove a handful of false ones.

The right instrument is a real observation record rather than a threshold on a
proxy. Specific periods known to be instrument gaps should be excluded by date
(step 2 does this for three MERLIN months); see "Still unverified" item 7 for the
general version, which is not built.

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
`AerSimulator` means subsampling, and a uniform subsample of a 94–97%-zero target
is almost all zeros — you end up with a few thousand training rows again, drawn
from a noisier distribution. Design the sampling deliberately (stratify on
non-zero rows) and record it in the experiment config.

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

## Build of 2026-09-06 — the first real tables

`python3 -m gfd_data.build`, hourly, both domains, nothing fetched.

| | tropis | subtropis |
|---|---|---|
| strikes | 2.242.100 | 5.301.491 |
| cell-hours | 1.841.040 | 3.314.304 |
| with ≥1 flash | 104.955 | 99.273 |
| zero-target share | 94,30% | 97,00% |
| months covered | 84 of 84 | 81 of 84 |
| mean day-coverage | 86% (min 13%) | 59% (min 3%) |
| cells | 30 | 56 |
| features | 14 | 13 (no KX) |
| non-zero range | 1 .. 2.391 | 1 .. 11.777 |

Both written to `data/processed/` as parquet plus `.meta.json`. CSV skipped —
both exceed the 500 000-row limit.

**Schema verified on read-back.** `time` round-trips as `period[h]`, and the
duplicate `lat`/`lon` columns visible in the smoke-test merge output do not
survive into the parquet. 29 columns tropis, 28 subtropis; otherwise identical.

### Three findings from the built tables

**1. The two domains are not observed to a comparable standard.** Tropis mean
day-coverage is 86%; subtropis is 59%. Given the export gaps in step 2, an
unknown share of that difference is instrument downtime rather than quiet sky.
The cross-domain gap is the TA's core result, so this belongs in Bab IV with both
numbers in it, not in a footnote.

**2. Six tropis cells hold zero flashes across all seven years** — 20% of the
grid:

```
-7,75 106,25   -7,75 106,75                        Indian Ocean, southern edge
-5,75 106,25   -5,75 107,75   108,25   108,75      northern edge, Java Sea
```

The southern pair is sea. The northern four are not — that is the coast around
Jakarta and Cirebon, which is not lightning-free, and the fifth cell in that row
(107,25) does carry flashes. The likelier reading is that the snapped bounding
box reaches past the LDS network's useful range, giving tropis an artificial zero
rim. Under `SPLIT_STRATEGY = "cell"` these six could land entirely in test, where
a model would score perfectly on them for the wrong reason. Dropping
all-zero cells is a defensible preprocessing step; record it if taken.

**3. Subtropis flash counts fall off with distance from the Cape, Spearman
−0,955.** No subtropis cell is empty, but the range is four orders of magnitude:

```
28,75 −80,75     31 km    444.193 flashes
26,75 −78,75    267 km          87 flashes
```

**State this carefully.** Florida's peninsula is genuinely the most
lightning-prone part of the United States and the Cape sits near its middle, so
distance-from-sensors and distance-from-sea-breeze-convergence are nearly
collinear inside this box — a perfect detector would show a gradient here too. At
matched distances the inland cells carry roughly 3× the ocean cells, which is
real physics. The defensible claim is that instrument response and climatology
are **confounded** here and cannot be separated using MERLIN alone, not that the
gradient is an artefact.

A land mask would not fix it: 30,25/−81,25 is over land and still carries only
6.968 flashes against 437.287 at 28,75/−81,25.

Separating the two effects needs an instrument with uniform detection efficiency
across the box. GOES-16 GLM is one, and the MERLIN/GLM ratio against distance
would give the detection-efficiency curve directly. Expensive — GLM L2 LCFA
granules are 20 seconds each, 5–9 GB per day — so this is a possibility, not a
plan.

### Cross-check tooling

`merlin-crosscheck/` lives outside this repo and imports nothing from
`gfd_data`. `metar_check.py` runs the METAR test (cheap, a few hundred KB per
month, no VPN); `glm_check.py` runs the GLM one, scoped to specific days.

---

## Still unverified — carry these into the thesis, not into a footnote

1. **The PLN source clock — resolved, pending written confirmation.** The diurnal
   check gives a 16:00 local peak with Florida as a matching control, and the UTC
   alternative would imply a physically impossible midnight maximum (step 1). The
   Jakarta assumption holds. Confirmation from PLN through the pembimbing is
   still worth having, but this is no longer a risk to the build.
2. **CG/IC in MERLIN.** No discrimination column. If the KSC export includes
   intracloud strokes, the subtropis target is not ground flash density.

   One piece of evidence now points the right way: MERLIN is **5,7% positive**
   against PLN's **14,1%**, on a signed peak-current comparison over the full
   record. IC contamination raises the positive fraction, and MERLIN sits well
   below the CG-only reference. Low-amplitude positive fractions are also close
   (3,1% against 2,6%). Suggestive that the export is CG-only, but not
   conclusive — confirm against the archive documentation before Bab III.
3. **Flash versus stroke.** PLN groups strokes into flashes via `Multi.`; MERLIN
   does not. Comparing raw MERLIN rows against flash-grouped PLN rows compares
   stroke density to flash density. Harmonise on one side or the other and record
   which.
4. **The two ERA5 flux-divergence variable names.** Step 4b.
5. **Detection efficiency — now measured, and confounded.** Subtropis flash
   counts correlate with distance from the Cape at Spearman −0,955, from 444.193
   flashes at 31 km down to 87 at 267 km. Tropis shows the same effect in a
   different form: six edge cells with zero flashes in seven years. Both are
   consistent with range-limited networks, but on the subtropis side the gradient
   is confounded with real Florida climatology and cannot be separated using
   MERLIN alone. The two domains come from different networks, so a cross-domain
   generalization gap may be measuring instrument rather than climate — still the
   biggest threat to the validity of the core experiment.
6. **The CDS queue explanation.** Fair-share demotion or European daytime load.
   Both fit; neither is established.
7. **MERLIN uptime across the whole record.** Five exports returned nothing or
   almost nothing, and METAR proves MERLIN missed a thunderstorm sitting on one
   of its own sensor sites in March 2021 (step 2). The three fully-empty months
   are only the cases where MERLIN logged *literally nothing* — a month where it
   was down for three weeks but caught one storm on day 29 appears in the
   coverage table at 1/31 and looks merely quiet. Subtropis has 56 of 81 months
   below 90% day-coverage. The strike-day proxy cannot distinguish downtime from
   quiet sky, so `coverage` may be systematically overstating uptime for
   subtropis across 2018–2024.

   A real observation record is buildable: a day when a station inside the box
   reports `TSRA` and MERLIN has zero strikes is a day MERLIN was not working. If
   it is built it must be built for **both** domains — West Java has METAR
   stations too (Husein Sastranegara, Soekarno-Hatta, Halim) and IEM carries
   international stations — or it injects a domain-dependent selection effect
   into the one comparison the TA exists to make. Not started.

   The natural home for it is an optional coverage source on `observed_months`:
   the union of windows actually observed, where such a record exists, falling
   back to the strike-day proxy where it does not. Raised and deferred, not
   rejected. `lightning.py` is currently untouched.
8. **KX missing from subtropis.** Step 4e. Unexplained, deferred.
9. **2022-12 and 2024-02.** Absent from the subtropis table, and not yet checked
   against METAR the way 2021-03 was. Currently excluded, which is the safe
   default but not an established finding either way.

