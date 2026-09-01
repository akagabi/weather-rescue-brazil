"""
Task 9 Step 4: freeze. Writes gold/MANIFEST.json - a sha256 per gold/sheets/*.json
file plus a freeze timestamp. Run this ONCE, after every gold sheet's content is
final (Steps 1-3 done, review queue resolved). From then on gold/ is read only
through wrb.gold.load_gold(), which verifies every file against this manifest
and raises on any mismatch.

Re-running this script after freezing is only for a deliberate re-freeze
(e.g. a genuine, reviewed correction to a gold cell) - it always overwrites
gold/MANIFEST.json with the current on-disk state and a fresh timestamp.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GOLD_DIR = Path(__file__).resolve().parent.parent / "gold"
SHEETS_DIR = GOLD_DIR / "sheets"
MANIFEST_PATH = GOLD_DIR / "MANIFEST.json"


def freeze() -> dict:
    sheet_paths = sorted(SHEETS_DIR.glob("*.json"))
    if not sheet_paths:
        raise SystemExit(f"no sheet files found under {SHEETS_DIR} - nothing to freeze")

    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sheet_paths}
    manifest = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "sheet_count": len(files),
        "files": files,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    manifest = freeze()
    print(f"froze {manifest['sheet_count']} gold sheets -> {MANIFEST_PATH}")
    print(f"frozen_at: {manifest['frozen_at']}")
