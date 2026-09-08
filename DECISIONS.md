# DECISIONS.md

**Project-wide decision record. Merged 8 September 2026.
Batch 3 (modelling design, D-29 to D-39) added 8 September 2026.**

Where this disagrees with `config.py`, `config.py` wins.

**This file supersedes all three of its inputs** — `code/modelling/DECISIONS.md`,
the batch 1 draft (data and target definition) and the batch 2 draft
(acquisition and data quality). Delete those three rather than leaving them to
drift; three files sharing one D-number namespace is what produced the
collisions this merge resolves.

Every choice in this project that a reader could reasonably have made
differently, with its reasoning, its cost and its provenance — so the thesis can
cite it by ID rather than re-deriving the argument in prose.

---

## How to read this file

**Six fields per entry:** what was decided, why, what it costs, how to reverse
it, which Bab it belongs in, and who decided it.

**The `Who` field is the one that cannot be reconstructed later**, and it is
preserved verbatim from the drafts. It has already caught two things nothing
else would have: `MIN_COVERAGE = 0.0` was Rafly's call over an objection, and so
was hourly resolution. Both invert the assumption a reader would otherwise make.
Where it says "inherited", "predates the recoverable chats" or "not
established", that is the accurate record and not a placeholder for something
tidier.

**Entries are ordered by chapter, not by ID.** That is what makes the file
usable while writing. IDs are labels; the contents table below is the index.

**Provenance tags on figures:**

- **[repo]** — stated in `config.py`, `RUNBOOK.md`, or a source docstring, and
  cross-checked where more than one file carries it.
- **[derived]** — computed from repo values, with the arithmetic shown.
- **[measured]** — counted or read directly from the built tables or the files
  on disk, 8 September 2026.

No `[unverified]` figures remain. D-28's benchmark and cosine figures were the
last to be checked, against `qnn.py` on 8 September, and are tagged `[repo]`
like the rest.

---

## Numbering

One entry moved and one is new. Everything else keeps the ID it had.

| Range | Owner | Note |
|---|---|---|
| D-01 – D-14 | modelling record | unchanged — cited from `metrics.py`, `config.py`, `dataset.py`, `experiments.py`, `training.py` |
| D-15 – D-20 | batch 1 | unchanged |
| D-21 | batch 1 | **was batch 1's D-14**, which collided with the modelling record's D-14 |
| D-22 – D-27 | batch 2 | unchanged |
| D-28 | new | the PennyLane gradient backend, which had no ID at all |
| D-29 – D-39 | batch 3 | modelling design: what the code implements and the record did not carry |

**Why D-21 moved rather than the modelling D-14.** The modelling IDs are cited
from executable code — `dataset.assert_no_leakage` raises a `ValueError` naming
"DECISIONS.md D-02 and D-08", and `build.py`'s metadata block points at "D-01 and
D-08". D-03 and D-04 are cited over twenty times across six files. Nothing
outside the batch 1 draft cited its D-14, so moving it was free.

**Two duplicate pairs were merged rather than kept side by side.** Batch 1 wrote
entries on the fitting target and on reporting windows without knowing the
modelling record already had D-03 and D-04 on those subjects. The modelling IDs
survive and both texts are folded into them.

**One code citation is now wrong and is not yet fixed.** `config.py:255` cites
"DECISIONS.md D-14" for the PennyLane switch, which is D-28. See the discrepancy
register, O6.

---

## Build of record — 2026-09-06, after the intensity patch

| | tropis | subtropis |
|---|---|---|
| Strikes | 2.242.100 | 5.301.491 |
| Cells | 30 | 56 |
| Cell-hours | 1.841.040 | 3.314.304 |
| Non-zero cell-hours | 104.955 | 99.273 |
| Zero share | 94,30% | 97,00% |
| Non-zero range | 1 .. 2.391 | 1 .. 11.777 |
| Months covered | 84 of 84 | 81 of 84 |
| Day-coverage, mean (min) | **85% (13%)** | 59% (3%) |
| Predictors | 14, `KX` present | 13, `KX` absent |
| Missing values | none | none |

**Day-coverage is row-weighted**, over the rows actually in the table: tropis
mean 0,8549 min 0,1290; subtropis mean 0,5921 min 0,0323 **[measured]**. An
earlier version of this table gave tropis as 86%, which predates the measurement
and was probably month-weighted. Say which weighting in Bab IV. The figures come
from the `coverage` column of the built parquet — `.meta.json` does *not* carry
them.

No predictor in either table contains a NaN. **No imputation step is required
anywhere in the modelling package.** Say so in Bab III.

---

## Contents by chapter

An entry belonging in two chapters is listed under both and written out once, in
its primary chapter.

### Bab I — what the thesis claims to be

| ID | Entry | Written out in |
|---|---|---|
| D-21 | Temporal resolution: one row is one cell-hour | Bab III §3 |
| D-28 | PennyLane over Qiskit for gradients | Bab III §6 |

Conditional entries only: neither touches Bab I unless the scope sentence or the
judul changes. **They are one conversation, not two** — see the section below.

### Bab III — Analisis dan Metodologi

| | ID | Entry |
|---|---|---|
| §1 Sources and acquisition | D-22 | PLN workbooks: every sheet, cloud-to-ground only |
| | D-23 | MERLIN: a reverse-engineered URL codec, 29-day windows, 89 exports |
| | D-24 | NASA POWER: point requests on the native grid, per-year |
| | D-25 | ERA5: one CDS request per domain-month |
| §2 Quality and exclusions | D-26 | Three MERLIN months hold no data and are excluded, not filled |
| | D-17 | The PLN clock is local Jakarta time — validated, not assumed |
| §3 The shape of the dataset | D-21 | Temporal resolution: one row is one cell-hour |
| | D-15 | Spatial grid: 0,5°, boxes snapped outward |
| | D-16 | Bin labelling: UTC, forced, at hourly resolution |
| | D-18 | The coverage gate is off: `MIN_COVERAGE = 0.0` |
| | D-19 | Empty cells are filled with explicit zeros |
| | D-20 | Zero inflation is carried and reported, not engineered away |
| §4 Target and preprocessing | D-03 | The fitting target is `log1p(flash_count)`; reporting in GFD units |
| | D-08 | Intensity is built into the pipeline, used later |
| | D-02 | Feature set: 13 base predictors, hour encoding as an axis |
| | D-11 | All-zero cells are identified before any split |
| | **D-35** | Feature scaling: min-max onto [0, π], clipped, fitted on train alone |
| §5 Experimental protocol | D-04 | Train hourly, aggregate the predictions to a reporting window |
| | D-06 | Rolling-origin cross-validation across years |
| | D-07 | Training rows may be reshaped; test rows may not |
| | D-13 | The default task is a hurdle model |
| | **D-38** | Sampling mechanics: stratified, largest-remainder, stage-filtered first |
| | **D-36** | Every model carries its own scaler; cross-domain uses the source's |
| | **D-29** | The compute budget, and the two-tier split it forces |
| | **D-30** | **Equal optimizer steps per epoch** — the batch's headline |
| | **D-37** | Sweep protocol: one fold, one seed, config mutated in place |
| §6 Implementation | D-09 | PyTorch for both models, via `TorchConnector` |
| | D-28 | PennyLane over Qiskit for gradients |
| | **D-32** | A trainable affine head on the quantum output |
| | **D-31** | Output-bias initialisation and layer calibration, both arms |
| | **D-33** | Quantum architecture: `z` map, `real_amplitudes` reps = 2, local readout |
| | **D-34** | The ladder is six rungs, and parity is 47 against 52 |
| | **D-39** | A reduced Qiskit run, to show the two gradient paths converge |
| §7 Requirements | D-12 | NF-01 will not be met at hourly resolution, stated in advance |

### Bab IV — Hasil dan Pembahasan

| | ID | Entry |
|---|---|---|
| Limitations that frame every result | D-27 | The detection-efficiency gradient is measured, and confounded |
| | D-10 | `coverage` is reported, never acted on |
| | D-18 | Coverage distribution over the rows trained on |
| | D-20 | Zero share beside every metric |
| | D-26 | The coverage asymmetry between the domains |
| | D-24 | The AOD broadcast |
| | D-11 | All-zero cells under a cell-holdout split |
| Results | D-04 | The window curve and the clustering contrast |
| | D-13 | Stage-wise results |
| | D-02 | The 13/14/15 feature sweep |
| | D-05 | Spatial aggregation |
| | D-06 | Fold variability, and the solar-cycle limitation |
| | D-07 | The zero-ratio sweep |
| | D-14 | The sample-efficiency curve |
| | D-08 | The units argument and the detection-efficiency bias |
| | D-01 | The cost of dropping `KX` |
| | D-03 | The calibration factor |
| | **D-30** | `nn_full` under an equalised step budget — same budget, more data |
| | **D-34** | The six-rung ladder, and 47 against 52 |
| | **D-36** | The residual cross-domain gap as a transfer finding |
| | **D-37** | The sweep asymmetry, declared |
| | **D-29** | Seed and fold counts, declared |

### Bab V — Penutup dan Evaluasi

| ID | Entry | Written out in |
|---|---|---|
| D-12 | NF-01 evaluated against every reporting window | Bab III §7 |
| D-14 | Sample efficiency: the finding and its limitation | Bab IV |
| D-20 | The NF-01 renegotiation | Bab III §3 |
| D-01 | `KX` and the weakened predecessor comparison | Bab IV |
| **D-34** | `nn_full`, and parameter parity as a weak currency | Bab III §6 |
| **D-30** | Which comparison the thesis is actually making | Bab III §5 |

---

# Bab I — two questions about what the thesis claims to be

No entry is written out here. Two are listed because they are the only decisions
in this record that can reach the title page, and **they should be raised with
the pembimbing as one conversation rather than two.**

**D-21 — is this ground flash density?** Ground flash density conventionally
means flashes per km² per year. An hourly cell-count is lightning *occurrence*,
a well-studied task with its own metrics (POD, FAR, CSI, Brier). If the hourly
build is what the TA reports, Bab I's scope sentence has to say so.

**D-28 — is this Qiskit?** The circuits are built and verified against Qiskit,
but every gradient in the results was computed by PennyLane `lightning.qubit`.
"Framework Qiskit" in the judul is defensible but no longer self-evidently
accurate.

Both are questions about what the thesis *is*, both have been drifting, and both
have the same shape: a defensible answer exists, but only if it is stated rather
than discovered by an examiner. Open questions 7, 8 and 9.

---

# Bab III — Analisis dan Metodologi

## §1 — Sources and acquisition

## D-22 — PLN workbooks: every sheet, cloud-to-ground only

**Decided.** `load_pln` globs `data/raw/pln/*.xlsx` and concatenates.
`load_pln_workbook` reads **every sheet of every workbook** unless told
otherwise, so it does not matter whether the seven years arrive as separate
files or as separate sheets in one file. Rows are kept where `Discrimination`
begins with `CG`, case-insensitively; polarity is derived from the `+`/`-`
suffix of that same field. Timestamps are localised to `cfg.TROPIS.tz` and
converted to UTC.

Result: **2.242.100 CG strikes, 2018-01-01 .. 2024-12-31** **[repo]**. That is
what the loader returns, post-filter — not a raw row count.

**Why.** Reading every sheet removes a configuration question that the supplier
controls and the project does not: PLN can reorganise its export between
deliveries without breaking the loader. The CG filter is what makes the target
*ground* flash density rather than total lightning; the source discriminates and
the code uses the discrimination rather than assuming it.

The filter runs unconditionally rather than being made optional. The comment is
explicit that this is deliberate.

**What it costs.** Almost nothing, as it turns out — but the checking is the
point, and one caveat survives.

**The CG filter is a no-op, and this closes what would have been a serious
exposure.** Measured 8 September across all seven sheets of `Data Petir Jabar
2018-2024 ORIGINAL.xlsx` **[measured]**:

| Sheet | CG rows | Non-CG rows |
|---|---|---|
| 2018 | 309.592 | 0 |
| 2019 | 374.927 | 0 |
| 2020 | 289.359 | 0 |
| 2021 | 303.061 | 0 |
| 2022 | 378.101 | 0 |
| 2023 | 290.097 | 0 |
| 2024 | 296.963 | 0 |
| **Total** | **2.242.100** | **0** |

The total matches what `load_pln()` returns exactly **[derived]**. **The PLN
export is CG-only at source in every year**, so the filter discards nothing and
has never discarded anything.

**Record the check, not just the result.** Before it was run, an earlier comment
had generalised "2024 contains no IC rows" to the whole record, and that
generalisation was correct — but it was not known to be. Had the yield differed
by year, the filter would have been doing real work in some years and none in
others, and the tropis target would have been **defined differently across the
record**: a CG-only density where the source was already clean, a
filtered-from-mixed density where it was not. Under D-06's chronological folds
that difference would have landed directly on the train/test boundary, where a
composition change is indistinguishable from a trend the model is supposed to
learn. It did not happen, and now it is known not to have happened rather than
assumed.

Two things follow. The filter stays, because it is what makes the target's
definition explicit rather than inherited — a future delivery could carry IC
rows and the filter is what would catch it. And Bab III can state that the
tropis target is CG-only **as a verified property of the source**, not as a
consequence of a preprocessing step.

The one remaining caveat is scope: the tropis strike count depends on what is in
`data/raw/pln/`, so both the total and this composition check must be re-run if
a workbook is ever added or replaced. The filename says `20182024`; the contents
are whatever the loader reports.

Incidentally, the seven-sheets-in-one-workbook layout is exactly the case the
read-every-sheet design exists for.

`load_pln_workbook` hardcodes `cfg.TROPIS.tz` rather than taking a domain. This
is correct today, because PLN only ever feeds tropis, but it means the timezone
assumption lives in the loader rather than on the `Domain` — so if written
confirmation from PLN ever contradicts D-17, this is the line that changes, not
just `config.TROPIS`.

**How to reverse it.** The sheet behaviour is a parameter (`sheets=`). The CG
filter is not parameterised and would need a code change; that is appropriate,
since removing it changes what the target means.

**Bab.** III, data-source subsection. State the CG filter explicitly — it is
part of the target's definition, not a preprocessing detail.

**Who.** **Predates the recoverable chats.** The loader design and the CG filter
both pre-exist every conversation I can search. The correction to the IC comment
is mine. **Not established, and I am not assigning it — tell me if you wrote the
loader or if it came with the pipeline.**

---

## D-23 — MERLIN: a reverse-engineered URL codec, 29-day windows, 89 exports

**Decided.** The KSC Weather Archive has no documented API, so
`merlin_download.py` reconstructs its export URLs directly. The whole query
lives in one token:

```
/wxarchive/MerlinCloudToGround/Export/BXHPAAABXHPMAAAAAABaAAA
                                      \_____/\_____/\_______/
                                       start    end   filters
```

Each 7-character block is one datetime, one base-62 digit per field —
`[century][year mod 100][month][day][hour][minute][second]` — over the alphabet
`A=0..Z=25, a=26..z=51, 0=52..9=61`. The trailing nine characters
(`FILTER_TAIL = "AAAABaAAA"`) are the non-date filters at their defaults and are
reproduced verbatim.

`MAX_WINDOW_DAYS = 29`. The archive rejects anything over 30 days; 29 leaves
margin against off-by-one at the boundaries.

Downloaded files are never renamed and never merged by hand. Overlapping
exports are de-duplicated in code on `(timestamp, lat, lon, peak_current_ka)`.

Result: **89 exports, 5.301.491 strikes after de-duplication, 583 MB,
2018-01-03 .. 2024-12-31** **[repo]**. Three exact-duplicate strike records were
dropped on load **[repo]**.

**Why.** The archive caps each export at 30 days, so seven years cannot be
pulled by hand in any reasonable number of sittings — but the export URL is
deterministic, so it can be generated. The codec was derived by diffing six
tokens from controlled searches (+1 second, +1 minute, +1 hour, +1 day on each
endpoint), and `self_test()` re-checks seven known tokens before any bulk run.
That is the load-bearing part of the design: a change to the site's encoding
fails loudly instead of silently downloading the wrong period.

Not renaming the files is deliberate — the archive's own filenames are the
provenance record. Not merging by hand is deliberate for the same reason:
concatenation in code is reproducible and a manual merge is not.

**What it costs.** Three operational constraints, all recorded in the module.

The archive is **geo-restricted** and a browser-extension VPN is not enough; the
script runs through the OS network stack, so the VPN must be device-level.
Separately, macOS ships its trust roots in the Keychain while Python verifies
against `certifi`, and `kscweather` serves a chain `certifi` alone cannot
complete — hence `truststore`, with `--ca-bundle` and `--use-curl` as fallbacks.

**The window arithmetic is exact, and this corrects the RUNBOOK.** 2018-01-01 to
2024-12-31 is 2.557 days; at a 29-day stride that is ⌈2557/29⌉ = **89 windows**
**[derived]**. Measured 8 September: `--dry-run` emits **89 windows against 89
files, one-to-one**, stride confirmed at 29 days and contiguous
(`20180101_20180129`, `20180130_20180227`, `20180228_20180328`), and a filename
diff of expected-against-present is **empty in both directions** — no window
lacks a file and no file is unexpected **[measured]**.

So there is no shortfall to explain. `RUNBOOK.md` step 2 claims 86 windows at a
30-day step and attributes the gap to manual re-pulls; neither half is true. See
outstanding item O3.

**How to reverse it.** `--window-days` is a flag; the codec is not
parameterised and should not be. `--self-test` is the guard, and
`download_range` aborts if it fails.

**Bab.** III, data-source subsection. The codec derivation is worth a short
paragraph — it is genuine method, and "we downloaded it from the website" would
understate what was actually required.

