# Data acquisition runbook

Four sources, two of them files you already have, two of them things you fetch.
Only one needs an account.

| Source | How you get it | Account? | Grid | Notes |
|---|---|---|---|---|
| PLN Puslitbang LDS | Given to you as `.xlsx` | no | point strikes | one sheet or file per year |
| NASA MERLIN | Manual export from the KSC web archive | no | point strikes | short window per export → many files |
| NASA POWER | HTTP API, synchronous | **no** | 0.5° × 0.625° | 1 parameter per regional request |
| ERA5 | Copernicus CDS API, queued | **yes** | 0.25° × 0.25° | licence must be accepted in the browser |

Everything lands in `data/raw/<source>/`, and `python -m gfd_data.build`
turns it into `data/processed/gfd_<domain>.csv`.

---

## Step 0 — environment

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`xarray`, `netcdf4` and `cdsapi` are only needed for ERA5. Steps 1–3 work
without them.

---

## Step 1 — PLN Puslitbang (tropical lightning)

Drop every workbook into `data/raw/pln/`:

```
data/raw/pln/
    Data_Petir_Jabar_20182024_Repaired.xlsx     # currently 2024 only
    Data_Petir_Jabar_2018.xlsx                  # ...add the rest
    ...
```

The loader reads **every sheet of every workbook** and concatenates, so it does
not matter whether the years arrive as separate sheets in one file or as
separate files. It keeps rows whose `Discrimination` starts with `CG` and
derives polarity from the `+`/`-` suffix.

```bash
python -c "from gfd_data.lightning import load_pln; d=load_pln(); print(d.shape, d.timestamp.min(), d.timestamp.max())"
```

**One thing to confirm with PLN before you write this up.** The loader assumes
`Date and time` is local Jakarta time (`Domain.tz = "Asia/Jakarta"` in
`config.py`). If the LDS actually writes UTC, change that field to `"UTC"`.
It shifts strikes across month boundaries by seven hours — small, but it is the
kind of thing an examiner asks about, and you want a definite answer rather than
an assumption.

---

## Step 2 — NASA MERLIN (subtropical lightning)

Export from <https://kscweather.ksc.nasa.gov/wxarchive/MerlinCloudToGround> and
drop every CSV into `data/raw/merlin/` unchanged. The loader globs the folder,
concatenates, and drops exact-duplicate strike records where two exports
overlap at a boundary.

```
data/raw/merlin/
    merlin-cloud-to-ground-export-20264427104454.csv
    merlin-cloud-to-ground-export-...csv
    ...
```

**Budget this properly.** The file you have covers a single day (2023-07-15,
3 208 strikes). Two years is 730 days. Before you start clicking, check what the
archive's real per-export cap is — if it is 30 days you need about 25 exports;
if it is one day you need 730 and you should write a scripted downloader
instead. Either way, do not rename the files: keeping the archive's own
filenames is your provenance record, and the loader does not care what they are
called.

Do not merge them into one spreadsheet by hand. Concatenation in code is
reproducible and a manual merge is not.

---

## Step 3 — NASA POWER (PS, PRECTOTCORR, T2M, RH2M, WS2M, AOD_55_ADJ)

No key, no queue, no registration.

**3a. Smoke-test one parameter first** so you can see the response shape before
committing to a dozen downloads:

```bash
python3 -m gfd_data.smoke_power
```

That fetches `T2M` for the tropical box, saves it under `data/raw/power/`, and
prints the parsed head. If the parser complains about the JSON shape, open the
saved file — the raw payload is always written to disk before parsing, so a
parse failure never costs you a re-download.

**3b. Then fetch everything:**

```bash
python3 -m gfd_data.power
```

Two constraints from the POWER docs are already handled in the code, but know
they exist because they explain the loop:

- a **regional** request may ask for only **one parameter**, so the code issues
  one request per parameter and joins afterwards;
- a regional request is capped at a **4.5° × 4.5° box (100 grid points)**. Both
  your domains fit. If you ever widen West Java or Florida past that, the
  request has to be tiled.

**Expect AOD_55_ADJ to be the problem child.** The predecessor study had to
impute it with monthly averages. Look at the missing-value report that
`build.py` prints before you decide whether to keep the feature, impute it, or
drop it — and whichever you choose, say so explicitly in Bab IV rather than
letting a silent `fillna` do it.

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
3. Open the dataset page for **ERA5 monthly averaged data on single levels**,
   go to the *Download* tab, and **accept the licence**. This is the step
   everyone skips; without it every request returns
   `403 … required licences not accepted`, regardless of how correct your token is.

