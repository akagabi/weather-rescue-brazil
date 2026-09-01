import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

RANGES = {"tmax": (-10.0, 50.0), "tmin": (-15.0, 45.0), "precip": (0.0, 400.0),
          "pressure": (650.0, 800.0)}  # mmHg era units; adjust per-series in G2
TOL = 0.15  # tolerance for printed mean/sum reproduction (rounding in period arithmetic)

class Row(BaseModel):
    date: str
    cells: dict[str, float | None]
    flags: dict[str, str] = {}

class Sheet(BaseModel):
    source: str; bib: str; page: int
    station: str; period: str
    columns: list[str]
    rows: list[Row]
    printed_totals: dict[str, float] | None = None

def validate_sheet(s: Sheet) -> list[str]:
    v: list[str] = []
    for r in s.rows:
        tmax, tmin = r.cells.get("tmax"), r.cells.get("tmin")
        if tmax is not None and tmin is not None and tmax < tmin:
            v.append(f"{r.date}: tmax {tmax} < tmin {tmin}")
        for col, val in r.cells.items():
            lo_hi = RANGES.get(col)
            if val is not None and lo_hi and not (lo_hi[0] <= val <= lo_hi[1]):
                v.append(f"{r.date}: {col}={val} outside physical range {lo_hi}")
    if s.printed_totals:
        for key, printed in s.printed_totals.items():
            parts = key.rsplit("_", 1)
            if len(parts) != 2:
                v.append(f"printed_totals key '{key}' is malformed (expected <col>_mean or <col>_sum)")
                continue
            col, kind = parts
            vals = [r.cells[col] for r in s.rows if r.cells.get(col) is not None]
            if not vals:
                continue
            calc = (sum(vals) / len(vals)) if kind == "mean" else sum(vals)
            if abs(calc - printed) > TOL:
                v.append(f"printed {key}={printed} but computed {calc:.2f} (possible row/col shift)")
    return v


class GoldTamperError(RuntimeError):
    """Raised by load_gold() when a gold sheet file's contents no longer match
    the sha256 recorded in gold/MANIFEST.json at freeze time (Task 9 Step 4).

    The frozen gold set is the eternal judge for every later scoring task -
    any drift, whether an accidental edit, a bad merge, or filesystem
    corruption, must fail loudly rather than silently changing what "correct"
    means."""


def load_gold(gold_dir: str | Path = "gold") -> list[Sheet]:
    """Load every gold/sheets/*.json Sheet, verifying each file's sha256
    against gold/MANIFEST.json first. Raises GoldTamperError on any mismatch
    (missing manifest, missing manifest entry for a file, or a hash that no
    longer matches the file on disk) - this is the ONLY sanctioned read path
    for the frozen gold set."""
    gold_dir = Path(gold_dir)
    sheets_dir = gold_dir / "sheets"
    manifest_path = gold_dir / "MANIFEST.json"

    if not manifest_path.exists():
        raise GoldTamperError(
            f"{manifest_path} does not exist - gold set is not frozen. "
            "Run scripts/freeze_gold.py first."
        )
    manifest = json.loads(manifest_path.read_text())
    files = manifest.get("files", {})

    sheet_paths = sorted(sheets_dir.glob("*.json"))
    if not sheet_paths:
        raise GoldTamperError(f"no sheet files found under {sheets_dir}")

    on_disk = {p.name for p in sheet_paths}
    manifest_names = set(files.keys())
    if on_disk != manifest_names:
        missing_from_manifest = sorted(on_disk - manifest_names)
        missing_from_disk = sorted(manifest_names - on_disk)
        raise GoldTamperError(
            "gold/sheets contents do not match gold/MANIFEST.json - "
            f"on disk but not in manifest: {missing_from_manifest}; "
            f"in manifest but not on disk: {missing_from_disk}"
        )

    sheets: list[Sheet] = []
    for path in sheet_paths:
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        expected = files[path.name]
        if actual != expected:
            raise GoldTamperError(
                f"{path.name}: sha256 mismatch - expected {expected}, got {actual}. "
                "This sheet was modified after the gold set was frozen "
                "(gold/MANIFEST.json). If the change is intentional, re-run "
                "scripts/freeze_gold.py to re-freeze."
            )
        sheets.append(Sheet(**json.loads(content)))

    return sheets