**Who.** **Not established.** The module docstring describes the derivation but
not who did it, and I found no chat covering it. **Ask: did you reverse-engineer
the token codec, or did I?** The `MAX_WINDOW_DAYS = 29` margin and the
`truststore` diagnosis read as mine but I cannot evidence either.

---

## D-24 — NASA POWER: point requests on the native grid, per-year, per-parameter frequency

**Decided.** Three linked choices about request shape.

**Point, not regional, at hourly.** `/api/temporal/hourly/regional` does not
exist and returns a bare 404. So the hourly fetch loops over grid points and
issues one request each, carrying every hourly parameter at once (the point
endpoint accepts up to 15). Daily and monthly *do* support regional requests,
one parameter at a time, and `AOD_55_ADJ` still uses one.

**POWER's native points, not the project's cell centres.** MERRA-2 geometry:
latitudes on exact multiples of 0,5, longitudes on exact multiples of 0,625.

**Per-year chunking.** `POWER_HOURLY_CHUNK = "Y"`.

Counts: the two domains hold **84 native points** — tropis 6 lat × 5 lon = 30,
subtropis 9 × 6 = 54 **[derived from the snapped bboxes and `POWER_GRID_LAT` /
`POWER_GRID_LON`; matches the figure in `config.py`]**. At `"Y"` that is
84 × 7 = 588 point requests, plus 2 regional AOD requests, **590 total**
**[derived]**. Under `"ALL"` it would be 86.

On disk: **591 files** **[measured]**.

**Per-parameter native frequency.** `POWER_PARAM_FREQ` records the finest
resolution at which POWER publishes each parameter — `PS`, `PRECTOTCORR`, `T2M`,
`RH2M`, `WS2M` hourly; `AOD_55_ADJ` monthly. A parameter coarser than
`TIME_FREQ` is fetched at its own resolution and broadcast across the finer
periods. This is a fact about NASA POWER, not a project setting.

`POWER_TIME_STANDARD = "UTC"`, sent explicitly, because the hourly endpoint
defaults to Local Solar Time.

**Why.** The point/regional split is forced by the API. Requesting POWER's own
points rather than the project's cell centres is not: several project cells fall
inside one POWER longitude cell, and the POWER docs warn that repeatedly
requesting the same underlying location can get the caller blocked. So the
choice avoids both duplicate billing and a plausible ban.

`"Y"` over `"ALL"` is a retry-cost argument. `"ALL"` was tried first and
returned HTTP 422 — *"please shorten your requested time extent for a JSON
formatted data request"*. `"Y"` is slower overall but a failure costs one year of
one point instead of seven, and the cache is finer grained so an interrupted run
resumes closer to where it stopped.

LST is a 15-degree longitude swath rather than a civil timezone, so it is not
Asia/Jakarta and could not be reconciled with the other three sources. See D-16.

**What it costs.** The AOD broadcast is the real one, and it is a limitation
rather than an implementation detail: at hourly resolution `AOD_55_ADJ` is
**constant across ~730 consecutive rows**. It cannot explain hour-to-hour
variance in the target, so it will rank near zero in any feature-importance
analysis for that reason alone rather than because aerosol loading is
unimportant. Both `config.py` and the RUNBOOK say to consider dropping it
against a scarce qubit budget, and to say which in Bab IV either way.

Hourly `PRECTOTCORR` is mm/hour where the monthly product is mm/day. **The units
are not comparable across resolutions** — this matters if an hourly and a
monthly build are ever set side by side.

**One duplicated point-year, unexamined.** 590 requests against 591 files:
`power_tropis_hourly_m006p500_p106p250` holds 8 files where every other point
holds 7, a duplicated year window from a re-pull **[measured]**. The build
reported 100% key overlap so it is harmless, but it has not been opened. Say
which figure is which in Bab III — 590 is the request count, 591 is the file
count, and quoting one for the other invites a question. Open question 16.

**How to reverse it.** `POWER_HOURLY_CHUNK` and `POWER_PARAM_FREQ` are config
values; the cache is keyed by filename, so switching chunk size orphans the
existing files rather than reusing them. The point/regional split is structural.

**Bab.** III for the request shape and the units caveat, IV for the AOD
broadcast and whatever is decided about keeping it.

**Who.** **Mine, corrected under fire, with you executing.** I set
`POWER_HOURLY_CHUNK = "ALL"` without knowing the limit and said so at the time;
your run returned the 422; I recommended `"Y"`; you set it and launched. The
point-only discovery was mine, from the POWER docs, after the `hourly/regional`
404. The native-grid argument is mine, from the same docs. You did not object to
any of it, and the one question you raised — whether moving to yearly chunks
undid the move to hourly resolution — was about my wording, not the decision.

---

## D-25 — ERA5: one CDS request per domain-month

**Decided.** `ERA5_HOURLY_CHUNK = "M"`. Seven years × 12 months × 2 domains =
**168 requests**, each about 1,3 MB. On disk: **168 files, 258 MB**
**[measured for the file count; size repo]**.

Six single-level variables: `convective_available_potential_energy`, `k_index`,
`total_column_cloud_ice_water`, `total_column_cloud_liquid_water`, and the two
flux divergences. All 24 hours requested.

**Why.** `"Y"` was **tested by hand and refused**. One domain-year is roughly
53.000 fields, which exceeds the CDS cost limit; the CDS either declines it
outright or gives it very low priority. `config.py` records this as a settled
negative result rather than an untried option, with an explicit instruction not
to switch.

A monthly chunk is also cheap to retry, which matters against a queued service.

**What it costs.** 168 sequential queued requests is roughly a night's work
rather than the fourteen jobs `"Y"` would have been. The CDS queue behaviour
degraded during the fetch and the cause was never established — fair-share
demotion for sustained usage, or ordinary European-working-hours load. Both fit
the timing; neither is proven, and `RUNBOOK.md` is explicit that neither should
be asserted in the thesis.

**The middle ground is untested.** A quarterly chunk is ~13.000 fields and 56
requests. The cost threshold sits somewhere between a month and a year and only
the two ends have been probed. Adding `"Q"` needs a branch in
`fetch_chunk_hourly` **and** a matching glob in `_files`, or `load_era5` silently
picks up the wrong set of files.

**Two variable names were never verified**, and this is unresolved rather than
merely unchecked. `vertical_integral_of_divergence_of_cloud_frozen_water_flux`
and `..._liquid_water_flux` are a best reconstruction, not something confirmed
against the live CDS catalogue. Four of the six are stable and known good. The
check is cheap — tick the six variables on the dataset's Download tab and press
"Show API request", which prints the exact strings — and it has not been done.
See open question 13.

**A related structural fact, since it explains the parser.** Instantaneous
fields (CAPE, KX, TCIW, TCLW) and time-averaged flux fields (VIIWD, VILWD) do
not share a GRIB `stepType`, so the CDS ignores `download_format: "unarchived"`
and returns a ZIP holding one NetCDF per `stepType`, still named `.nc`.
`_open_members` handles both shapes and merges on the shared axes.

**How to reverse it.** One config value, but the filenames encode the chunk, so
changing it orphans 168 files rather than reusing them.

**Bab.** III for the acquisition; the instantaneous-versus-interval pairing
(ERA5 gives a snapshot at the top of the hour, the target counts flashes inside
the hour) belongs there too — it is one of the three costs recorded under D-21.

**Who.** **Mine as a default; the `"Y"` test was my suggestion and it failed.**
`"M"` was the original setting rather than a chosen alternative — I proposed
testing whether `"Y"` would work, you asked whether to switch, I said to test
before switching, and the test refused it. So `"M"` survives by elimination
rather than by argument, which is a weaker provenance than it looks and is worth
recording as such.

---

## §2 — Quality and exclusions

## D-26 — Three MERLIN months hold no data and are excluded, not filled

**Decided.** Five of the 89 exports returned nothing usable. Three months
consequently hold no strike record at all and are **absent from the processed
table** rather than zero-filled: **2021-03, 2022-12, 2024-02** **[repo]**.

| File | Window | Rows |
|---|---|---|
| `merlin_20210306_20210403.csv` | 6 Mar – 3 Apr 2021 | 0 |
| `merlin_20221204_20230101.csv` | 4 Dec 2022 – 1 Jan 2023 | 1 |
| `merlin_20230102_20230130.csv` | 2 – 30 Jan 2023 | 0 |
| `merlin_20231019_20231116.csv` | 19 Oct – 16 Nov 2023 | 0 |
| `merlin_20240212_20240311.csv` | 12 Feb – 11 Mar 2024 | 0 |

**This is missing content, not missing files.** All 89 windows have a file and
all 89 files map to a window, verified by a two-way filename diff on
8 September **[measured]**. Four of the five are well-formed CSVs with a header
and zero data rows; the fifth returned a single row for a 29-day window. Every
day of 2018–2024 was requested by some export.

**Why they are not transport failures.** `fetch_window` validates the response
with `looks_like_csv()` and writes any non-CSV body to `FAILED_<dates>.html`
without saving a CSV at all. A VPN drop or a geo-block therefore could not
produce a well-formed empty CSV — it would produce an HTML file under a
different name. The archive answered, correctly formed, with nothing in it.

**2021-03 is a proven instrument gap.** METAR from the Iowa Environmental
Mesonet ASOS archive shows thunderstorms during a month MERLIN recorded as
empty:

```
2021-03-31 20:54Z  KCOF ... +TSRA BKN021 24/20 ... TSB54
2021-03-06 15:53Z  KDAB ... -TSRA ... OCNL LTGICCG OHD-NW-N TS OHD-NW-N MOV E
```

`+TSRA` at KCOF is a heavy thunderstorm **at Patrick SFB — one of the three
sites where MERLIN's own sensors are installed**. `LTGICCG OHD` at Daytona is
in-cloud *and cloud-to-ground* lightning directly overhead at 29,2°N −81,1°W,
inside the domain box. MERLIN returned zero CG strikes for the month.

**Why excluded rather than filled.** Filling would assert roughly 40.000
cell-hour rows of confident zero per month, which for 2021-03 is now known to be
false. Exclusion is `aggregate_gfd`'s default behaviour — months with no records
at all are dropped by a separate mechanism from the coverage gate and reported
as `NO DATA for N months`. **No code was changed to achieve this.**

**What it costs.** Subtropis covers 81 of 84 months against tropis's 84
**[repo]** — the two domains no longer span the same period, in a project whose
core result is a cross-domain comparison. That asymmetry belongs in Bab IV with
both numbers in it.

The three months are also only the cases where MERLIN logged *literally
nothing*. A month where the network was down for three weeks but caught one
storm on day 29 appears in the coverage table at 1/31 and looks merely quiet. So
the true downtime is bounded below by these three, not measured by them. That is
the same limitation D-10 and D-18 describe from the other side.

**How to reverse it.** The five files were not deleted and remain in
`data/raw/merlin/`. Re-pulling them is **untried**: `fetch_window` skips a window
whose file already exists unless `--overwrite` is passed, so a naive re-run
prints `cached` and fetches nothing. If a re-pull ever returns data, the months
re-enter the build with no other change. Open question 17.

**Bab.** III for the exclusion and its mechanism; IV for the coverage asymmetry
between the domains. The METAR check is a genuine validation result and should
be written as one, in the same register as the PLN timezone finding in D-17 —
an instrument was checked against an independent instrument and found wanting.

**Who.** **Nobody, as a decision — it is `aggregate_gfd`'s default that nobody
overrode**, and it is recorded here because a default that goes unchallenged is
still a choice a reader could have made differently. The METAR cross-check is a
deliberate act and `merlin-crosscheck/metar_check.py` exists to repeat it, but
**I cannot establish who ran it or whose idea it was — ask.** The
excluded-not-filled framing in `RUNBOOK.md` is mine.

---

## D-17 — The PLN clock is local Jakarta time, validated, not assumed

**Decided.** `TROPIS.tz = "Asia/Jakarta"`. The loader localises the raw
`Date and time` field as Jakarta and converts to UTC. As of 2026-09-06 this is
recorded in `config.py` as settled.

**Why.** Nothing in the PLN export states its clock, so this began as an
assumption. It is now a physical result. Running `smoke_lightning --domain
tropis` over all 2.242.100 strikes gives a peak at 16:00 local with 431.544
flashes, flanked by 15:00 and 17:00, trough at 08:00–10:00 **[repo]**.

The argument is stronger than "that looks plausible", and this is the part that
matters for Bab III. The loader localises the raw field as Jakarta and the smoke
test converts back, so the histogram is the raw field's own hour. Were the
export UTC, true West Java local time would be raw + 7 and the peak would land
at 23:00 — a midnight maximum for tropical convection, which is not physical.
Florida is the control: MERLIN genuinely is UTC and its local-hour peak lands at
15:00 **[repo]**.

**What it costs.** Nothing now. What it would have cost had it gone the other
way is the point: at monthly resolution a seven-hour error moved a handful of
strikes across month boundaries, but at hourly it would displace *every* tropis
row by seven hours in exactly the dimension hourly resolution exists to capture,
and produce a plausible cross-domain gap that is pure artefact. `TZ_MODE` being
forced to UTC does not rescue this — that fixes the label, and this is about
whether the timestamps were correctly interpreted before labelling.

**How to reverse it.** One field on `TROPIS` — but note that
`load_pln_workbook` hardcodes `cfg.TROPIS.tz` rather than taking a domain, so if
written confirmation ever contradicts the finding, the loader is the line to
change, not just the config.

**Bab.** III, as a validation paragraph, not an assumption.

Write it up as evidence. "Jawa Barat is in WIB so we assumed local time" invites
the obvious follow-up at sidang; "the diurnal cycle demonstrates the field is
local" does not. An export tool can emit UTC for an Indonesian network — what
rules that out here is the physics, not the geography. Written confirmation from
PLN through the pembimbing is still worth having, but it would confirm a finding
rather than settle an unknown.

**Who.** The check was mine — `smoke_lightning.check_timezone` exists for this.
The result is the instrument's. The decision to treat it as settled rather than
blocking is mine and appears unobjected.

---

## §3 — The shape of the dataset

## D-21 — Temporal resolution: one row is one cell-hour

*Was batch 1's D-14. Renumbered in the merge; nothing outside that draft cited
it.*

**Decided.** `TIME_FREQ = "h"`. Every training row is one 0,5° cell for one
clock hour. The `"D"` and `"M"` code paths remain working; nothing is built at
either.

**Why.** Two halves, and only one of them is in the record.

**The positive case is Rafly's: hourly gives a more accurate input-to-output
mapping** between a meteorological state and the lightning associated with it.
Recorded as **recollection**. It is not in `config.py`, `RUNBOOK.md`, or any
recoverable chat, and it has never been set out as an argument — so Bab III will
be making this case for the first time rather than citing it. See open
question 7.

**The negative case for the alternatives is written down.** `config.py` states
hourly is "the project's decision, not a placeholder", and `"M"` is retained
solely because the predecessor study aggregated monthly, so a monthly build is
the only artifact that could ever be set beside his numbers.

**What it costs.** Three things, all consequential.

1. **It departs from the proposal.** Temporal aggregation was the approved
   mitigation for data sparsity; hourly is the opposite move. `RUNBOOK.md` is
   explicit that this "needs a sentence in Bab III and a conversation with the
   pembimbing, not a silent config change."
2. **It changes the target's character.** See D-20 and D-03.
3. **It may change the problem statement.** Ground flash density conventionally
   means flashes per km² per year. An hourly cell-count is lightning
   *occurrence*, which has its own literature and its own metrics (POD, FAR,
   CSI, Brier). If the hourly build is what the TA reports, the title and the
   Bab I scope have to say so.

Row counts: **1.841.040 tropis, 3.314.304 subtropis [measured]**, read from
`data/processed/gfd_<domain>_hourly.meta.json` (`n_rows`). The same files give
`zero_target_share` 0,942991 and 0,970047, and `n_cells` 30 and 56. Non-zero
rows are 104.955 and 99.273 **[measured]**, matching what `dataset.stage_rows`
asserts. The arithmetic closes: 104.955 / 1.841.040 = 5,70% and
99.273 / 3.314.304 = 3,00%, giving the 94,30% and 97,00% zero shares quoted
throughout **[derived]**.

**How to reverse it.** One value in `config.py`. Changing it changes which POWER
endpoint is called, which ERA5 product is downloaded and whether it is
collapsed, how strikes are binned, and how the target is normalised; nothing
else needs editing. All three resolutions can coexist on disk — raw files are
named by resolution and processed tables go to
`gfd_<domain>_<hourly|daily|monthly>.*`. Hourly and daily share their ERA5
downloads, so switching between those two is free once the fetch is done.
Switching to monthly means a fresh ERA5 download against a different dataset
and a different licence.

**Bab.** III (method and its departure from the proposal), and I if the scope
sentence changes.

**Who.** **Rafly's, and taken against my stated objections at the time.**

The sequence was **monthly → daily → hourly**. He asked for daily, then asked
whether hourly was possible, then chose it. (An earlier revision of this entry
queried whether the intermediate step was daily or whether the project went
straight from monthly; the daily step is correct and that query was wrong.)

I objected on three grounds. All three are now in this record as costs rather
than as blockers, which is the right place for them, but the fact that they were
raised *before* the decision and not discovered after it is itself worth
recording:

1. **Zero inflation** — the target becomes 94–97% zeros and R² stops meaning
   much. See D-20.
2. **The problem statement may change** — hourly cell-counts are lightning
   occurrence, not ground flash density. See cost 3 above and open question 8.
