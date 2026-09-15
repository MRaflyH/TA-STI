# RUNBOOK — `gfd.dataset`

Clean checkout to two built tables. Reasoning lives in `DECISIONS.md`; this is
the sequence and what to expect from it.

`dataset/` is frozen as of 2026-09-14 (D-15, amended by D-16).

---

## 1. Before anything

`data/raw/` must already exist. `config.py` raises on import if it does not,
and prints the repo root it resolved to. Nothing here creates it.

```
data/raw/
├── pln/       1 .xlsx workbook, 7 sheets   NOT re-acquirable
├── merlin/    89 .csv exports
├── power/     590 .json  (588 fetched + 2 AOD, kept but unused)
└── era5/      504 .nc    (see the layout below)
```

ERA5 breaks down as 84 domain-months per group:

| domain | group | files | holds |
|---|---|---|---|
| tropis | main | 84 | cape kx tciw tclw viiwd vilwd |
| tropis | `_tier1` | 84 | vimdf crr totalx cin cbh tcwv d2m |
| subtropis | main | 84 | cape tciw tclw viiwd vilwd |
| subtropis | `_kx` | 84 | kx |
| subtropis | `_tier1` | 84 | vimdf crr cin cbh tcwv d2m |
| subtropis | `_totalx` | 84 | totalx |

The asymmetry is not a mistake. See §5.

**PLN cannot be downloaded.** Those records came through the supervisors and
are not public. If `data/raw/pln/` is empty the tropis half cannot be rebuilt.
Back up `data/raw/` outside the repo.

---

## 2. Setup, once

