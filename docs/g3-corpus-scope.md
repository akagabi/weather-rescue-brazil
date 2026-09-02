# G3 corpus scope — Revista do Observatório on DocVirt

Date: 2026-09-02. Task: G3 Task 2a (discovery only, R$0 — no paid VLM
calls; page classification done with the free Read-tool vision and the
already-frozen gold sheets). Method: `scripts/discover_revista.py` +
manual page reads. All live fetches sequential, ≥2s apart, UA
`WeatherRescueBrazil/0.1 (open climate data rescue; contact:
gabesuit@gmail.com)`. NO CAPTCHA anything. Cached images live under
`data/raw/docvirt/{docId}/` (gitignored).

API (CAPTCHA-free, no auth — see docs/g0-inventory.md):
`GET https://api.docvirt.com/v1/documents/obnacional/{docId}/{page}` →
page image (webp). Page-not-found returns HTTP 422
`{"sucesso":false,"mensagem":"documentnotfound"}`.

## Headline numbers

- **Revista volumes found on DocVirt: 3** — docIds **14, 15, 16**
  (G0 knew only docId 14; **15 and 16 are newly discovered here**).
- **Primary single-station daily monthly-tables available: ~36**
  across the three volumes — **12 fully mapped & confirmed** (docId 14),
  **~24 more** in docIds 15–16 (format confirmed, spot-verified; see
  caveats).
- **Year span: 1886 (Dec 1885–Nov 1886) + 1889 + 1889–1890.**
  **Gap: 1887 and 1888 are NOT on DocVirt** (no docId slot exists for
  them; see neighbour probe).
- **Bonus**: docId 14 also carries **supplementary daily tables from
  other Brazilian stations** (Porto do Maranhão, an engineering-works
  station) — additional daily weather tables, not exhaustively mapped.
- **Estimated paid-pipeline cost: ~US$0.30 (docId 14 only) to ~US$1.75
  (all 3 volumes + supplementary tables)** — well under the US$10 cap.

## The discovery that changed the count