3. **The ERA5 instantaneous-versus-interval mismatch** — ERA5 hourly fields are
   instantaneous values at the top of the hour, while a target row counts every
   flash *inside* the hour. The pipeline pairs the predictor at time T with
   strikes in [T, T+1h), so the predictor describes the opening of the interval
   and the target describes the whole of it. Monthly and daily aggregation hid
   this question; hourly does not. It belongs in Bab III.

He chose hourly anyway, which is his call to make. **How this gets written up
matters.** An objection raised, heard, and overridden is a stronger position at
sidang than one never raised — but only if the record says it happened that way.
Bab III should carry the reason for hourly and these three costs together, not
the reason alone.

---

## D-15 — Spatial grid: 0,5°, boxes snapped outward

**Decided.** `GRID_DEG = 0.5`. Cell centres fall at multiples of 0,5° plus
0,25°. Each domain's bounding box is expanded outward to whole grid boundaries
by `Domain.snapped_bbox()`. Cell area is computed from the cosine of latitude,
so a Florida cell is correctly smaller than a West Java one.

**Why.** `config.py`: 0,5° "matches the predecessor study and the native NASA
POWER latitude resolution." Two reasons at once — comparability with the work
this TA positions itself against, and one fewer regridding step on the largest
predictor source.

The boxes themselves are "the observed extents of the supplied strike files,
snapped outward", with a standing instruction to re-check after adding data.

**What it costs.** Snapping outward is what produces the tropis zero rim. The
tropis box becomes 5 lat × 6 lon = 30 cells; subtropis 8 × 7 = 56 **[measured;
`n_cells` in both `.meta.json` files reads 30 and 56]**. Six of the 30 tropis
cells hold zero flashes across all seven years — 20% of the grid — and the
likelier reading is that the snapped box reaches past the LDS network's useful
range rather than that those cells are lightning-free. Four of the six are coast
around Jakarta and Cirebon, which is not a plausible zero. That is D-11's
problem.

0,5° also does not match either predictor grid natively: POWER is 0,5° × 0,625°,
AOD is 1°, ERA5 is 0,25°. Every join embodies a regridding choice.

**How to reverse it.** One value, but it invalidates every processed table and
every POWER point request, since `native_points` is derived from the snapped
box. Not free.

**Bab.** III.

**Who.** **Inherited, and the reason is confirmed:** 0,5° follows the
predecessor study and matches NASA POWER's native 0,5° latitude step — the two
reasons in `config.py`, both endorsed. The attribution itself predates the
recoverable chats and stays marked **inherited** rather than assigned to anyone:
it arrived with the proposal rather than being decided during this work. That is
the accurate record, and it is also the more useful one — an inherited value
with a confirmed rationale is defensible in Bab III without anyone having to
claim authorship of it.

---

## D-16 — Bin labelling: UTC, forced, at hourly resolution

**Decided.** `TZ_MODE = "utc"`. At `TIME_FREQ = "h"` the setting is ignored
entirely and forced to UTC in `lightning._bin_timestamps` and
`era5._bin_time`. The diurnal cycle is carried instead by an explicit
`hour_of_day_local` column.

**Why.** At monthly resolution the calendar was the domain's local one — a
"January" of West Java lightning should be January in Jakarta time — and seven
hours moved almost no strikes across a month boundary, so the choice was nearly
free. At hourly it stops being about which storms land in which bin, since an
hour is the same hour on either clock, and becomes about how the bin is
*labelled*. Every source has to agree on the label or the join silently produces
nothing. NASA POWER's hourly endpoint does offer local solar time, but LST is
longitude-derived and is not Asia/Jakarta, so UTC is the only convention all
four sources can honour.

**What it costs.** Nothing on the physics, because `hour_of_day_local` is
emitted separately and is a better representation of "3 p.m. local" than a
shifted bin label would be. It costs one obligation downstream: because bins are
UTC, a model without the local-hour column learns the UTC-to-local offset
separately per domain — which is exactly the domain-specific quirk the
cross-domain experiment exists not to measure. The modelling config calls
`hour_of_day_local` "the single most important feature you have." See D-02.

Subtropis uses `local_tz = "Etc/GMT+5"` rather than `America/New_York`,
deliberately: New York observes DST, which shifts the clock while the sun does
not move, and Asia/Jakarta is a fixed +7. A DST zone on one side would make the
diurnal feature mean something slightly different in each domain for half the
year.

**How to reverse it.** It is not reversible at hourly resolution — the force is
in the binning functions, not the config. It becomes live again at `"D"`.

**Bab.** III.

**Who.** Not established. The reasoning is written in `lightning.py`'s docstring
and `config.py`'s comment, both in my voice as far as I can tell, and I found no
exchange where you weighed in. Probably mine, unobjected.

---

## D-18 — The coverage gate is off: `MIN_COVERAGE = 0.0`

**Decided.** No month is excluded on coverage grounds. Every month holding at
least one strike record contributes a full complement of rows, however thin.
Months with no records at all are still excluded, by a separate mechanism, and
reported as `NO DATA for N months`.

**Why.** The negative case is fully argued in `config.py` and is the stronger
half. A 0,9 gate would delete 56 of 81 subtropis months and 26 of 84 tropis —
about 70% of Florida **[repo]**. Worse, it deletes *opposite halves of the year*
in the two domains: tropis thins in the JJAS dry season, subtropis in DJF
winter. The two training sets would no longer span comparable seasonal ranges,
and any cross-domain generalization gap measured afterwards would be partly an
artefact of the filter.

And the reason is not merely that 0,9 deletes too much. `coverage` conflates a
quiet sky with a dead detector. At 0,9 the quiet skies vastly outnumber the dead
detectors, so the filter discards hundreds of real observations to remove a
handful of false ones. It is the wrong lever.

The underlying proxy — a day with at least one strike somewhere in the domain is
a day the network was up — is sound over a month and useless over anything
shorter, because at sub-monthly resolution the thing it cannot distinguish is
exactly the thing being predicted. A quiet 3 a.m. hour and an offline detector
look identical. So the gate could only ever have been monthly.

**What it costs.** This is the pipeline's largest open exposure and it should be
stated as such. A month observed on 6 of 31 days still emits 744 hourly rows,
and the ~600 hours inside the 25 unobserved days become rows asserting "no
lightning here". They are not observations of zero; they are absences of
observation wearing a zero, and against a 94–97% zero target they are invisible
in aggregate and impossible to distinguish downstream.

The exposure is also **asymmetric between the domains**, which matters more than
its size. In West Java a day with zero CG strikes across the whole province is
close to meteorologically impossible, so a zero-strike day there is much more
likely to be an outage. In Florida in January a genuinely quiet day is entirely
plausible. The same setting therefore encodes a different assumption in each
domain, and the difference lands in the cross-domain gap the TA exists to
measure.

Day-coverage as built, **row-weighted over the rows actually in the table
[measured]**: tropis mean 0,8549, min 0,1290; subtropis mean 0,5921, min 0,0323.
So **85%** and 59% mean, 13% and 3% minimum.

Two notes on those figures. An earlier draft said 86% for tropis; the measured
value rounds to 85%, and the measured one is correct — the build-of-record table
at the top of this file carries the corrected figure. And these are
**row-weighted**, not per-month; the earlier 86% / 59% figures were probably
month-weighted. Say which in Bab IV. Row-weighted is arguably the better
statistic here, because this entry's reporting obligation is about the rows the
model actually trains on.

`.meta.json` does *not* carry `mean_day_coverage` or `min_day_coverage`. It
holds `n_rows`, `zero_target_share` and `n_cells`. The coverage figures come
from the `coverage` column of the built parquet:

```python
df = pd.read_parquet("data/processed/gfd_tropis_hourly.parquet",
                     columns=["coverage"])
df.coverage.mean(), df.coverage.min()
```

**How to reverse it.** One value. But the right instrument is not this lever at
all: periods known to be instrument gaps should be excluded **by date**, which
is what D-26 already does for the three lost MERLIN months. The general
version — a real observation record built from METAR, for both domains — is open
question 18 and is not built.

**Bab.** III for the setting, IV for the coverage distribution over the rows
actually trained on, beside the zero share.

**Resolving the internal tension.** `config.py` and `RUNBOOK.md` each carry two
positions in the same passage: mitigation 1 says "filter or weight on `coverage`
at modelling time and record the threshold (F-05)", and a later paragraph
concludes the gate "is the wrong lever". These are formally about different
levers — a build-time gate and a modelling-time weight — but the objection
transfers. `coverage` is correlated with the target through lightning activity
itself, so down-weighting low-coverage rows preferentially removes low-activity
periods and inflates apparent performance. That is the same reason `coverage`
sits in `EXCLUDE_COLUMNS` under D-10; using it as a weight reintroduces the
problem through a side door.

**This record resolves the tension toward reporting, not acting.** Report the
distribution of `coverage` over the rows actually trained on. Do not filter or
weight on it. The honest framing is that observation coverage and target
magnitude cannot be separated with the data available — a limitation, not a
preprocessing step. Both source files still carry both positions; see
outstanding items O1 and O2.

**Who.** Split, and worth recording accurately. I read `MIN_COVERAGE = 0.0`
as a bug when I first found it and said the value looked wrong against every
other statement in the repo. You kept it. The argument now written in
`config.py` for why 0.0 is correct — the seasonal asymmetry, the wrong-lever
framing — is mine, developed afterwards to justify your call. **The decision is
yours; the reasoning is mine.** If that is not how you remember it, this is the
entry to correct first.

---

## D-19 — Empty cells are filled with explicit zeros

**Decided.** `aggregate_gfd(fill_empty_cells=True)` builds a full
cell × period skeleton and inserts explicit `flash_count = 0` rows.

**Why.** Dropping them would quietly train the model on "periods that had
lightning", which raises the mean of the target and makes R² look better than it
is. Rafly's own statement of the same point: don't let the model predict
lightning where there wasn't any. **This is the argument the decision rests on,
and it holds whatever the detector was doing.**

**A second justification was remembered, and it must not be used.** Rafly
recalls having also justified the fill as *assuming no sensor error* — that a
zero in the table is a real observation of no lightning. **D-18 contradicts that
directly, on this project's own measurements.** With the coverage gate off,
row-weighted day-coverage reaches a tropis minimum of 12,90%: there are months
in the built table observed on roughly one day in eight, and every unobserved
hour inside them is a filled zero that is an absence of observation rather than
an observation of absence.

So the fill is correct, but not for that reason. **Bab III should give the
target-mean argument only.** The sensor-error version would be a claim this
project has already measured and disproved about its own data, and D-18 sits a
few pages away saying so.

**What it costs.** The skeleton is the memory high-water mark of the build; the
code prints a warning above 2.000.000 rows. And the fill interacts with D-18:
zeros inside a thinly-observed month are indistinguishable from zeros inside a
well-observed one.

**The scope of the fill is deliberately limited, and this is the part to get
right in Bab III.** Filling is done only over periods the raw data actually
covers — `_time_index` builds from the months that survived the coverage step,
so a month with no records contributes no rows at all, neither one monthly row
nor 744 hourly ones. Filling the whole configured year range instead would
invent zeros for stretches with no data whatsoever, which is not a quiet
inaccuracy: it hands the model rows whose target is zero for reasons that have
nothing to do with meteorology. The three lost MERLIN months are excluded on
this mechanism, not zero-filled — see D-26.

**How to reverse it.** The argument is a parameter, but every caller uses the
default and the smoke tests pin it explicitly.

**Bab.** III.

**Who.** **Rafly's, by recollection.** It predates the recoverable chats, so it
cannot be confirmed or contradicted from the record — it rests on his memory and
is marked as such rather than presented as established. The justification
currently in `RUNBOOK.md` is mine, written afterwards; the sensor-error
justification he also remembers is retracted above.

---

## D-20 — Zero inflation is carried and reported, not engineered away

**Decided.** The zero share is accepted as a property of the target at hourly
resolution. It is measured at build time, printed, stored in `.meta.json` as
`zero_target_share`, and reported beside every R². No build-time rebalancing.

**Measured, build of 2026-09-06: 94,30% tropis, 97,00% subtropis** **[repo,
stated identically in `config.py`, `RUNBOOK.md` and the modelling config]**.

**Why.** Two consequences follow and both are reporting obligations rather than
modelling problems.

1. **R² is close to meaningless on this target.** Predicting zero everywhere
   already explains most of its variance. So report the zero share beside every
   R², and beat a trivial baseline — the cell's climatological hourly rate —
   before claiming the model learned anything. `metrics.regression_metrics`
   takes a `baseline` argument for exactly this and every metric table carries
   it, because an R² without the floor is uninterpretable rather than merely
   incomplete. See D-07 and D-12.
2. **NF-01 (R² > 0,9, NRMSE < 0,1) is unreachable at this resolution**, and not
   because of the model. It was already in tension with the only comparable
   published result at *monthly* resolution. This is a target-renegotiation
   conversation with the pembimbing, not a modelling problem to solve. D-12
   carries the decision.

**What it costs.** Sample size grows without the informative count growing. A
uniform subsample of a 94–97%-zero target is almost all zeros, so you end up
with a few thousand training rows again drawn from a noisier distribution. Say
which *n* you mean: neither the strike count nor the raw row count is the number
that matters for training.

**Correcting ">99%".** Earlier comments across the repo estimated the zero share
at ">99%" and were too high. The conclusion is unchanged, but the correction is
material: 104.955 non-zero tropis cell-hours and 99.273 subtropis **[repo]** is
considerably more signal than ">99%" implies, and it is why stage 2 of the
hurdle model is tractable without aggressive subsampling. Non-zero counts run
**1..2.391 tropis and 1..11.777 subtropis [measured]**. The last stale copy of
">99%" was fixed at `lightning.py:308` — applied item A1.

**How to reverse it.** Not a reversible setting — it is a property of the data
at `TIME_FREQ = "h"`. It changes if D-21 changes.

**Bab.** III for the measurement, IV for reporting it beside every metric, and
IV or the penutup for the NF-01 renegotiation.

**Who.** Mine, throughout — the measurement, the baseline requirement, and the
NF-01 argument. You have not objected, but you have also not endorsed the NF-01
position anywhere I can see, and it is the one that will surface at sidang.

---

## §4 — Target and preprocessing

## D-03 — The fitting target is `log1p(flash_count)`; reporting is in GFD units

*Merged. The modelling record and the batch 1 draft both had an entry on this
subject; both texts are folded in here.*

**Decided.** Two different columns for two different jobs.

- `config.TARGET_COLUMN = "gfd_per_km2_per_year"` — the **reporting** unit, kept
  so the hourly, daily and monthly builds share a scale and so numbers can be
  set beside the predecessor's.
- `mcfg.COUNT_COLUMN = "flash_count"` with `TARGET_TRANSFORM = "log1p"` — the
  **fitting** target. Inverted with `expm1` and converted to GFD units for every
  reported number.

`gfd_per_km2_per_year` is never a fitting target at hourly resolution.

**Why.** `gfd_per_km2_per_year = flash_count / area_km2 / period_days × 365,25`,
and `period_days` is 1/24 for an hour. So annualising a single hour inflates one
flash by 365,25 × 24 = 8.766× **[derived; matches the constant `HOURS_PER_YEAR`
in `metrics.py`]**. The result is a count process wearing a density's units, and
its non-zero values form a spike-or-zero distribution that no squared-error
optimiser handles well. `build.py` prints this warning at run time.

`flash_count` is the honest hourly quantity. The log transform compresses a
range that runs 1..2.391 in tropis and 1..11.777 in subtropis.

The reporting column is kept rather than dropped because it is the unit the
thesis speaks in, it is comparable across the three builds, and it is what the
predecessor used.

**What it costs.** An ordering obligation that is easy to get wrong silently,
and a systematic bias.

*Order.* Predictions come out of the model in standardised log space and must be
un-standardised, then `expm1`'d, and only *then* summed. **Never sum in log
space** — summing `log1p` values and inverting once gives a geometric mean, not
a total. `metrics.aggregate_windows` therefore refuses to guess and demands raw
counts. This matters directly for D-04.

*Bias.* Fitting MSE on `log1p(count)` gives the conditional mean in log space;
`expm1` of that is median-like and by Jensen's inequality sits below the
conditional mean of the count. So inversion under-predicts. Measured on tropis
fold 2, mean predicted 6-hour GFD was 0,37 to 0,45 of mean observed across every
model on the ladder, which is what identifies it as the transform rather than
the model **[repo, `metrics.py`]**. The one-parameter Duan smearing estimator
corrects it, fitted on validation and never on test.

`gfd_per_km2_per_day` is also in the output, for direct comparison against the
predecessor's numbers — though note he reports his target as km⁻¹day⁻¹, which is
not a density unit at all, since a flash density is per area per time. Define
the unit explicitly in Bab III. Any such comparison must be run at
`TIME_FREQ = "M"`.

**How to reverse it.** `TARGET_TRANSFORM` accepts `"anscombe"` and `"none"`.
Moving the fitting target back to the GFD column would mean removing
`flash_count` from `EXCLUDE_COLUMNS` on one side and adding it on the other;
they have to move together.

**Bab.** III for the definition and the unit, IV for the calibration factor.

**Who.** Mine. `build.py`'s runtime warning and the RUNBOOK paragraph are both
my text; I have no record of you disagreeing.

---

## D-08 — Intensity is built into the pipeline, used later

**Decided.** `aggregate_gfd` emits `mean_peak_current_ka`, `positive_share`,
`median_abs_peak_current_ka`, `max_abs_peak_current_ka` and
`p95_abs_peak_current_ka`, and `build_domain` carries them into the processed
table. Whether they are modelled is a separate decision.

**Why build them now.** Recovering them later means a full rebuild of both
parquets. Building them cost tens of seconds. The first two were already
computed by `aggregate_gfd` and were being dropped by `build_domain`'s column
selection.

