"""G4.0 dataset assembly: leakage guard, window candidates, manifest hash."""

import pytest

from wrb.dataset import (
    GOLD_PAGES, GoldLeakageError, assert_no_gold_leakage, manifest_hash, window_candidates,
)


def _ex(doc="15", page=44, day=1, sha="a" * 64, is_gold=False):
    return {"doc": doc, "page": page, "day": day, "sha256": sha, "image": f"{doc}_{page}_{day}.png",
            "is_gold": is_gold}


def test_gold_pages_are_the_nine_frozen_ones():
    assert GOLD_PAGES == frozenset(("14", p) for p in (22, 41, 57, 75, 90, 109, 142, 179, 212))


def test_guard_passes_clean_manifest():
    assert_no_gold_leakage({"examples": [_ex(), _ex(page=60, day=2, sha="b" * 64)]})


def test_guard_raises_on_gold_page_id():
    with pytest.raises(GoldLeakageError, match="gold page"):
        assert_no_gold_leakage({"examples": [_ex(doc="14", page=22)]})


def test_guard_raises_on_gold_flag():
    with pytest.raises(GoldLeakageError, match="is_gold"):
        assert_no_gold_leakage({"examples": [_ex(is_gold=True)]})


def test_guard_raises_on_identical_image_hash():
    with pytest.raises(GoldLeakageError, match="identical"):
        assert_no_gold_leakage({"examples": [_ex(sha="c" * 64)]}, gold_image_hashes=frozenset({"c" * 64}))


def test_guard_reports_multiple():
    m = {"examples": [_ex(doc="14", page=p) for p in (22, 41, 57, 75, 90, 109, 142)]}
    with pytest.raises(GoldLeakageError, match=r"\+2 more"):
        assert_no_gold_leakage(m)


def test_window_candidates():
    chain = [10, 20, 30, 40, 50]
    assert window_candidates(chain, 3) == [[10, 20, 30], [20, 30, 40], [30, 40, 50]]
    assert window_candidates(chain, 5) == [chain]


def test_manifest_hash_is_order_independent_and_content_sensitive():
    a = {"examples": [_ex(day=1, sha="a" * 64), _ex(day=2, sha="b" * 64)]}
    b = {"examples": list(reversed(a["examples"]))}
    assert manifest_hash(a) == manifest_hash(b)
    c = {"examples": [_ex(day=1, sha="a" * 64), _ex(day=2, sha="d" * 64)]}
    assert manifest_hash(a) != manifest_hash(c)
