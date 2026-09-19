# Why the Annales' text-column pages read short — a negative result

The wind layout yields **5 to 31 rows where the month has 30 or 31**. This is
the largest remaining data gap in the Annales, and four approaches were tried
on 2026-09-15. None of them fixed it. Written down so the next attempt starts
from here rather than from the beginning.

**It is not a wind problem.** The same eight pages re-produced as
`rio-1883-nebulosite` — a layout whose columns are also half text, cloud forms
beside each hour's figure — came back at 6, 9, 12, 20, 29, 30, 31 rows for
months of 28 to 31. The shared property is TEXT COLUMNS: an ink profile finds
row boundaries in a grid of figures and loses them in a grid of words, so the
pitch comes out wrong and the crops straddle rows. Doc 8 page 98 returned cell
counts of 17, 31, 34 and 35 where sixteen were expected — two printed rows in
one rectangle.

The reads themselves are fine. Page 98's first row came back
`9 | 6 | C,C-K,N | 10 | C-K,K,K-N | ...`, which is exactly what the page
prints. **The model reads these tables well; the geometry hands it the wrong
rectangle.**

## What is actually wrong

Not the reading. Doc 8 page 43 is crisp — a person reads its Date column at a
glance — and the rows the pipeline does find come back clean.

**The row chain is not a consecutive run.** On page 43 the chain holds 5 rows
spanning 4 pitches, sitting at the *bottom* of the table: it found the last
five rows, not the first five. On page 107 the chain holds 31 rows spanning
**35** pitches, so it skips some rows and doubles on others while still
reporting `ok=True`. A chain length equal to the day count is therefore not
evidence that the right rows were found.

## What was tried

**1. The Cuyabá oracle** (`--oracle torch`), which fixed the equivalent problem
on the Cuyabá `RESUMO`. It read **13 of 30** day numbers on page 43 and refused
the page. The reason is specific and visible in the scan: the Annales set their
Date column in **old-style figures**, where `1` is a small-capital `I`, `10`
reads as `IO` and `11` as `II`. The oracle was never going to win that. This is
the difference from Cuyabá, where the printed numbers are lining figures and
reading them was the easy part.

**2. Widening the oracle's candidate window.** The window is anchored on the
chain, so a chain that has lost five-sixths of its rows drags the window with
it. Fixed (`resolve_by_oracle` now uses every peak when the chain is under half
the day count) and it moved the read from 11 of 30 to **13 of 30**. Kept,
because the reasoning is right, but it is not the bottleneck.

**3. Fitting a regular grid to the ink peaks** (`wrb.rows.grid_from_peaks`).
The peaks are a *noisy superset*, not a clean series: page 107's 31 peaks have
gaps of 22, 15, 91, 72, 46, 44, 26, 23. The fit is refused on every real page,
which is the correct behaviour for the guard it carries and means it adds
nothing today. Kept and tested; it will work on a layout whose peaks are clean.

**4. Bounding the table with horizontal rules** and dividing by the day count.
The rule detector finds exactly one full-width rule per page — the page edge at
y≈1750. The table's internal rules are not full-width at this threshold.

## What is left to try

- **Teach the oracle old-style figures.** A few dozen labelled Date-column
  crops would probably do it, and it would fix the root cause rather than
  routing around it.
- **Fit the grid to the CHAIN rather than the peaks**, using the chain's pitch
  and accepting that the chain may start mid-table. Page 43's five rows are
  evenly spaced at pitch 24 and sit at the bottom; extending upward by 25 rows
  is arithmetic. What is missing is any way to confirm the extension landed on
  real rows — which loops back to reading the day numbers.
- **Detect the table's internal rules at a lower threshold** than full width.

## What it costs

At v0.3, 220 usable wind rows on 17 pages. The pages are located well enough to
be worth having and badly enough that roughly a third of each month is missing.
Nothing in the file is wrong because of this; there is simply less of it.

---

## 2026-09-19 — the reader localises better than the ink profile

Four approaches failed above, all of them geometric. The fifth is not: it asks
the model that reads the rows where the rows are.

### The 43 were not missing data

First, a correction to what this document and the dataset card implied. The
"43 pages that still refuse" were refused **by one run**, the v0.5 relocation
pass. They were not absent from the dataset — an earlier run had produced
fifteen of them already, at a third of their length. Doc 5 page 411 was
published with 3 of its 31 days and doc 8 page 228 with 4 of 31. The list was
built by diffing a worklist against one output file, which measures what that
run did, not what the dataset holds.

So the work below did not add pages. It replaced bad reads of pages that were
already there, which is worth more per row and was invisible until someone
counted days instead of pages.

### The oracle was the wrong model