**Statistics chosen.** The signed mean is kept because polarity is physically
meaningful. The spread statistics use absolute value: a cell-hour holding one
+40 kA and one −40 kA strike has a mean near zero and a median magnitude of 40,
and the second number is the useful one. The median is the headline rather than
the mean because CG peak current is heavy-tailed and the mean of a handful of
strikes is dominated by the largest.

**They are leakage for the GFD task.** All five derive from the same strike
records as the target. They are in `cfg.EXCLUDE_COLUMNS` and must never be
predictors for GFD.

**The NaN structure defines the experiment.** They are NaN wherever
`flash_count == 0` — the mean intensity of no strikes is undefined, not zero.
Verified in the build: 0 zero-rows carry any intensity value, and 100% of
non-zero rows carry all five statistics, in both domains.

### RESOLVED 2026-09-06: MERLIN's `Signal Strength` is kA

The argument is the upper tail, not the median. Tropis maxes at 520 kA and
subtropis at 551,3. Peak CG current has a physical ceiling near 500 kA, and two
independently operated networks agreeing within 6% of it is not an artefact of
an arbitrary sensor unit. Same shape of argument as the one that settled the
PLN timezone in D-17: physics, not labelling.

### Which makes the median gap a detection-efficiency finding

Per-cell-hour median absolute peak current:

| | median | IQR | max |
|---|---|---|---|
| tropis | 19,5 kA | 13,5–27,5 | 299 |
| subtropis | 36,9 kA | 23,05–60,65 | 537 |

Tropis sits squarely in published negative-CG climatology. Subtropis is roughly
double. Florida CG is somewhat stronger than tropical average, not 2× stronger.
MERLIN loses low-amplitude strikes, truncating the bottom of the distribution
and dragging the median up — the same mechanism as the −0,955 distance
gradient. **Cross-domain intensity comparison therefore measures MERLIN's
sensitivity floor as much as Florida's meteorology.** State this before any
intensity result. See D-27.

### `positive_share` is dominated by singleton cell-hours

Mean 0,195 tropis and 0,102 subtropis; medians 0,011 and 0,000; against
record-level figures of 14,1% and 5,7%. A cell-hour containing exactly one
positive strike scores 1,0. As an unweighted per-row target it is mostly noise
about how many strikes landed that hour. Weight by `flash_count` or apply a
minimum-count threshold before using it.

**Bab.** III for the columns, Bab IV for the units argument and the
detection-efficiency bias.

**Who.** Not recorded in the modelling record.

---

## D-02 — Feature set is 13 base predictors, with the hour encoding as an axis

**Decided.** `cfg.FEATURE_COLUMNS` minus `KX` gives 13. On top of that,
`hour_of_day_local` is included by default, cyclically encoded as
`sin(2πh/24)`, `cos(2πh/24)` — so the default running configuration is **15
columns**. The encoding is a config value, and 13 / 14 / 15 is one of the
one-factor-at-a-time sweeps.

**Why.** Time bins are UTC (`TZ_MODE` is forced to `"utc"` at hourly
resolution — D-16). Without a local-hour feature, a model must learn the
UTC-to-local offset separately for each domain — precisely the domain-specific
quirk the cross-domain experiment exists not to measure. Leave it out and the
cross-domain gap is partly a measurement of a clock. Cyclic encoding is used
because hour 23 and hour 0 are adjacent and a raw integer asserts they are 23
apart.

**Cost.** The cyclic encoding spends two columns where one would do, and on the
QNN each column is a qubit. That is why it is a sweep axis rather than a silent
default — the 13/14/15 comparison measures whether the second qubit earns its
place.

**Never predictors, at any setting.** `year` (worse than useless under a
chronological split — every test row carries a value never seen in training),
`days_in_month` (bookkeeping), `flash_count`, `gfd_per_km2_per_day`,
`gfd_per_km2_per_year` (the target and deterministic functions of it), `domain`
(a free giveaway in the cross-domain experiment), `coverage`, `observed_days`
(see D-10), `area_km2`, `period_days`, and every column in `INTENSITY_COLUMNS`
(see D-08). Enforced by `cfg.EXCLUDE_COLUMNS`.

**Bab.** III for the feature list, Bab IV for the sweep result.

**Who.** Not recorded in the modelling record.

---

## D-11 — All-zero cells are identified before any split

**Decided.** Cells with zero flashes across all seven years are identified and
their handling is recorded. Under a cell-holdout split they must not fall
entirely into test.

**Why.** Six tropis cells — 20% of the 30-cell grid — hold zero flashes across
the whole record. The southern pair is Indian Ocean. The northern four are the
coast around Jakarta and Cirebon, which is not lightning-free, and the fifth
cell in that row does carry flashes; the likelier reading is that the snapped
box reaches past the LDS network's useful range, giving tropis an artificial
zero rim. Under a cell split these six could land entirely in test, where a
model would score perfectly on them for the wrong reason.

**A land mask would not fix the subtropis gradient.** 30,25 / −81,25 is over
land and carries 6.968 flashes against 437.287 at 28,75 / −81,25.

**Dropping all-zero cells is defensible preprocessing.** `DROP_ALL_ZERO_CELLS`
is `False` by default so the choice stays visible. If taken, record it here and
in Bab III. Open question 15.

**Bab.** III if cells are dropped, Bab IV either way.

**Who.** Not recorded in the modelling record.

---

## D-35 — Feature scaling: min-max onto [0, π], clipped, fitted on train alone

**Decided.** `FEATURE_RANGE = (0.0, π)`, `CLIP_TEST_FEATURES = True`,
`STANDARDISE_TARGET = True`. One `Scaler` serves both arms. It is fitted on the
**training rows only** and then applied to validation and test.

**Why clipping is a correctness measure, not a convenience.** This is the part
to lead with. A test value above the training maximum maps past π, and a
rotation past π **aliases back onto a different angle**. The model does not
raise, does not warn, and does not produce an obviously bad number — it returns
a confident wrong answer for that row. Clipping converts a silent wrong answer
into a saturated one, which is the failure mode you can reason about.

**Why [0, π] specifically.** Angle encoding needs a bounded range; an MLP is
indifferent to it. So the interval is chosen for the quantum arm and the
classical arm accepts it, which is the correct direction for the constraint to
flow under D-09.

**Why one scaler.** D-09 requires the only difference between the arms to be
the layer. Different preprocessing would be a second difference, and it is
exactly the kind an examiner asks about. **D-09 covers this only by
implication** — it says "same optimizer, batch size, loss, early stopping, seed
handling" and does not name the scaler. This entry is that gap closed.

**Target standardisation** happens after D-03's `log1p`, so both models see a
comparable loss surface, and is inverted before any reported number.

**What it costs.** Two asymmetries worth knowing about.

*Training is not clipped; validation and test are.* `prepare()` calls
`scaler.transform(Xtr, clip=False)` and clips everywhere else. That is
consistent — the scaler's range is *defined* by the training rows, so nothing
in training can fall outside it — but it means the clip path is exercised only
on data the model is judged on.

*Constant columns are mapped to the bottom of the range.* A column with
`hi <= lo` would divide by zero and produce NaN for every row; `fit()` sets
`hi = lo + 1` instead. Silent, and correct, but it means a degenerate feature
becomes a constant 0 rather than an error.

**How to reverse it.** All three are config values. `FEATURE_RANGE` is not
freely reversible — the quantum arm needs a bounded range whatever else changes.

**Bab.** III, preprocessing subsection, with the aliasing rationale stated. It
is a better sentence than "features were scaled to [0, π]".

**Who.** Not recorded.

---

## §5 — Experimental protocol

## D-04 — Train hourly, aggregate the predictions to a reporting window

*Merged. The modelling record and the batch 1 draft both had an entry on this
subject; both texts are folded in here.*

**Decided.** `REPORTING_WINDOWS_H = (1, 3, 6, 24)`, `PRIMARY_WINDOW_H = 6`. The
model predicts one cell-hour; these aggregate predictions afterwards. The window
is a reporting choice applied after inference, not a change to the dataset.
Training stays hourly.

**The ladder is the result. The 6-hour headline is a nomination, not a derived
optimum** — no selection criterion was applied to it. See "Who" below, and state
it that way in Bab IV.

**Why.** The hourly build exists because ERA5 and NASA POWER are hourly, and
because the diurnal cycle is a first-order physical signal that aggregating the
*inputs* would destroy. Nothing forces the *reporting unit* to also be hourly.

**1. The zero problem softens; it does not dissolve.** MEASURED against the
build of 2026-09-06. This corrects an earlier estimate that assumed independent
hours and was badly wrong.

| Window | Tropis zeros | Subtropis zeros |
|---|---|---|
| 1 h | 94,30% | 97,00% |
| 3 h | 90,09% | 94,52% |
| 6 h | 85,40% | 91,35% |
| 24 h | 64,63% | 76,63% |

Under independent hours a 6-hour tropis window would be 70,33% zeros. It is
85,40%. Convection clusters in time: solving 0,943ᵏ = 0,8540 says a 6-hour
window behaves like **2,69 independent hours** in tropis and **2,97** in
subtropis; a 24-hour window like **7,43** and **8,74**.

Subtropis is measurably LESS clustered than tropis — Florida sea-breeze cells
fire and die inside the afternoon where West Java's convection persists. That
contrast is a physical difference between the domains rather than an
instrumental one, and it belongs in Bab IV as ballast alongside the
detection-efficiency problem in D-27.

The gain is real but modest: 24-hour tropis reaches 35,37% non-zero against
5,70% hourly, a factor of 6,2.

**Aggregation changes the REPORTING target only.** Training remains hourly and
remains 94,30% / 97,00% zeros. Do not claim otherwise. This is why D-13 exists.

**2. R² becomes interpretable at the wider windows**, where variance stops
being dominated by zeros. At 6 h it is still marginal.

**3. The window is a free test axis.** One trained model, four aggregations,
one skill-versus-reporting-window curve.

**4. The 24-hour tropis dataset is 76.710 rows** — small enough to hand a QNN
almost whole, which relaxes D-07's subsampling considerably.

**5. It matches the operational question.** "GFD over the next six hours for
this cell" is a statement a protection engineer can use. "GFD for the hour
beginning 14:00 UTC" is not.

**Cost, and it is real.** Summing predictions is unbiased only if the model is
calibrated. A model under-predicting by 10% per hour under-predicts the 6-hour
total by 10% — the error accumulates rather than cancelling. So `calibration()`
reports the predicted/observed ratio beside every windowed result, and the D-03
smearing correction becomes load-bearing rather than cosmetic.

Aggregation also constrains test sampling upstream: `TEST_DAYS` samples whole
days evenly spaced across the test year rather than random rows, because random
rows leave partial windows.

Windows are formed by floor-and-group rather than by resampling, so the three
excluded MERLIN months (D-26) are not invented and scored as zeros.

**Rejected alternative.** Aggregating *before* training (building 6-hourly rows
by summing counts and averaging predictors) discards the within-window diurnal
structure the hourly build was paid for, and forces a choice of daily statistic
per predictor that hourly resolution otherwise removes from the thesis.

**How to reverse it.** Both constants are config values and the metric runner
takes an explicit `windows` argument.

**Bab.** III for the mechanism, IV for the window curve and the clustering
contrast.

**Who.** Mine, in the modelling rewrite — and **the primary-window choice is
unjustified.** No criterion for preferring 6 hours to 3 or 24 is recorded in
`config.py`, in `metrics.py`, or in any recoverable chat, because none was
applied. It was a default I set and nobody challenged.

**Recorded as a nomination rather than a derivation.** The 1/3/6/24-hour curve
is the result; 6 h is nominated as the headline figure for readability, and
nothing in the analysis depends on the nomination — every window is reported and
a reader can take any of them as the headline instead.

Write it that way in Bab IV. "Six hours was selected as the operationally
relevant window" is a claim the record cannot support, and it invites precisely
the question at sidang that the honest version does not. The honest version
costs nothing here, because the whole curve is on the page.

If a criterion is ever wanted, it would have to come from outside this record —
a lightning-warning lead time from a standard or from PLN's own operational
practice would justify a specific window. That is a new decision, not a
reconstruction of this one.

---

## D-06 — Rolling-origin cross-validation across years, not one held-out year

**Decided.** Three folds, always training on the past and testing on the future:

| Fold | Train | Test |
|---|---|---|
| 1 | 2018–2021 | 2022 |
| 2 | 2018–2022 | 2023 |
| 3 | 2018–2023 | 2024 |

Results are reported as mean ± standard deviation across folds. Rolling origin
is used for the default configuration and the headline QNN-versus-NN
comparison; the one-factor-at-a-time sweeps use fold 3 alone, to keep the
compute affordable. **State this asymmetry in Bab IV** — it is a defensible
allocation, but only if declared.

**Why, and what it does not fix.** A single held-out year makes the headline
number hostage to one year's climate state, and 2018–2024 is not climatically
uniform: it contains a triple-dip La Niña (2020–2023) and a strong El Niño
peaking in the 2023–24 boreal winter. ENSO is a first-order driver of tropical
convection over Indonesia, so 2024 alone is a poor summary of the record.

**The solar-cycle limitation, stated honestly.** An approximately 11-year
modulation of thunderstorm activity by the solar cycle — via sunspot number and
galactic cosmic ray flux — appears in the literature. This record cannot test
it. Solar cycle 24 bottomed out around late 2019 and cycle 25 climbed toward a
maximum around 2024–25, so 2018–2024 spans roughly **half a cycle,
monotonically**. Three consequences:

1. No split can resolve an 11-year period in a 7-year record. Rolling-origin CV
   does not fix this and is not claimed to.
2. A monotonic solar trend is perfectly confounded with everything else that
   trends monotonically over the same window — ENSO phase, LDS network
   upgrades, urbanisation, MERLIN sensor changes. Not separable by any method
   with this data.
3. 2024 sits at the extreme end of that trend, an additional reason not to rest
   the headline result on it alone.

Write this as *a possible source of interannual variability this record cannot
resolve*, not as established physics. Reported effect sizes for solar
modulation of lightning are small and the literature is contested;
overclaiming invites a question at sidang that cannot be answered from these
data.

**Cost.** 3× compute on the headline runs — the largest single compute cost in
the project.

**Bab.** III for the protocol, Bab IV for the limitation.

**Who.** Not recorded in the modelling record.

---

## D-07 — Training rows may be reshaped; test rows may not

**Decided.** The test set is the fold's held-out year, whole, at its natural
class ratio, never resampled. The training set is subsampled — uniformly at
random, stratified across cell and month so a subsample cannot come out all
Jakarta and all December. The zero-to-non-zero ratio of the *training* set
(natural / 75% / 50%) is one OFAT axis.

**Why subsample at all.** Tropis is 1.841.040 rows and subtropis 3.314.304. A
13-qubit `real_amplitudes` ansatz at 4 reps has 65 trainable parameters;
parameter-shift gradients cost 2 circuit evaluations per parameter per sample,
so 130 evaluations per sample per step. At an optimistic 1 ms per statevector
evaluation, one epoch over 10.000 samples is roughly 20 minutes — and the
matrix needs dozens of epochs across dozens of configurations across five
seeds. The full table is four orders of magnitude out of reach. A design
constraint, not a tuning problem.

**Correction — the arithmetic above describes a run that was not made.** It
assumes 13 qubits at `ANSATZ_REPS = 4`, giving 65 weights, and an optimistic
1 ms per statevector evaluation. The reported runs use **15 qubits at reps = 2**
— 45 weights, per `qnn.py`'s `(ANSATZ_REPS + 1) × per_layer` — at a **measured
6,97 ms** per sample on the backend actually used (D-28). Both configurations
are legal; 13/4 is a corner of the `ansatz_reps` sweep, not the default.

The two errors do not point the same way. **The weight over-count partially
offsets the timing optimism**: 65 × 2 evaluations at 1,00 ms gives 130 ms per
sample, against a real 45 × 2 at 4,87 ms giving 438,70 ms on Qiskit
parameter-shift. Net, this entry **underestimates by 3,4×** **[derived]**.

**The design constraint stands and is if anything stronger** — the full table is
further out of reach than the paragraph says, not nearer. Only the illustrative
numbers are wrong. Quote D-28's measured figures in Bab III rather than these.

**D-13 changes the arithmetic favourably.** Stage 2 trains on non-zero rows
only: 104.955 tropis and 99.273 subtropis. Both are within reach without
aggressive subsampling. Stage 1 still faces the full table.

**Why the asymmetry.** Rebalancing training data is a legitimate technique.
Rebalancing test data produces a number evaluated against a world that does not
exist. Same mechanism as D-10: any reweighting correlated with the target
inflates apparent performance.

**Metrics that survive the imbalance.** RMSE alone is dominated by zeros.
Report MAE alongside, and report a zero/non-zero classification view
(precision, recall, F1, AUC) beside the regression metrics. Always report the
trivial baselines — predict-the-mean and predict-zero-everywhere — because
against a 94–97% zero target those already explain most of the variance and no
R² is interpretable without them.

**Bab.** III for the protocol, Bab IV for the ratio sweep.

**Who.** Not recorded in the modelling record.

---

## D-13 — The default task is a hurdle model, not single-model count regression

**Decided.** `TASK` is a config value taking `"hurdle"`, `"count"` or
`"occurrence"`, defaulting to `"hurdle"`.

- **Stage 1, occurrence.** Binary: did any lightning occur in this cell-window?
- **Stage 2, intensity-given-occurrence.** Regress `log1p(flash_count)` on
  non-zero rows only.
