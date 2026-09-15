# Why the Annales wind pages read short — a negative result

The wind layout yields **5 to 31 rows where the month has 30 or 31**. This is
the largest remaining data gap in the Annales, and four approaches were tried
on 2026-09-15. None of them fixed it. Written down so the next attempt starts
from here rather than from the beginning.

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
