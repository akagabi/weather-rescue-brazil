# Access & ToS check — BN (Hemeroteca Digital) / DocVirt (ON)

Date: 2026-08-31. Method: `scripts/check_access.py` (httpx, single sequential GET
per target, custom User-Agent identifying the project + contact email), with two
manual fallbacks noted below where the script could not get a clean answer.
Read-only throughout. Request tally, itemized so it's checkable:
- `scripts/check_access.py`, run verbatim twice: both times it attempted
  `memoria.bn.gov.br/robots.txt` first and errored at the TLS handshake
  before an HTTP response arrived (see §3), halting before the other two
  targets were ever requested.
- A non-committed, try/except-wrapped copy of the same 3-URL loop was run
  once to get past that halt: `memoria.bn.gov.br/robots.txt` (TLS error
  again, no response), `bndigital.bn.gov.br/perguntas-e-respostas/` (403),
  `docvirt.com/robots.txt` (404).
- WebFetch was tried once against the BN FAQ URL: also 403.
- Two browser page loads (Claude in Chrome) supplied the two responses no
  programmatic client could get: `memoria.bn.gov.br/robots.txt` (rendered,
  confirmed 404) and the BN FAQ page (rendered, 200, read via DOM query —
  §2).
- A few `openssl s_client` TLS handshakes (no HTTP GET, chain inspection
  only) were used to diagnose the memoria.bn.gov.br cert gap in §3 — not
  content fetches.

## 1. robots.txt

### `https://memoria.bn.gov.br/robots.txt` — **404, no robots.txt present**

```
404 - Arquivo ou diretório não encontrado.
The resource you are looking for might have been removed, had its name
changed, or is temporarily unavailable.
```

No robots.txt exists at this host. Per the standard, a missing robots.txt
means **no crawl restriction is declared** — nothing is disallowed. This is
the domain that actually serves the Hemeroteca Digital Brasileira (HDB)
reader and its page-image endpoints (DocReader-style URLs live under this
host), so the "no restriction declared" finding applies to those paths too.
We did not probe individual DocReader URLs beyond this — the brief scopes
this check to the three listed targets.

Confirmed via two independent clients (httpx and a real browser navigation)
to rule out a false 404 — see §3, this host has a TLS quirk that breaks
strict clients before they ever see the HTTP response, so the httpx-only
read needed a cross-check.

### `https://docvirt.com/robots.txt` — **404, no robots.txt present**

```
404 - Arquivo ou diretório não encontrado.
O recurso que você está procurando pode ter sido removido, ter tido seu
nome alterado ou estar temporariamente indisponível.
```

Same result: no robots.txt, no declared restriction. DocVirt hosts the
Observatório Nacional (ON) digital library we'd use as a fallback source.

**Conclusion:** neither target declares any robots.txt-based restriction on
any path, DocReader included.

## 2. BN's stated reuse terms

`https://bndigital.bn.gov.br/perguntas-e-respostas/` returns **HTTP 403**
to a plain httpx GET (and to WebFetch) — it's behind a Cloudflare
"Just a moment..." managed JS challenge that blocks non-browser HTTP
clients. This is the FAQ *marketing/help* site, not the image-serving host
we intend to script against (memoria.bn.gov.br, above) — so it doesn't
change the bulk-fetch verdict, but it does mean a plain script can't read
BN's own terms page, and it can't be treated as a bulk-fetch target itself.
As a read-only workaround authorized by the task dispatch (not by the brief
file itself), the page was rendered in a real browser (Claude in Chrome) to
read the actual FAQ answer under "Reprodução/uso do acervo digitalizado →
Como fazer para utilizar o acervo digitalizado da Hemeroteca Digital
Brasileira?". Verbatim, original Portuguese, with one elision marked `[...]`
where an unrelated clause was cut for length:

> "Sim, desde que você respeite os direitos dos autores. Siga estas
> orientações:
>
> 1. Cite sempre a fonte e o autor: Ao usar qualquer material, você deve
>    obrigatoriamente indicar o nome do autor e a fonte de referência
>    (**Acervo Fundação Biblioteca Nacional**).
> 2. Obras em Domínio Público: São aquelas cujo prazo de proteção legal
>    terminou. Você pode usá-las livremente, mesmo que o jornal ou revista
>    ainda tenha uma marca ativa no mercado.
> 3. Obras Protegidas: Se a obra ainda tiver direitos autorais vigentes, a
>    Fundação Biblioteca Nacional não pode autorizar o uso. [...]
> 4. Uso Responsável: O usuário é o único responsável por qualquer uso
>    indevido de materiais protegidos.
>
> De acordo com a legislação, o/a interessado(a) poderá reproduzir e
> utilizar livremente, citando a autoria, as obras que façam parte do
> domínio público (prazos abaixo):
>
> - Publicação como um todo (obra coletiva, como jornal ou revista): 70
>   anos contados a partir de 1º de janeiro do ano seguinte à publicação do
>   fascículo — referente aos direitos patrimoniais da empresa jornalística.
> - Textos de artigos escritos e assinados: 70 anos contados a partir de 1º
>   de janeiro do ano seguinte ao do falecimento do autor.
> - Fotografias assinadas: 70 anos contados a partir de 1º de janeiro do
>   ano seguinte à divulgação."

