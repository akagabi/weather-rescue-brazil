import respx, httpx
import pytest
from pathlib import Path
from wrb.cache import PageCache
from wrb.fetch_docreader import DocReaderFetcher

TEMPLATE = "https://memoria.bn.gov.br/fake/{bib}/{page}"


@respx.mock
def test_fetch_uses_cache_and_rate_limit(tmp_path: Path):
    route = respx.get("https://memoria.bn.gov.br/fake/364568/7").mock(
        return_value=httpx.Response(200, content=b"JPG", headers={"content-type": "image/jpeg"}))
    f = DocReaderFetcher(PageCache(tmp_path), delay_s=0, url_template=TEMPLATE)
    assert f.fetch_page("364568", 7) == b"JPG"
    assert f.fetch_page("364568", 7) == b"JPG"   # second call: cache
    assert route.call_count == 1


@respx.mock
def test_non_image_response_raises(tmp_path: Path):
    respx.get("https://memoria.bn.gov.br/fake/364568/8").mock(
        return_value=httpx.Response(200, content=b"<html>err</html>", headers={"content-type": "text/html"}))
    f = DocReaderFetcher(PageCache(tmp_path), delay_s=0, url_template=TEMPLATE)
    with pytest.raises(ValueError):
        f.fetch_page("364568", 8)


def test_url_template_required(tmp_path: Path):
    with pytest.raises(ValueError):
        DocReaderFetcher(PageCache(tmp_path))


def test_url_template_rejects_desert_ant(tmp_path: Path):
    from wrb.guard import BillingGuardError
    with pytest.raises(BillingGuardError):
        DocReaderFetcher(PageCache(tmp_path), url_template="https://desert-ant.example/{bib}/{page}")


@respx.mock
def test_fetch_range_returns_cache_paths(tmp_path: Path):
    respx.get("https://memoria.bn.gov.br/fake/364568/1").mock(
        return_value=httpx.Response(200, content=b"P1", headers={"content-type": "image/jpeg"}))
    respx.get("https://memoria.bn.gov.br/fake/364568/2").mock(
        return_value=httpx.Response(200, content=b"P2", headers={"content-type": "image/jpeg"}))
    f = DocReaderFetcher(PageCache(tmp_path), delay_s=0, url_template=TEMPLATE)
    paths = f.fetch_range("364568", 1, 2)
    assert paths == [PageCache(tmp_path).path("hdbn", "364568", 1), PageCache(tmp_path).path("hdbn", "364568", 2)]
    assert paths[0].read_bytes() == b"P1"
    assert paths[1].read_bytes() == b"P2"