- **Reporting.** Expected count = P(occurrence) × E[count | occurrence],
  converted to GFD units per D-03.

**Why.** The measured window curve in D-04 killed the assumption that a wide
reporting window would make single-model count regression well-conditioned. At
6 hours the target is still 85,40% / 91,35% zeros.

**What it buys.** Stage 1 at a 24-hour window is a 35/65 split in tropis — the
first well-conditioned learning problem in this project. Stage 2 runs on
104.955 tropis and 99.273 subtropis rows, both QNN-tractable without aggressive
subsampling. Stage 1 yields F1 and AUC, which unlike RMSE and R² are not
hostage to the zero share. A hurdle model is the standard treatment for
zero-inflated counts, so it needs no defending.

**Cost.** Two models per configuration instead of one, so the experiment matrix
doubles. `"count"` remains available so the single-model comparison is still
runnable if a reviewer asks for it.

**Bab.** III for the formulation, Bab IV for the stage-wise results.

**Who.** Not recorded in the modelling record.

---

## D-38 — Sampling mechanics: stratified, largest-remainder, stage-filtered first

**Decided.** Three mechanical choices inside `dataset.py`, each of which was a
bug before it was a decision.

**Stratified draws, not uniform.** `STRATIFY_BY = ("lat", "lon",
"month_of_year")`. An unstratified draw from a table with a strong seasonal
cycle and a 20% dead rim (D-11) is not a miniature of the whole — it can come
out "all Jakarta and all December".

**Largest-remainder allocation.** Per-stratum counts are floored, then the
remainder is handed to the strata with the largest fractional parts, so the
draw sums to **exactly** n rather than to n ± the number of strata.

**Stage filter before the validation cap, not after.** `prepare()` applies
`stage_rows()` to train, validation and test, and only then caps validation to
`MAX_VAL_ROWS`.

**Why the ordering matters, measured.** The other order caps to 1.000 rows and
*then* drops zeros, which left the count stage with **112 validation rows** —
far too few to early-stop on. The comment in `prepare()` records this as the
reason the two lines are in this order, which is the only thing stopping someone
from "tidying" them back.

**What it costs.** Stratification is not free at scale, and the strata are
defined by columns that must exist in the frame — `_stratified_draw` falls back
to an unstratified sample if none of `STRATIFY_BY` is present, silently. That
fallback has never fired, but nothing announces it if it does.

**How to reverse it.** `STRATIFY_BY` is a config tuple. The ordering is
structural and should not be reversed.

**Bab.** III, sampling subsection. The 112-row figure is worth keeping — it is
concrete evidence that the ordering is load-bearing rather than stylistic.

**Who.** Not recorded. All three read as fixes made during implementation.

---

## D-36 — Every model carries its own scaler, and cross-domain uses the source's

**Decided.** Two rules that interact.

**Each arm keeps its own `Prepared`.** `fit_models` stores `preps[name]` per
model and `evaluate` uses that model's scaler, not a shared one.

**Cross-domain evaluation transforms the target domain's rows with the scaler
fitted on the SOURCE domain.** Target rows are loaded once, unscaled, and each
model applies its own transform.

**Why the source scaler.** Re-fitting on the target would leak target statistics
into a model that must never have seen them. A cross-domain result computed that
way measures a model that has already been told the answer's range.

**Why per-model scalers — and this was a real bug.** `nn_full` trains on every
row (D-34), so its scaler is fitted on ~2,4M rows while every other arm's is
fitted on 3.000. Evaluating `nn_full` through the shared 3.000-row scaler
shifted every test feature. Symptom: validation losses healthy at 0,08–0,22
against a test log loss of 0,2867. **After the fix `nn_full` went from worst to
best in 5 of 8 cells.**

**What it costs.** A consequence worth stating rather than correcting away: for
a cross-domain scenario the D-03 smearing factor also comes from the **source**
domain, so it does not fix a target-scale mismatch. The residual gap that leaves
is a **transfer finding**, not an artefact. Say so in Bab IV — the temptation is
to fit the factor on the target and make the number look better.

**How to reverse it.** Structural. Reversing either rule reintroduces a
documented bug.

**Bab.** III for the protocol, IV for the residual cross-domain gap.

**Who.** Not recorded. Both read as fixes made during implementation.

---

## D-29 — The compute budget, and the two-tier split it forces

**Decided.** `TRAIN_ROWS = 3.000`, `MAX_EPOCHS = 30`,
`EARLY_STOPPING_PATIENCE = 6`, `SEEDS = (0, 1, 2)`, `MAX_VAL_ROWS = 1.000`,
`VAL_FRACTION = 0.15`, `TEST_DAYS = 30`. Sweeps override to 1.000 rows,
15 epochs, `TEST_DAYS = 20`, one seed, one fold (D-37).

**Why these values.** The budget is one night for the final set, and the numbers
are solved backwards from it. 36 QNN runs — 2 stages × 2 domains × 3 folds ×
3 seeds — at ~18 min each is ~11 h. `config.py` records what each rung cost:
**4.000 rows × 30 epochs was ~70% of the whole budget**; 3.000 brings it under a
night. **Five seeds would not fit.** `MAX_EPOCHS` at 50 is 14,4 h against 30 at
8,7 h.

`MAX_VAL_ROWS = 1.000` is the one that is not obvious. The quantum layer costs
~7 ms per row, so **evaluation is a first-order cost, not a rounding error**: a
full 236.610-row validation set costs **27 minutes per epoch against 7 seconds
of training**. Validation exists only to decide when to stop, and a few thousand
rows estimate the loss well enough for that.

**What it costs.** Three seeds is the minimum that supports a mean ± sd at all,
and D-14 shows why it is also the minimum that is safe — a single-seed sweep
produced a textbook sample-efficiency crossover that three seeds erased
completely.

`estimate_budget()` in `experiments.py` is the honest version and carries three
corrections that each mattered: training, validation **and** test inference are
all first-order at ~7 ms/row (an earlier projection counted training only and
understated by ~3 h); cell counts differ by domain, 30 against 56; and the count
stage evaluates on non-zero rows only, so its test set is ~1/20 of the
occurrence stage's. It is a **worst case** assuming every run reaches
`MAX_EPOCHS`; observed early stopping fires between epochs 11 and 28, so expect
~70%.

**How to reverse it.** All config values. Raising any of them is a linear cost;
the budget is the constraint, not the code.

**Bab.** III for the protocol, IV where the seed and fold counts are declared.

**Who.** Not recorded. The trade-offs are documented in `config.py`; the choice
of one night as the budget is not attributed anywhere.

---

## D-30 — Equal optimizer steps per epoch, so the shared loop is actually fair

**The headline of this batch.** It is the entry most likely to change what gets
written in Bab IV, because the pre-fix version produced a result that looked
like a finding.

**Decided.** `training.fit` caps optimizer steps per epoch at
`ceil(TRAIN_ROWS / BATCH_SIZE)` — about 47 steps — for **every** arm, whatever
size its training set is. A large-data arm draws each batch from a bigger pool
and the shuffle means it still sees new rows every epoch, but its **budget** is
identical to everyone else's.

**Why. Without the cap, the comparison was broken and the breakage looked like a
result.** `nn_full` trains on ~2,4M rows. At batch 64 that is roughly 28.000–
38.000 optimizer steps in a single epoch, against ~47 for the 3.000-row arms —
**about 35× the training budget**. Early stopping only acts at epoch boundaries,
so `nn_full` had run far past its optimum before validation was checked even
once, at a learning rate tuned for the small arms.

**The pre-fix number was misleading, not merely wrong.** `nn_full` scored
**below the trivial floor** on subtropis occurrence — 0,2867 against 0,1228.
Read at face value that says **"more data hurts"**, which is a publishable-
sounding claim about where QNNs and classical models stand. It is false. What it
actually says is **"the shared loop gave one arm 35× the budget at a learning
rate tuned for the others."** That number could have entered Bab IV as a
finding, and it would have been wrong in a way no reader could have caught from
the results table.

**What the fix makes true.** D-09 claims the only difference between arms is the
layer, and lists optimizer, batch size, loss, early stopping and seeds as the
things held equal. **Step count was not on that list and was not equal.** The
cap is what converts D-09 from an intention into an enforced property. Without
it the central comparison of the thesis is not the comparison it says it is.

The framing to use: **same budget, more data.** That is the question `nn_full`
is there to answer, and it is only answerable once the budget is genuinely the
same.

**What it costs.** `nn_full` no longer uses its data advantage the way an
unconstrained run would — it sees more distinct rows but takes no more steps. So
the arm measures "more data at a fixed optimisation budget", not "more data with
proportionate compute". That is the honest comparison here, but it is a narrower
claim and Bab V should say which one it is making.

**How to reverse it.** `max_steps` is computed in `training.fit`, not
configurable. Removing it reintroduces the bug.

**Bab.** III, as a design choice with its measured justification. `RUNBOOK.md`
already marks it *Bab III material* and it is.

**Who.** Not recorded. It appears as bug 7 in the modelling RUNBOOK's defect
list — found during implementation, not planned.

---

## D-37 — Sweep protocol: one fold, one seed, shorter runs, config mutated in place

**Decided.** `run_sweep` runs one-factor-at-a-time around the defaults:
`SWEEP_FOLD = 2` (fold 3, test 2024), **one seed**, `max_epochs = 15`,
`train_rows = 1.000` except on the `train_rows` axis itself, and
`TEST_DAYS = 20` instead of 30. The axis under test is written onto the module
config for the duration and restored in a `finally` block.

Declared axes: `train_rows`, `hour_encoding`, `ansatz_reps`, `feature_map`,
`observable`, `train_zero_ratio`, `shots`, `feature_reduction`.

**Why.** Sweeps choose settings; they do not produce the headline table. Full
rolling-origin CV on every axis is unaffordable and would not be more
informative about which setting to pick. D-06 declares the asymmetry — **this
entry records the protocol that asymmetry refers to**, which D-06 does not.

The config mutation is deliberate and the docstring says so: the alternative is
threading every knob through every function signature, making the common path
harder to read for the benefit of a path used a handful of times.

**What it costs.** Three things.

A sweep result is **one seed**. D-14 is the standing warning: a single-seed
sweep on `train_rows` produced a clean sample-efficiency crossover that three
seeds erased, with a seed-to-seed sd four times the apparent effect. **A sweep
picks a setting; it does not establish a finding.**

`TEST_DAYS = 20` and `max_epochs = 15` mean a swept configuration is not
measured under the conditions the finals run in. Fine for ranking, not for
quoting.

The mutation is not thread-safe and leaves the config wrong if the process is
killed mid-sweep rather than raising.

**Two axes are not sound as written.** `feature_reduction` is never read by any
code — see the register — and `shots` is untested against an analytic gradient.
Six of the eight are sound; the entry should not be read as certifying all
eight. Four of the sound six have not been run at all (`ansatz_reps`,
`observable`, `feature_map`, `hour_encoding`).

**How to reverse it.** `SWEEP_FOLD`, `SWEEPS` and the overrides are config;
the mutation pattern is structural to `run_sweep`.

**Bab.** III for the protocol, IV where the asymmetry is declared alongside
D-06.

**Who.** Not recorded.

---

## §6 — Implementation

## D-09 — PyTorch for both models, via `TorchConnector`

**Decided.** The QNN is wrapped as a `torch.nn.Module` through
`qiskit_machine_learning.connectors.TorchConnector`. The classical NN is a
plain `torch.nn.Module`. Both train in one loop: same optimizer, same batch
size, same loss object, same early-stopping rule, same seed handling.

**Why not `MLPRegressor`.** scikit-learn's estimator owns its training loop.
You cannot make it use your optimizer, batch size, early-stopping rule or seed
handling, so every comparison drawn against it carries a confound, and "the NN
was trained differently" is the first objection an examiner will raise. The
only difference between the two models must be the layer.

**The comparison ladder.** Five entries, reported together: predict-the-mean
floor, ridge regression, parameter-matched NN (≈65 weights, roughly
`13 → 4 → 1`), the QNN, and an unconstrained NN (`13 → 64 → 64 → 1`). The
parameter-matched NN alone is not enough — it is deliberately crippled and a
reviewer will say so. The unconstrained NN is the performance ceiling the QNN
is really being measured against.

**Cost.** `torch` enters `requirements.txt` and `environment-lock.txt` is
regenerated — a change to the NF-02 story that must be recorded, not silent.
CPU-only torch is roughly a 200 MB install.

**The open item under this entry has since been settled, and the answer was
no.** It read: "whether `qiskit-machine-learning==0.9.1` exposes a
reverse/adjoint estimator gradient — the difference between a QNN sweep
finishing in an hour and finishing in a day, and it should be measured rather
than assumed." It was measured. It does not. **See D-28**, which is what
replaced it.

**Bab.** III, implementation subsection.

**Who.** Not recorded in the modelling record.

---

## D-28 — PennyLane `lightning.qubit` + `adjoint` for gradients, not Qiskit

*New in this merge. The decision was taken and implemented but had no ID; it
appeared only as a resolved open item under D-09, and `config.py:255` cites
"D-14" for it, which is wrong — see O6. Every figure below is from `qnn.py`'s
module docstring, verified 8 September 2026.*

**Decided.** Circuits are defined and verified against Qiskit, but every
gradient in the reported results is computed by PennyLane `lightning.qubit`
with the `adjoint` differentiation method. `qiskit-machine-learning`'s
parameter-shift path is not used for production runs.

**Why. The benchmark, per sample** **[repo]**:

| Backend + gradient | ms/sample | Full sweep |
|---|---|---|
| Qiskit `Statevector` + parameter-shift | 438,70 | 526,5 h |
| Qiskit `Aer` + parameter-shift | ~305 | ~366 h |
| Qiskit `Aer` + SPSA | 12,01 | 14,4 h |
| **PennyLane `lightning.qubit` + `adjoint`** | **6,97** | **8,4 h** |

526,5 hours is not a slow sweep, it is a sweep that does not happen. 8,4 hours
is an overnight run.

**It is a change in scaling, not a constant factor**, and that is the sentence
Bab III wants. Parameter shift needs **2 circuit evaluations per weight** — at
45 weights, 90 circuits per sample, and the count grows with the parameter
count. The adjoint method needs **one backward pass for all 45**. So the gap
does not merely persist as the circuit grows; it widens. Quoting the 63× ratio
alone understates the argument by making it look like a faster implementation of
the same algorithm.

**Why SPSA was rejected despite being cheap, and this part is checkable.** SPSA
estimates the gradient from random perturbation directions, so a k=1 estimate is
a **rank-1 projection** of the true gradient. Random-projection theory predicts
an expected cosine similarity of about **1/√d**, which at d = 45 is **0,149**.

Measured **[repo]**:

| k | cosine to true gradient |
|---|---|
| 1 | 0,137 ± 0,224 |
| 16 | 0,277 |

The k=1 measurement lands on the prediction — 0,137 against 0,149, inside a
standard deviation. The docstring reports the growth as following a **√k law**
and extrapolates that reaching a usable **0,7** needs **k ≈ 84**, which costs
more per step than parameter shift does.

So SPSA is not a cheaper route to the same gradient; it is a cheap route to a
direction that is mostly wrong, and buying the accuracy back costs more than the
method it was replacing.

**Write it in that order** — theory predicted the value, measurement matched the
prediction, and the extrapolation rests on a law rather than on a curve fitted
to two points. An examiner can check each step. A qualitative "SPSA was too
noisy" cannot be checked and invites the obvious follow-up.

**But quote the docstring's functional form rather than reconstructing it.**
The three published numbers do not close under the simplest reading of the law.
Taking cosine ∝ √(k/d) with d = 45: k=1 gives 0,149 ✓, but k=16 gives 0,596
against the measured 0,277, and cosine = 0,7 arrives at k ≈ 22 rather than 84.
Anchoring the constant on the measured 0,137 instead moves those to 0,548 and
k ≈ 26. Working backwards from k ≈ 84 → 0,7 implies a constant of 1/√171.

Three readings, three different answers, none of them 84. **The docstring
presumably carries the exact form — saturation, a per-step cost weighting, or an
effective dimension larger than the weight count — and Bab III needs that form
verbatim rather than my reconstruction of it.** This is precisely the passage
where being checkable is the point, so it is the one place the argument must not
be paraphrased from memory.

**Why not `pennylane-qiskit`.** Refused deliberately, and the reason is
**dependency management, not speed** (`qnn.py:29`). The plugin pins its own
supported Qiskit range, so installing it could drag the environment off
Qiskit 2.5.2 — the version the pipeline was built and verified against — and
break the pipeline to fix the modelling side.

That is the same argument as the one-environment decision and it serves the same
requirement: **NF-02**. One environment, one lock file, one resolved dependency
set that reproduces the results. A plugin whose version constraints are outside
the project's control is a reproducibility liability regardless of what it does
at runtime.

**Equivalence is proved, not asserted.** `verify_against_qiskit(n, trials=3,
tol=1e-10)` (`qnn.py:314`) builds the same circuit both ways and compares
outputs across three trials to **1e-10**. That is what licenses describing the
model as the Qiskit circuit it is defined as, while reporting that its gradients
were computed elsewhere.

**What it costs.** Two things, one technical and one presentational.

*Technical.* A second quantum framework enters the dependency set, so NF-02's
reproducibility story now spans Qiskit and PennyLane. `environment-lock.txt`
must record both.

*Presentational, and larger.* **The judul says "Framework Qiskit".** The
circuits are Qiskit, verified to 1e-10 against Qiskit, and would run on Qiskit
given 526 hours. But every reported number came out of PennyLane. That is
defensible and it is not dishonest — it is a simulator choice, not a model
change — **but it has to be stated rather than left for an examiner to notice.**
Open question 9.