The neighbour probe first fetched only page 1 of each docId. **DocVirt
serves the same generic blank-cover image (md5 `366db2…`) as page 1 for
docIds 14, 15 and 16** (it is also docId 14's *last* page, 216). That
shared placeholder masked docIds 15/16 in a page-1-only scan. Fetching
page 2+ of each revealed both are genuine multi-page **Revista do
Observatório** volumes (title page: "REVISTA DO OBSERVATORIO —
Publicação mensal do Observatorio do Rio de Janeiro"). **Lesson: probe
page 2, not page 1, to test docId existence in this acervo.**

## docId 14 — Revista, Ano I (1886) — 216 pages — FULLY MAPPED

"Imperial Observatorio". 12 primary daily monthly-tables (header
"Resumo das observações meteorologicas feitas no Imperial Observatorio
no mez de <Mês> de <Ano>"; 28–31 daily rows × ~14 numeric columns +
a "Mez" summary row). Page numbers below are **scan/API page numbers**
(what the fetch uses), not the printed folios.

| # | Period | Scan page | Source of confirmation |
|---|--------|-----------|------------------------|
| 1 | 1885-12 | 22  | gold sheet + direct read |
| 2 | 1886-01 | 41  | gold sheet |
| 3 | 1886-02 | 57  | gold sheet |
| 4 | 1886-03 | 75  | gold sheet |
| 5 | 1886-04 | 90  | gold sheet |
| 6 | 1886-05 | 109 | gold sheet |
| 7 | 1886-06 | 141 | direct read (deferred table — see note) |
| 8 | 1886-07 | 142 | gold sheet + direct read |
| 9 | 1886-08 | 158 | direct read |
| 10| 1886-09 | 179 | gold sheet |
| 11| 1886-10 | 194 | direct read |
| 12| 1886-11 | 212 | gold sheet + direct read |

Notes / gaps:
- **June 1886 was deferred.** The August-issue's meteorological bulletin
  was skipped ("Um accidente… impediu-nos de publicar neste numero o
  costumado boletim… será inserido na proxima Revista", scan 128); the
  June daily table was then inserted late, immediately before July's
  (scan 141, right before Jul at 142). Both are present.
- **No December 1886 table.** The volume ends after the Nov table:
  scan 213–215 are the Nov climatological summary + "Noticias varias",
  scan 216 is the blank end-cover, scan 217 = HTTP 422. Dec 1886 falls
  in the next volume(s).
- Each daily table is typically followed by 1–2 pages of daily
  narrative notes and a "Revista Climatologica do mez" **normals-summary
  table** (a *different*, non-daily table — not counted above).

### Bonus — supplementary station daily tables inside docId 14
Interspersed catch-up tables from other Brazilian stations, same
daily-grid shape but different column set / different station:
- **Porto do Maranhão** (commissão hydraulica): Fevereiro 1886 — scan 159.
- **Engineering-works station** (signed *Fabio Hostilio de Moraes Rego,
  Engenheiro Chefe*): Março, Abril, Maio, Junho 1886 — scan 160–161.
- Likely more elsewhere in the volume (not exhaustively searched).
At least ~5–6 additional station-months are present. These are extra
daily weather data worth rescuing but are outside the primary
Imperial-Observatorio series.

## docId 15 — Revista, later Ano (1889) — 200 pages

"Observatorio Astronomico". Same primary daily monthly-table format,
now with décadas (10-day) subtotals and a slightly wider column set
(adds evaporação / ozone / chuva em millimetros).
- **Directly verified:** scan 195 = daily table "no mez de **Novembro
  de 1889**".
- Page 2 = Revista title page; scan 41 = "Aspecto do céo… mez de Março
  de 1889" (almanac).
- **Estimated ~12 monthly daily-tables covering 1889** (one per issue;
  only Nov 1889 verified page-exact — the rest are inferred from the
  216-page/12-table cadence of docId 14 and the confirmed format).

## docId 16 — Revista, next Ano (1889–1890) — 176 pages

"Observatorio Astronomico". Carries BOTH the single-station daily
tables AND a new landscape "**Resumo mensal das observações
simultaneas**" (multi-station, per-decada summaries for S. Paulo,
Bahia, Ouro Preto, Santa Cruz, etc.).
- **Directly verified:** scan 20 = daily table "no mez de **Dezembro de
  1889**"; scan 41 = multi-station simultaneous summary for Out 1889 /
  **Jan 1890**.
- Year span ≈ **Dec 1889 through 1890**.
- **Estimated ~12 single-station monthly daily-tables** plus a series of
  multi-station monthly summaries (bonus, different schema). Only Dec
  1889 verified page-exact.

## Neighbour docId probe (dead-ends documented)

`scripts/discover_revista.py` fetched page 1 of docIds 1–30, then
page 2+ of the ambiguous ones. Findings:
- **docIds 1–16: page 1 served.** docIds 14/15/16 = Revista (above).
- **docIds 1–13 = OTHER acervo works, NOT Revista.** Consistent with
  G0's 8 folder titles (Apresentação, 175 Anos-ON, ANNALES, 2×CRULS,
  EPHEMERIDES, FORTIN atlas). Spot-checked page 2 of docs 9–12: all are
  plain bound-book covers (leather/marbled bindings) of separate
  volumes; doc 3 (ANNALES) and doc 13 are 1-page stubs (page 2 = 422).
  Docs 4–8 have large page-1 images (≈450–685 KB) = dense plates /
  atlas-style volumes.
- **docIds 17–30: HTTP 422 "documentnotfound"** — no documents. Dead end.
- Conclusion: **the acervo exposes exactly three Revista volumes
  (14/15/16). 1887 and 1888 are not digitized here** (no docId between
  14 and 15; nothing Revista-shaped among 1–13 or 17–30).

## Estimated paid-pipeline cost

Formula (per the task): cost ≈ (#table-pages) × (calls/page) ×
US$0.005/call, where calls/page = **n=3 consensus table calls + 1 period
call + zoom re-read calls**. Assuming ~1–3 zoom re-reads per page →
**5–7 calls/page → US$0.025–0.035 per table page**.

| Scope | #daily-table pages | Est. cost (US$) |
|-------|--------------------|-----------------|
| docId 14 only (confirmed, 1886) | 12 | **0.30 – 0.42** |
| All 3 Revista volumes, primary series | ~36 | **0.90 – 1.26** |
| + docId 14 supplementary station tables | ~42–48 | **1.05 – 1.68** |
| + docId 16 multi-station summaries | ~50–55 | **1.25 – 1.93** |

**Overall range: ~US$0.30 (minimum, docId 14 only) to ~US$1.9 (maximum,
everything).** A representative "all three volumes, primary tables only"
target is **~US$1.0–1.3**. Every scenario is far below the US$10 cap.
(Page images themselves are R$0 — CAPTCHA-free, cache-once.)

## Caveats / honesty notes

- docId 14's 12 tables are fully enumerated: 6 verified by direct image
  read (22, 141, 142, 158, 194, 212) and 6 anchored by the frozen gold
  sheets (41, 57, 75, 90, 109, 179).
- For docIds 15 and 16 the **format and presence** of the daily tables
  are confirmed, but only **one table page each** was verified
  page-exact (15/195 = Nov 1889; 16/20 = Dec 1889). The "~12 per
  volume" counts are **estimates** from cadence, not a page-by-page map.
  A full map of 15/16 would need ~15–20 more free page reads each.
- Page counts (14=216, 15=200, 16=176) confirmed by binary-search to the
  422 boundary.
