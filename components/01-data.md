# Component 1 — Data

**Owns:** what exists on disk. Acquisition only.
**Does not own:** the build, the merge, feature selection. That is Component 2.
**Machine:** Mac. **Config:** `code/pipeline/src/gfd_data/config.py`.
**Hard date:** raw freeze, day 3.

---

## Inputs

Four sources, all already on disk for 2018–2024, both domains:

| Source | Domain | Note |
|---|---|---|
| PLN Puslitbang LDS | tropis | not public, must not be redistributed |
| NASA MERLIN | subtropis | 89 exports, 29-day windows, 5 empty |
| NASA POWER | both | 84 native points, per-year requests |
| ERA5 (CDS) | both | one request per domain-month |

---

## Tasks, in priority order

### 1.1 — KX re-pull for subtropis (day 1, launch first)

The `KX` gap is **diagnosed, not unknown**. The subtropis NetCDFs genuinely
lack the variable under any short name; a fresh six-variable request for that
box returns five, but `k_index` requested **alone** for the same box returned
`kx` cleanly, twice, in 84 and 27 seconds. The CDS will serve it. What fails is
the six-variable request for this box specifically.

**Do:** ~84 supplementary single-variable requests for the subtropis box,
2018–2024, then merge into the existing `.nc` set.

**Why it matters:** it restores 14 base predictors and with it the exact feature
set the predecessor study used, which is the cost D-01 currently records against
the Bab V comparison.

**Cutoff:** if it has not landed by end of day 2, drop `KX` from both domains,
keep `DROPPED_PREDICTORS = ["KX"]`, and say so in Bab IV. Decide by the date,
not by hope.

### 1.2 — New meteorological parameters (day 1–3)

Widen the candidate set beyond the predecessor's fourteen. Two constraints:

- **The CDS queues per account, not per machine.** Running KX and new-parameter
  requests simultaneously does not double throughput; they compete. Sequence
  them: KX first (84 short requests), new parameters behind it.
- **Every candidate needs a citation before it is requested**, because Bab II
  has to review every parameter Bab IV tests (contract C-6). A parameter
  downloaded without a paper behind it cannot be justified later.

The candidate list is drafted with Component 5 and frozen on day 3.

**Known-refused, do not retry:** ERA5 `"Y"` (yearly) chunking. Measured at
~53.000 fields for one domain-year, which exceeds the CDS cost limit; the CDS
declines it or gives it very low priority. Settled negative result. Quarterly
(~13.000 fields, 56 requests) is the untested middle ground and would need a
`"Q"` branch in `fetch_chunk_hourly` **and** a matching glob in `_files`.

### 1.3 — Drop AOD (day 3, at rebuild)

`AOD_55_ADJ` arrives as one regional **monthly** request per domain and is
broadcast across every hour of that month. At hourly resolution it carries zero
within-month variance, so it cannot inform an hourly prediction.

This is a measurable, statable reason and belongs in Bab IV's feature-selection
subsection. Removing it also removes the "AOD broadcast" limitation the old
record carried.

### 1.4 — MERLIN empty-month re-pull (day 1–2, cheap)

Five MERLIN exports came back empty, covering three months. `fetch_window`
skips a window whose file exists unless `--overwrite` is passed. If the archive
has backfilled since, one command recovers three months.

**Cost:** about an hour. **Needs the device-level VPN.** Untried.

Whatever the outcome, the empty months are **excluded, not filled** — see
Component 2.

---

## Outputs

Handed to Component 2 at the raw freeze:

- `data/raw/era5/` — 84 files per domain, plus the KX supplement if it landed
- `data/raw/power/` — 588 hourly point-year files, plus regional monthlies
- `data/raw/pln/`, `data/raw/merlin/` — unchanged unless 1.4 recovers data
- A one-line statement per source of **what arrived and what did not**, which
  is what Bab III §1 reports.

---

## Done-criteria

- [ ] KX resolved either way, and the verdict recorded
- [ ] New parameters either downloaded or explicitly deferred to Bab VII
- [ ] AOD removal reflected in `ERA5_VARIABLES` / `POWER_PARAMS`
- [ ] MERLIN re-pull attempted and its result recorded
- [ ] No further acquisition after day 3

---

## Carry-forward from v1

| Old ID | Subject | Verdict | Note |
|---|---|---|---|
| D-22 | PLN workbooks, CG-only at source | carried | verified in all seven years; 14,1% positive is a solid CG-only reference |
| D-23 | MERLIN URL codec, 29-day windows, 89 exports | carried | note the RUNBOOK's stride arithmetic is wrong (29 days, not 30) |
| D-24 | POWER point requests, per-year | carried | the AOD broadcast limitation is retired by 1.3 |
| D-25 | ERA5, one request per domain-month | carried | |
| D-26 | Three empty MERLIN months excluded, not filled | carried | re-test cheaply first (1.4) |
| D-17 | PLN clock is local Jakarta time, validated | carried | `SETTLED 2026-09-06` in the config |
| D-01 | `KX` dropped from both domains | **revisited** | reversal is being attempted; new entry either way |

---

## Open, and not closing this week

- **Is the MERLIN export CG-only?** Half-resolved. There is no discrimination
  column. MERLIN is 5,7% positive against PLN's 14,1% on signed peak current;
  IC contamination *raises* the positive fraction, and MERLIN sits well below
  the CG-only reference. Settled only by the KSC Weather Archive's documentation
  for the MerlinCloudToGround product, not by more analysis. **Until settled,
  every subtropis result is provisional and must say so.**
- **Flash or stroke.** PLN groups strokes into flashes via its `Multi.` column;
  MERLIN does not and has no multiplicity column.
- **`data/raw/` backup.** The only permanent-loss risk on the list. Not a
  documentation task.
