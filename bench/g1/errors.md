# G1 error taxonomy — Gemini (gemini-flash-lite-latest) vs frozen gold

9/9 gold sheets scored (3,822 cells). Method: for every gold row/column
cell, `wrb.metrics.score()` calls it wrong if the values differ by more
than `TOL=0.05` or one side is missing; a row is a **structural error** if
its date is absent from the prediction entirely, or `>=3` of its 14 cells
are wrong together (the row/column-shift signature). This file covers
every sheet with `cell_acc < 0.95` per the Task 11 brief, plus a
whole-dataset characterization of the structural-error rate and two
cross-cutting findings the coordinator asked to be quantified.

## Per-sheet scores (final, after two harness bugfix rounds — see below)

| gold file | period | cell_acc | structural_err_rate | flagged_recall | n_cells |
|---|---|---|---|---|---|
| 14_22.json | 1885-12 | 0.956 | 0.097 | 0.000 | 434 |
| **14_41.json** | **1886-01** | **0.065** | **1.000** | 0.000 | 434 |
| 14_57.json | 1886-02 | 0.974 | 0.036 | 0.000 | 392 |
| 14_75.json | 1886-03 | 0.977 | 0.000 | 0.000 | 434 |
| 14_90.json | 1886-04 | 0.979 | 0.067 | 0.000 | 420 |
| 14_109.json | 1886-05 | 0.982 | 0.000 | 0.000 | 434 |
| 14_142.json | 1886-07 | 0.970 | 0.032 | 0.077 | 434 |
| **14_179.json** | **1886-09** | **0.790** | **0.967** | 0.000 | 420 |
| 14_212.json | 1886-11 | 0.981 | 0.000 | 0.000 | 420 |
| **aggregate** | | **0.851** | **0.244** | **0.009** | **3,822** |

(cell_acc aggregate is micro-averaged by cell count; structural_err_rate
and flagged_recall are macro-averaged per sheet — see `scripts/run_g1.py
aggregate()`.)

Two sheets fall under the brief's `cell_acc < 0.95` taxonomy threshold:
**14_41** and **14_179**. Both turn out to be **whole-sheet systematic
failures**, not scattered misreads — see below.

## Whole-dataset error-bin counts (571 wrong cells total, 14.9% of 3,822)

| bin | wrong cells | % of wrong | what it is |
|---|---|---|---|
| **structure** | 518 | 90.7% | row missing from pred (date mismatch) or `>=3` cells wrong together in one row |
| **glyph** | ~40 | ~7% | isolated single-cell misreads, small numeric delta, otherwise-correct row |
| **image/illegible** | ~10 | ~2% | precip cell null on one side only (blank/trace rainfall day) |
| **schema** | 0 (residual) | 0% | bad JSON / wrong field name — see "schema bug, found and fixed" below; zero left in the final run |

**Headline: this benchmark's error surface is completely dominated by
`structure`, not `glyph`** — 90.7% of all wrong cells come from just two
whole-sheet failures, not from garden-variety OCR digit confusion. That
reframes what G2 needs to fix: per-cell OCR is already good (isolated
glyph errors are ~7% of the *wrong* cells, i.e. ~1% of *all* cells) — the
open problem is getting the model to reliably apply page-level structural
conventions (date/period header, and the barometer-elision reconstruction
rule) on every row, not to read individual digits more carefully.

### The two whole-sheet structural failures

**14_41 (Jan 1886) — wrong month in every date, correct cell values.**
Every per-cell value transcribed by the model for this sheet is *correct*
(row 1 spot-checked cell-by-cell below); the model wrote `1886-10-01`
instead of `1886-01-01` for every row, so all 31 dates fail to match a
gold row at all → `structural_err_rate=1.0`, `cell_acc=0.065` (only
accidental matches on cells that also happen to be `null` in gold count
as correct). This is a genuine model failure to read the page's own
section header ("Resumo... no mez de Janeiro de 1886") even though the
prompt never asked it to infer the month — it's printed once at the top of
the page and should need no inference at all.

```
gold row 1 (1886-01-01): {"pressure": 756.06, "pressure_max": 756.54, ...}
pred row 1 (1886-10-01): {"pressure": 756.06, "pressure_max": 756.54, ...}
```
Identical cells, wrong month. Not an OCR problem — a page-structure
comprehension problem.

**14_179 (Sep 1886) — barometer-elision reconstruction ignored for 29/30
rows.** The prompt's rule #4 explicitly documents that "the barometer
columns elide the thousands+hundreds digits after the first row" and asks
the model to "reconstruct the elided prefix from the anchor row". The
model got day 1 right, then silently reverted to reading the elided
2-digit printed form literally for every subsequent day:

```
1886-09-02  pressure=764.35       pred=64.35    (elided prefix "7" not restored)
1886-09-03  pressure=763.21       pred=63.21
1886-09-04  pressure_max=763.09   pred=63.09
...(29/30 rows, pressure/pressure_max/pressure_min only)
```
87 of the sheet's 518 structural-bin cells are this single failure mode
repeated down the page. `tmax` on one unrelated row is the only other
wrong cell in this sheet (0.79 cell_acc, not lower, precisely because the
damage is confined to 3 of 14 columns).

### Smaller structural rows in otherwise-healthy sheets

A handful of single-row `>=3`-wrong-cell events occur even in sheets that
score well overall (14_22 days 13/18/23; 14_57 day 4; 14_90 days 5/27;
14_142 day 14). Inspecting these:

- **14_57 day 4 / 14_142 day 14**: a genuine **column shift**, one column
  to the right, starting exactly at `precip`:
  ```
  14_142, 1886-07-14: gold precip=2.7  evap_sol=2.0  evap_sombra=1.5  ozone=4.0
                       pred precip=None evap_sol=2.7  evap_sombra=1.2  ozone=5.0
  ```
  `pred.evap_sol == gold.precip` exactly. Both occurrences land on a day
  where gold's `precip` cell is unusually placed/blank-looking on the
  page — consistent with a blank or hard-to-anchor cell causing the
  model's column tracking to slip by one for the rest of that row.
- **14_90 day 27**: a 3-column shift within the temperature triplet:
  ```
  gold: tmean=21.4 tmax=28.0 tmin=19.9   pred: tmean=28.0 tmax=19.9 tmin=16.1
  ```
  `pred.tmean == gold.tmax` and `pred.tmax == gold.tmin` exactly — the
  model read the row's three temperature values but wrote them into the
  wrong 3 slots.
- **14_22 day 23**: same signature — `pred.tmean(25.1) == gold.tmax(25.1)`.

So the "small" structural rows are the same failure family as the two big
ones (row/column alignment breaking down), just localized to 1 row instead
of a whole sheet.

## Finding 1: the model almost never self-flags its own errors

`flagged_recall` — the fraction of wrong cells the model itself marked
`"uncertain"` in `flags` — is **0.009 aggregate, and exactly 0.0 on 8 of
9 sheets**. Across all 571 wrong cells in the whole run, exactly **one**
was self-flagged (14_142, 1886-07-31, `pressure_min`: gold 756.54, pred
765.54, `flags={"pressure_min": "uncertain"}` — a plausible digit
transposition, not one of the "impossible value" cases below).

**This is a real, load-bearing finding for G2's design**: the prompt
explicitly instructs the model to flag illegible/uncertain cells (rule 1),
and it follows that instruction essentially never even when visibly wrong.
Zero-shot self-reported confidence is not a usable signal for
routing/triage in G2 — any human-in-the-loop design needs an
*independent* uncertainty estimate (e.g. cross-provider disagreement,
range/consistency checks against `validate_sheet`), not the model's own
flag.

## Finding 2: faithful-vs-normalize — does the model "correct" gold's flagged printed errors?

