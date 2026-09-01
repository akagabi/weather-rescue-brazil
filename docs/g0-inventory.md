# G0 candidate inventory (AMENDED SCOPE)

Date: 2026-08-31/09-01. Method: `scripts/pull_probe.py` for the two
CAPTCHA-free sources (DocVirt, IAG-USP); documented evidence only (Task 4's
investigation + the DocVirt/docmulti search UI + one already-obtained sample
page) for the three Hemeroteca Digital Brasileira (hdbn) candidates, which
this task does **not** attempt to fetch. R$0 spend throughout. No parallel
fetching; all live requests were sequential with a >=2s delay and the
identifying User-Agent `WeatherRescueBrazil/0.1 (open climate data rescue;
contact: gabesuit@gmail.com)`.

## What was fetched (script, this task)

| source | candidate | items | on-disk size |
|---|---|---|---|
| docvirt | Revista do Observatório (docId 14, Tomo I / 1886) | 28 page images (.webp) | 6.3 MB |
| docvirt | Annales de l'Observatoire Impérial (docId 3) | 1 page image (dead end, see below) | 50 KB |
| iagusp | Boletim Climatológico Anual 2010 (.pdf, ~54 internal pages) | 1 file | 2.9 MB |
| iagusp | Boletim Climatológico Anual 2020 (.pdf, ~40 internal pages) | 1 file | 2.3 MB |
| **total** | | **31 fetched items** (30 page images/PDFs + attribution sidecars), **~11 MB** | |

Counting the two PDFs' internal pages (~94) toward the "page images/PDF
pages" budget, the probe covers roughly 28 + 94 = 122 underlying pages
across 31 fetched files — comfortably past the ~30-50 target once the PDFs'
internal pagination is counted; counting only fetched *items* (the more
literal reading), it's 31. Either way, `scripts/pull_probe.py` is
re-runnable at zero marginal cost: a second run (verified) completed in
0.095s wall time because `PageCache` short-circuits every request that
already has a cached file — no repeat network trips.

hdbn (Jornal do Commercio, Diário do Rio de Janeiro, Gazeta de Notícias):
**zero fetches attempted**, by design (see "Why hdbn was not probed" below).

## DocVirt addressing scheme (discovered)

`docvirt.com/obnacional/acervo.html` is a legacy static page (an old form
posting to `docvirt.com/asp/ObNacional.asp`) that **redirects** to a modern
React SPA at `app.docvirt.com/obnacional/...` ("DocPro - DocReader Web" —
same vendor family as BN's DocReader, but a different, newer deployment with
no CAPTCHA gate observed anywhere in the app).

Reverse-engineered live (Claude in Chrome, `window.fetch`/`XMLHttpRequest`
patched to log every call made while browsing):

- The left-side "Folders" panel lists the acervo's 8 titles (Apresentação,
  175 Anos - ON, ANNALES, two CRULS works, EPHEMERIDES, FORTIN atlas,
  REVISTA do Observatório). Clicking a folder issues:
  `GET https://api.docvirt.com/v1/metadata/{collection}/{docId}/{page}` and
  `GET https://api.docvirt.com/v1/documents/{collection}/{docId}/{page}`.
- **The second call is the actual page image.** For this acervo,
  `collection = "obnacional"`. It returns the raw image bytes directly
  (`content-type: image/webp`, HTTP 200) — no JSON wrapper, no auth header,
  no cookies, no CAPTCHA. Confirmed by fetching the same URL with plain
  `httpx.get()` and no browser session at all: identical bytes, verified as
  a genuine scanned page (1676x2480px, visually confirmed — see below).
- `docId` per title, read off the network log while clicking each folder:
  **14 = Revista do Observatório**, **3 = ANNALES**. (Not derived from the
  visible folder order — read directly off the API calls.)
