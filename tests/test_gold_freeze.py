"""
Task 9 Step 4: freeze. `gold/MANIFEST.json` (written by `scripts/freeze_gold.py`)
records a sha256 per gold sheet file plus a freeze timestamp. `wrb.gold.load_gold()`
is the ONLY sanctioned way later tasks read the gold set: it must verify every
sheet file against the manifest before returning anything, and raise a clear
error the moment a single byte has drifted (accidental edit, bad merge,
filesystem corruption - doesn't matter which).
"""
import json
import shutil
from pathlib import Path

import pytest

from wrb.gold import GoldTamperError, Sheet, load_gold

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLD_DIR = REPO_ROOT / "gold"


def test_load_gold_returns_nine_sheets_on_the_real_frozen_gold():
    sheets = load_gold(GOLD_DIR)
    assert len(sheets) == 9
    assert all(isinstance(s, Sheet) for s in sheets)
    # sanity: every sheet actually has rows, not just schema-valid emptiness
    assert all(s.rows for s in sheets)


def test_tamper_detected(tmp_path):
    tamper_dir = tmp_path / "gold"
    shutil.copytree(GOLD_DIR, tamper_dir)

    # mutate one sheet file after the manifest was computed
    victim = sorted((tamper_dir / "sheets").glob("*.json"))[0]
    data = json.loads(victim.read_text())
    data["rows"][0]["cells"]["tmean"] = (data["rows"][0]["cells"]["tmean"] or 0) + 1000.0
    victim.write_text(json.dumps(data, indent=2))

    with pytest.raises(GoldTamperError):
        load_gold(tamper_dir)


def test_tamper_detected_missing_manifest_entry(tmp_path):
    tamper_dir = tmp_path / "gold"
    shutil.copytree(GOLD_DIR, tamper_dir)

    manifest_path = tamper_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    # drop one sheet's hash entirely - a file with no manifest record is just
    # as much a tamper signal as one with a mismatched hash
    manifest["files"].pop(next(iter(manifest["files"])))
    manifest_path.write_text(json.dumps(manifest, indent=2))

    with pytest.raises(GoldTamperError):
        load_gold(tamper_dir)
