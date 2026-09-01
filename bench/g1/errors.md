# G1 error taxonomy — Gemini (gemini-3.5-flash + gemini-flash-lite-latest) vs frozen gold

Two Gemini models were run against all 9 frozen gold sheets (3,822 cells
each): **gemini-flash-lite-latest** (the lite tier — `bench/g1/gemini-flash-lite.json`,
the first run completed, before the controller required a full-flash gate
number) and **gemini-3.5-flash** (`bench/g1/gemini-flash.json`, the
**primary gate result** — see "gemini-flash-latest is unavailable" below
for why this model and not the controller's originally-named one). Method:
for every gold row/column cell, `wrb.metrics.score()` calls it wrong if the
values differ by more than `TOL=0.05` or one side is missing; a row is a
**structural error** if its date is absent from the prediction entirely, or
`>=3` of its 14 cells are wrong together (the row/column-shift signature).
This file covers every sheet with `cell_acc < 0.95` (on either model,
though the two mostly agree on which sheets that is) per the Task 11
brief, plus a whole-dataset characterization and cross-cutting findings.

## gemini-flash-latest is unavailable (documented, not silently swapped)

The controller-mandated model id, `gemini-flash-latest`, was **persistently
503 ("This model is currently experiencing high demand")** for this API
key at run time — confirmed independently three separate times: (1) direct
`curl` checks minutes apart during the initial Task 11 pass, (2) a full
8-attempt/60s-capped-backoff retry through this harness itself
(`src/wrb/vlm.py::_request_with_retry`) exhausting on both probe sheets
without a single non-503 response, and (3) the coordinator's own direct
test. `gemini-3.5-flash` (a current, stable, non-"-latest" Flash model,
confirmed via the live `/v1beta/models` list and via direct `curl`
including image input) was used as the full-flash gate model instead. If
Google resolves the outage, `ENDPOINTS["gemini-flash-full"]` in `vlm.py`
is a one-line swap back.

## Per-sheet scores: lite vs full-flash

| gold file | period | lite cell_acc | lite struct_err | full cell_acc | full struct_err |
|---|---|---|---|---|---|
| 14_22.json | 1885-12 | 0.956 | 0.097 | 0.977 | 0.032 |
| **14_41.json** | **1886-01** | **0.065** | **1.000** | **0.065** | **1.000** |
| 14_57.json | 1886-02 | 0.974 | 0.036 | 0.957 | 0.000 |
| 14_75.json | 1886-03 | 0.977 | 0.000 | 0.993 | 0.000 |
| 14_90.json | 1886-04 | 0.979 | 0.067 | 0.988 | 0.000 |
| 14_109.json | 1886-05 | 0.982 | 0.000 | 0.988 | 0.000 |
| 14_142.json | 1886-07 | 0.970 | 0.032 | 0.993 | 0.000 |
| **14_179.json** | **1886-09** | **0.790** | **0.967** | **0.998** | **0.000** |
| 14_212.json | 1886-11 | 0.981 | 0.000 | 0.990 | 0.000 |
| **aggregate** | | **0.851** | **0.244** | **0.881** | **0.115** |

flagged_recall aggregate: lite 0.009 (macro-mean of per-sheet rates — see
"two denominators" note below; raw whole-dataset figure 1/571 ≈ 0.0018),
full **0.000** — the full model never self-flagged a single one of its
454 wrong cells. Both `n_sheets_scored = 9/9`, zero harness errors on
either run.

**gemini-3.5-flash is the better model on 7 of 9 sheets and dramatically
better on the sheet that broke lite worst**: 14_179 (the barometer-elision
sheet, see below) goes from 0.790/0.967 structural on lite to a clean
0.998/0.000 on full-flash — full-flash applied the prompt's elision
reconstruction rule correctly on every row where lite dropped it after row
1. The one sheet where lite edges out full-flash is 14_57 (0.974 vs
0.957) — full-flash has zero structural rows there but a few more
scattered small glyph misses, so its *aggregate* structural_err_rate
(0.115) is less than half of lite's (0.244) even though the two models'
overall cell_acc gap (0.881 vs 0.851) is modest. **14_41 fails identically
on both models** (both score 0.065/1.000) — see the corrected writeup
below; this is a shared failure mode, not lite-specific.

Two sheets fall under the `cell_acc < 0.95` taxonomy threshold on at least
one model: **14_41** and **14_179**. Both turn out to be **whole-sheet
systematic failures**, not scattered misreads — see below. (Numbers below
are for the **lite** run unless a section says otherwise, since that was
the first fully-analyzed run; the full-flash run's error profile is the
same shape, just smaller, except for 14_179 which full-flash essentially
solved and 14_41 which neither model solved.)

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

**14_41 (Jan 1886) — wrong YEAR AND MONTH in every date; per-cell
transcription is excellent but not perfect.** [Corrected after an
independent review caught an error in an earlier draft of this section,
which is why this correction is being called out explicitly.] Since
`score()` joins by exact date string, a wrong date fails every column in
that row under date-based scoring regardless of whether the cell values
themselves are right — so to check the *actual* per-cell transcription
quality, gold and pred rows below are paired by **position** (row 1 vs
row 1, etc.), not by date:

- **Lite** wrote `1887-10-01` (year **1887**, month **10**) for gold's
  `1886-01-01` — both year and month wrong, and consistently wrong the
  same way for all 31 rows (`1887-10-02`, `1887-10-03`, ...).
- **Full-flash** wrote `1888-01-01` (year **1888**, month correct: `01`)
  for the same gold row — year wrong by 2, but the month this model reads
  correctly. **Both models get the year wrong on this sheet, by a
  different and inconsistent amount** — a shared failure to read the
  page's own printed year (from the section header, "Resumo ... no mez de
  Janeiro de 1886"), independent of whichever model reads the month
  correctly.

Per-cell transcription, position-matched, is very good but **not
perfect** — an earlier draft of this section incorrectly claimed row 1's
cells were "identical" to gold; they are not:

```
gold row 1 (1886-01-01): pressure_min=753.42 (all 13 other cells match pred)
lite pred row 1 (1887-10-01): pressure_min=755.42   <- glyph miss: 3 misread as 5
full pred row 1 (1888-01-01): pressure_min=755.42   <- same glyph miss, both models
```

Across the whole sheet, position-matched: **lite gets 6/434 cells wrong
(1.4%)** — `pressure_min` (twice), `pressure_max` (three rows, each off by
almost exactly 1.00), and `wind_force` (5.9 misread as 5.0) — and
**full-flash gets 4/434 wrong (0.9%)** — `pressure_min` (twice, same two
rows as lite), one `tmean` (25.0 vs 25.6), and the same `wind_force` miss.
Both are small, genuine glyph-level misses, not a wholesale
mistranscription. So the accurate framing is: **per-cell OCR on this sheet
is close to the sheet-wide average (~99% correct if you could match rows
correctly) — the catastrophic 0.065 `cell_acc` score comes entirely from
the date field's year (both models) and, on lite only, month also being
wrong**, not from bad table-reading.


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

`flagged_recall` (lite run) has **two different denominators that both say
the same thing, and are worth keeping distinct**:

- **0.009** is the *aggregate as reported in the per-sheet table above* —
  the macro-average of each sheet's own `flagged_recall` (itself
  `flagged-and-wrong / wrong` **within that sheet**), then averaged evenly
  across the 9 sheets. This is what `scripts/run_g1.py::aggregate()`
  computes and what appears in the summary table.