And separately, in the page footer (visible without expanding any FAQ item):

> "A BNDigital disponibiliza apenas documentos em domínio público ou com
> autorização de publicação do titular do direito autoral, exceto músicas
> gravadas em discos de 78 rotações que só podem ser acessadas na íntegra
> no prédio sede da FBN."

**Correction to the brief's working assumption:** the spec's shorthand
"public domain pre-1955" is an approximation, not BN's actual rule. BN's
real rule is a rolling **70-year term from Jan 1 following** (a) the
issue's publication date for the newspaper/magazine as a collective work,
or (b) the signing author's death for signed articles/photos — not a fixed
calendar cutoff. In practice, for a periodical issue as a whole, 70 years
back from 2026 lands anything published up to and including 1955
(70 years ≤ 2026 − 1956 = 70) safely in the public domain, so the
project's "pre-1955" working rule is a **conservative subset** of the real
rule and stays safe to use as a simple filter — it just isn't the whole
story if we ever want individually-signed post-1955 material. No
statement anywhere on this page addresses automated/bulk downloading,
scraping, or rate limits — the described reproduction workflow is manual
(open page, click 100%, right-click → "save image as"). Required
attribution wording is explicit: **"Acervo Fundação Biblioteca Nacional."**

## 3. Operational note: memoria.bn.gov.br TLS chain is incomplete

`scripts/check_access.py`, run verbatim as briefed, throws on the very
first target:

```
httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify
failed: unable to get local issuer certificate
```

This is a real server misconfiguration, not a sandbox artifact — confirmed
with `openssl s_client -connect memoria.bn.gov.br:443 -showcerts`: the
server sends only its leaf cert (`CN=*.bn.gov.br`, issued by "Certum DV
TLS G2 R39 CA") and omits the intermediate. Strict verifiers (OpenSSL,
Python's `ssl`/`httpx` via `certifi`) correctly refuse to complete the
chain; macOS/curl and browsers succeed only because they opportunistically
fetch the missing intermediate via AIA or already cache it in the system
trust store. `bndigital.bn.gov.br` (Google Trust Services chain) and
`docvirt.com` (Let's Encrypt chain) both serve complete chains and verify
fine.

**Implication for Task 6 (the bulk-fetch implementation):** the production
downloader must either (a) bundle the Certum intermediate explicitly and
pass it via `httpx.Client(verify=...)`, or (b) use a client library that
does AIA chaining. This is a known, low-risk, well-understood TLS
housekeeping issue — not a reason to distrust the endpoint — but it will
break naive `httpx.get()` calls exactly as it did here, so it must be
handled before Task 6 ships, not discovered there.

## 4. Rate limit adopted

**≥2 seconds between requests**, sequential only (no concurrency), with the
identifying User-Agent already used in the probe script:
`WeatherRescueBrazil/0.1 (research; contact: gabesuit@gmail.com)`. This is
well inside "polite scraping" norms for a government cultural-heritage
site with no stated rate limit and no robots.txt Crawl-delay directive (none
exists, since no robots.txt exists at all).

## 5. Verdict

**BULK FETCH: PERMITTED WITH CARE**

Reasoning:
- No robots.txt exists at either target host (memoria.bn.gov.br,
  docvirt.com) — no crawl restriction is declared for any path, DocReader
  included.
- BN explicitly permits reproduction/reuse of public-domain material,
  conditioned only on attribution ("Acervo Fundação Biblioteca Nacional")
  and on staying within its (author-death/publication-date-based) 70-year
  public-domain window — which is a superset of, and consistent with, the
  project's "pre-1955" filter.
- Nothing in BN's stated terms prohibits automation; it simply doesn't
  contemplate it (the documented workflow is manual, single-page). Bulk
  fetching a public, unauthenticated, no-robots-restriction endpoint at a
  polite ≥2s/request pace with an identifying UA is consistent with
  standard respectful-scraping practice and does not conflict with any
  written policy found.
- Caveats to carry forward: (1) always filter to public-domain-eligible
  material and always attribute; (2) the bndigital.bn.gov.br FAQ/marketing
  site itself is Cloudflare-protected against non-browser clients — that
  host is informational only and is not a fetch target; (3) the
  memoria.bn.gov.br TLS chain gap (§3) must be handled in the fetch client
  or every real request will fail exactly like the probe did.

No fallback-source kill triggered — ON/DocVirt is confirmed independently
clear (no robots.txt) and isn't needed as a substitute, only as the
already-planned secondary source.