**The framing to use in Bab III** is the author's own, from the docstring: the
architecture is **taken from the Qiskit template**, **executed on a
backpropagating simulator**, with **equivalence verified numerically to 1e-10**.
Three clauses, in that order. It concedes nothing that is not true and claims
nothing that is not proved.

**How to reverse it.** The Qiskit path is kept runnable and
`verify_against_qiskit()` is what keeps it honest. Reversing means accepting the
526-hour sweep, so it is reversible in principle and not in practice.

**Bab.** III, implementation subsection, with the benchmark table, the scaling
argument and the SPSA cosine result. Bab I if the judul changes.

**One number to reconcile.** This entry works at **45 weights**; D-07's
subsampling arithmetic works at **65**, from a 13-qubit `real_amplitudes` ansatz
at 4 reps. 45 is consistent with 15 qubits at 2 reps — which is the default
feature count under D-02's cyclic hour encoding. The two entries are probably
describing different configurations rather than disagreeing, but they are now in
one document and a reader will notice. **Unresolved; flagged rather than
silently reconciled.**

**Who.** **Mine. Benchmarked, recommended and implemented by me.** Rafly does
not recall being asked, and reports no familiarity with PennyLane. He did not
make this decision.

**That absence is the record, not a gap in it.** The largest deviation in the
project — the one that reaches the title page — was taken by the assistant, on
its own benchmark, and the supervisor of the work found out afterwards. Nothing
about the decision is wrong: the measurements hold, the equivalence is proved to
1e-10, and the alternative was a sweep that does not finish. But the *process*
is worth stating, because "who chose PennyLane" is a fair question at sidang and
"I did, after Claude benchmarked it and recommended it" is a different answer
from "Claude did, and I found out later."

Write the technical case in Bab III on its merits. This field exists so the
provenance is not reconstructed from the merits afterwards.

---

## D-32 — A trainable affine head on the quantum output

**Decided.** `OUTPUT_AFFINE_HEAD = True`. `QuantumModel` wraps the circuit's
expectation value in a trainable `a·y + b` (`nn.Linear(1, 1)`).

**Why it is structural, not decoration.** A Pauli expectation lives in
**[−1, 1]**. A standardised `log1p(count)` target does not. Without the head the
model is **structurally unable to reach the target range**, and the failure
presents as *"the QNN does not learn"* — which is a conclusion about quantum
machine learning rather than about a missing two-parameter layer.

For the occurrence stage the output is a **logit**, paired with
`BCEWithLogitsLoss` rather than sigmoid-then-BCE, which is numerically stabler.

**The Qiskit tutorial omits this**, because its toy target is already in range.
That is worth a sentence in Bab III: the departure from the reference
implementation is deliberate and the reason is the target, not the model.

**What it costs.** Two parameters, which is why the QNN reports **47 trainable**
against 45 circuit weights — see D-34. It also means "the QNN" in every result
is a circuit *plus* a classical affine layer, and Bab III should say so rather
than let a reader assume the expectation value is the prediction.

**How to reverse it.** Config flag; `False` substitutes `nn.Identity`. Doing so
reproduces the "does not learn" failure, which is the point of keeping the flag.

**Bab.** III, architecture subsection.

**Who.** Not recorded.

---

## D-31 — Output-bias initialisation and layer calibration, applied to both arms

**Decided.** Two initialisation steps, given to the quantum and classical arms
identically.

**`initial_bias(y_train, stage)`** sets the output bias so an untrained model
predicts the base rate — the logit of the positive rate for occurrence, the mean
for count. It goes to **every gradient-trained arm**; the closed-form arms solve
for their intercept directly.

**`calibrate_output()`** rescales the head so the untrained model matches the
target's marginal spread. Both `QuantumModel` and `ClassicalModel` implement it.

**Why, and both are measured.** Without the bias, a model on a 5,79%-positive
target spends its whole budget dragging the intercept from 0 to −2,79: at
lr 0,01 with 16 steps per epoch that move alone takes **~280 steps, more than a
15-epoch run has**. It never reaches the features.

Without the calibration, the quantum arm has a second version of the same
problem. `z_feature_map` leaves every qubit on the Bloch equator where ⟨Z⟩ = 0
exactly; small-angle init tilts each by ~0,1; `local_mean` averages 15 of those
with mixed signs, so the layer's output std lands near **0,03** against a target
std of **1,0**. A head starting at weight 1,0 must learn a weight near **30**,
and at lr 0,01 that takes thousands of steps. **Symptom: occurrence converges
after 3 epochs to just below the trivial floor, and count is still descending at
epoch 29 of 30. Two failure modes, one cause.**

**Why both arms get it, and this is the load-bearing part.** A standard-init MLP
already produces O(1) outputs, so calibration changes little for the classical
arm. **It is applied anyway.** Giving a calibration step to one arm and
withholding it from the other is exactly the asymmetry that makes D-09's
comparison unanswerable at sidang. The classical rescale is exact rather than
approximate: with `out = W·h + b`, the map `(out − m)/s + bias` is reproduced by
`W' = W/s` and `b' = (b − m)/s + bias`.

**What it costs.** Both are computed from **training** rows only
(`max_rows = 256`), so neither leaks. The QNN's calibration reads the layer's
output on real data before training, which is one extra forward pass.

**How to reverse it.** `calibrate_output` is applied by `training.fit` if the
model exposes it; removing it from one arm only would break D-09.

**Bab.** III, implementation subsection. The two failure modes are worth
stating — they are concrete evidence that "the QNN does not learn" is a claim
that needs a controlled setup behind it.

**Who.** Not recorded. Both read as fixes made during implementation.

---

## D-33 — Quantum architecture: `z` map, `real_amplitudes` at reps = 2, local readout

**Decided.** One qubit per feature, 15 by default. `FEATURE_MAP = "z"` at
`FEATURE_MAP_REPS = 1`; `ANSATZ = "real_amplitudes"` at `ANSATZ_REPS = 2` with
`ANSATZ_ENTANGLEMENT = "linear"`; `OBSERVABLE = "local_mean"`; `SHOTS = None`
(exact expectation values).

Weight count is `(reps + 1) × n` = **45**, plus the D-32 head = 47 trainable.

**Why `local_mean`, which is the one with a real argument behind it.** The stock
template's `global_z` — Z on every qubit — **saturates badly past a handful of
qubits and is a known barren-plateau accelerant**. Keeping every term
single-qubit keeps the cost function local, and the gradient does not vanish
exponentially with n. **The proposal already commits to local cost functions as
the barren-plateau mitigation**, so this is the config honouring a commitment
made in Bab II rather than a free choice.

`global_z` is kept as a sweep value specifically as **the ablation arm that
demonstrates why it was not chosen** — which is a stronger position than
asserting it.

`z` over `zz`: the product encoding is shallow and has no entanglement. `zz` at
`full` on 15 qubits is 105 two-qubit blocks and very deep; the config warns to
prefer linear or circular if it is tried at all.

**What it costs, and what is not justified.** `ANSATZ_REPS = 2` sits in the
middle of a 1–4 sweep, and `FEATURE_MAP_REPS = 1`, the linear entanglement on
both map and ansatz, and `real_amplitudes` over `efficient_su2` **carry no
recorded reasoning**. They are defaults that survived. The observable choice is
argued; the rest of the architecture is not.

`SHOTS = None` means every reported number is an exact expectation, so **no
result in this thesis includes shot noise**. That is the right default for a
simulator study and it must be stated — a reader may assume otherwise from
"quantum". See the register on the `shots` sweep axis.

**How to reverse it.** All config values, all sweep axes. Four of the sweeps
that would inform these choices have not been run.

**Bab.** III, architecture subsection, with the barren-plateau argument and the
Qiskit circuit figure from `build_circuit()`.

**Who.** Not recorded, except that the local-cost commitment is inherited from
the proposal.

---

## D-34 — The ladder is six rungs, and parity is 47 against 52

**Decided.** `MODEL_LADDER` runs **six** entries, not the five D-09 names:
`baseline_trivial`, `ridge`, `nn_matched`, `qnn`, `nn_large`, **`nn_full`**.
`NN_ACTIVATION = "tanh"`, `NN_LARGE_HIDDEN = (64, 64)`, and `nn_matched`'s width
is **solved** by `solve_matched_hidden` rather than hand-picked.

**`config.py` defines `MODEL_LADDER` twice.** The first assignment has five
rungs; a second, later assignment adds `nn_full` and silently shadows it. **The
six-rung version is the live one** and is what this entry documents. See the
register — two definitions of the ladder in the modelling half's source of truth
is a defect even though the effective value is correct.

**Why `nn_full`.** It is `nn_large` trained on every row rather than the QNN's
subsample, and it **deliberately breaks parity**. The matched arms exist to make
D-09's comparison meaningful; `nn_full` exists because *"the classical model can
use 400× the data at a thousandth the cost"* is a real finding about where QNNs
currently stand, and **an examiner will ask about it whether or not it was
measured**. Measure it, label it, report it separately, and put it in Bab V.
Read it alongside D-30 — the arm is only interpretable because the step budget
was equalised.

**Why `tanh`.** Bounded, like the quantum readout. Keeping the nonlinearity's
range comparable removes one more difference between the arms.

**Parity is 47 against 52, and the code says to report both.** The QNN has 47
trainable parameters (45 circuit + 2 head); `solve_matched_hidden(15, 47)`
returns a hidden width of 3, giving **52**. Exact parity is impossible here:
parameter count moves in **steps of `n_in + 2` = 17** per hidden unit. The
docstring's instruction is explicit — *report the actual counts of both models
rather than claiming they are equal* — and Bab IV should follow it.

Parity is solved rather than guessed so that changing `ANSATZ_REPS` or the
feature count cannot silently break it.

**What it costs, and this belongs in Bab V.** **Parameter parity is a weak
currency.** The QNN's 45 weights act on a 32.768-dimensional Hilbert space;
45 classical weights on 15 inputs buy a hidden layer of **three units**. The two
are not comparable in any deep sense. That is the argument for reporting the
whole ladder rather than a single matched pair, and it is a limitation of the
comparison rather than a result from it.

`ridge` is written out rather than imported from scikit-learn so the intercept
handling and the unpenalised bias term are visible. On the occurrence stage it
fits 0/1 labels as a linear probability model — crude, and a reference point
rather than a contender.

**How to reverse it.** `MODEL_LADDER`, `NN_ACTIVATION` and `NN_LARGE_HIDDEN` are
config values. `NN_MATCHED_HIDDEN` can override the solver.

**Bab.** III for the ladder, IV for the results, V for `nn_full` and the
weak-currency argument.

**Who.** Not recorded. `nn_full` appears as a late addition — bugs 6, 7 and 8 in
the RUNBOOK are all about getting it to run correctly.

---

## D-39 — A reduced Qiskit run, to show the two gradient paths converge together

**Decided, not yet run.** One reduced training run on the Qiskit
parameter-shift path, compared against the PennyLane adjoint path used for every
reported result.

**Scope, stated so no reader assumes more:** **500 rows × 15 epochs, one fold,
one seed, occurrence stage only.** At 438,70 ms/sample that is
**~55 minutes** **[derived]**. The **full hurdle pair at full size would be
21,9 h**, and it is not being run.

**Why.** `verify_against_qiskit()` proves the two implementations agree on the
**forward pass** to 1e-10. That answers a question about the *circuit*. The
question at sidang is about the **training** — *how do you know PennyLane's
gradients gave you the same model?* — and forward equivalence does not answer
it directly.

The theoretical argument is sound: parameter-shift and adjoint both compute the
exact analytic gradient, so forward equivalence to 1e-10 implies gradient
equivalence. But that is an argument. **An hour converts it into an exhibit**,
on the largest deviation in the project (D-28). Ten hours buys very little more,
because what is being demonstrated is that the curves agree — not that a
full-fidelity result was reproduced.

**What it shows, and what it does not.** It shows **agreement of training curves
under a reduced budget**. It does **not** show reproduction of a full-fidelity
result, it does not cover the count stage, and it does not cover the
cross-domain scenarios. State all three in Bab III; a demonstration oversold is
worse than none.

**The command, so this does not become an intention with no execution path:**

```bash
cd "$(git rev-parse --show-toplevel)/code/modelling/src"
python3 -c "
from gfd_model import config as mcfg, dataset as ds, experiments as X
mcfg.DEVICE, mcfg.DIFF_METHOD = 'default.qubit', 'parameter-shift'
fit = X.fit_models('tropis', ds.folds()[mcfg.SWEEP_FOLD], 'occurrence',
                   seed=0, train_rows=500, max_epochs=15, models=('qnn',))
print(fit['diagnostics']['qnn'].summary())
"
```

Run the same line with the defaults restored for the adjoint arm, and compare
the two `train_loss` / `val_loss` curves. **[unverified]** — the invocation is
written from the signatures in `experiments.py` and has not been executed; if
`fit_models` does not accept `models=` as a keyword the call needs adjusting,
not the decision.

**How to reverse it.** Nothing is committed until it runs. If the curves
disagree, that is a finding about D-28 and not a defect in this entry.

**Bab.** III, beside the D-28 benchmark table and the equivalence check.

**Who.** **Rafly's**, taken on 8 September 2026 on the reasoning above, after I
put the cost of both the long and short versions in front of him. He chose the
short one for the stated reason: the question is about the training, not the
circuit.

---

## §7 — Requirements

## D-12 — NF-01 will not be met at hourly resolution, stated in advance

**Decided.** NF-01 (NRMSE < 0,1 and R² > 0,9) is kept as written, reported as
not met at hourly resolution, and explained.

**Why.** NF-01 was written against a monthly GFD density. At hourly resolution
the target is a count process that is 94–97% zeros, and R² on such a target is
close to meaningless — predicting zero everywhere already explains most of the
variance. A category difference, not a modelling failure.

**What D-04 changes, and by how much.** Less than hoped. At 24 h the tropis
zero share is 64,63%, so R² becomes interpretable but the target is still
zero-dominated. Report NF-01 against every window in the D-04 curve; that is a
far stronger answer than either quietly missing it or quietly redefining it.

**Raise this with the pembimbing before Bab V, not in it.**

**Bab.** III when NF-01 is restated, Bab V in the evaluation.

**Who.** Not recorded in the modelling record.

---

# Bab IV — Hasil dan Pembahasan

Entries whose primary home is Bab IV. Many Bab III entries also report here; the
contents table lists them.

## D-27 — The subtropis detection-efficiency gradient is measured, and confounded

**Decided.** The distance-dependent falloff in MERLIN flash counts is reported
as **a confound between instrument response and climatology that cannot be
separated using MERLIN alone** — not as an artefact, and not as physics.

**The measurement.** Subtropis flash counts fall off with distance from the Cape
at **Spearman −0,955**, across four orders of magnitude **[repo]**:

```
28,75 −80,75     31 km    444.193 flashes
26,75 −78,75    267 km          87 flashes
```

**Why the careful framing.** Florida's peninsula is genuinely the most
lightning-prone part of the United States and the Cape sits near its middle, so
distance-from-sensors and distance-from-sea-breeze-convergence are nearly
collinear inside this box. **A perfect detector would show a gradient here too.**
At matched distances inland cells carry roughly 3× the ocean cells, which is
real physics. Claiming the gradient is an artefact would be as wrong as ignoring
it.

**A land mask would not fix it.** 30,25 / −81,25 is over land and carries 6.968
flashes against 437.287 at 28,75 / −81,25 **[repo]**. This is also recorded at
D-11.

**Two independent lines of evidence now point the same way**, and one further
observation is consistent with them. Neither line existed when the gradient was
first measured.

*Line 2 — amplitude.* Once MERLIN's `Signal Strength` was settled as kA (D-08,
resolved 2026-09-06 on the upper tail — tropis maxes at 520 kA, subtropis at
551,3, against a physical CG ceiling near 500), the median gap became
interpretable. Per-cell-hour median absolute peak current is **19,5 kA tropis
against 36,9 subtropis** **[repo]**. Tropis sits squarely in published
negative-CG climatology; subtropis is roughly double. Florida CG is somewhat
stronger than tropical average, not 2× stronger. MERLIN is losing low-amplitude
strikes, truncating the bottom of the distribution and dragging the median up —
the same mechanism as the distance gradient, seen in a different variable and
measured independently of it.

*Corroboration, not a third line — transfer.* `code/modelling/RUNBOOK.md`
reports that on `tropis_to_sub` **occurrence** the parameter-matched network
beats the trivial floor, while on `tropis_to_sub` **count** every model is worse
than the floor. Occurrence transfers; magnitude does not. That is what a
truncated amplitude distribution predicts — **but it is not evidence for it**,
because a genuine climatological difference in count distributions between West
Java and Florida predicts exactly the same pattern. The observation is
consistent with the instrument reading and cannot discriminate between it and
the alternative.

**Claim it that way.** Two independent measurements plus one consistent
observation is a harder position to attack than three asserted independents,
and the third would not survive the first person who noticed that a cross-domain
count gap is what the experiment is trying to measure in the first place.

**What it costs.** This is the largest threat to the validity of the core
experiment and should be stated as such rather than in a footnote. The two
domains come from different networks, so **a measured cross-domain
generalization gap may be measuring instrument rather than climate.** Tropis
shows the same problem in a different form — six edge cells with zero flashes in
seven years, D-11 — so neither side is clean.

Any cross-domain *intensity* claim measures MERLIN's sensitivity floor as much
as Florida's meteorology. Say so before the result, not after it.

