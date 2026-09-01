# DocReader endpoint discovery — memoria.bn.gov.br (Hemeroteca Digital Brasileira)

Date: 2026-08-31. Method: `curl`/`openssl` for TLS and static-file checks, plus
a real browser (Claude in Chrome DevTools) for the JS-driven viewer, since the
viewer is an ASP.NET WebForms app that only resolves image URLs client-side.
Read-only throughout except for one interactive CAPTCHA solve, described
below, needed to observe the mechanism.

## Result: NO stable, reusable URL template exists. Endpoint discovery is
## BLOCKED for production use by a per-document CAPTCHA gate added 2025-10-03.

`DocReaderFetcher` (this task) is implemented, fully TDD'd against a fake
injected template, and ready to use — but nobody can fill in a real
`url_template` for `bib=364568` (or any other bib) today, because no such
formulaic template exists. See "Why no template exists" below. This is a
**controller decision point**, not a coding gap.

## 1. Collection structure (discovered, not guessed)

`bib=364568` ("Jornal do Commercio (RJ), 1829 a 2016") is a **meta-collection
of 20 sub-libraries**, one per decade, not a fetchable document itself:

- `GET https://memoria.bn.gov.br/docreader/DocReader.aspx?bib=364568` 302s to
  `docmulti.aspx?bib=364568` — a search/index page listing 20 rows (990,344
  pages, 20 "Libraries").
