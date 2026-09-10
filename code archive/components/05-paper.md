# Component 5 — Paper

**Owns:** the document, the bibliography, the chapter map, the declarations.
**Does not own:** any measured figure. Those come from C1–C4 and are quoted,
never paraphrased from memory.
**Driver:** `paper/Rafly TA/TA.tex` (II4092).

**Do not restate the template or the skill.** Compile order and package list
live in `TA.tex`'s own header comment; what each Bab must contain lives in the
chapter files in `Template Baskara`, in Indonesian; float patterns, `\label`
prefixes, `.bib` shapes and Indonesian style rules live in the `itb-sti-thesis`
skill. What follows is only what none of them knows.

---

## 5.1 — The bibliography port (day 1, before anything else)

`paper/Rafly TA/daftar-pustaka.bib` is currently **byte-identical to the
template's dummy file**, with three fake citekeys. Any `\autocite` written
against it either fails or silently resolves to `laudon2020` — and the second is
worse.

**The port is mechanical and takes about thirty minutes.** Copy all 61 entries
from `paper/Rafly Final Proposal/daftar-pustaka.bib` over the dummy file. Entry
quality does not matter: biber only emits entries that are actually cited, so an
unused entry produces nothing in Daftar Pustaka. Port everything, then fix
content later.

**Four entries are broken and will produce n.d. citations and biber warnings.
Fix or drop during the port:**

| Citekey | Problem |
|---|---|
| `haywardTBD` | empty `journal`, `number`, `volume`, `year` |
| `dualGOES_TBD` | **no author at all**, plus all fields empty |
| `shanTBDMLI` | empty `journal`, `number`, `volume`, `year` |
| `mgstbd2020DLNWP` | author reads `{M. G. S. et al.}` — mangled |

**The port is not the same job as rewriting Bab II.** The port unblocks
citations on day 1. Rewriting the quantum literature is intellectual work on
days 2–3, and it adds and removes entries afterwards, which is normal.

---

## 5.2 — Chapter mapping

Three schemes are in play and they do not match:

| Scheme | Chapters |
|---|---|
| v1 `DECISIONS.md` | 5: III Analisis dan Metodologi, IV Hasil dan Pembahasan, V Penutup |
| **TA template (the one being written)** | **7: I Pendahuluan, II Studi, III Analisis, IV Perancangan, V Implementasi, VI Evaluasi, VII Penutup** |
| Proposal (II4091) | 5, ending Rencana Selanjutnya |

So a `Bab IV` in the old record means **results**, while Bab IV in the document
is **Perancangan**, and the record's "Bab V — Penutup" is the template's Bab VII.
**Every `Bab` field carried forward needs translating, and the mapping is not
one-to-one.** Working translation:

| v1 record says | TA document |
|---|---|
| Bab III (sources, quality, dataset shape) | Bab III Analisis |
| Bab III (architecture, protocol) | Bab IV Perancangan |
| Bab III (implementation, environment) | Bab V Implementasi |
| Bab IV (results, limitations) | Bab VI Evaluasi |
| Bab V (Penutup) | Bab VII Penutup |

**v2 entries use the seven-chapter scheme directly.** No translation layer.

---

## 5.3 — Bab II and Bab VI are one argument

Not reverse engineering. Two halves that must line up:

- **Bab II** establishes the candidate list: here are N meteorological
  parameters the literature links to lightning, one citation each. That answers
  *why N features*.
- **Bab VI** measures them: Spearman, mutual information, redundancy,
  leave-one-out ablation. That answers *why the M that survived*.

**The rule that keeps it honest:** Bab II covers **every** parameter tested,
including the ones that fail. A parameter in the results table but absent from
Bab II looks arbitrary. A parameter reviewed in Bab II that vanishes without
comment looks buried. So the candidate list is frozen and written up **before**
the ablation results are seen (contract C-6).

**Bab II's known weakness is the quantum half, not the "why".** The lightning
and motivation sections hold up; the "what is quantum" material needs
rewriting. Budget days 2–3 for it.