Verify:

```bash
python3 -c "import cdsapi; cdsapi.Client(); print('CDS client OK')"
```

**4b. Confirm the two flux-divergence variable names before the first run.**

Four of the six names in `config.ERA5_VARIABLES` are stable and I am confident
in them: `convective_available_potential_energy`, `k_index`,
`total_column_cloud_ice_water`, `total_column_cloud_liquid_water`.

The other two —
`vertical_integral_of_divergence_of_cloud_frozen_water_flux` (VIIWD) and
`vertical_integral_of_divergence_of_cloud_liquid_water_flux` (VILWD) — are my
best reconstruction, not something I verified against the current CDS catalogue.
Confirm them the reliable way: on the dataset's *Download* tab, tick the six
variables you want, then press **"Show API request"**. The CDS prints the exact
Python dict, including the exact variable strings. Paste those into
`config.ERA5_VARIABLES` and you are guaranteed to match.

Do the same check for `ERA5_SHORTNAME_MAP` after your first download — that maps
the *short* names inside the NetCDF (`cape`, `kx`, `tciw`, …) onto your column
names. `parse_era5_netcdf` prints any column it does not recognise, so one run
tells you if a key is off.

**4c. Fetch:**

```bash
python3 -m gfd_data.era5
```

One request per domain-year (7 for West Java, 2 for Florida). Requests queue
server-side; monthly means over a small box usually return in a few minutes.
`download_format: "unarchived"` is set deliberately — without it the CDS hands
back a `.zip` and the NetCDF reader fails on what looks like a corrupt file.

---

## Step 5 — build the modelling tables

```bash
python3 -m gfd_data.build
```

Produces, per domain:

```
data/processed/gfd_tropis.csv          # 30 cells × 84 months = 2 520 rows
data/processed/gfd_tropis.meta.json    # config snapshot, for F-05 replay
data/processed/gfd_subtropis.csv       # 56 cells × 24 months = 1 344 rows
data/processed/gfd_subtropis.meta.json
```

Columns: `domain, month, year, month_of_year, lat, lon,` the six POWER
features, the six ERA5 features, then `flash_count, area_km2, days_in_month,
gfd_per_km2_per_day, gfd_per_km2_per_year`.

Use `--no-power --no-era5` to build the lightning half alone while you are still
waiting on downloads.

The join is a **left join onto the lightning grid**, so a cell-month that the
meteorological sources do not cover appears as a NaN row rather than vanishing.
The build prints a missing-value share per feature — read it every time.

---

## Decisions this pipeline makes for you, and why

**Monthly, not daily.** Every row is one cell-month. This follows the temporal
aggregation the proposal already committed to as the mitigation for satellite
sparsity, and it is what makes the ERA5 *monthly means* product the right
product. It also keeps the table at a few thousand rows, which matters when
each training epoch runs on a simulator.

**Empty cell-months are kept as zeros.** `aggregate_gfd(fill_empty_cells=True)`
inserts explicit `flash_count = 0` rows. Dropping them would quietly train the
model on "months that had lightning", which raises the mean of the target and
makes R² look better than it is. The cost is heavy zero-inflation: on the single
MERLIN day you currently have, 36 of 1 344 cell-months are non-zero. With two
full years that thins out, but check the distribution before you trust any R².

**GFD is per km² per year.** `gfd_per_km2_per_year = flash_count / area_km2 ×
365.25 / days_in_month`, with cell area computed from the cosine of latitude so
that a Florida cell is correctly smaller than a West Java one. Note the
predecessor paper reports its target as km⁻¹day⁻¹, which is not a density unit —
a flash density is per area per time. Use the conventional unit and define it
explicitly in Bab III; `gfd_per_km2_per_day` is also in the output if you want
to compare numbers directly against theirs.

**Ocean cells are included.** The Florida bounding box covers a lot of Atlantic
and Gulf. MERLIN detects over water, but detection efficiency and the physics
both differ offshore, and this is exactly the kind of thing that shows up as an
unexplained cross-domain generalization gap. Decide deliberately whether to
apply a land mask, and record the decision.