- Each row's actual sub-library id is embedded in an `onmouseover="showMenu(
  event,\"364568_NN\",...)"` handler (zero-padded, `NN` = 01..20, sequential
  by decade: `364568_01` = 1827-1829 … `364568_09` = 1900-1909 …
  `364568_14` = 1950-1959 … `364568_20` = 2010-2016). Extracted via
  `document.querySelectorAll('img[onmouseover]')` in DevTools, not guessed.
- Only `bib=364568_NN&pagfis=<absolute page number within that decade>` opens
  the actual per-page DocReader viewer (`DocReader.aspx`, not `docmulti.aspx`).
  `pagfis` is an absolute page counter across every "Edição" (issue) in that
  decade's sub-library, not a per-issue page number.

So even the *addressing scheme* for a fetchable "document" is two-level
(`bib_NN` + `pagfis`), already more than the brief's flat `bib`+`page` model
assumes — this alone was learn-by-doing, confirmed via the live grid, not
inferred.

## 2. Why no template exists: images are server-assigned per render, not
## computable from (bib, page)

The initial `GET DocReader.aspx?bib=364568_09&pagfis=1` response (confirmed
via plain `curl`, no JS) embeds:

```html
<img id="DocumentoImg" onDragStart="return false;" onMouseDown="return false;" src="" />
```

`src=""` — empty. The real path is only populated by a follow-up
client-side action. Watching it happen in a real browser (page 1, then
clicking "Next page" to page 2 of the same document) captured:

```
page 1: cache/3369304421961/I0000001-1-0-000728-000563-008434-006521.JPG
page 2: cache/3369304421961/I0000002-1-0-000728-000565-008434-006548.JPG
```

`3369304421961` is a server-assigned per-document id (also the `id=` in the
CAPTCHA challenge URL, see below) — not derivable from `bib`/`pagfis`, and
different again for a different document (`364568_04`, tested separately).
The trailing numeric fields after the zero-padded page number
(`1-0-000728-000565-008434-006548`) encode per-scan values (height/width and
what looks like a size/checksum field — they shift slightly page to page,
e.g. `000563`→`000565`, `006521`→`006548`) that a client has no way to
predict; they only appear in the server's ASP.NET AJAX `UpdatePanel` partial
postback response for that specific page of that specific document
(`ScriptManager1=...PagPosBtn` request, response contains the literal
`<img ... src="cache/.../I0000002-....JPG">` HTML fragment). There is no
`{bib}/{page}` → filename formula; the filename must be read out of a live,
stateful ASP.NET WebForms session (ViewState + cookies) for that exact
document.

**This matches independent third-party confirmation**: the only known
community scraper for this exact site, [pyHDB](
https://github.com/ericbrasiln/pyHDB) (Eric Brasil, IHLM-UNILAB, academic
tool, predates the 2025-10-03 CAPTCHA rollout below), also drives a full
Selenium browser session and reads `driver.find_element(By.CSS_SELECTOR,
"#DocumentoImg").get_attribute('src')` before downloading with `urllib` —
see its `src/imgs.py::get_img`. It never had a static template either.

## 3. The actual blocker: mandatory per-document CAPTCHA (added 2025-10-03)

Loading **any** document's first page (tested independently on two different
sub-libraries/decades — `364568_09` 1900-1909 and `364568_04` 1850-1859, both
comfortably public-domain by the project's own 70-year rule) shows a modal
with this notice (verbatim):

> "Prezados (as) Pesquisadores, informamos que a partir do dia 03/10/2025,
> com objetivo de fortalecer a segurança da informação e proteção de dados da
> nossa plataforma Hemeroteca Digital Brasileira, implementamos a
> funcionalidade CAPTCHA. A partir de agora, ao realizar determinados acessos
> ou ações, será necessário concluir essa verificação simples para
> prosseguir."

— a distorted-3-digit-code CAPTCHA (`RadCaptcha`), different on each
document (`166` for `364568_09`, `024` for `364568_04`). **No image request
of any kind fires until the CAPTCHA is solved** — confirmed via DevTools
Network tab: only skin/icon assets load pre-solve; the moment the CAPTCHA is
validated, the `cache/{docId}/I...JPG` request fires for the first time.

Crucially, this is a **per-document** gate, not per-session: solving it once
for `364568_09` did not exempt a fresh navigation to `364568_04` in the same
browser session/cookies (`ASP.NET_SessionId` + `DocReaderID`, the latter a
1-year cookie) — a brand-new CAPTCHA appeared. It *is* session-scoped for
**subsequent pages within the same already-unlocked document**: after solving
once for `364568_09` page 1, clicking through to page 2 of that same document
loaded its image with no further CAPTCHA.

This directly updates Task 2's `docs/access.md` §3/§5 verdict ("BULK FETCH:
PERMITTED WITH CARE"), which predates this rollout and explicitly says it
"did not probe individual DocReader URLs beyond \[robots.txt\]." The
permissiveness of BN's stated ToS (no robots.txt restriction, attribution-only
reuse terms) is unchanged, but it is now moot for a purely-scripted client:
the site added an interactive access-control gate that an `httpx`-only,
non-JS client cannot pass, and defeating a CAPTCHA programmatically (OCR/ML
solving) is a materially different act than the "polite scripted GETs against
an open endpoint" the earlier review authorized — it is deliberately designed
friction, not an oversight.

## 4. What is NOT blocked: the static image files themselves

Once a `cache/{docId}/I....JPG` path is known (by any means), the file itself
requires **no cookies, no session, no auth** — confirmed by fetching the same
URL both with and without the browser's session cookies via plain `curl`:
both returned `200 image/jpeg`, identical 65536-byte body, real JPEG
(563×728px). It really is `JORNAL DO COMMERCIO`'s front page for that issue —
visually confirmed. So the block is entirely at *URL-discovery* time, not at
*fetch* time; this is why `DocReaderFetcher` itself (a plain `httpx.get` once
handed a real URL) needed no special auth handling beyond the TLS fix below.

## 5. TLS chain gap (Task 2 carry-forward, now fixed here)

`memoria.bn.gov.br` sends only its leaf certificate (`CN=*.bn.gov.br`, issued
by "Certum DV TLS G2 R39 CA") and omits the intermediate — confirmed again
with `openssl s_client -connect memoria.bn.gov.br:443 -showcerts` (exactly
one `CERTIFICATE` block). Plain `httpx.get()` against this host fails:

```
httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify
failed: unable to get local issuer certificate
```

Fixed properly (no `verify=False`): the leaf's Authority Information Access
extension names the CA Issuers URL
(`http://certumdvtlsg2r39ca.repository.certum.pl/certumdvtlsg2r39ca.cer`);
that intermediate was downloaded, converted DER→PEM, and verified to
complete the chain against certifi's root bundle
(`openssl verify -CAfile <certifi bundle> -untrusted bn-intermediate.pem
leaf.pem` → `OK`). It's committed at `src/wrb/certs/bn-intermediate.pem`
(full provenance in that file's header comment) and loaded by
`wrb.fetch_docreader._bn_ssl_context()`:

```python
ctx = ssl.create_default_context(cafile=certifi.where())
ctx.load_verify_locations(cafile="src/wrb/certs/bn-intermediate.pem")
```

`DocReaderFetcher` builds and uses this context automatically whenever
`memoria.bn.gov.br` appears in the injected `url_template`. Verified live
(2026-08-31): plain `httpx.get()` against a real `memoria.bn.gov.br` image
URL fails with `CERTIFICATE_VERIFY_FAILED`; the same request through
`_bn_ssl_context()` succeeds (`200`, `image/jpeg`, 65536 bytes — the same
front page above).

## 6. Recommendation

This needs a controller call before Task 4's "confirmed template" and
"live smoke, 5 pages" steps can be completed as specified:

- **(a) Accept the CAPTCHA as an automation boundary** and re-scope: a human
  (or a separate, explicitly-approved interactive tool) solves the CAPTCHA
  and resolves each document's page-URL list once per document, out of band;
  `DocReaderFetcher` would then need a different shape than a pure
  `url_template.format(bib, page)` (e.g. accept a pre-resolved
  `{page: url}` map per document) to fit how BN actually serves images. This
  is a real scope/design change to Task 4 and probably to Task 5/6's
  probe-window plan.
- **(b) Pivot to the secondary source** flagged in `docs/access.md` §5 —
  Observatório Nacional via DocVirt (`docvirt.com`) — which was independently
  confirmed clear of robots.txt restrictions and has not been checked for a
  similar CAPTCHA gate; Task 4 would need a fresh, separate endpoint-discovery
  pass against that host.
- **(c) Wait/retry** — the CAPTCHA feature is only 11 months old as of this
  writing; policy or implementation could change, but nothing here suggests
  it will loosen.

No option was chosen unilaterally: (a) changes Task 4/5's designed interface,
(b) changes the source entirely, either is a real decision, not an
implementation detail.