---

## 5.4 — Scope, and the sentence that has never been written

**The positive case for hourly resolution exists only as recollection and must
be written out.** From the bimbingan: *there is too much meteorological variety
within a single month for a monthly aggregate to be a fair prediction target.*
That sentence is the argument. Since hourly departs from the proposal's approved
sparsity mitigation, Bab III has to make the case in full, **alongside the
objections it was taken against rather than instead of them**.

**The framing, settled.** The model maps a meteorological state to lightning in
that state. It becomes a forecast when driven by forecast fields from an NWP
system, which is how operational lightning forecasting works. So *prediksi*
survives and no lead time is needed in the target.

**The caveat that must be stated, in Bab VI or VII.** ERA5 is a **reanalysis**:
it assimilates observations after the fact. Forecast CAPE at +6 h carries error
that analysis CAPE does not. The skill measured here is therefore an **upper
bound on operational skill**, and the gap is however wrong the NWP's forecast
fields are — an amount this thesis does not measure. Declared, it is a strength.
Discovered by an examiner, it is a hole.

---

## 5.5 — Declare, rather than let an examiner discover

Each is defensible only if stated outright:

- every **subtropis result is provisional** until the MERLIN CG/IC question is
  settled;
- the 6-hour reporting window is **a nomination for readability**, not a
  derived optimum;
- Run A uses **one fold** against Run C's three — an ENSO-heavy record, so say
  what that costs;
- **NF-01 will not be met** at hourly resolution, said in advance;
- **NF-02 is met in mechanism and untested end-to-end**;
- which weighting a coverage figure uses — **row or month**;
- **seven hyperparameters have no recorded reasoning**, and that is a
  limitation to state, not a gap to fill;
- ERA5 is a reanalysis (§5.4);
- the **detection-efficiency confound**: subtropis flash counts fall off with
  distance from the Cape at Spearman −0,955 across four orders of magnitude.
  Report it as a confound between instrument response and climatology that
  **cannot be separated using MERLIN alone** — not as an artefact, and not as
  physics.

---

## 5.6 — Compile hygiene

**Toolchain: full MacTeX, not BasicTeX.** `brew install --cask mactex-no-gui`,
then open a new terminal so `xelatex` is on the PATH. BasicTeX ships neither
`algorithm` nor `datetime2-bahasai`, and patching with `tlmgr` stops working
once the next TeX Live release freezes the mirror. That cost a day in August
2026.

**Never trust a compile that "worked" without reading the log.** Two silent
failures have already happened:

- A committed `.bcf` or `.bbl` lets biber succeed against a **stale file from
  the template author's machine**. It reported three citekeys — Baskara's dummy
  bibliography — while `xelatex` had actually died before `\addbibresource`.
  Build artifacts stay gitignored for exactly this reason.
- `Template Baskara/` ships its own `TA.log`. **Read the log in the directory
  you compiled**, never that one; its line numbers describe a different machine.

**Two drivers.** `paper/Rafly TA/TA.tex` is the TA (II4092);
`paper/Rafly Final Proposal/ProposalTA.tex` is the proposal (II4091), with
different geometry, frontmatter and float conventions. **A convention copied
from the wrong one will compile and look wrong.**

**Decimal comma in the deliverable, decimal point in code and JSON.**

---

## Done-criteria

- [ ] `.bib` ported day 1; four broken entries fixed or dropped
- [ ] Candidate parameter list written into Bab II before the ablation runs
- [ ] Hourly-resolution argument written out in full, with its objections
- [ ] Every item in §5.5 appears in the document
- [ ] Compiled from a clean directory, log read line by line

---

## Open, and gating

- **The two title questions.** Is an hourly cell-count still "ground flash
  density", and does "Framework Qiskit" survive the backend choice. **One
  pembimbing conversation, not two.** Run A, if it succeeds, retires the second
  outright by producing a fully-Qiskit result.
- **The MERLIN CG/IC question.** Decides what the subtropis target is called.
  Needed before Bab III.
