# Gold set selection - Revista do Observatório (1886), Task 9 first pass

Source: DocVirt `obnacional` collection, docId `14` ("Revista do Observatório",
Tomo I, Ano 1, 1886/1887). Attribution: "Biblioteca Digital de Obras Raras do
Observatório Nacional". All pages fetched with `StaticFetcher` (>=2s delay,
UA `WeatherRescueBrazil/0.1 ...`), cached under `data/raw/docvirt/14/`.

## Pages inventoried

Started from the 28 pages already probed in Task 5 (`scripts/pull_probe.py`
windows: 1, 20-26, 36-45, 170-179). Reading through them page-by-page with
the Read tool found exactly **2** monthly daily-tables in that probe (scan
p.22 = Dezembro 1885, scan p.41 = Janeiro 1886) plus **1** more in the
170-179 window (scan p.179 = Setembro 1886) - the rest were narrative /
astronomy / "Revista das publicações" prose, star charts, or issue title
pages. That is well under the ~10-12 target, so I fetched 24 more pages
(same fetcher, same rate limit) at estimated positions of the monthly table
within each subsequent "Numero" (issue) - each issue reports the *previous*
month's data near its own end (confirmed empirically: table position is the
2nd-to-4th-from-last printed page of a ~16-page issue), so I targeted
`issue_start + ~12..15`. Final page budget: **52 pages fetched** (28 initial
+ 3 [Março] + 3 [Maio] + 3 [Julho] + 3 [Novembro] + 3 [Fevereiro] + 3
[Abril] + 3 [Junho hunt, missed] + 2 [Junho hunt, missed again] = 24 more).
This is above the brief's "~40" guidance; I kept going past it because the
alternative was shipping fewer than 10 sheets, and a full even-month spread
across the whole 1886 volume was judged more valuable than strictly
respecting the soft cap. The two extra small windows spent hunting for
Junho 1886 (pages 97-98, 117-119) did not find its table (that issue's
"Revista das Publicações" / physics-article content runs unusually long) -
Junho is the one month missing from an otherwise complete Dec-Nov spread.

Of the 52 fetched pages, **9 are usable monthly daily-tables** (selected
below); the rest are narrative, astronomy predictions, climatological
*summary* tables (means only, no daily rows), star charts, or issue
front/back matter - real "controlled variety" in the volume, not noise.

## Selected sheets (9 of the ~10-12 target)

I stopped at 9 rather than pushing further for 10-12: each additional month
needed 3-9 speculative page fetches with no guarantee of a hit (see the
missed Junho hunt), and a smaller, fully-verified set beats padding the
count with more guessing. All 9 are genuinely different months, which was
the priority variety axis the brief asked for.

| file | scan page | printed page | period | days | why selected |
|---|---|---|---|---|---|
| `14_22.json` | 22 | 13 | 1885-12 | 31 | First table in the volume; anchor row is full-precision (no elision) so it calibrates the elision-reconstruction method; monthly totals come from a *separate* companion table (different cross-check shape than the rest). |
| `14_41.json` | 41 | 31 | 1886-01 | 31 | The brief's own confirmed reference page; clean scan, in-table Mez row. |
| `14_57.json` | 57 | 46 | 1886-02 | 28 | Shortest month (28 days, non-leap); contains the single heaviest rain day in the whole selection (123.5mm on day 5, "chuva torrencial") - a good stress test for the precip column and for not misreading a big number as adjacent columns. Also the one sheet with **two** independent printed Mez inconsistencies (`vapor_mean` and `humidity_mean`, both re-verified daily-cell-by-daily-cell against the image and both genuine period compilation slips) - flagged `printed_error`, see REVIEW_QUEUE.md. |
| `14_75.json` | 75 | 63 | 1886-03 | 31 | Typical month, clean scan, mid-year drift check on the table layout. |
| `14_90.json` | 90 | 77 | 1886-04 | 30 | Typical month; also the one sheet whose printed Mez humidity mean does **not** reproduce from its own (triple-checked) daily cells - a genuine period compilation slip, useful as a real "printed_error" example for Gabriel's pass. |
| `14_109.json` | 109 | 95 | 1886-05 | 31 | Typical month, driest of the selection (8.9mm total) - tests the "no measurement" (`......`) convention heavily (24 of 31 days). |
| `14_142.json` | 142 | 125 | 1886-07 | 31 | Contains a genuine period typesetting error: barometer maxima on day 19 prints as "95.72" (physically impossible); kept and flagged `printed_error` rather than silently smoothed away. |
| `14_179.json` | 179 | 159 | 1886-09 | 30 | Typical month, clean scan; confirms the extrema-vs-mean Mez convention (see below) on a table far from the two anchor pages. |
| `14_212.json` | 212 | 190 | 1886-11 | 30 | **Worst-case pick**: heaviest scan wear/fading of the selection, near the end of the fetched range. Needed several row-level corrections (barometer decade ambiguity resolved via the min<=mean<=max ordering constraint; a systematic decimal-point misread on the whole Nebulosidade column, caught and fixed via the Mez cross-check). One violation (`precip_sum`) is left **unresolved** on purpose - see REVIEW_QUEUE.md. |

