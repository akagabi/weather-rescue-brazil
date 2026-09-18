# The Radcliffe series: another country, another language, an outside answer key

*2026-09-18*

Four pages of **Astronomical and Meteorological Observations made at the
Radcliffe Observatory, Oxford** (Internet Archive, `astronomicaland03obsegoog`),
produced into the dataset: 103 rows, 83 usable, 1,078 values, 1851–1879.

They matter out of proportion to their size, for one reason. Every other
measurement in this project is self-graded — the gold set is our own labels,
and a checksum test asks whether the model's numbers close the model's own
parse. Oxford has published these same observations, digitised independently
more than a century later. These rows can be marked by somebody else.

## The pages

Thirteen other pages from this volume are on disk and are **not** in the
dataset: they are daily tables, tower thermometers and wind-relation forms with
no profile. Only four are the year-by-month summaries.

| page | table | profile | rows | usable |
|---|---|---|---|---|
| 120 | I — mean monthly barometer, inches | `radcliffe-1855-1879` | 25 | 15 |
| 121 | II — mean monthly dry bulb, °F | `radcliffe-drybulb-1855-1879` | 25 | 21 |
| 122 | III — mean monthly wet bulb, °F | `radcliffe-wetbulb-1855-1879` | 25 | 22 |
| 123 | IV — monthly rainfall, inches | `radcliffe-rain-1851-1879` | 28 | 25 |

Table III was added for this run, by copying Table II's profile and changing
the ranges and the name. No labelled rows, no code. It reached 22 of 25 on
first contact, which is the claim in `docs/ADDING-A-PUBLICATION.md` holding up
on a fourth publication.

## What the external grading says