From the repo root:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e code/
```

Python 3.13.7. The floor is 3.12 — numpy 2.5.2 will not install below it.

`pip install -e code/` cannot live in `requirements.txt`; a freeze would write
a machine-specific path.

Check it took:

```bash
python3 -c "from gfd.dataset import era5; print(era5.DATASET)"
```

Prints the CDS dataset name if the package resolves and `data/raw/` was found.

---

## 3. Build

```bash
python3 -m gfd.dataset.build
```

A few minutes. Writes `data/processed/gfd_{domain}_hourly.parquet` and a
`.meta.json` beside each.

Expected:

| | tropis | subtropis |
|---|---|---|
| strikes after dedup | 2 236 390 | 5 301 491 |
| rows | 1 841 040 | 3 436 608 |
| cells | 30 | 56 |
| columns | 41 | 41 |
| zero share | 94,30% | 97,11% |
| cell-hours with flashes | 104 955 | 99 273 |

Four lines worth reading rather than skimming:

- `[pln] dropped 5,710 duplicate rows` and `[merlin] dropped 3 duplicate rows`.
  Both expected. D-16 explains why this cannot wait for `selection/`.
- `key overlap 100.0%` for power and era5 in both domains.
- `[features] table matches the contract (20 candidates)`. Anything else means
  a column arrived that nobody has classified.
- `missing by predictor: CIN 23,5% / CBH 1,2%` for tropis, `46,4% / 8,4%` for
  subtropis. Expected and structural — see O-8. Every other predictor is
  complete.

`--domain tropis` builds one. `--no-power` / `--no-era5` skip a source.

---

## 4. What the table holds

41 columns, one row per (0,5° cell, clock hour):

- **20 candidate predictors** — `lat`, `lon`; 5 POWER; 13 ERA5.
- **5 raw temporal** — `year`, `month_of_year`, `day_of_year`,
  `hour_of_day_utc`, `hour_of_day_local`. Neither candidates nor excluded.
  `selection/` owns every encoding (D-13).
- **the target** — `flash_count`, plus `gfd_per_km2_per_day` and
  `gfd_per_km2_per_year`, which are the same count in reporting units. Fit on
  `log1p(flash_count)`; convert to GFD only after aggregating (D-3).
- **5 intensity statistics** — a second target. NaN wherever `flash_count` is
  0, which is correct: the mean intensity of no strikes is undefined.
- **bookkeeping** — `domain`, `time`, `month`, `area_km2`, `days_in_month`,
  `observed_days`, `coverage`, `period_days`.

`coverage` is reported, never acted on in `dataset/` (D-8). It is measured from
lightning activity itself, so it partly measures the weather: Spearman 0,84 and
0,92 against mean flash count.

---

## 5. Re-acquiring the raw data

Only needed on a clean machine. Everything caches, so a re-run resumes.

### ERA5

Needs a free CDS account, a token in `~/.cdsapirc`, and the licence accepted in
the web UI for `reanalysis-era5-single-levels` specifically.

```bash
python3 -m gfd.dataset.era5              # main request, both domains
python3 -m gfd.dataset.era5 --check      # what is on disk against what is mapped
```

**Run one CDS job at a time.** Two concurrent fetches coincided with a transfer
that returned 0 bytes after the job reported success. `era5.py` retries three
times, deletes the partial file first, treats a zero-byte file as not cached,
and carries on past a failure rather than abandoning the run — but there is no
reason to test it.

**Some variables do not come back for the subtropis box in a multi-variable
request, and do when asked alone.** Confirmed twice, for `k_index` and
`total_totals_index`, absent from all 84 files each time. Cause unknown. The
workaround is a supplementary pass, which is why the layout in §1 is
asymmetric:

```bash
python3 -m gfd.dataset.era5 --domain subtropis --supplement k_index
python3 -m gfd.dataset.era5 --domain subtropis --supplement total_totals_index
python3 -m gfd.dataset.era5 --tag tier1 --supplement vertical_integral_of_divergence_of_moisture_flux,convective_rain_rate,total_totals_index,convective_inhibition,cloud_base_height,total_column_water_vapour,2m_dewpoint_temperature
```

Supplements are suffixed so the main glob skips them, and `load_era5` merges
them by reading the columns each file actually holds — a tag names a batch, not
a variable list.

A full pass is 168 requests and took about 64 hours in September 2026. Queue
time dominates and varies by two orders of magnitude.

### NASA POWER

Open — no account, no key.

```bash
python3 -m gfd.dataset.power             # 588 requests
python3 -m gfd.dataset.power --check     # disk against expected, by filename
```

`--check` lists the two AOD files as "not part of a fetch". Correct: AOD was
dropped (D-5) and the files are kept.

### MERLIN

**Geo-restricted.** A browser VPN extension is not enough — this goes through
the OS network stack, so the VPN must be device-level.

```bash
python3 -m gfd.dataset.merlin --self-test
python3 -m gfd.dataset.merlin --start 2018-01-01 --end 2024-12-31
```

The KSC archive has no documented API; the URL token is reverse-engineered. The
self-test re-derives seven captured tokens and runs automatically before any
bulk download, so a change to the site's encoding fails loudly rather than
quietly fetching the wrong period.

---

## 6. Validation

Not tests. These produce evidence for the thesis.

```bash
python3 -c "
from gfd.dataset import lightning as lit
from gfd import config as cfg
lit.check_diurnal(lit.load_pln(), cfg.TROPIS)"
```

Flash count by local hour. This settled the PLN timezone: the peak is at 16:00
local. A peak in the small hours would mean the source clock is wrong, which at
hourly resolution displaces every row of a domain.

```bash
python3 -m gfd.dataset.era5 --check
python3 -m gfd.dataset.power --check
```

---

## 7. What has never run

Stated because it should not be claimed otherwise.

- `merlin.download_range`, `power.fetch_point`, `power.fetch_regional`. The
  files on disk were fetched by the v1 implementation of the same procedure.
  The MERLIN token codec is verified against seven captured tokens; the HTTP
  path in this codebase is not.
- The ZIP branch of `era5._open_members` fires only when a request mixes GRIB
  stepTypes. It ran once, on an eight-variable trial that included a mean-rate
  field. All 13 current variables are `instant`, so it does not fire now.
- The longitude conversion in `era5.parse_netcdf` has never altered a value.
  The CDS sends −180..180 for both boxes. It is a guard, not a fix.
