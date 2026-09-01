import ssl
import time
from importlib import resources
from pathlib import Path

import certifi
import httpx

from wrb.cache import PageCache
from wrb.guard import assert_personal

USER_AGENT = "WeatherRescueBrazil/0.1 (open climate data rescue; contact: gabesuit@gmail.com)"


def _bn_ssl_context() -> ssl.SSLContext:
    """
    memoria.bn.gov.br serves an incomplete TLS chain (leaf only, no
    intermediate) - see docs/docreader-endpoints.md and docs/access.md §3.
    Strict verifiers need the missing Certum intermediate loaded alongside
    certifi's root bundle. Never fall back to verify=False.
    """
    ctx = ssl.create_default_context(cafile=certifi.where())
    intermediate = resources.files("wrb.certs").joinpath("bn-intermediate.pem")
    ctx.load_verify_locations(cafile=str(intermediate))
    return ctx


class DocReaderFetcher:
    def __init__(self, cache: PageCache, delay_s: float = 2.0, url_template: str | None = None):
        if url_template is None:
            raise ValueError("url_template required - copy the confirmed template from docs/docreader-endpoints.md")
        assert_personal(url_template)
        self.cache, self.delay_s, self.template = cache, delay_s, url_template
        self._last = 0.0
        self._ssl_context = _bn_ssl_context() if "memoria.bn.gov.br" in url_template else True

    def fetch_page(self, bib: str, page: int) -> bytes:
        cached = self.cache.get("hdbn", bib, page)
        if cached is not None:
            return cached
        wait = self.delay_s - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = self.template.format(bib=bib, page=page)
        r = httpx.get(url, timeout=60, headers={"User-Agent": USER_AGENT},
                       follow_redirects=True, verify=self._ssl_context)
        self._last = time.monotonic()
        r.raise_for_status()
        if "image" not in r.headers.get("content-type", ""):
            raise ValueError(f"non-image response for {url}: {r.headers.get('content-type')}")
        self.cache.put("hdbn", bib, page, r.content,
                        {"url": url, "attribution": "Acervo Fundação Biblioteca Nacional", "bib": bib, "page": page})
        return r.content

    def fetch_range(self, bib: str, start: int, end: int) -> list[Path]:
        out = []
        for p in range(start, end + 1):
            self.fetch_page(bib, p)
            out.append(self.cache.path("hdbn", bib, p))
        return out