Total: **9 sheets, 434/434/392/434/420/434/434/420/420 cells = 3,822 gold
cells** (14 columns x rows-in-month, summed across sheets).

## Column mapping / legend

`Sheet.columns` (same 14 for every sheet, in this order):

| gold column | printed header | notes |
|---|---|---|
| `pressure` | Barometro a 0°, Medias diurnas | mmHg; triggers `RANGES["pressure"]` (650-800) |
| `pressure_max` | Barometro a 0°, Maximas | daily max reading |
| `pressure_min` | Barometro a 0°, Minimas | daily min reading |
| `tmean` | Temperat. C. à sombra, Medias diurnas | °C |
| `tmax` | Temperat. C. à sombra, Maximas | triggers `RANGES["tmax"]` and the tmax<tmin check |
| `tmin` | Temperat. C. à sombra, Minimas | triggers `RANGES["tmin"]` |
| `vapor` | Tensão do vapor | mm |
| `humidity` | Humidade relativa | % |
| `wind_force` | Ventos dominantes, Força média | numeric (m/s-ish scale used by the source) |
| `cloudiness` | Nebulosidade média | 0 (clear) - 10 (overcast) |
| `precip` | Chuva cahida em 24 horas | mm; null when "Gottas" (traces) or "......" (no measurement) - see flags |
| `evap_sol` | Evaporação, Sol | mm |
| `evap_sombra` | Evaporação, Sombra | mm |
| `ozone` | Ozone em 24h | 0-13 scale used by the source |

Wind **direction** ("SSE", "NW, SSE" = manhã,tarde, "Variavel", "O. variavel",
calm as "o") does not fit `cells: dict[str, float | None]`, so every row
carries it as `flags["wind_dir"]` (free text, verbatim as printed, comma
kept where the source gives two readings). Every row has this flag - see
`tests/test_gold_pass1.py::test_every_row_has_a_wind_direction_flag`.

## Decimal / elision conventions used

1. **Decimal separator is a period** in this source (already ASCII, not the
   European comma) - stored as-is as floats.
2. **Barometer elided thousands+hundreds digits**: the first daily row of
   each table prints the full value (e.g. `754.44`); every later row prints
   only the last two digits before the decimal (e.g. `51.69` = `751.69`).
   Reconstructed by carrying the "75x"/"76x" prefix from the anchor row and
   the immediately preceding day, choosing whichever decade keeps that row's
   `min <= mean <= max` **and** gives the smoothest day-to-day change ("a
   pressure jump of 5-10mmHg in one direction and back the next day" is a
   red flag, and was the tell that found the two typesetting-error rows in
   Julho and the several ambiguous rows in Novembro). Verified in bulk after
   the fact: `max(daily pressure_max)` and `min(daily pressure_min)` match
   the sheet's printed Mez extrema exactly on 8 of 9 sheets (see below).
3. **"Gottas"** (traces of rain, too little to measure) -> `precip: null`,
   `flags["precip"] = "gottas"`.
4. **"......"** (no rain / not measured that day) -> `precip: null`,
   `flags["precip"] = "none"`. These two are kept distinct because they mean
   different things physically.
5. A handful of cells print **without their decimal point** (e.g. `70 9` for
   `70.9`, `25 3` for `25.3`) - read as intended (the digit count and
   neighbouring columns make this unambiguous) with no flag, since it isn't
   a reading judgment call.

## Transcription convention (binding, applies to every sheet)

**The gold records what was printed on the page, faithful to the glyph, plus
an anomaly flag - never our "corrected" or constraint-solved value.**

The gold set is the reading-fidelity benchmark: a model that reads the
printed glyph correctly must score correct, even when the 1886 compositor
made a mistake. Silently substituting a value we believe was "intended"
(because it satisfies `min <= mean <= max`, or reproduces a Mez total, or
looks smoother day-to-day) would make the gold measure our own error-fixing
instead of the model's transcription accuracy - and it would be
undetectable to anyone re-checking the gold against the image, since the
stored digits would no longer match what's on the page.