The gold set deliberately preserves 9 cells across 5 sheets where the
*printed* value is physically impossible (e.g. a daily minimum pressure
that exceeds the day's own maximum) — the gold curator confirmed each one
against the scan image and kept the literal printed digit rather than the
"intended" value, per the project's faithful-transcription convention
(`gold/SELECTION.md`). This is exactly the scenario the prompt's rule #2
("Do NOT guess or silently correct an impossible value") targets.

Comparing Gemini's prediction against gold's literal value at each of
these 9 cells:

| sheet | date | column | gold (literal, printed) | Gemini pred | result |
|---|---|---|---|---|---|
| 14_142 | 1886-07-27 | pressure | 752.55 | 752.55 | **faithful** |
| 14_142 | 1886-07-19 | pressure_max | 795.72 | **765.72** | **normalized** |
| 14_212 | 1886-11-03 | pressure_min | 757.43 | 757.43 | **faithful** |
| 14_212 | 1886-11-16 | pressure_max | 750.13 | **760.13** | **normalized** |
| 14_212 | 1886-11-21 | pressure_min | 757.99 | **754.99** | **normalized** |
| 14_212 | 1886-11-26 | pressure_max | 754.52 | **764.52** | **normalized** |
| 14_212 | 1886-11-26 | evap_sombra | 27.0 | **2.7** | **normalized** |
| 14_212 | 1886-11-28 | pressure_max | 753.83 | 753.83 | **faithful** |
| 14_212 | 1886-11-30 | pressure | 742.03 | 742.03 | **faithful** |

**5 of 9 (56%) were silently normalized toward a physically-plausible
value, despite an explicit prompt instruction not to.** Two of these are
uncannily precise: for 14_142/1886-07-19, the gold curator's own note says
"previously silently corrected to 765.72, guessing a misprinted leading
digit '9' for '6' ... reverted" — Gemini produced exactly 765.72. For
14_212/1886-11-26 `evap_sombra`, the gold note says "previously silently
corrected to 2.7 ... reverted" — Gemini produced exactly 2.7. In neither
case did the model flag the cell as uncertain/corrected (0 of these 5 have
any `flags` entry for that column) — it presents the "fixed" reading with
the same confidence as a faithful one, with no signal a substitution
happened.

This is exactly the failure mode the gold set's faithful-transcription
convention exists to catch, and it is real and non-trivial (>50% of the
tested cases here) even in a prompt that explicitly warns against it. For
G2: an explicit instruction is not sufficient to suppress this; treat any
cell that fails `validate_sheet`'s physical-range/ordering checks as a
place to specifically ask the model "transcribe the raw glyph, do not
apply physical reasoning" or to cross-check against a second pass/provider
rather than trust either output alone.

## Schema bug found and fixed before the counted run (not in the numbers above)

Two harness bugs were discovered live during this task and fixed in
`src/wrb/vlm.py` before/during the run — noted here since they are exactly
the kind of "error taxonomy" finding this task exists to surface, even
though the final numbers above are net of the fix:

1. **Column-key naming (schema).** `Sheet.rows[].cells` is a generic
   `dict[str, float | None]` in the pydantic schema, so the JSON Schema
   embedded in the original prompt carried no information about which
   literal key strings to use per column. A first probe run showed the
   model filling in its own plausible English synonyms
   (`bar_mean`/`temp_mean`/`vapour_tension`/...) instead of the gold set's
   real keys (`pressure`/`tmean`/`vapor`/...), which silently pushed
   `cell_acc` to ~0 and `structural_err_rate` to 1.0 for every row **even
   though the transcribed values were correct** — not a transcription
   failure at all, a scoring-key mismatch. Fixed by pinning the exact 14
   keys in the prompt (`SYSTEM_PROMPT`/`_CELL_KEYS` in `vlm.py`).
2. **Non-numeric cell values, JSON "extra data", and read timeouts
   (schema/robustness).** Once real load hit the harness: (a) sheet 14_179
   had the model write `"precip": "Gottas"` (Portuguese "drops" — trace
   rainfall, matching the gold set's own `precip: null` +
   `flags["precip"]="gottas"` convention for exactly this case) directly
   into a numeric slot; (b) sheet 14_142 twice returned extra JSON content
   alongside the real payload — once trailing after it, once (on retry)
   the *prompt's own embedded JSON Schema* echoed *before* the real
   data; (c) sheet 14_57 hit a bare 60s `httpx.ReadTimeout` on a loaded
   endpoint. All three were fixed in `vlm.py`
   (`_normalize_non_numeric_cells`, `_load_json_candidates` trying every
   JSON value found rather than just the first, and a 120s timeout +
   `ReadTimeout` added to the retry loop) with focused respx tests added
   for each (`tests/test_vlm_parse.py`). Without these fixes, 3 of 9
   sheets would have errored out entirely rather than scored.

## 5 worst examples

1. **14_41, every row** (see above) — correct cells, wrong month in every
   date; effectively 0% recoverable score for a sheet that was
   transcribed almost perfectly.
2. **14_179, 29/30 rows** — barometer-elision rule (prompt rule #4)
   ignored after the anchor row; `pressure`/`pressure_max`/`pressure_min`
   off by exactly the elided `7xx` prefix on every affected row.
3. **14_212, 1886-11-16, pressure_max**: gold `750.13` (printed,
   physically impossible per-row) → pred `760.13` — silent normalization
   toward plausibility, no flag.
4. **14_142, 1886-07-19, pressure_max**: gold `795.72` (printed,
   confirmed against the image, physically anomalous) → pred `765.72` —
   matches the gold curator's own explicitly-rejected "guessed intended
   value" digit-for-digit.
5. **14_90, 1886-04-27**: `tmean`/`tmax`/`tmin` shifted one column right
   (`pred.tmean == gold.tmax`, `pred.tmax == gold.tmin`) — a clean 3-cell
   column-shift on an otherwise well-scored sheet.