**How to reverse it.** It is a property of the instrument, not a setting.
Separating the two effects needs a detector with uniform efficiency across the
box. **GOES-16 GLM would do it** — the MERLIN/GLM ratio against distance gives
the detection-efficiency curve directly — at 5–9 GB per day for L2 LCFA
granules. `merlin-crosscheck/glm_check.py` exists and is scoped to specific
days. `RUNBOOK.md` calls this a possibility rather than a plan, and that is the
right status.

**Bab.** IV, as the headline limitation on the cross-domain result. Not a
footnote.

**Who.** **The measurement is the instrument's; the framing is mine, and it is
signed off.** The "confounded, not artefact" reading, the matched-distance 3×
comparison and the land-mask counter-example are all my text in `RUNBOOK.md`.
Rafly endorsed the framing as the headline limitation for Bab IV on
8 September 2026, with one downgrade: the transfer result was originally written
as a third independent line and is now recorded as corroboration, because
different count distributions across domains are also what a genuine
cross-domain gap looks like. That correction is his.

---

## D-10 — `coverage` is reported, never acted on

**Decided.** `MIN_COVERAGE` stays at 0,0. `coverage` is neither a filter nor a
sample weight. The distribution of `coverage` over the rows actually trained on
is reported in Bab IV beside the zero share.

**Why not filter.** A 0,9 gate would delete 56 of 81 subtropis months and 26 of
84 tropis — and it deletes *opposite halves of the year* in the two domains
(tropis thins through the JJAS dry season, subtropis through DJF winter). The
two training sets would no longer span comparable seasonal ranges, so any
cross-domain gap measured afterwards would be partly an artefact of the filter.

**Why not weight either.** `coverage` is correlated with the target through
lightning activity itself — the observation proxy is "a day with at least one
strike somewhere in the domain is a day the network was up", so a genuinely
quiet month and a dead detector look identical. Down-weighting low-coverage
rows preferentially removes low-activity periods and inflates apparent
performance. `coverage` is in `EXCLUDE_COLUMNS` for exactly this reason; using
it as a weight reintroduces the problem through a side door.

**The honest framing.** Observation coverage and target magnitude cannot be
separated with the data available. That is a limitation, not a preprocessing
step. The right instrument is a real observation record, which does not exist —
open question 18.

**Bab.** IV, as a limitation. The build-side decision is D-18.

**Who.** Not recorded in the modelling record.

---

## D-01 — `KX` is dropped from both domains

**Decided.** No model uses the ERA5 K index. Both domains present 13 base
predictors: `lat`, `lon`, the six NASA POWER parameters, and five of the six
ERA5 variables.

**Why.** `KX` is present in the tropis build and absent from the subtropis
build. The cross-domain experiment fits on one domain and applies the fitted
model to the other, so a 14-feature source against a 13-feature target either
raises a shape error or gets silently intersected by the shared preprocessing
chain — dropping `KX` without recording it. Making the drop explicit is the
difference between a documented decision and an undocumented accident.

**Common misstatement to avoid.** `KX` is not a MERLIN field. MERLIN supplies
only lightning strikes. `KX` is ERA5, and it is missing from the *subtropis ERA5
download*. Diagnosed 2026-09-06: the NetCDFs genuinely lack the variable under
any short name, so it is not an `ERA5_SHORTNAME_MAP` miss; a fresh six-variable
request for the subtropis box returns five variables; but `k_index` requested
**alone** for that same box returns `kx` cleanly, twice, in 84 and 27 seconds.
The CDS will serve it. What fails is the six-variable request for this box
specifically.

**Cost.** `KX` is one of the fourteen predictors the predecessor study used. The
feature set no longer matches his, which weakens the Bab V comparison. This is
the real price and it should be stated, not buried.

**Reversible.** Yes, at ~84 supplementary single-variable CDS requests of ~750
fields each — faster-queuing than the original fetch. A time trade, not a
technical constraint. Open question 14.

**Bab.** IV, feature-selection subsection. State the cost.

**Who.** Not recorded in the modelling record.

---

## D-05 — Spatial aggregation is a supplementary result, not a second main axis

**Decided.** Predictions are aggregated over 2×2 cell blocks in both domains.
Whether 3×3 is available in subtropis depends on the grid shape — subtropis is
**56 cells**, not the 54 NASA POWER points; confirm the lat×lon dimensions
before claiming it. Open question 19.

**Why the arithmetic matters.** GFD is a density. Aggregating cells means
`sum(counts) / sum(areas)`, never the mean of the per-cell densities — cell
areas differ with latitude (`_cell_area_km2` accounts for meridian convergence)
so averaging densities is wrong.

**Why it is supplementary.** Tropis is 30 cells. A 5×5 block is very nearly the
whole domain, so 2×2 is about the limit. Temporal aggregation (D-04) has far
more headroom and carries the argument.

**Hazard.** Six tropis cells hold zero flashes across all seven years — 20% of
the grid. Any spatial block containing them scores well for the wrong reason.
See D-11.

**Bab.** IV, short subsection.

**Who.** Not recorded in the modelling record.

---

## D-14 — Sample efficiency was tested and is not supported

**Decided.** The thesis does not claim a low-data advantage for the QNN. It
reports that one was looked for, with adequate replication, and not found.

**What was measured.** `train_rows` at 500 / 1.000 / 3.000, three seeds, on
fold 2. QNN minus parameter-matched NN:

| rows | occurrence (log loss) | count (RMSE) |
|---|---|---|
| 500 | +0,0237 (sd 0,0191) | +0,0054 (sd 0,0513) |
| 1.000 | +0,0274 (sd 0,0142) | +0,0067 (sd 0,0287) |
| 3.000 | +0,0269 (sd 0,0082) | +0,0208 (sd 0,0173) |

Positive is worse. On occurrence the gap exceeds the pooled standard deviation
at every rung and does not shrink across a 6x range of data. On count it is
positive everywhere and widens, clearing the noise only at 3.000.

Improvement over the range: QNN 0,0285, nn_matched 0,0317. The classical model
improves marginally faster, so the gap is flat to slightly widening.

**Why this is a result and not a null.** The constant-offset shape is
informative: if the QNN were data-limited the gap would shrink with n, and if
it were capacity-limited relative to the classical model the gap would grow.
Neither happens on occurrence. The deficit is in representational fit — what
this circuit can express about these features — not in how efficiently it
learns from examples.

**The single-seed near-miss, recorded deliberately.** The first sweep used one
seed and produced a textbook crossover: QNN ahead by 0,0111 on count at 500
rows, behind by 0,0138 at 3.000. Three seeds erased it — the replicated count
gap is +0,0054, +0,0067, +0,0208. The seed-to-seed sd on that arm is 0,0396,
roughly four times the apparent effect. This is what D-06's replication
requirement is for, and it is worth a sentence in Bab IV — a single-seed
quantum-advantage claim is not evidence.

**Cost.** ~80 min for 18 runs per stage.

**Limitation to state.** 500–3.000 rows is a narrow window and all of it small.
An advantage below 500, or a crossover above 3.000, would not appear.
Extending to 10.000 is ~30 min per fit and affordable at one seed.

**Bab.** IV for the curve, Bab V for the finding and its limitation.

**Who.** Not recorded in the modelling record.

---

# Bab V — Penutup

No entry is written out here. Four report into the evaluation, and are written
out in the chapters shown.

- **D-12** — NF-01 evaluated against every window in the D-04 curve, rather than
  quietly missed or quietly redefined. Raise with the pembimbing *before* Bab V.
- **D-14** — the sample-efficiency finding, and the narrowness of the range it
  was measured over.
- **D-20** — the NF-01 renegotiation, if it happens.
- **D-01** — `KX` and the weakened comparison against the predecessor.

---

# Discrepancy register

Every known conflict between this record and the repo, or inside the repo.
Two fixes have landed; eleven are outstanding, of which **two are code defects
rather than documentation drift** (O9 and O10) and one is a deletion (O8).

## Applied

### A1 — `lightning.py:308`, the ">99% zeros" estimate

`aggregate_gfd`'s docstring, in the "AND THE GATE IS CURRENTLY OFF" paragraph,
read "against a target that is already >99% zeros" while `config.py`,
`RUNBOOK.md` and the modelling config all carried the measured 94,30% / 97,00%.
Replaced with the measured figures.

`grep -rn ">99%" code/pipeline/src/ code/modelling/src/` returned two hits; the
other, `config.py:121`, is the correction text itself — the sentence recording
that the old estimate was wrong — and was correctly kept.

### A2 — `config.py`'s self-contradiction on `KX`, applied 8 September 2026

The block above `ERA5_SHORTNAME_MAP` read "KX IS MISSING FROM THE SUBTROPIS
BUILD AND NOBODY KNOWS WHY" with three candidate causes, while
`DROPPED_PREDICTORS` further down the same file carried the correct 2026-09-06
diagnosis. The dated block won on evidence — it named a date and two timings;
the other named nothing and said the opposite.

**Fixed first, deliberately.** Every entry in this record carries "where this
disagrees with `config.py`, `config.py` wins", and that rule was inert while
`config.py` answered the same question twice, differently. Comments only; a diff
excluding comments is empty.

**One addition beyond the drafted replacement, and it is the better line.** The
applied text opens with **"DO NOT ADD AN ALIAS HERE LOOKING FOR IT."** The old
block's cheapest candidate cause was "the subtropis files carry `k_index` under
a short name this map does not have" — a one-line fix, listed first, sitting
directly above the map it would be added to. So the wrong fix was both the most
tempting and the most convenient at exactly the site a debugger would land on,
and deleting the wrong explanation does not by itself stop someone re-deriving
it. Naming the wrong fix and forbidding it is stronger. Worth copying as a
pattern wherever a stale diagnosis is retired next to the code it would have
touched.

Verified after the fix: `grep -rn "{dom}" code/` returns exactly one hit,
`RUNBOOK.md:536` — outstanding item O4.

## Outstanding

### O1 — `config.py`'s `MIN_COVERAGE` block carries both positions

Mitigation 1 says filter or weight on `coverage`; the closing paragraph says the
gate is the wrong lever. As argued in D-18, these are nominally about different
levers but the objection transfers, and D-10 already bans `coverage` as a
predictor for the same correlation.

**Fix:** mitigation 1 should read "report the threshold if you ever act on it,
but do not — see D-18", or the two mitigations should collapse into one. Comment
edit, not a code change.

```bash
grep -n "filter or weight\|Filter or weight" code/pipeline/src/gfd_data/config.py
```

### O2 — `RUNBOOK.md` carries the same two positions

Numbered mitigation 1 says "Filter or weight on `coverage` at modelling time and
record the threshold in the experiment config (F-05)". A later paragraph
concludes "**The gate stays at 0.0. It is the wrong lever**". Same fix as O1.

```bash
grep -n "Filter or weight\|wrong lever" code/pipeline/RUNBOOK.md
```

### O3 — `RUNBOOK.md` step 2, the window count is wrong twice

**Current text.** *"The archive caps each export at **30 days**, so 2018–2024
took **89 exports**"*, and later: *"`--dry-run` over 2018–2024 lists 86 windows
at the default 30-day step, against 89 files on disk. The difference is manual
re-pulls and boundary retries, not a gap."*

Both halves are wrong. The archive's cap is 30 days but `MAX_WINDOW_DAYS = 29`,
so the step is 29. At 29 days the span yields 89 windows, which is exactly the
file count — so there is no difference for re-pulls to explain.

**Replacement.**

> The archive caps each export at **30 days**; `MAX_WINDOW_DAYS = 29` leaves
> margin against off-by-one at the boundaries. At a 29-day stride 2018–2024
> yields **89 windows**, and there are **89 files on disk in one-to-one
> correspondence** — `--dry-run` and the directory listing agree exactly, in
> both directions. Do not rename or delete files; the archive's own filenames
> are the provenance record.
>
> Five of the 89 files hold no usable data. That is missing **content**, not
> missing files — see below.

The correction matters beyond tidiness: the old text says the file set is
*approximately* right for unverifiable reasons, and the true statement is that
it is *exactly* right. The second is defensible at sidang and the first is not.

```bash
grep -n "86 windows\|manual re-pulls\|caps each export" code/pipeline/RUNBOOK.md
```

### O4 — `RUNBOOK.md` step 4e, stale KX diagnosis and the last glob copy

**Now the only place either problem survives.** After A2 was applied,
`grep -rn "{dom}" code/` returns exactly one hit: **`RUNBOOK.md:536`**.

Current text opens *"The cause has not been diagnosed"*, lists three
possibilities, and closes *"Deferred, not resolved."* All three were disproved
on 2026-09-06 — see D-01.

The diagnostic snippet is also wrong, independently of the staleness:

```python
files = sorted(cfg.RAW_ERA5_DIR.glob(f'*{dom}*.nc'))
```

`"subtropis"` contains `"tropis"` as a substring, so with `dom='tropis'` this
matches both domains' files and the tropis row of the output is the union of the
two. `_files()` in `era5.py` globs `era5_{domain.name}_hourly_*.nc`, which is
prefixed and correct.

**Replacement.** Delete the three hypotheses and the snippet; replace with the
diagnosis and a pointer to D-01.

> **4e. `KX` is absent from the subtropis build — diagnosed 2026-09-06.**
>
> The build reports `!! absent features: ['KX']` for subtropis. Tropis carries
> all 14 predictors, subtropis 13. Both domains have their full 84 `.nc` files,
> so this is not a shortfall by file count.
>
> Diagnosed: the subtropis NetCDFs genuinely lack the variable under any short
> name, so `ERA5_SHORTNAME_MAP` is not at fault. A fresh six-variable request
> for the subtropis box returns five variables. But `k_index` requested **alone**
> for that same box returns `kx` cleanly, twice, in 84 and 27 seconds. The CDS
> will serve it; the six-variable request for this box is what fails.
>
> **Decision: `KX` is dropped from both domains.** See `DECISIONS.md` D-01 for
> the reasoning and the cost. Reversible at ~84 supplementary single-variable
> requests.

Once this is applied, `grep -rn "{dom}" code/` should return nothing at all.
That is the single check that the glob bug is gone from the repo.

```bash
grep -n "has not been diagnosed\|Deferred, not resolved\|{dom}" code/pipeline/RUNBOOK.md
```

### O5 — `RUNBOOK.md` step 1 and `smoke_lightning.py` are stale about `config.py`

`RUNBOOK.md` step 1 says *"`config.py` still opens its `TROPIS` definition with
'THE OPEN QUESTION IN THIS FILE' and carries `tz="Asia/Jakarta",   # VERIFY with
PLN Puslitbang` — keep the reasoning, change the verdict."*

