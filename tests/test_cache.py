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
