---
pretty_name: Weather Rescue Brazil
license: cc0-1.0
language:
  - pt
  - fr
tags:
  - climate
  - historical
  - meteorology
  - nineteenth-century
  - brazil
  - table-extraction
size_categories:
  - 1K<n<10K
task_categories:
  - tabular-to-text
configs:
  - config_name: default
    data_files: data/dataset/weather-rescue-brazil.jsonl
---

# Weather Rescue Brazil

Daily meteorological observations from Brazilian observatories, 1883–1890,
transcribed from printed nineteenth-century tables by an open 2B model running
offline, with every row carrying its provenance and a quality verdict.

> This is an independent project. It is not affiliated with Zooniverse or with
> the Weather Rescue / Rainfall Rescue projects, whose naming family it
> gratefully follows.

## Citing it

**DOI: [10.5281/zenodo.22876699](https://doi.org/10.5281/zenodo.22876699)** — the concept DOI, which always
resolves to the newest version. To pin this exact release use
[10.5281/zenodo.22876700](https://doi.org/10.5281/zenodo.22876700).

> Bueno, Gabriel (2026). *Weather Rescue Brazil: nineteenth-century weather
> observations transcribed by a small offline model* (0.10) [Data set].
> Zenodo. https://doi.org/10.5281/zenodo.22876699

Citation is not required — the transcriptions are CC0 — but it is how the
work becomes findable.

## What is in it

| | |
|---|---|
| Rows | 7,418 |
| Usable rows (`checks_pass` + `qc_clean`) | **3,998** |
| Values in usable rows | 48,341 |
| Pages transcribed | 258 |
| Period | 1851 to 1890-11 (one page captioned 1893, flagged) |
| Stations | Imperial Observatório (Rio), Santa-Cruz (Rio), Corumbá, Cuyabá, Porto do Maranhão, Radcliffe Observatory (Oxford) |
| Sources | *Revista do Observatório* (1886–1891), *Annales de l'Observatoire Impérial* (1882–1885), *Astronomical and Meteorological Observations, Radcliffe Observatory* (1851–1879) |
| Languages of the printed tables | Portuguese, French, English |

Measured variables: atmospheric pressure (mean, max, min, and for 1883–85 seven
readings a day), air temperature (mean, max, min, in-shelter and unsheltered),
vapour tension, relative humidity, wind direction and force, cloudiness,
rainfall, evaporation, ozone, and for Cuyabá the height of the Rio Cuyabá.

Each row is one printed line: `values_as_printed` (what the page shows, no
silent correction), `values` (the publication's conventions undone in code,
e.g. the barometer's elided leading digit restored), `markers` (words the page
prints instead of a number — `Gottas`, `Inap.` — kept verbatim), `raw` (the
model's literal output), `verdict`, and full provenance including the station
read from the printed caption.

## What "usable" actually means — read this before filtering

**`checks_pass` does not mean the row is correct. It means the row does not
contradict itself**, and *what* verified it differs by publication. This is
measured, not asserted:

| Profile | What verifies a row | Human check against the page |
|---|---|---|
| Annales 1883 (barometer, thermometer, vapour, actinometry) | the **printed arithmetic on the page itself** — e.g. `Oscillation = Max − Min`, checked twice per line; `θ = T − t`, three times per line | **0 errors** in the rows examined |
| Revista (Rio, Santa-Cruz, Corumbá, Cuyabá, Porto do Maranhão) | the **day sequence only** — no arithmetic | **2 errors in 8** (Santa-Cruz) |
| Radcliffe (Oxford) | the **printed annual mean or total**, against the twelve months of the same row | graded against **Oxford's own published series** — see below |

The tier with real arithmetic behind it survived every check thrown at it. The
tier with only a day-order test is where human reading found errors, and it is
23% of what the file calls usable.

### The one part of this file graded by someone else

Everything above is self-graded: our gold set is our own labels, and a checksum
test asks whether the model's numbers close the model's own parse. The 103
Radcliffe rows are different. Oxford has published the same observations,
digitised independently more than a century later
(`data/reference/oxford/`), so those rows can be compared against an outside
answer key. The two series are not numerically identical — Oxford homogenised
theirs — so the test is not equality but whether every cell sits on one fitted
relation, which a misread digit cannot.

| | cells compared | on the fitted relation |
|---|---|---|
| Dry bulb, rows this file calls **usable** | 252 | **100.0%** |
| Dry bulb, rows it **flags** | 48 | 95.8% |
| Rainfall, rows this file calls **usable** | 300 | **96.7%** |
| Rainfall, rows it **flags** | 36 | **44.4%** |

The second and fourth lines are the point. The verdict column is not decoration:
the rows it flags are more than ten times as likely to disagree with Oxford.
This is the first evidence in the project that `checks_pass` predicts agreement
with an independent source, rather than only internal consistency. Reproduce it
with `scripts/g4_external_test.py --case rain --rows <the dataset>`.

Two caveats that belong next to those numbers. The comparison covers rainfall
and dry bulb only, because those are the two series Oxford publishes — the wet
bulb and barometer tables have no external key and rest on their printed
checksums alone. And 336 rainfall cells is a small sample; the dry-bulb 100% is
252 cells, not a guarantee. Two misread digits are known and recorded:
`tmin` 21.16 for a printed 21.3, and `cloudiness` 0.01 for a printed 0.00, both
in Santa-Cruz. They are in `data/verify/corrections.jsonl` and the rows carry
`human_verified: true`.

**Recommended filter:** `verdict != "flagged"`. For the strictest subset, add
`padded_trailing == false` and restrict to the Annales profiles.

## Known limitations

- **The Radcliffe tables are monthly summaries, not daily observations, and
  their rows are YEARS.** Four pages, 103 rows, 83 usable: one row per year
  with twelve monthly columns and a printed annual mean or total. They do not
  belong in a daily time series without being unstacked first — the row's date
  is its `year` value, and `period`/`period_end` give the span the *page*
  covers, not the row. Units are as printed: inches and degrees Fahrenheit.
- **The Radcliffe barometer table is the weakest thing in this file**: 15 of
  its 25 rows pass, against 84–89% for the other three. The cause is measured
  and named rather than guessed. Its integer part is elided down each column
  (`29·969`, then `·404`, `·589`, then `30·108` when it changes), its decimal
  point is set high on the line, and it double-rules between December and the
  Yearly Mean — which the reader takes for an empty column. The first two are
  undone in code and tested; the third is repaired only when the row is
  otherwise exactly right. What remains is ten rows that disagree with their
  own printed mean, and they are flagged. Oxford publishes no pressure series
  for these years, so there is no external key to appeal to. A two-band crop
  that never shows the reader the double rule is the fix, and it is not built.
- **1882 comes from a second Annales volume** (doc 5), added after the first
  release: 496 usable rows, 202 of them 1882, in the same French daily layouts.
  Checked the same way as the rest — 2 climatologically impossible values in
  3,417 (0.06%), no ordering violations.
- **509 rows were re-dated after v0.2** and carry `period_as_published` with
  the wrong month they shipped with. The caption parser matched month names by
  substring, and *Rio de Janeiro* contains *janeiro*, so 16 Annales pages headed
  "du mois de Mars/Mai/Juillet/Août/Octobre/Novembre/Décembre … DE RIO DE
  JANEIRO" were dated to January. Only the month was wrong; the values, the
  page, the station and the verdicts are unchanged, and only doc 5 (the v0.2
  addition) was affected. Fixed in `wrb.caption`, corrected by
  `scripts/g4_audit_periods.py`, frozen as **v0.2.1**.
- **92 pages had read short and 49 were recovered in v0.5.** A page whose row
  locator finds 5 rows of 30 is not damaged — doc 8 page 43 is crisp, and a
  person reads its Date column at a glance. What defeats the detector is a
  layout whose columns are text: an ink profile finds row boundaries in a grid
  of figures and loses them in a grid of words. Re-run with oracle localisation
  (printed day numbers decide, geometry only proposes) plus candidates proposed
  at half the pitch, those 92 pages gave 1,303 rows where they had given 1,039,
  and 803 of the new ones are usable. 43 still refused that run.
- **Fifteen of those 43 were being published at a third of their length, and
  v0.7 re-reads them in full.** They were never missing — an earlier run had
  produced them, badly. Doc 5 page 411 was published with **3 of its 31 days**,
  doc 8 page 228 with 4 of 31. Localised by the production reader rather than
  by the ink profile, the same fifteen pages give **426 rows covering 31 days
  where they gave 149 covering 9**, and 119 usable where they gave 41. Fourteen
  replaced what was published; one covered fewer days than before and was left
  alone. `docs/g4-wind-locator.md` has the method and `scripts/g4_replace_pages.py`
  the swap, which is keyed on **how many printed days a read accounts for** and
  not on how many rows pass QC — choosing the read with the better verdicts
  would be choosing by the score.
- **Five of those fifteen produce nothing usable, and that is the QC working.**
  They are layout mismatches, not localisation failures: doc 5 page 342 is a
  thermometer table assigned the wind profile, doc 8 pages 317 and 372 read ten
  cells where the barometer profile declares fourteen. The rows are localised
  correctly and every one of them is `flagged`. They are kept for transparency,
  like the other whole-profile sections below.
- **A further 26 pages were read short and never re-tried, and v0.8 re-reads
  them.** The same localiser, on pages that had simply never been through it:
  18 produced, **441 rows against the 328 those pages had published**, and 13
  replaced what was there. Two of them now read their month end to end with
  nothing flagged at all — doc 5 page 327 gives 22 rows and 22 `checks_pass`
  where it published 31 rows, 22 days and 13 usable. Five pages covered no more
  days than before and were left alone.
- **A layout that prints two rows per day cannot be oracle-localised, and now
  says so.** Corumbá writes two readings a day, so a month is 62 rows but only
  31 distinct day numbers exist, and the oracle keys its assignment by day —
  at most 31 can ever be confirmed against a bar of 0.55 × 62 = 34. Doc 16 page
  72 read 30 of its 31 days, which is near perfect, and was refused for it. No
  Corumbá page needs this today so the fix is not built; what is fixed is the
  silence, because an unreachable bar looked exactly like a page the reader
  could not read.
- **A single bad row assignment was condemning whole pages, and v0.9 stops it.**
  Doc 5 page 313 read **31 of its 31 days**, all in order, and was refused
  twice over — once because one pair of rows sat 9px apart, once because that
  same pair dragged the least-squares line past tolerance. Thirty good rows
  thrown away to avoid one bad one. The line is now fitted robustly (drop the
  worst day, refit, while a majority still supports it) and an overlap sends
  the page to that line rather than refusing it. 13 more pages produced, **400
  rows against the 149 they had published**.
- **23 pages are still refused, and the reason is recorded per page.** Fourteen
  never read enough days to fit a line at all, five fitted a line that did not
  survive placing the rows and reading them back, three do not lie on one line,
  and one is Corumbá (above). The Annales set their dates in old-style figures
  — 1 as a small-capital I, 10 as IO — and that remains the root cause
  (`docs/g4-wind-locator.md`).
- **Two rows cannot be the same day.** On a layout that prints one row per day,
  a day appearing twice means one of those rows is not a data row — doc 5 page
  309 reads 1…31 and then a thirty-second row claiming 28. Where the rest of the
  page is in order the impostor names itself, and only it is flagged; the real
  row keeps its verdict. 578 rows across 169 pages, of which 84 were previously
  counted usable. The check is skipped on layouts that print two rows per day
  (Corumbá), where a repeated day is the form working correctly.
- **A wind-direction cell must hold a direction.** The wind layouts print no
  summary column, so until v0.2.2 their only check was the force range (0–6).
  A direction cell is not free text, and one holding a force figure, a
  temperature or a fragment of a caption is a misread the page can refute. It
  names the cause of 291 rows across 34 pages — 285 of which the earlier checks
  had already flagged for other reasons, and 6 of which it found on its own.
  Eight of those pages fail as a whole: they were assigned the wrong layout
  entirely (doc 5 page 351 is a thermometer table produced as wind). None of
  them were ever in the usable set.
- **Wind was almost entirely missing until v0.3, and it was a bug rather than
  the source.** Every fifteen-cell wind page was rejected by the
  layout-assignment step for containing compass points — which is what a wind
  table contains — so the only "wind" pages that got through were pages
  *misidentified* as wind. Of the 197 wind rows in v0.2.2, **eleven** were
  usable, on two pages. v0.3 adds 16 recovered pages and the figure is now
  **220 usable rows on 17 pages**, spanning 1883–1885. The remaining wind gap
  is the row locator rather than the assignment: a wind row is mostly compass
  text and carries far less ink than a row of figures, so the detector finds 5
  to 30 rows where the month has 30 or 31. The oracle used at Cuyabá — printed
  day numbers decide, geometry only proposes — would close it.
- **A 31-month gap.** 1887-01 through 1888-11 are absent, and it is a source
  limitation, not a pipeline failure: those volumes are not digitised in the
  accessible collection (`docs/g3-corpus-scope.md`). The series is not
  continuous across 1883–1890.
- **3,420 of 7,418 rows are `flagged`**, including whole-profile sections
  (`rio-1883-nebulosite`, `rio-1883-vento`) where the printed layout puts two
  values in one cell and the model's column count is unreliable. These are kept
  for transparency, not for use.
- **One page of prose was removed in v0.10.** Doc 14 page 140 is a Portuguese
  article whose caption belongs to a table on the neighbouring leaf, and 30 of
  its lines had been produced as weather rows — `"justamente no meio de Junho
  apresenta sua fr-"` was in this file. Every one was `flagged`, so a consumer
  following the recommended filter never saw them, and the preflight rejects
  that page now (0 of 30 days). But the rows from the run that predated the
  preflight were never cleared out. Keeping a flagged row is defensible when it
  is an observation the checks could not confirm; it is not defensible when the
  row is not an observation at all.
- **Station coordinates are not yet good enough for a reanalysis feed.** None
  of the six was read from the publications; all carry `verified: false`, so
  the SEF export writes them as `NA`. One was also plainly wrong and is fixed
  in v0.11: the Imperial Observatório was recorded at the Morro de São
  Januário site, which it did not occupy until **1913** — 23 years after these
  observations end. From 1850 to 1920 it stood on the **Morro do Castelo**, a
  hill since levelled. The longitude now used, 43°10′21″W, is the one the
  observatory published for itself and is already this project's reference
  meridian; the latitude is the Castelo site rather than a printed value, so
  the flag stays false until someone reads the position off the page.
- **A barometer reading its station's altitude cannot produce is now flagged.**
  `wrb.qc.pressure_implausible` had existed for some time and was called only
  by a test, so it never reached a verdict. Correcting the observatory's
  altitude from 30 m to 61 m exposed what that cost: doc 15 page 89 day 1
  reads 781.6 mmHg (~1042 hPa), which Rio does not do at any altitude. It had
  been `checks_pass` because mean, max and min all misread the same elided
  leading digit, so the row agreed with itself, and it cleared the old
  tolerance by 0.4 mmHg against the wrong altitude.
- **No row in this file has been verified line-by-line by a human.** The frozen
  gold set — nine pages, triple-transcribed — is a separate evaluation corpus
  and is *not* part of this dataset.
- **The rows are not byte-reproducible from the current code.** The row
  locator's answer has drifted since the Revista rows were produced, so their
  crops cannot be regenerated exactly. See `data/dataset/version.json` for the
  frozen fingerprint of the published state.
- **Provenance detail:** 64 rows carry a station assumed from the worklist
  rather than read from a printed caption, and say so in `station_source`.

## How it was made

Five stages, all open: page fetch from DocVirt (polite, resumable, no CAPTCHA
circumvention); a geometry sweep to find ruled tables; per-publication profiles
declaring the printed layout **as data**, so a new publication is a JSON file
and not code; a Qwen3.5-2B LoRA fine-tuned locally on 400 hand-read rows,
reading one row crop at a time at 99.08% cell accuracy on the frozen gold (the
same ceiling as the three-vote API consensus it was distilled against); and a
validator layer of physical ranges, printed checksums, and shape checks.

Total API spend across the whole project: **US$1.56**.

## Provenance and rights

Images: **Biblioteca Digital de Obras Raras do Observatório Nacional, via
DocVirt.** Works of 1886–1890, public domain in Brazil (Lei 9.610); no rights
are asserted over the underlying observations here.

**The observations themselves are not ours to licence** — they come from
nineteenth-century Brazilian government publications and are in the public
domain (Lei 9.610). Anyone may use the numbers for any purpose.

What this project added — the transcriptions, the per-row verdicts, the
corrections and the provenance — is dedicated to the public domain under
**CC0 1.0**. Use it for anything, commercial or not, with or without credit.
The pipeline code and the model weights are **Apache-2.0**. See
[LICENSE](LICENSE).

A waiver rather than a licence, deliberately: a faithful transcription of a
printed public-domain table exercises no creative selection, and Lei 9.610
art. 7º §2º says protection "não abarca os dados ou materiais em si mesmos".
Until 2026-09-17 these were CC BY-NC 4.0, which asserted a right that probably
did not exist — this card said "anyone may use the numbers for any purpose"
three lines above the NC clause — and which barred the dataset from ISPD,
Scientific Data, Dryad, Figshare and Brazilian federal open data while quietly
lowering its ingestion priority at C3S.

Please carry the attribution:

> Acervo: Biblioteca Digital de Obras Raras do Observatório Nacional, via
> DocVirt. Digitalizado e transcrito pelo projeto Weather Rescue Brazil.

## Repository layout

| Path | |
|---|---|
| `data/dataset/weather-rescue-brazil.jsonl` | the dataset |
| `data/dataset/README.md` | the working dataset notes, with every correction recorded |
| `data/dataset/version.json` | frozen fingerprint of the published state |
| `data/verify/` | human judgements and corrections against the page images |
| `profiles/*.json` | one file per printed layout |
| `docs/` | gate reports, blind tests, and the method findings |
| `scripts/g4_merge.py`, `scripts/g4_rescore.py` | rebuild the dataset from stored model output, no model and no images |