- Page numbers are 1-based and sequential per `docId`. `docId=14` goes up
  to 216 (shown in the viewer's own "n / 216" page counter). `docId=3`
  (ANNALES) only serves page 1 — page 2 returns
  `HTTP 422 {"sucesso":false,"mensagem":"documentnotfound","data":null}`.
  This is a real, confirmed API response, not a client bug (the same
  request pattern works fine for `docId=14` up to page 216) — ANNALES
  appears to be a stub/cover-only entry in this acervo, not a digitized
  volume. **Dead end, documented, not pursued further** (per the brief's
  "if script-hostile, document why and move on").
- `docvirt.com/robots.txt` -> 404 (no file, no restriction — reconfirmed
  from Task 2). `app.docvirt.com/robots.txt` -> 200,
  `User-agent: * / Disallow:` (**explicitly** open, not just silent).
  `api.docvirt.com/robots.txt` -> 404 (no restriction).
- No CAPTCHA of any kind was seen anywhere in the DocVirt SPA — checked by
  grepping the entire minified JS bundle for "captcha": the only hit is an
  unrelated `react-google-recaptcha` widget wired to the site's "Fale
  conosco" contact form, nothing related to page-image serving.

**Final URL template**, confirmed live and used by `scripts/pull_probe.py`:
```
GET https://api.docvirt.com/v1/documents/{collection}/{docId}/{page}
```
`{collection}="obnacional"`, `{docId}` per title above, `{page}` 1-based.

## Content confirmed inside Revista do Observatório (docId 14)

Manual review of the fetched pages (visual inspection of decoded images,
not OCR) confirms this is a **direct hit** for the project's mission:

- Page 22 (Numero 1, Jan 1886 issue, reporting Dezembro 1885): a full
  numeric daily table — columns *Data | Barometro a 0° (Maximas/Minimas/
  Medias) | Temperatura C. à sombra (Maximas/Minimas/Medias) | Tensão do
  vapor | Humidade relativa | Ventos dominantes (Direcção/Força média) |
  Nebulosidade média | Chuva cahida em 24 horas | Evaporação (Sol/Sombra) |
  Ozone em 24h* — one row per day of the month. This is essentially the
  exact table shape the project exists to rescue.
- Page 23-24: a narrative day-by-day summary ("Resumo das observações...")
  plus a **"Revista climatologica do mez"** table comparing the month's
  values against multi-year normals — a built-in checksum-adjacent
  cross-reference (current month vs. historical average for the same
  elements).
- Page 40 (a later issue, reporting Janeiro 1886): the same narrative
  template recurs verbatim in structure ("Resumo das observações
  meteorologicas feitas no Imperial Observatorio no mez de Janeiro de
  1886..., Dia 1 —, Dia 3 —, ..."), confirming the monthly cycle repeats
  predictably.
- Pages 170-179 (near the end of the same volume, ~10 months later):
  same 2-column typography, same running header ("REVISTA DO
  OBSERVATORIO"), same font and column width — but this particular window
  landed on narrative/comparative-science content (a lightning-strike
  photograph analysis, an English-language reprint of a New South Wales
  observatory's results, comparisons of Brazilian/Chilean/Argentine
  station data) rather than another raw numeric table. This is expected
  and useful: it confirms **typographic consistency across the full
  volume** while also showing the "controlled variety" the brief's scoring
  criterion asks for (not every page is a data table — roughly 1-2 dense
  tables per ~16-18 page monthly installment, the rest narrative/scientific
  prose, in a single consistent font and layout).
- Not every page is meteorological: the same volume also carries
  astronomy content (star-position tables, e.g. page 31's "Posições das
  estrellas de comparação" for comet observations) interleaved with the
  weather sections — real controlled variety, not noise, since the
  layout/typography stays identical either way.

ANNALES (docId 3): only the single served page was reviewed — a
front-matter/title page, not enough to assess table content. No further
investigation is possible without the collection owner digitizing more
pages (out of this task's control).

## IAG-USP boletim PDFs

`https://www.estacao.iag.usp.br/boletim.php` lists PDF download options via
a legacy CGI form (`POST ../cgi-bin/redirect.pl`). The `<option value=...>`
strings turned out to be **directly fetchable relative paths off the site
root** — confirmed live:
```
GET https://www.estacao.iag.usp.br/Boletins/{year}.pdf   (annual "Boletim Climatológico")
```
also present but not fetched here: `Boletins/{SEASON}{year}.pdf` (seasonal),
`Mensais/{Mes}{year}.pdf` (monthly), `Relatorios/Relat_tecnico_{n}.pdf`
(technical reports) — same base-path pattern, same TLS fix applies.

TLS note (new, this task): `www.estacao.iag.usp.br` has the same class of
gap as `memoria.bn.gov.br` (Task 4) — the server sends only its leaf
certificate and omits the issuing intermediate. Unusually, the gap here is
**two certs deep**: the leaf's issuer ("Let's Encrypt YR2") is itself
signed by a second intermediate ("ISRG Root YR" — despite the name, not a
true root; it's cross-signed by the already-trusted "ISRG Root X1"). Both
certs were fetched from Let's Encrypt's own AIA URLs, verified to complete
the chain against certifi's bundle, and committed at
`src/wrb/certs/iagusp-intermediate.pem` (full provenance in that file's
header, mirroring `bn-intermediate.pem`'s format). Loaded automatically by
`wrb.fetch_static._iagusp_ssl_context()`.

Two annual boletins were downloaded (`2010.pdf`, `2020.pdf`, a decade
apart) to check template stability. Reviewed page-by-page (`Read` tool's
PDF support):
- Both are **born-digital** (word-processed, not scanned) — vector text,
  full color, a title page + credits/ISSN page + table of contents +
  numbered sections (temperature, precipitation, humidity, wind, pressure,
  phenomena, irradiation/insolation), each with its own table(s): daily
  records, monthly records, monthly means, and full daily data tables for
  the year. ISSN 1415-4374, "Boletim Climatológico Anual da Estação
  Meteorológica do IAG/USP" — published annually since at least the 1990s
  (v.14 for 2010 confirms a continuous volume-numbered series; v.23 in the
  2020 edition's colophon shows a ~3-year publication lag, i.e. the 2020
  edition was actually printed in 2023).
- The 2010 and 2020 editions share the **same visual template**
  (headings, table styling, section order) — high internal consistency,
  as expected for institutional annual reports — with only cosmetic
  changes (added seal/logo art in the 2020 cover, updated university
  officer names).
- Legibility is effectively perfect (no OCR degradation at all — it's
  native digital text). This cuts both ways for training value: it's an
  excellent, zero-noise *reference/validation* set for a table-structure
  model, but it does not exercise the OCR-under-degradation problem the
  historical scans do, and 1997-2025 data isn't "at risk" the way
  brittle 19th-century paper is — USP already maintains and republishes it.

## Why hdbn (Jornal do Commercio / Diário do Rio de Janeiro / Gazeta de
## Notícias) was not probed by script

Per the controller ruling amending this task and per
`docs/docreader-endpoints.md` (Task 4): every document's first page on
`memoria.bn.gov.br` is gated by a mandatory, per-document CAPTCHA added
2025-10-03. It is confirmed (two independent documents, two different
decades) that **no image request of any kind fires until the CAPTCHA is
solved**, and solving it is per-document, not per-session — there is no way
to script past it without either OCR/ML CAPTCHA-solving (a materially
different, not-authorized act) or a human solving it once per document,
out of band. This task does not attempt either. The three candidates below
are scored purely from: (a) Task 4's investigation (collection structure,
confirmed real page fetched by hand once, TLS fix), (b) the docmulti
search/listing pages (`DocReader.aspx?bib=...` -> `docmulti.aspx?bib=...`),
which are themselves plain fetchable HTML with no CAPTCHA (only the
per-document *viewer* is gated) and which expose useful metadata — title,
year span, page/edition counts — and (c) general/verified publication
history for each title (web search, see Rights column below).

Fetched politely and read for metadata only (no CAPTCHA involved, this is
the *search/listing* page, not a document viewer):
`https://memoria.bn.gov.br/docreader/DocReader.aspx?bib={bib}` redirects to
`docmulti.aspx?bib={bib}`, a table of N decade sub-libraries with page
counts. Task 4 already extracted this for `bib=364568` (Jornal do
Commercio: 20 sub-libraries, ~990,344 total pages,
`364568_01`=1827-1829 ... `364568_20`=2010-2016). The other two bibs
(`094170` Diário do Rio de Janeiro, `103730` Gazeta de Notícias) were
identified from BN's own public catalog pages (`bndigital.bn.gov.br`
article pages for each title, plus DocReader URLs surfaced in web search
results) but their listing pages were **not** fetched in this task (out of
scope for a script that fetches nothing from this host at all, to keep the
"did we touch a CAPTCHA-adjacent host" answer unambiguously "no").

**Open question for the gate report** (per amendment 1 — for the project
owner to answer by unlocking in his own browser): is the CAPTCHA granularity
truly per-document (i.e., per `bib_NN` + specific issue/edição), or could it
in practice be per decade-sub-library (`bib_NN`) such that solving it once
per decade unlocks every issue in that decade? Task 4's evidence shows
solving it for `364568_09` did not exempt `364568_04` (different decades) —
consistent with either interpretation, since those are different
sub-libraries. It was **not** tested whether solving it for one *issue*
within `364568_09` exempts a *different* issue within the same
`364568_09` decade sub-library — that distinction matters a lot for
Task 6/G1 (if per-decade, a human could unlock ~20 CAPTCHAs total for all
of Jornal do Commercio's history; if truly per-issue/edição, the CAPTCHA
count scales with the number of issues, likely hundreds to thousands).

## Rights column (project-owner request)

Public-domain status for all three hdbn titles' 19th-century material is
governed by Lei 9.610 art. 45: 70 years from Jan 1 following the issue's
publication (collective work) — so anything published up to and including
1955 is safely public domain regardless of who owns the brand today, and
moral rights (attribution) never expire. BN's own stated terms (Task 2,
`docs/access.md` §2) require citing "Acervo Fundação Biblioteca Nacional"
as the source. This standing note applies to every 1850-1890 candidate
below; the table adds only what's specific to each title's *current*
ownership/branding, since an active owner can still put up a rights banner
or ToS notice on top of material that is legally free to use.

| candidate | owner status | rights notice observed | note |
|---|---|---|---|
| Jornal do Commercio (RJ) | **Active owner**: acquired by/published under **Diários Associados** (DA group) until it ceased print/digital circulation on 2016-04-29 (189 years). DA is very much an active media company today. | Not directly checked (no CAPTCHA-free page to inspect on `memoria.bn.gov.br`); BN's own reproduction terms (Task 2) apply regardless of DA branding. | **Same risk category the amendment calls out for DA-owned titles** (e.g. Diário de Pernambuco) — DA's continued existence means a DA-style rights/trademark banner is plausible if BN's site or DA's own archives surface this title. Does not change the legal public-domain status of pre-1955 issues, but is worth a heads-up before any redistribution beyond training-data use. |
| Diário do Rio de Janeiro | **Extinct**: ceased publication in 1878 (per Wikipedia + `diariodorio.com`'s own historical write-up). No successor company holds an active claim. | None found; no current owner to post one. | Lowest-friction rights profile of the three — safely public domain by both the 70-year rule and by having no living rights-holder brand to navigate. |
| Gazeta de Notícias (RJ) | **Extinct**: sources place closure between 1942 and 1956 (Wikipedia says 1956; some secondary sources say 1942) — either way, decades past any living-owner concern. | None found. | Same low-friction profile as Diário do Rio de Janeiro; the exact closure year (1942 vs. 1956) doesn't change the public-domain analysis for the project's target period (1850-1890), only matters if the corpus were ever extended past 1955. |

DocVirt / IAG-USP candidates: both are institutional, government-funded
archives (Observatório Nacional, a federal research institute; IAG-USP, a
public university) publishing their own historical/scientific record with
no paywall, no CAPTCHA, and (for IAG-USP) an open PDF-download UI clearly
intended for public reuse. Neither site's material implicates a
Diários-Associados-style active-brand risk. Attribution strings used in
this task's fetches (see sidecar `.json` files next to every cached file):
`"Biblioteca Digital de Obras Raras do Observatório Nacional"` and
`"Estação Meteorológica do IAG-USP"`.

## Scoring table

Legibility/consistency/verdict below are from direct visual review of the
fetched pages (not OCR). "Access friction" reflects this task's central
finding: DocVirt/IAG-USP are pull-anytime; hdbn requires a human to clear a
CAPTCHA per document before a script can ever run against it.

Per reviewer request, every row below carries a short **RIGHTS** cell (no
blanks) — a one-line summary of ownership/PD status; the fuller per-title
rights analysis remains in the "Rights column (project-owner request)"
section further down, which this cell links back to.

| candidate | period covered | table found? | variables | layout consistency (1-5) | legibility (1-5) | printed monthly sums? | access friction | est. total pages, full series | rights | training-value verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| **Revista do Observatório** (DocVirt, docId 14+) | 1886-1891 (3 tomos, per the folder's own intro page: 193p+188p+164p ≈ 545 printed pages across all 3 tomos; this task fetched Tomo I only, 216 scan pages) | **Yes** — full daily numeric table monthly (barometer, temp max/min/mean, vapor tension, humidity, wind dir+force, cloudiness, rain, evaporation, ozone) | T (max/min/mean), pressure, vapor tension, humidity, wind dir+force, cloudiness, precip, evaporation, ozone — the widest variable set of any candidate here | **5** — identical 2-col typography/header confirmed at scan pages 1, 22, 40, and 170-179 (~90% of the volume span) | **5** — clean scan, sharp serif type, no fading | **Yes** — "Revista climatologica do mez" table gives monthly normals vs. current-month values, a built-in cross-check | **None** — no CAPTCHA, no auth, plain GET | ~545 (3 tomos) if all tomos are as fully digitized as Tomo I (unconfirmed for Tomo II/III — not checked this task) | 1886 work, PD by Lei 9.610 (>70yr); federal institute (Observatório Nacional), open acervo, no rights banner | **Best candidate found this task.** Richest variable set, highest legibility, zero access friction, built-in checksum table. Recommended v1 series. |
| Annales de l'Observatoire Impérial (DocVirt, docId 3) | Unknown (only 1 page served) | Unknown | Unknown | N/A (1 page) | 5 (the one page seen) | Unknown | None in principle, but **content itself is unavailable** past page 1 | Unknown, likely small given only 1 page is served | same as Revista: federal institute acervo, PD, no rights banner | **Not viable** — insufficient digitized pages to evaluate, let alone train on. Dead end, documented. |
| Boletim Climatológico Anual (IAG-USP, 1997-2025) | 1997-2025 (this task fetched 2010 + 2020) | **Yes** — full daily data tables per year, plus monthly/annual summary and record tables | T, precip, humidity, wind, pressure, phenomena (fog/frost/hail/thunder), solar irradiation/insolation — very wide, modern-instrument variable set | **5** — same institutional template across a 10-year gap | **5 (trivial)** — born-digital, not scanned; no OCR problem exists here at all | **Yes**, extensively (records tables, monthly means, annual series) | **None** — plain HTTPS download, no CAPTCHA (once the TLS intermediate is bundled) | ~29 PDFs (1997-2025) at ~40-55 pages each ≈ 1,200-1,600 pages | public university (USP), open PDF-download UI, no paywall/CAPTCHA; still copyrighted (not yet PD, published 1997-2025) but openly published for reuse | **High legibility, but low "rescue" value** — this data is already fully digital and actively maintained by USP; it is not at risk. Best used as a clean validation/reference set for table-structure work, not as the primary training corpus (the mission is rescuing *fragile* historical records). |
| Jornal do Commercio (hdbn, `bib=364568`) | 1827-2016 (20 decade sub-libraries, ~990,344 total pages per Task 4) | Presumed yes for at least some issues (not independently confirmed this task — CAPTCHA-blocked; Task 4 confirmed one real front-page image, not a met table) | Unknown pending unlock | Unknown pending unlock (daily newspaper across 189 years almost certainly drifts in layout/typeface repeatedly) | Unknown pending unlock; Task 4's one sample was a clean, legible scan | Unknown | **High** — mandatory per-document CAPTCHA (2025-10-03+); scripting blocked entirely; needs a human to unlock, per-document, out of band | Largest by far if usable (990k pages across the whole run; a narrow 1850-1890 slice would still be substantial) | extinto 2016; ex-Diários Associados (active media group), DA-banner risk possible; target-period (1850-90) issues PD by Lei 9.610 | **Highest theoretical volume, but currently un-scriptable.** Cannot be scored on table/variable/consistency criteria without the owner unlocking sample documents by hand. DA-group rights-notice risk noted above. |
| Diário do Rio de Janeiro (hdbn, `bib=094170`) | 1821-1878 (2 sub-libraries: 094170_01 1821-1858, 094170_02 1860-1878) | Unknown pending unlock | Unknown pending unlock | Unknown pending unlock | Unknown pending unlock | Unknown | **High** — same CAPTCHA gate | Unknown; shorter run than Jornal do Commercio (57 years vs. 189) | extinct 1878, no living rights-holder brand; PD by Lei 9.610 (>70yr) | **Unscored pending unlock.** Lowest rights friction of the three hdbn titles (fully extinct, no active owner) if it is ever unlocked. |
| Gazeta de Notícias (hdbn, `bib=103730`) | 1875-1942/1956 (source disagreement on exact end year; sub-libraries by decade, at least `103730_01`..`103730_04`+ observed in web search results) | Unknown pending unlock | Unknown pending unlock | Unknown pending unlock | Unknown pending unlock | Unknown | **High** — same CAPTCHA gate | Unknown | extinct 1942/1956 (sources disagree), no living rights-holder brand; PD by Lei 9.610 (>70yr) | **Unscored pending unlock.** Notable literary/press-history value (Machado de Assis wrote for it 1883-1900) but that's irrelevant to this project's meteorological-table mission; scored purely on met-table potential, which is unknown until unlocked. |

## Recommended v1 series

**Revista do Observatório (DocVirt, `docId=14`+, `collection=obnacional`),
starting with the confirmed Tomo I (1886).** It is the only candidate this
task could fully evaluate end-to-end: zero access friction (no CAPTCHA,
plain `httpx.get`, already TLS-fixed and committed), the widest confirmed
variable set of any candidate (9 distinct meteorological variables plus a
built-in monthly-normals cross-check table), perfect legibility, and
layout consistency confirmed across ~90% of the volume's page range. It
does carry real rescue value (unlike the IAG-USP PDFs) since this is a
138-year-old physical archive rarely consulted outside specialist circles,
digitized once by DocVirt with no ongoing maintenance guarantee. The two
open items before committing further budget: (1) confirm whether Tomos II
and III (1887-1891, docIds not yet identified — the folder tree only
exposed one entry per title, so the other tomos may be nested one level
deeper, or the DocVirt catalog may simply not have digitized them yet) are
equally digitized, and (2) get the project owner's read on the CAPTCHA
open question above, since if hdbn's Jornal do Commercio turns out to be
per-decade-unlockable rather than per-issue, its 990k-page run would likely
outscore Revista do Observatório on volume alone despite the extra manual
step.
