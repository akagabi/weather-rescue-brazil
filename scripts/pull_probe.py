"""
G0 probe pull (AMENDED SCOPE - see .superpowers/sdd/2026-08-31-.../task-5-brief.md
amendments). R$0, read-only, sequential, >=2s between requests.

Fetches the CAPTCHA-free, no-auth candidates only:
  - DocVirt (docvirt.com / api.docvirt.com) - Observatorio Nacional's "Biblioteca
    Digital de Obras Raras" collection ("obnacional"). Addressing scheme
    discovered by reverse-engineering the SPA's network calls (see
    docs/g0-inventory.md "DocVirt addressing scheme"):
        GET https://api.docvirt.com/v1/documents/{collection}/{docId}/{page}
    returns the raw page image (image/webp) directly - no cookies, no auth,
    no CAPTCHA. Confirmed via docvirt.com/robots.txt (404, no restriction)
    and app.docvirt.com/robots.txt ("Disallow:" - explicitly open).
  - IAG-USP boletim PDFs (www.estacao.iag.usp.br) - direct PDF downloads
    under /Boletins/{year}.pdf. TLS chain needs the intermediate bundled at
    src/wrb/certs/iagusp-intermediate.pem (see that file for provenance).

Does NOT touch memoria.bn.gov.br (Hemeroteca Digital Brasileira / hdbn):
per-document CAPTCHA gate added 2025-10-03, confirmed in
docs/docreader-endpoints.md. Those candidates (Jornal do Commercio,
Diario do Rio de Janeiro, Gazeta de Noticias) are scored in
docs/g0-inventory.md from documented evidence only - no fetch attempted here.
"""

from pathlib import Path

from wrb.cache import PageCache
from wrb.fetch_static import StaticFetcher, _iagusp_ssl_context

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "raw"

# --- hdbn candidates (Hemeroteca Digital Brasileira / DocReader) ----------
# NOT FETCHED - per-document CAPTCHA blocks scripted access (see
# docs/docreader-endpoints.md). Recorded here only so the ids from Task 4's
# investigation live somewhere machine-readable, and so this file documents
# what was *considered* even though nothing was pulled.
HDBN_CANDIDATES_BLOCKED = {
    "jornal_do_commercio": {"bib": "364568", "note": "20 decade sub-libraries, 364568_01..364568_20"},
    "diario_do_rio_de_janeiro": {"bib": "094170", "note": "094170_01 (1821-1858), 094170_02 (1860-1878)"},
    "gazeta_de_noticias": {"bib": "103730", "note": "103730_01..103730_04+ by decade"},
}

# --- DocVirt (Observatorio Nacional, "obnacional" collection) -------------
# docId discovered by clicking each folder in the app.docvirt.com SPA and
# reading the resulting `GET /v1/documents/obnacional/{docId}/{page}` calls
# (window.fetch/XHR patched in DevTools - see docs/g0-inventory.md).
DOCVIRT_COLLECTION = "obnacional"
DOCVIRT_ATTRIBUTION = "Biblioteca Digital de Obras Raras do Observatório Nacional"

DOCVIRT_CANDIDATES = {
    # Revista do Observatorio, Tomo I (Ano 1, 1886) - 216 scanned pages.
    # Windows chosen from manual reconnaissance (2026-08-31):
    #   - page 1: title/cover page.
    #   - 20-26: Numero 1 (Jan 1886 issue) - includes the full numeric daily
    #     table (pg 22: barometro/temperatura/vapor/humidade/vento/nebulosidade/
    #     chuva/evaporacao/ozone for Dezembro 1885) and its narrative +
    #     "Revista climatologica do mez" summary table (pg 23-24).
    #   - 36-45: a later monthly installment (Numero ~2) - checks layout
    #     drift within the same volume; contains another monthly narrative
    #     summary (pg 40: "Resumo ... no mez de Janeiro de 1886").
    #   - 170-179: near the end of the volume (Numero ~10-11) - checks
    #     layout consistency across the full year of issues.
    "revista_do_observatorio": {"doc_id": "14", "windows": [(1, 1), (20, 26), (36, 45), (170, 179)]},
    # ANNALES de l'Observatoire Imperial de Rio de Janeiro - only page 1 is
    # served by the API; page 2 returns 422 "documentnotfound". Fetched once
    # to document the dead end (see docs/g0-inventory.md).
    "annales": {"doc_id": "3", "windows": [(1, 1)]},
}

# --- IAG-USP boletim PDFs --------------------------------------------------
IAGUSP_ATTRIBUTION = "Estação Meteorológica do IAG-USP"
IAGUSP_PDFS = [
    "https://www.estacao.iag.usp.br/Boletins/2010.pdf",  # ~15 yrs into the digital-born series
    "https://www.estacao.iag.usp.br/Boletins/2020.pdf",  # most recent full year, template comparison
]


def pull_docvirt(cache: PageCache) -> list[Path]:
    fetcher = StaticFetcher(cache, delay_s=2.0)  # default ssl_context=True: standard chain, no fix needed
    paths = []
    for name, spec in DOCVIRT_CANDIDATES.items():
        doc_id = spec["doc_id"]
        for start, end in spec["windows"]:
            for page in range(start, end + 1):
                url = f"https://api.docvirt.com/v1/documents/{DOCVIRT_COLLECTION}/{doc_id}/{page}"
                try:
                    p = fetcher.fetch("docvirt", doc_id, page, url, ext="webp", attribution=DOCVIRT_ATTRIBUTION)
                    paths.append(p)
                    print(f"  docvirt/{name} page {page}: {p} ({p.stat().st_size} bytes)")
                except Exception as e:
                    print(f"  docvirt/{name} page {page}: FAILED ({e})")
    return paths


def pull_iagusp(cache: PageCache) -> list[Path]:
    fetcher = StaticFetcher(cache, delay_s=2.0, ssl_context=_iagusp_ssl_context())
    paths = []
    for url in IAGUSP_PDFS:
        year = url.rsplit("/", 1)[-1].removesuffix(".pdf")
        p = fetcher.fetch("iagusp", year, 1, url, ext="pdf", attribution=IAGUSP_ATTRIBUTION)
        paths.append(p)
        print(f"  iagusp/{year}: {p} ({p.stat().st_size} bytes)")
    return paths


if __name__ == "__main__":
    cache = PageCache(DATA_ROOT)
    print("=== DocVirt (Observatorio Nacional) ===")
    docvirt_paths = pull_docvirt(cache)
    print("=== IAG-USP boletim PDFs ===")
    iagusp_paths = pull_iagusp(cache)
    print(f"\nTotal files in cache: {len(docvirt_paths) + len(iagusp_paths)}")
    print("hdbn candidates NOT fetched (CAPTCHA-blocked) - see docs/g0-inventory.md")