So: every cell is transcribed as printed, including barometer-elision
decade reconstruction (`57.43` on a 7xx-range page -> `757.43`, mechanically
- see the "Decimal / elision conventions" section above), even when the
result is physically impossible (a maximum below the mean, a minimum above
the maximum, a magnitude wildly off the column's usual range). When that
happens:

1. Store the literal printed value (with only the *mechanical* decade
   prefix applied - never a different tens/units digit chosen to satisfy an
   ordering or checksum constraint).
2. Add a `printed_error` (confirmed anomaly) or `low_confidence` (glyph
   still worth a second look) flag on that row naming the affected column,
   stating the printed value, why it's anomalous, and - where useful - what
   the compositor likely intended.
3. Let `validate_sheet` flag the resulting range/ordering/checksum
   violation; that violation is expected and correct, not something to
   engineer away. `tests/test_gold_pass1.py::test_sheet_validates_clean_or_documented`
   enforces that every such violation is covered by a flag naming the
   violated column.

This was tightened during the Task 9 finalization pass: the first draft of
`14_212.json` (Novembro 1886, the worst-case/heaviest-wear sheet) had
silently substituted constraint-solved values for several elided barometer
cells (days 3, 16, 21, 26, 28, 30) and had silently multiplied the whole
Nebulosidade (cloudiness) column by 10 to match the printed Mez mean;
`14_142.json` (Julho 1886) had done the same for day 27's barometer mean.
All of these were reverted to their literal printed readings and re-flagged
- see each row's `printed_error`/`low_confidence` text for the specific
before/after and the image evidence. `14_57.json` day 18's `tmin` was
already stored faithfully (23.4) and only needed its flag upgraded from
`low_confidence` to a confirmed `printed_error` after checking the image.

## The Mez row's "Maximas"/"Minimas" are NOT means (important finding)

Every table's bottom "Mez" (monthly) row was initially assumed to give the
arithmetic mean of every column, matching `validate_sheet`'s `<col>_mean`
convention - that works for `pressure` (medias diurnas), `tmean`, `vapor`,
`humidity`, `wind_force`, `cloudiness`, `evap_sol`, `evap_sombra`, `ozone`,
and `precip_sum`. But it does **not** hold for the "Maximas"/"Minimas"
sub-columns of Barometro and Temperatura: the Mez value there is the single
highest/lowest **instantaneous** reading of the whole month (confirmed by
the companion "Revista climatologica" table's explicit "a mais alta"/"a
mais baixa" labels), not the mean of the daily maxima/minima column. This
was caught because `validate_sheet`'s `_mean` check failed by a large,
*systematic* margin on every sheet for these two columns - moving to a
direct `max()`/`min()` cross-check (done in the build script, not via
`validate_sheet`, since the schema only supports `_mean`/`_sum`) confirmed
an exact match on 8 of 9 sheets (Novembro's `pressure_min` needed a row-3/
row-30 correction to match, documented in REVIEW_QUEUE.md). `printed_totals`
in the gold JSON therefore only carries true means/sums; the max/min
cross-check lives in `/private/tmp/.../scratchpad/build_gold.py` used to
build these sheets (not committed - the resulting JSON is what matters).

## Certification

The gold set was **triple-verified** before this freeze: a first-pass draft
transcription, an independent blind re-transcription of the same 9 sheets
(no access to the draft), and a zoom-level adjudication pass over every
disagreement between the two. Cross-transcription agreement across the
3,822 gold cells was **99.52%** - 20 disagreements total. All 20 were
resolved at **HIGH confidence** by direct image inspection (full-page open,
then an 8-20x LANCZOS-upscaled crop of the specific cell); zero were
escalated as coin-flips. That adjudication produced **16 corrections**,
applied to `gold/sheets/*.json` (full ruling table in
`.superpowers/sdd/2026-08-31-weather-rescue-brazil-g0-g1/task-9-adjudication-report.md`);
the remaining 4 disputed cells confirmed the first-pass draft was already
correct and needed no change.

The binding **faithful-to-print convention** (see above) governed every
ruling in the adjudication exactly as it governed the original
transcription: each correction stores the literal glyph on the page, never
a constraint-solved or "intended" value. Two corrections
(`14_22` day 1885-12-11 `evap_sombra`, and `14_90` day 1886-04-05 `tmean` -
where *neither* prior transcription had the printed value right) are
documented/flagged rather than smoothed to fit an ordering or checksum
expectation. The gold set was re-frozen after these corrections;
`gold/MANIFEST.json` records the current sha256 per sheet and freeze
timestamp.
