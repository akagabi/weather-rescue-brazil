import ssl
import time
from importlib import resources
from pathlib import Path

import certifi
import httpx

from wrb.cache import PageCache

USER_AGENT = "WeatherRescueBrazil/0.1 (open climate data rescue; contact: gabesuit@gmail.com)"


def _iagusp_ssl_context() -> ssl.SSLContext:
    """
    www.estacao.iag.usp.br serves an incomplete TLS chain (leaf + one missing
    intermediate, which itself needs a second cross-signed intermediate) -
    see src/wrb/certs/iagusp-intermediate.pem for full provenance. Never fall
    back to verify=False.
    """
    ctx = ssl.create_default_context(cafile=certifi.where())
    extra = resources.files("wrb.certs").joinpath("iagusp-intermediate.pem")
    ctx.load_verify_locations(cafile=str(extra))
    return ctx


class StaticFetcher:
    """
    Rate-limited GET for CAPTCHA-free, no-auth-required static sources
    (DocVirt page-image API, IAG-USP boletim PDFs). Unlike DocReaderFetcher
    (memoria.bn.gov.br, gated by a per-document CAPTCHA - see
    docs/docreader-endpoints.md), these hosts serve content directly from a
    plain GET, so this fetcher takes a fully-formed URL per call rather than
    a url_template.
    """

    def __init__(self, cache: PageCache, delay_s: float = 2.0, ssl_context: ssl.SSLContext | bool = True):
        self.cache = cache
        self.delay_s = delay_s
        self.ssl_context = ssl_context
        self._last = 0.0

    def fetch(self, source: str, doc: str, page: int, url: str, ext: str, attribution: str) -> Path:
        cached = self.cache.get(source, doc, page, ext=ext)
        if cached is None:
            wait = self.delay_s - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            r = httpx.get(url, timeout=60, headers={"User-Agent": USER_AGENT},
                          follow_redirects=True, verify=self.ssl_context)
            self._last = time.monotonic()
            r.raise_for_status()
            self.cache.put(source, doc, page, r.content,
                            {"url": url, "attribution": attribution, "doc": doc, "page": page}, ext=ext)
        return self.cache.path(source, doc, page, ext=ext)