`DayOracle` runs **Qwen3-VL-2B-Instruct zero-shot** on the left 22% of a row
and asks, in Portuguese, for the first number. The production reader is the
gen3 LoRA, and reading the day is the first thing it was trained to do: the day
is cell 0 of every row target it ever saw. `--oracle adapter` uses it, and
reuses the model already loaded for the rows rather than holding two 2B models
in memory.

Two measurements shaped it, both counter to the obvious guess:

| | doc5/411 | doc8/346 | doc5/342 |
|---|---|---|---|
| full row, 140 tokens | 61% · 241s | 77% · 456s | 73% · 178s |
| **full row, 10 tokens** | **65% · 64s** | **77% · 96s** | **73% · 70s** |
| left 22% crop, 10 tokens | 35% · 57s | 74% · 86s | 60% · 49s |

**Stop after ten tokens.** The day is the first cell; decoding the other
fifteen columns to read it is waste. Identical day sets, 3.7–4.8× faster.

**Do not narrow the crop.** Showing the reader only the part of the row the day
occupies made it *worse* and made it disagree with the full-width answer on 9
of 19 days. It uses the rest of the row to know what it is looking at. This is
the same shape of result as the Radcliffe crop-scale test, where more pixels
also hurt: the crop the model was trained on is the crop it reads best.

### Half-pitch candidates were destroying the rows they found

When the chain is short, candidates are proposed at half the page pitch so that
rows the peak finder missed still get proposed. Every printed row is then
proposed two or three times, every copy reads the same day — correctly — and
the uniqueness rule threw all of them away as "contested". Doc 8 page 346 read
**24 of its 31 days and kept 5**.

Claimants within a pitch of each other are now collapsed to their midpoint
before anything decides what is contested. They are not competing claims; they
are one row proposed more than once. That page went 5 → 15.

### The ink profile's pitch is the thing that is broken

The refusal message reported only how many days were read, so a page whose
*reading* was fine and whose *bookkeeping* was not looked identical to one the
reader could not read. With the breakdown printed, the real number appeared:

    doc8/346  24 days read, 17 uncontested, 7 contested (0 resolved), 2 non-monotonic -> 15 kept
    doc5/411  20 days read, 13 uncontested, 7 contested (4 resolved), 4 non-monotonic -> 13 kept

And then the decisive one. `loc.pitch` said **15.0 px** and **12.0 px**; the
printed day numbers said **23.1 px** and **18.9 px**. The ink profile cannot
find rows in a grid of words — which is why these pages were refused in the
first place — so *any* test that checks the day assignment against `loc.pitch`
throws away the good measurement to protect the broken one. A first version of
the acceptance rule did exactly that, and had to be removed.

No pitch candidate rescues it either: the best available by peak count gives
peaks whose spacing is 27–69% regular. The peaks are not the rows.

### Verify by reading, not by trusting geometry

So the pitch comes from the days, and the check comes from reading:

1. read every candidate, keep the days that come back unambiguous;
2. fit `y = a + b·day` through those pairs — a spacing measurement that never
   touched the ink profile;
3. **place all N rows on that line and read them again.** If the line is right
   the days come back 1, 2, 3 … in order.

Step 3 is the only guard here that does not depend on the thing that failed,
and it separates cleanly:

| | placed | hold their expected day | verdict |
|---|---|---|---|
| doc 5 page 411 | 31 | **27 (87%)** | accepted |
| doc 8 page 346 | 31 | 5 (16%) | refused |

The four misses on 411 are misread digits on correctly placed rows (`19` for
10, `10` for 19), not misplacements.

### Result

15 of 43 pages localised, **426 rows against the 149 those same pages had
published**, 119 usable against 41. 28 still refuse, and the reason is now
recorded per page: 8 overlap after interpolation, 7 do not lie on one line, the
rest read too few days.

### Two operational faults this exposed

**A 206.9:1 crop killed a three-hour run**, twenty-five pages into forty-three,
because Qwen's image processor refuses anything past 200:1. Over-wide crops are
now padded with white rather than rejected, and — more importantly — a page
that raises is counted as a refused page with its exception recorded instead of
ending the job. Only the `.partial` file saved the 114 rows already written.

**`g4_merge` is the wrong tool for a re-read.** It drops duplicates on the full
provenance key, first occurrence wins, so merging a better read of an existing
page keeps the old rows and appends the new ones past the old row count — the
same printed line published twice under two indices. `scripts/g4_replace_pages.py`
does the swap properly, keyed on how many printed days a read accounts for.
Coverage, not verdicts: the read that accounts for 31 of a month's days saw
more of the page than one that accounts for 9, and that is a fact about the
page rather than a score. On these fifteen the two criteria happened to agree
on the same fourteen pages, which is reassuring and is not the reason.
