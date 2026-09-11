"""The dataset card's numbers must match the dataset.

Written after correcting two stale figures in one sitting - both quoted from a
state that a later fix had already changed. A card is the artefact's front door
and the one document a reader trusts without checking; numbers in it have to be
mechanically tied to the file, not typed from memory.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.freeze import check_version, fingerprint  # noqa: E402

CARD = ROOT / "DATASET_CARD.md"
DATASET = ROOT / "data" / "dataset" / "weather-rescue-brazil.jsonl"


def card_text() -> str:
    return CARD.read_text()


def test_rows_match_the_artifact():
    fp = fingerprint(DATASET)
    assert f"| Rows | {fp['rows']:,} |" in card_text().replace("|", "|")


def test_usable_count_matches_the_artifact():
    fp = fingerprint(DATASET)
    assert f"**{fp['usable']:,}**" in card_text()


def test_values_count_matches_the_artifact():
    fp = fingerprint(DATASET)
    assert f"{fp['values_usable']:,}" in card_text()


def test_flagged_count_matches_the_artifact():
    rows = [json.loads(l) for l in DATASET.open() if l.strip()]
    flagged = sum(1 for r in rows if r.get("verdict") == "flagged")
    assert f"**{flagged:,} of {len(rows):,} rows are `flagged`**" in card_text()


def test_pages_match_the_artifact():
    rows = [json.loads(l) for l in DATASET.open() if l.strip()]
    pages = len({(str(r.get("item")), r["page"]) for r in rows})
    assert f"| Pages transcribed | {pages} |" in card_text()


def test_the_published_state_still_verifies():
    """The card describes a frozen artefact. If the file moved, the card's
    numbers are the least of it - the card must be re-derived."""
    assert check_version(DATASET, ROOT / "data" / "dataset" / "version.json") == []