Fit one relation across all cells — a scale for rain (printed inches vs
published mm), an offset for temperature (°F vs Oxford's homogenised °C) — then
ask how many cells sit on it. A misread digit cannot sit on a line fitted by
every other cell.

| | cells | on the relation |
|---|---|---|
| Dry bulb, **usable** rows | 252 | **100.0%** |
| Dry bulb, **flagged** rows | 48 | 95.8% |
| Dry bulb, all rows | 300 | 99.3% |
| Rain, **usable** rows | 300 | **96.7%** |
| Rain, **flagged** rows | 36 | **44.4%** |
| Rain, all rows | 336 | 91.1% |

**The verdict column predicts agreement with an outside source.** Rainfall rows
the pipeline flags are more than ten times as likely to disagree with Oxford as
the rows it passes. Nothing else in this project has shown that; every previous
defence of `checks_pass` was an argument about internal consistency.

It also settles an old confusion in these documents. The rainfall figure has
been quoted as both 96.7% and 91.1%. Both are right: 96.7% is the usable
subset, 91.1% is every row read including the flagged ones. They are now
labelled wherever they appear.

Reproduce:

    python scripts/g4_external_test.py --case rain \
        --rows data/dataset/weather-rescue-brazil.jsonl

Oxford's files are in `data/reference/oxford/`. They used to be read from a
scratchpad directory that no longer existed, which meant the only externally
graded test in the project could not be re-run by anyone, including us.

## Five conventions the pipeline had never met

Each is declared in the profile and undone in code. None is a special case in
the producer, and each is gated so that no existing layout changes — the test
`test_day_layouts_are_untouched_by_the_index_repairs` asserts this by sweeping
every profile on disk.

**1. The rows are years.** The producer's preflight required `1 <= index <= 31`
before it would read a page, and the rescorer looked for a run of days inside
the same bounds. Both were day-of-month assumptions written as constants. They
now read `Profile.index_range`, which comes from the index column's own
declared `range`, and `index_kind` says what the column counts. Without this
the entire series would have published as `flagged` with `not_a_day_row`
against rows that are perfectly good.

**2. The decimal point is raised.** British scientific printing of the period
sets the separator high on the line: `29·969`, never `29.969`. The reader
reproduces it faithfully, which is correct behaviour, and the parser rejected
every one. Three of the four tables produced nothing but nulls until `·` was
accepted as a decimal separator.

**3. The integer part is elided down the COLUMN.** January reads `29·969`,
`·404`, `·589`, then `30·108` when it changes — and the carry runs down the
column, not along the row. This is a different convention from the `elided`
flag already in the schema, which means a constant prefix always omitted. It
needs the whole page, so it is resolved in the page pass, not per row.

The reading is not asserted, it is checked: under the column carry the printed
Yearly Mean equals the mean of the twelve restored months to ±0.0004 on every
row examined, and does not under any other reading. Along-the-row carry gives
1857 a mean of 30.765 where the page prints 29.765.

**4. The year is set in old-style figures.** Two distinct failures, and they
need different answers:

* *Split.* `1856` comes back as `18 | 56`, one cell too many, every value after
  it shifted a column right. Both halves are correct — this is a segmentation
  failure, not a reading one — so they are joined when the joined digits land
  inside the declared range and the first token alone does not. The repaired
  row's printed checksum then closes, which is the proof: a wrong join does not
  close a twelve-term mean.
* *Truncation.* `1856` comes back as `18`, with the row otherwise complete and
  correct. Nothing in the row can recover the lost digits. The page can: it
  prints one row per year consecutively, and the years that *did* read are
  witnesses to one mapping from row position to year. The gap is filled only
  when at least three of them agree unanimously on one offset, and the row
  records `index_from_page_sequence` saying the value did not come off the
  page. This is the day oracle's rule — printed labels decide, gaps are
  interpolated between confirmed anchors — applied to a column of years.

**5. A double rule is not a column.** Table I rules a heavy double line between
December and the Yearly Mean, and the reader returns an empty cell there:
`... | 688 | null | 29·721 | 785` where the page prints Nov ·688, Dec 29·721,
Yearly ·785. Dropped only when the row is exactly one cell too long, the
surplus is a single interior blank, and every numeric cell lands in range once
it is gone. That took the barometer page from 7 of 25 to 15 of 25.

All five are recorded on the row, never silent. The first four produce
`problems` entries that are *soft* — recorded without disqualifying the row —
because none of them excuses a row from the page's own arithmetic. A wrong
repair does not close a checksum, which is exactly why they can be soft.

## What did not work, and is written down so it is not tried again

**A bigger crop.** The obvious response to a misread year was more pixels. At
scale 3.0 and 4.0 the reader got *worse*: `1855` itself began truncating to
`18`, and digits started dropping (`600` → `6`, `840` → `84`). Scale 2.0 is the
best of the three. More resolution is not more legibility.

**The Dec/Yearly transposition.** Several barometer rows looked transposed
across the double rule, and the hypothesis was tempting because it would have
explained a systematic ~0.08 shortfall in the printed mean. Tested before
implementing: of the 11 rows failing their checksum, exchanging December and
the Yearly Mean rescues **2**. It is not the cause, and a "fix" chosen because
it improves a score rather than because it is true would have silently
corrupted nine rows.

## What is left

* **The barometer table, at 15 of 25, is the weakest thing in the dataset.**
  The remaining ten rows disagree with their own printed mean and are flagged.
  Oxford publishes no pressure series for these years, so there is no external
  key. The fix is a two-band crop that never shows the reader the double rule —
  the same band-cropping that solved the 26-column *Resumo simultaneas* form —
  and it is not built, because `g4_produce.py` reads one band per row.
* **The wet bulb has no external key either.** It rests on its printed annual
  mean. A cross-table check is available and unused: the wet bulb can never
  exceed the dry bulb for the same month, and both tables are in this dataset.
* **These rows are monthly summaries in a daily dataset.** They are not
  unstacked into (year, month) observations and the SEF export does not map
  `jan`…`dec` to a variable code, so it reports them as unmapped rather than
  writing them. That is the honest behaviour, not a silent drop, but it means
  the Radcliffe rows are in the JSONL and not in the SEF files.