It doesn't. `config.py` now opens `TROPIS` with **"SETTLED 2026-09-06, but read
the reasoning"** and carries `tz="Asia/Jakarta",   # confirmed by diurnal check
-- see RUNBOOK step 1.` The fix the RUNBOOK asks for was applied on 2026-09-06.
The RUNBOOK is out of date about the config, not the reverse.

**Replacement:**

> `config.py` records this as settled (`SETTLED 2026-09-06`) and carries the
> reasoning at `TROPIS`. Written confirmation from PLN through the pembimbing is
> still worth having, but it would confirm a finding rather than settle an
> unknown. See `DECISIONS.md` D-17.

`smoke_lightning.py`'s module docstring is stale on the same point — it still
describes `config.TROPIS` as carrying "a VERIFY comment that never mattered at
monthly resolution and matters enormously now". The **check** it describes is
still worth running and should be kept; only the description of the config is
wrong. Replace with: "`config.TROPIS` records the clock as settled; this check
is what settled it, and it is worth re-running after any change to
`data/raw/pln/`."

```bash
grep -rn "THE OPEN QUESTION IN THIS FILE\|VERIFY with PLN" code/pipeline/
```

### O6 — `config.py:255` cites the wrong D-number

`config.py:255` cites "DECISIONS.md D-14" for the PennyLane-over-Qiskit gradient
switch. D-14 is "Sample efficiency was tested and is not supported". The
gradient decision is **D-28**, created in this merge; before it, the decision had
no ID at all and the citation pointed at whatever happened to occupy D-14.

**Fix:** change the citation to D-28.

This is the higher-priority of the two citation errors — it points at a
genuinely wrong entry, in the file that is the declared source of truth, for the
largest deviation in the project.

```bash
grep -n "D-14" code/pipeline/src/gfd_data/config.py
```

### O7 — `metrics.py:21` cites D-12 for the metric floor

`metrics.py:21` reads "D-07 and D-12, the floor". The floor rule actually lives
in D-07 ("always report the trivial baselines"); D-12 is NF-01, which discusses
*why* R² needs the floor without being the rule itself.

**Loose rather than plainly wrong** — a reader following the citation lands on
relevant material. Lower priority than O6. Fix by citing D-07 alone, or by
keeping both and making the two roles explicit.

```bash
grep -n "D-07 and D-12" code/modelling/src/gfd_model/metrics.py
```

### O8 — `experiments.py.bak` sits inside the package — DELETE IT

**Superseded code inside an importable package, and this is the worst of the
four found in batch 3** because unlike a stale comment it can be executed.

`code/modelling/src/gfd_model/experiments.py.bak` holds the pre-fix versions of
two things that were fixed for documented reasons:

- `fit_models` passing `train_rows=None` for `nn_full` — which means *use the
  config default*, not *use everything*, so `nn_full` silently trained on 3.000
  rows and produced numbers identical to `nn_large` in all 432 rows of the first
  run (RUNBOOK bug 6).
- `evaluate` using a single shared scaler for every arm — the bug D-36 exists to
  prevent (RUNBOOK bug 8).

Same hazard class as the `config.py` KX block fixed in A2: it looks
authoritative and it is wrong. Worse, because a copy-paste out of it reinstates
two known defects.

**Fix: delete the file.** Git has it, which is the whole point of git.

```bash
git rm code/modelling/src/gfd_model/experiments.py.bak
```

Move this to **Applied** once removed.

### O9 — `FEATURE_REDUCTION` is declared, swept, and never read — CODE DEFECT

**This is a defect in the code, not drift in the documentation**, and it is the
one on this list that could put a false claim in the thesis.

`FEATURE_REDUCTION` is defined in `config.py` (`None | "pca6" | "pca8"`, marked
"sweep axis") and listed in `SWEEPS` as `(None, "pca8", "pca6")`. `run_sweep`
resolves the knob name to `FEATURE_REDUCTION` and `setattr`s it successfully.

**Nothing reads it.** `dataset.feature_names()` and `dataset.prepare()` never
reference it; no PCA is applied anywhere in the package.

**So the sweep runs, completes, and returns three identical result sets.** Read
at face value that is a clean null: *dimensionality reduction makes no
difference to this model*. **The predecessor study used PCA**, and the number of
principal components was one of his experimental factors — so this is a false
negative on a direct comparison point, produced by code that does nothing, in a
sweep that reports success.

If it reached Bab IV it would be indefensible, and it would be indefensible in
the specific way that is hardest to recover from: a stated result that the code
cannot have produced.

**Fix: either implement it or delete it.** Both are defensible; leaving it
declared is not. If deleted, remove the `SWEEPS` entry too, and say in Bab IV
that PCA was not tested and why — which is a weaker but honest position.

```bash
grep -rn "FEATURE_REDUCTION" code/modelling/src/
```

### O10 — `MODEL_LADDER` is assigned twice in `config.py`

The first assignment lists five rungs; a second, later assignment adds
`nn_full` and **silently shadows the first**. Only the six-rung version is live,
and it is the one D-34 documents.

The effective value is correct, so nothing is broken at runtime. But two
definitions of the model ladder in the file that is the modelling half's source
of truth is the same failure mode as A2 — a reader who stops at the first
assignment gets a different answer from the interpreter.

**Fix: delete the first assignment**, keeping the six-rung version and its
`nn_full` comment.

```bash
grep -n "^MODEL_LADDER" code/modelling/src/gfd_model/config.py
```

### O11 — `config.py` carries a superseded benchmark that contradicts D-28

Same pattern as A2, in the same file, and it should be cleared the same way. The
block sits **immediately above** the current benchmark and recommends a strategy
D-28 rejects outright.

**Old text — delete:**

```
# MEASURED 2026-09-06, 13 qubits / 39 weights / StatevectorEstimator, minutes
# per 10.000-row epoch:
#     ParamShift  40,9    LinComb  104,2    SPSA  1,2
#
# LinComb is SLOWER than ParamShift here, not faster: it builds a
# controlled-gate circuit per parameter and circuit construction dominates in
# the reference primitive. Exact gradients at ~41 min/epoch cannot carry a
# sweep, so SPSA explores and exact gradients confirm the finals. Record this
# split in Bab III rather than letting it surface in the results.
#
# RE-BENCHMARK AGAINST AER before accepting these. qiskit-aer batches through
# compiled C++ instead of a Python loop and may move ParamShift back into
# range, which would simplify the whole design.
```

**New text — replace with:**

```
# SUPERSEDED BENCHMARK REMOVED. An earlier 13-qubit / 39-weight measurement
# recommended "SPSA explores, exact gradients confirm the finals". That
# strategy was tested and REJECTED -- see DECISIONS.md D-28 for the cosine
# result that killed it. The Aer re-benchmark it asked for was done; its
# numbers are in the table below. Do not reinstate an SPSA path here.
```

Three things wrong with the old block, which is why it goes rather than gets a
footnote: it measures a configuration that is not the default (13 qubits at
39 weights, against 15 at 45); it recommends a two-tier gradient strategy that
D-28 rejects on measured evidence; and it asks for an Aer re-benchmark that has
since been done and appears four lines below it.

```bash
grep -n "LinComb\|RE-BENCHMARK AGAINST AER" code/modelling/src/gfd_model/config.py
```

---

# Open questions

Consolidated and deduplicated from all three inputs. **Answered questions are
kept rather than deleted** — a question that was asked and closed is evidence of
a check made, and several were closed by measurements worth citing.

Six answered, seventeen open.

## Answered

### 1. Who decided hourly, and what was the previous resolution? — ANSWERED 8 September
D-21. **Rafly's decision.** The sequence was monthly → daily → hourly: he asked
for daily, then asked whether hourly was possible, then chose it. He took the
decision against three objections raised at the time — zero inflation, the
problem-statement concern, and the ERA5 instantaneous-versus-interval mismatch.
All three are recorded in D-21 as costs.

### 2. Was 0,5° inherited or recommended? — ANSWERED 8 September
D-15. **Inherited, reason confirmed:** predecessor alignment plus NASA POWER's
native 0,5° latitude step. The attribution predates the recoverable chats and
stays marked inherited rather than assigned.

### 3. Where did the empty-cell fill come from? — ANSWERED 8 September
D-19. **Rafly's, by recollection**, predating the recoverable chats and
unverifiable either way. Answering it surfaced a second justification he also
remembered — "assuming no sensor error" — which D-18 contradicts on this
project's own measurements. D-19 now rests on the target-mean argument alone.

### 4. Why is 6 hours the primary reporting window? — ANSWERED: there was no reason
D-04. No selection criterion was applied or recorded. Rewritten as an explicit
nomination: the full 1/3/6/24-hour curve is the result and 6 h is nominated as
the headline for readability.

### 5. How many IC rows does the PLN export contain? — ANSWERED 8 September
D-22. **None, in any year.** All seven sheets are CG-only at source, totalling
2.242.100 and matching `load_pln()` exactly. The CG filter discards nothing,
there is no composition change across the record, and D-06's fold boundaries are
unaffected.

### 6. Does the NF-01 decision have an ID? — ANSWERED by this merge
It does: **D-12**. The confusion arose because `metrics.py:21` cites D-12 for the
metric floor, which is D-07's rule. That citation is outstanding item O7; the
decision itself was never without an ID.

## Open

### 7. The positive case for hourly still needs writing
D-21. Rafly's reason — a more accurate input-to-output mapping between a
meteorological state and the lightning associated with it — exists in this
record as **recollection**, but has never been set out as an argument anywhere.
Since hourly departs from the proposal's approved sparsity mitigation, Bab III
has to make that case in full, alongside the three objections it was taken
against rather than instead of them. **Needs writing.**

### 8. Does the hourly build change the problem statement?
D-21, third cost. Ground flash density conventionally means flashes per km² per
year; an hourly cell-count is lightning *occurrence*, with its own literature and
metrics (POD, FAR, CSI, Brier). If the hourly build is what the TA reports,
Bab I's scope sentence — and possibly the judul — has to say so. **A pembimbing
conversation. Raise it together with question 9.**

### 9. Does "Framework Qiskit" survive the PennyLane switch?
D-28. Circuits are Qiskit and verified to 1e-10 against Qiskit; every reported
gradient came from PennyLane `lightning.qubit`. Defensible, but it has to be
stated. **The same pembimbing conversation as question 8** — both are questions
about what the thesis claims to be, and they have been drifting separately.

### 10. Is the MERLIN export CG-only?
D-22, D-27. **Half-resolved.** There is no discrimination column. MERLIN is
**5,7% positive** against PLN's **14,1%** on signed peak current over the full
record; low-amplitude positive fractions are close (**3,1% vs 2,6%**). IC
contamination *raises* the positive fraction, and MERLIN sits well below the
CG-only reference.

That reference is now verified rather than assumed — question 5 established the
PLN export is CG-only at source in all seven years, so 14,1% is a solid CG-only
baseline. Only one side of the comparison is uncertain now, which makes the
inference stronger without making it conclusive.

**Settled by:** the KSC Weather Archive's documentation for the
MerlinCloudToGround product. Not by further analysis — the data has given what
it can. **Needed before Bab III**, because it decides what the subtropis target
is called. Until then every subtropis result is provisional and must say so.

### 11. Flash or stroke?
PLN groups strokes into flashes via its `Multi.` column; MERLIN does not, and has
no multiplicity column. Comparing raw MERLIN rows against flash-grouped PLN rows
compares **stroke density to flash density** — a systematic offset in the one
comparison the TA exists to make.

**Settled by:** a decision, not a lookup. Either group MERLIN rows into flashes
by a spatiotemporal clustering rule (the usual convention is strokes within
~10 km and ~0,5 s), or ungroup PLN back to strokes if `Multi.` permits it.
Whichever is chosen must be recorded and stated. **No decision has been taken.**

### 12. Were 2022-12 and 2024-02 outages, or genuinely quiet?
D-26. 2021-03 is proven downtime. The other two have never been checked the same
way. All three are currently excluded, which is safe but is not a finding.

**Settled by:** `python metar_check.py --month 2022-12 --raw` in
`merlin-crosscheck/`, and the same for 2024-02. Cheap — a few hundred KB per
month, no VPN. The bar is `TSRA` or `LTGICCG OHD` at a station inside the box;
`LTG DSNT SW` or a bare `VCTS` proves nothing.

### 13. The two ERA5 flux-divergence variable names
D-25. `vertical_integral_of_divergence_of_cloud_frozen_water_flux` and
`..._liquid_water_flux` were never verified against the live CDS catalogue. The
data arrived and parses, so they are probably right — but "probably right" is not
what NF-02 asks for.

**Settled by:** the CDS dataset Download tab → tick the six variables → **"Show
API request"**, on the **hourly** dataset page. Compare against
`cfg.ERA5_VARIABLES`. Five minutes, no download.

### 14. Is `KX` restored?
D-01. The CDS will serve `k_index` for the subtropis box when requested alone, so
this is a **time trade, not a technical constraint**: ~84 supplementary
single-variable requests. Restoring it brings both domains to 14 predictors and
restores the match with the predecessor's feature set.

**Settled by:** your decision on whether the Bab V comparison is worth the fetch
time. Not by more diagnosis — the diagnosis is complete.

### 15. Are the six all-zero tropis cells dropped?
D-11. `DROP_ALL_ZERO_CELLS = False`, off by default so the choice stays visible.
Dropping them is defensible; keeping them is defensible. What is not defensible
is letting them fall entirely into a test fold under a cell-holdout split.

**Settled by:** your decision, recorded in D-11 and in Bab III if taken.

### 16. The duplicated POWER point-year
D-24. `power_tropis_hourly_m006p500_p106p250` holds 8 files against every other
point's 7. The build reported 100% key overlap so it is harmless, but nobody has
opened the two files to confirm they cover the same window.

**Settled by:**
```bash
ls code/pipeline/data/raw/power/power_tropis_hourly_m006p500_p106p250*
```
and comparing the date ranges in the filenames. One minute.

### 17. Are the five empty MERLIN exports re-pullable?
D-26. Untried. `fetch_window` skips a window whose file exists unless
`--overwrite` is passed. If the archive has since backfilled, one command
recovers three months.

**Settled by:** re-running those five windows with `--overwrite` and checking
whether the row counts change. Cheap, but needs the device-level VPN.

### 18. MERLIN uptime across the whole record
D-10, D-18, D-26. The wider version of question 12, and the one that cannot be
closed cheaply. The three empty months are only the cases where MERLIN logged
*literally nothing*. Subtropis has 56 of 81 months below 90% day-coverage, and
the strike-day proxy cannot distinguish downtime from quiet sky — so `coverage`
may be systematically overstating uptime for subtropis across 2018–2024.

**Settled by:** a real observation record built from METAR — a day when a station
inside the box reports `TSRA` and the network logged zero strikes is a day the
network was not working. **If it is built it must be built for both domains** —
West Java has METAR stations too (Husein Sastranegara, Soekarno-Hatta, Halim) and
IEM carries international stations — or it injects a domain-dependent selection
effect into the one comparison the TA exists to make. Not started.

### 19. Subtropis grid dimensions
D-05. 56 cells; the lat×lon shape decides whether 3×3 spatial blocks exist.

**Settled by:** reading the shape off the built table. One line.

### 20. Twelve entries have no attribution — worth a pass, not housekeeping
**D-01, D-02, D-05, D-06, D-07, D-08, D-09, D-10, D-11, D-12, D-13 and D-14 have
no `Who` field.** The modelling record was written in a five-field format that
did not include one; the field was added in batch 1 and applied from D-15 onward.

**This is not a formatting gap.** In the entries that do carry it, the field
caught two things nothing else would have: `MIN_COVERAGE = 0.0` was Rafly's call
over an objection (D-18), and so was hourly resolution (D-21). Both invert the
assumption a reader would otherwise make about who decided what.

The twelve gaps are not neutral either. They cover the hurdle structure, the fold
design, the comparison ladder, the feature set and NF-01's fate — which is to
say they are concentrated in exactly the decisions most likely to be questioned
at sidang, and where "did you choose this, or did the assistant?" is exactly the
question that gets asked.

**Settled by:** a pass through the September chats, which are searchable. Not
attempted here, and **not reconstructable from the code** — the whole point of
the field is that it cannot be inferred from the artefact.

### 21. Does the `shots` sweep axis work at all? — SUSPECT AND UNTESTED
D-33, D-37. `SWEEPS["shots"] = (None, 4096, 1024)` while
`DIFF_METHOD = "adjoint"`. **Adjoint differentiation is an analytic method and
does not take finite shots.** PennyLane will either raise, or silently fall back
to a different gradient method — and if it falls back, the axis measures shot
noise *and* a changed gradient at the same time, which is uninterpretable.

**Do not describe this as a working sweep axis until it has been run.** Every
reported number in the project currently uses `SHOTS = None`, so no result
depends on it; the risk is entirely prospective.

**Settled by one line:**
```bash
cd "$(git rev-parse --show-toplevel)/code/modelling/src"
python3 -c "
from gfd_model import config as mcfg
from gfd_model.qnn import make_qnode, n_features_configured
import torch
n = n_features_configured()
q = make_qnode(n, device='lightning.qubit', diff_method='adjoint')
dev = __import__('pennylane').device('lightning.qubit', wires=n, shots=1024)
print('constructed; now check whether a backward pass raises')
"
```
If it raises, the axis is removed and Bab III says shot noise was not tested. If
it falls back, the axis needs `DIFF_METHOD` switched to `parameter-shift` for
that sweep only, and the cost recomputed against D-28's table.

### 22. Seven hyperparameters have no recorded reasoning
D-29, D-33, D-34. `LEARNING_RATE = 0.01`, `BATCH_SIZE = 64`,
`NN_LARGE_HIDDEN = (64, 64)`, ridge `alpha = 1.0`, `VAL_FRACTION = 0.15`,
`FEATURE_MAP_REPS = 1`, and linear entanglement on both feature map and ansatz.
None carries a comment or a recoverable chat. Rafly does not have them either,
so they are recorded as **not recorded** rather than reconstructed.

**The pattern is worth one line in its own right: the hyperparameters that shape
the comparison are the ones with the least justification behind them.** The
observable choice is argued from barren plateaus, the budget is argued from one
night, the step cap is argued from a measured failure — and the learning rate
that every one of those arguments assumes is a round number nobody defended.

**Settled by:** nothing available. This is a limitation to state in Bab III, not
a gap to fill: a post-hoc justification written now would be a reconstruction,
which is exactly what this record exists to avoid.

### 23. Four OFAT sweeps have not been run
D-37. `ansatz_reps`, `observable`, `feature_map` and `hour_encoding` are
declared and sound but unexecuted; only `train_rows` is done. Each is ~15 min
per seed. Until they run, D-33's architecture choices rest on argument alone —
which is fine for `local_mean`, where the argument is strong, and thin for
`ansatz_reps = 2`, where there is none.

**Settled by:** running them. `python3 -c "from gfd_model import experiments as
X; X.run_sweep('observable')"` and the same for the other three.

### 24. Does D-39's comparison run confirm the two gradient paths agree?
D-39, D-28. Decided and scoped at 500 rows × 15 epochs, occurrence stage, ~55
minutes. **Not yet run.** Until it is, D-28's training-equivalence claim rests
on the theoretical argument — sound, but an argument.

**Settled by:** the command in D-39.

---

# Batch 3 — written 8 September 2026

**Modelling design.** Eleven entries, D-29 to D-39, covering what
`code/modelling/src/gfd_model/` implements and the record did not carry: the
compute budget, the equal-step training cap, output-bias initialisation and
layer calibration, the affine head, the quantum architecture, the six-rung
ladder, feature scaling, per-model scalers, the sweep protocol, sampling
mechanics, and the reduced Qiskit comparison run.

**Two existing entries were corrected.** D-07's subsampling arithmetic now
carries a correction paragraph — it sized its budget against a sweep corner
(13 qubits at reps = 4) at an optimistic 1 ms, while the reported runs use
15 qubits at reps = 2 at a measured 6,97 ms. D-28's `Who` is answered: the
PennyLane switch was mine, and Rafly did not make it.

**Four discrepancies were added**, two of them code defects rather than
documentation drift — `FEATURE_REDUCTION` declared and never read (O9), and
`MODEL_LADDER` assigned twice (O10) — plus a deletion (O8) and a superseded
benchmark contradicting D-28 in `config.py` (O11).

**What batch 3 did not do.** It did not fill the twelve missing `Who` fields on
D-01 to D-14 (open question 20), and it did not run any of the four outstanding
sweeps, the `shots` check, or the D-39 comparison. Those are executions, not
writing.

**The record is now complete in coverage.** Every decision the project makes
that a reader could reasonably have made differently has an ID, a reason where
one exists, and an honest "not recorded" where one does not. What remains is
execution and attribution, both tracked in the open questions.
