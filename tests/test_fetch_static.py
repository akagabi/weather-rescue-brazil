import time

import respx, httpx
import pytest
from pathlib import Path
from wrb.cache import PageCache
from wrb.fetch_static import StaticFetcher


@respx.mock
def test_fetch_uses_cache(tmp_path: Path):
    route = respx.get("https://api.docvirt.com/v1/documents/obnacional/14/3").mock(
        return_value=httpx.Response(200, content=b"WEBP", headers={"content-type": "image/webp"}))
    f = StaticFetcher(PageCache(tmp_path), delay_s=0)
    p1 = f.fetch("docvirt", "14", 3, "https://api.docvirt.com/v1/documents/obnacional/14/3",
                 ext="webp", attribution="Biblioteca Digital de Obras Raras do Observatório Nacional")
    p2 = f.fetch("docvirt", "14", 3, "https://api.docvirt.com/v1/documents/obnacional/14/3",
                 ext="webp", attribution="Biblioteca Digital de Obras Raras do Observatório Nacional")
    assert p1 == p2 == PageCache(tmp_path).path("docvirt", "14", 3, ext="webp")
    assert p1.read_bytes() == b"WEBP"
    assert route.call_count == 1


@respx.mock
def test_fetch_stores_pdf_extension(tmp_path: Path):
    respx.get("https://www.estacao.iag.usp.br/Boletins/2020.pdf").mock(
        return_value=httpx.Response(200, content=b"%PDF-FAKE", headers={"content-type": "application/pdf"}))
    f = StaticFetcher(PageCache(tmp_path), delay_s=0)
    p = f.fetch("iagusp", "2020", 1, "https://www.estacao.iag.usp.br/Boletins/2020.pdf",
                ext="pdf", attribution="Estação Meteorológica do IAG-USP")
    assert p == PageCache(tmp_path).path("iagusp", "2020", 1, ext="pdf")
    assert p.read_bytes() == b"%PDF-FAKE"


@respx.mock
def test_fetch_enforces_delay_between_uncached_requests(tmp_path: Path):
    respx.get("https://api.docvirt.com/v1/documents/obnacional/14/1").mock(
        return_value=httpx.Response(200, content=b"P1", headers={"content-type": "image/webp"}))
    respx.get("https://api.docvirt.com/v1/documents/obnacional/14/2").mock(
        return_value=httpx.Response(200, content=b"P2", headers={"content-type": "image/webp"}))
    delay_s = 0.15
    f = StaticFetcher(PageCache(tmp_path), delay_s=delay_s)
    start = time.monotonic()
    f.fetch("docvirt", "14", 1, "https://api.docvirt.com/v1/documents/obnacional/14/1",
            ext="webp", attribution="x")
    f.fetch("docvirt", "14", 2, "https://api.docvirt.com/v1/documents/obnacional/14/2",
            ext="webp", attribution="x")
    elapsed = time.monotonic() - start
    assert elapsed >= delay_s


@respx.mock
def test_http_error_raises(tmp_path: Path):
    respx.get("https://api.docvirt.com/v1/documents/obnacional/3/2").mock(return_value=httpx.Response(422))
    f = StaticFetcher(PageCache(tmp_path), delay_s=0)
    with pytest.raises(httpx.HTTPStatusError):
        f.fetch("docvirt", "3", 2, "https://api.docvirt.com/v1/documents/obnacional/3/2",
                ext="webp", attribution="x")
