import json
from pathlib import Path
from wrb.cache import PageCache


def test_roundtrip_and_miss(tmp_path: Path):
    c = PageCache(tmp_path)
    assert c.get("hdbn", "364568", 1) is None
    p = c.put("hdbn", "364568", 1, b"JPGBYTES", {"url": "http://x", "attribution": "Acervo Fundação Biblioteca Nacional"})
    assert p.exists() and p.with_suffix(".json").exists()
    assert c.get("hdbn", "364568", 1) == b"JPGBYTES"
    # Verify sidecar metadata round-trips correctly
    meta = json.loads(p.with_suffix(".json").read_text())
    assert meta["attribution"] == "Acervo Fundação Biblioteca Nacional"
    assert meta["url"] == "http://x"
    assert "fetched_at" in meta and meta["fetched_at"]


def test_path_helper(tmp_path: Path):
    c = PageCache(tmp_path)
    p = c.path("hdbn", "364568", 1)
    assert p == tmp_path / "hdbn" / "364568" / "000001.jpg"


def test_custom_extension_roundtrip(tmp_path: Path):
    # non-image sources (e.g. IAG-USP PDF boletins) need a real extension,
    # not a forced .jpg on binary content that isn't a JPEG.
    c = PageCache(tmp_path)
    assert c.get("iagusp", "2020", 1, ext="pdf") is None
    p = c.put("iagusp", "2020", 1, b"%PDF-FAKE", {"url": "http://x", "attribution": "a"}, ext="pdf")
    assert p == tmp_path / "iagusp" / "2020" / "000001.pdf"
    assert c.get("iagusp", "2020", 1, ext="pdf") == b"%PDF-FAKE"
    # default extension is unaffected
    assert c.path("iagusp", "2020", 1) == tmp_path / "iagusp" / "2020" / "000001.jpg"