- **1/571 ≈ 0.0018** is the *raw, whole-dataset* count: of all 571 wrong
  cells across every sheet combined, exactly one was ever self-flagged
  `"uncertain"` by the model.

These aren't inconsistent — the 0.009 macro figure is pulled up almost
entirely by 14_142 alone (`flagged_recall=0.077` on that one sheet, the
only sheet with any self-flagged wrong cell at all; every other sheet is
exactly 0.0), while the raw whole-dataset fraction (0.0018) shows just how
rare that one flag is relative to total errors. Both numbers support the
same conclusion below; **exactly 0.0 on 8 of 9 sheets** either way. The
one self-flagged cell: 14_142, 1886-07-31, `pressure_min`: gold 756.54,
pred 765.54, `flags={"pressure_min": "uncertain"}` — a plausible digit
transposition, not one of the "impossible value" cases below. On the
**full-flash** run, `flagged_recall` is exactly **0.000** on all 9 sheets
and in the raw count (0 of 454 wrong cells self-flagged) — the full model
never self-flagged anything at all.

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

1. **14_41, every row** (see above, corrected) — wrong year in every date
   on **both** models (lite: 1887; full-flash: 1888), plus wrong month
   too on lite (10 vs 01); position-matched per-cell transcription is
   ~99% correct (6/434 wrong on lite, 4/434 on full-flash) — a 6.5%
   `cell_acc` score for a sheet whose table body was transcribed almost
   perfectly, entirely because the date-field year is wrong on both
   models tested.
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
