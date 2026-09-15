# The `Resumo mensal das observações simultaneas` form

A landscape sheet in the *Revista do Observatório* (docIds 15 and 16) carrying
**four station blocks**, each of three dekadal rows and a month row. It is the
widest-reaching layout in the corpus: ten pages found so far name **São Paulo,
Bahia, Ouro Preto, Santa Cruz, Maceió, Recife (Ponte B. de Macedo), Cidade do
Rio Grande** and the cruiser **Almirante Barroso**, against a dataset that is
otherwise almost entirely Rio de Janeiro.

## Three things it breaks

### 1. It is wider than the reader

26 printed columns — `Decadas`, five measurements, seventeen wind-frequency
counts (`Calma` plus sixteen rhumbs), `Força`, `Nebulosidade`, `Chuva total`
and `NOTAS` — against a reader reliable to about sixteen.

The fix was not training. Cropping **only the band that carries the
measurements** (`band_x_frac` in the profile) turns one unreadable row into one
readable row. Measured on docId 16 page 41 with the `gen3` adapter and **no
training on this layout at all**:

| | printed | model |
|---|---|---|
| 1ª | `697.68  22.84  25.13  17.97  80.1` | `697.68  22.84  25.13  17.97  80.1` |
| 2ª | `699.12  24.04  26.90  18.52  77.3` | `699.12  24.04  26.9   18.52  77.3` |
| 3ª | `697.71  22.02  25.60  18.50  82.3` | `697.71  22.02  25.6   18.5   82.3` |
| Mez | `698.50  23.03  25.88  19.67  79.9` | `698.5   23.03  25.88  19.67  79.9` |

**24 of 24 cells correct.** The only differences are trailing zeros the
compositor set and the reader does not (`25.6` for `25.60`), which is
formatting, not a misreading. The width was the problem, not the hand.

The wind counts, force, cloudiness and rainfall are a second band and are
**not** in this profile. They are recorded as unread rather than guessed at.

**The band is a fraction of the table, not of the page.** The first version
declared it as page-width fractions measured on docId 16 page 41. It read that
page perfectly and returned *nothing at all* on docId 15 page 126: the two
scans do not share a margin — the table's left rule sits at **0.133** of the
width on one and **0.102** on the other — so a band fixed on the first clips
the `Decadas` column on the second, and without the printed label no row can
be identified. The band is now anchored on each page's own outermost rules
(`wrb.blocks.band_from_rules`), and a page whose rules do not bound a plausible
table is **refused** rather than read at a guessed offset. One of the ten,
docId 15 page 199, is refused on exactly that ground.

### 2. The rows are decided by their printed label

Geometry proposes bands of ink in the barometer column; the label read out of
the first cell — `1ª`, `2ª`, `3ª`, `Mez` — says which of them are data rows
and where each block begins.

Grouping by pitch alone was tried first. Across the ten known pages it
recovers complete blocks on **3 of 10**: the three dekad rows sit at one pitch
and the `Mez` row a wider gap below, the gap varies with how many lines of
`NOTAS` the block carries, and scan contrast merges adjacent rows on some
pages entirely. The labels get all ten. This is the same finding as the
printed day numbers at Cuyabá (`docs/g4-cuyaba-locator.md`): **geometry
proposes, the print disposes.**

A block is only accepted when its labels read exactly `1, 2, 3, Mez`. Half a
block is worse than none — its `Mez` would be checked against the wrong three
dekads.

That strictness has a cost that took two runs to find. Candidates are proposed
generously — a run of ink taller than one row is **split** rather than dropped,
because a merged run loses both rows while a bad split only costs a crop that
comes back unlabelled — and so one printed row can arrive as two crops that
both read back as `1`. The block's labels then come out `1, 1, 2, 2, 3, 3,
Mez`, which is not `1, 2, 3, Mez`, and the whole block is discarded. **docId 15
page 126 returned one block of its four** while its band, its reads and its
station header were all correct. `dedupe_labels` collapses consecutive
same-label candidates, keeping the fuller read; it is safe by the form's own
structure, since within a block the labels run strictly `1, 2, 3, Mez` and
between blocks a `Mez` is followed by a `1`.

The **probe column** — where to ask "is there a row here" — stays a fraction of
the page, not of the table. Deriving it from the rules the way the band is
derived made it worse: the outer rule the detector returns is the printed frame
on some scans and the table edge on others, so a span computed from it landed
on the frame line itself and the ink profile locked onto the rule instead of
the numbers. The probe only has to land somewhere inside the numeric columns,
and a fixed `(0.150, 0.205)` does on all ten pages.

### 3. The station belongs to the block, not the page

Every layout before this one held a page to one station, named in the caption,
and the producer stamped it on the whole page. Here one sheet carries four, and
docId 16 page 41 is São Paulo, Bahia, Ouro Preto and Santa Cruz in that order.
A page-level station would be wrong for three blocks in four.

Each block is headed by its own printed line:

```
Estação, S. Paulo; Observador, Alberto Loefgren; Latitude, 23°36' S;
Longitude, 3°28' W; Hora local, 8h29m27s; Alt. do Bar. 735m42
```

A block that continues the station above it prints only a month line and **no
header at all** (docId 15 page 142's second block is Maceió's July under
Maceió's June). Such a block inherits the station above it and the row records
that it was inherited; a headerless block with nothing above it gets **no
station**, which is a gap to report rather than one to fill.

The header line also carries the coordinates — see `docs`-adjacent
`wrb/stations.py` for the two ways to misread them (longitudes are measured
from Rio, and a bare `2m W` is minutes of *time*).

## What the page asserts about itself, and how loosely

The `Mez` row is the month's summary of the three dekads, and
`monthly.aggregate` checks each column against it. But unlike the Revista's
daily pages — where a mean over 31 equal days reproduces to the last printed
digit — **this form's arithmetic does not close exactly**. Measured on docId 16
page 41, block 1 (São Paulo, October 1889):

| column | mean of the dekads | printed `Mez` | difference |
|---|---|---|---|
| barometer | 698.17 | 698.50 | +0.33 |
| dry bulb | 22.97 | 23.03 | +0.06 |
| t. max | 25.88 | 25.88 | 0.00 |
| humidity | 79.90 | 79.90 | 0.00 |
| **t. min** | **18.33** | **19.67** | **+1.34** |

The dekads cover 10, 10 and 11 days, and the `Mez` appears to be computed from
all the daily observations rather than from the three rounded dekad figures, so
a few tenths of disagreement is the form's normal state. `monthly.tolerance`
therefore takes a **per-column** number, calibrated from the pages themselves
rather than assumed — a tolerance tight enough for the daily pages flags every
row here.

That last line is the point of keeping the check at all: four columns confirm
themselves and the fifth raises its hand, at an order of magnitude above the
noise.

## These are not daily observations

Every row here is a **dekad** (a third of a month) or a **month**, not a day.
The published `weather-rescue-brazil.jsonl` is described as daily observations
and it should stay that way: mixing summaries into it would misstate what the
file is, and a consumer averaging it would double-count. They belong in a
companion file at a different temporal resolution, declared as such.

## Files

| | |
|---|---|
| `profiles/revista-resumo-simultaneas.json` | the band-A profile, 6 columns |
| `src/wrb/blocks.py` | block geometry, the label oracle, station inheritance |
| `src/wrb/stations.py` | the printed header line and its coordinates |
| `scripts/g4_simultaneas.py` | the producer |
| `data/g4/worklist_simultaneas.json` | the pages |
