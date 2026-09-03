"""G4.0 - row-level training set assembly + gold-leakage guard.

Each training example is one DAY ROW: a crop from `wrb.rows.locate_day_rows`
paired with that day's cells from the g2b+consensus transcription in
`bench/g3/revista-full.json`. The 9 frozen gold pages are NEVER training
data - they get their own, separate eval manifest (crops paired with the
frozen gold cells), and `assert_no_gold_leakage` is the tripwire that a
training manifest cannot contain them (by page id AND by image hash).

The pure parts live here (no torch): manifest schema, page → examples,
leakage guard, window candidates for pages whose row chain came out a few
rows too long. `scripts/g4_build_dataset.py` orchestrates and, when a page
needs it, calls the local VLM day-number oracle to pick the right window.
"""

from __future__ import annotations

import calendar
import hashlib
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image

from wrb.gold import Sheet, load_gold
from wrb.rows import RowLocation, locate_day_rows

GOLD_PAGES: frozenset[tuple[str, int]] = frozenset(
    ("14", p) for p in (22, 41, 57, 75, 90, 109, 142, 179, 212)
)
COLUMNS = ["pressure", "pressure_max", "pressure_min", "tmean", "tmax", "tmin", "vapor",
           "humidity", "wind_force", "cloudiness", "precip", "evap_sol", "evap_sombra", "ozone"]
MAX_EXTRA_ROWS = 3   # a chain up to this many rows too long is resolved by the day-number oracle


class GoldLeakageError(RuntimeError):
    pass


@dataclass
class RowExample:
    doc: str
    page: int
    period: str
    day: int
    date: str
    image: str                     # path relative to the manifest's directory
    sha256: str
    cells: dict[str, float | None]
    flags: dict[str, str]
    box: tuple[int, int, int, int]  # deskewed-page pixel box the crop was taken from
    pitch: float
    skew_deg: float
    is_gold: bool = False


@dataclass
class PageReport:
    doc: str
    page: int
    period: str
    day_count: int
    status: str                    # ok | needs_oracle | refused
    reason: str = ""
    chain: list[int] = field(default_factory=list)
    n_examples: int = 0


def day_count_of(period: str) -> int:
    y, m = (int(x) for x in period.split("-"))
    return calendar.monthrange(y, m)[1]


def page_image_path(root: Path, doc: str, page: int) -> Path:
    return root / "data" / "raw" / "docvirt" / doc / f"{page:06d}.webp"


def crop_boxes(image: Image.Image, boxes: list[tuple[int, int, int, int]], skew_deg: float,
               scale: float = 2.0) -> list[Image.Image]:
    if skew_deg:
        image = image.rotate(skew_deg, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    out = []
    for b in boxes:
        c = image.crop(b)
        if scale != 1.0:
            c = c.resize((max(1, round(c.width * scale)), max(1, round(c.height * scale))), Image.LANCZOS)
        out.append(c)
    return out


def png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def rows_by_day(sheet: Sheet | dict) -> dict[int, dict]:
    rows = sheet.rows if isinstance(sheet, Sheet) else sheet["rows"]
    out: dict[int, dict] = {}
    for r in rows:
        d = r if isinstance(r, dict) else r.model_dump()
        out[int(d["date"][-2:])] = d
    return out


def locate_page(image: Image.Image, day_count: int) -> tuple[RowLocation, str, str]:
    """Locate day rows; classify the page: ok / needs_oracle / refused."""
    loc = locate_day_rows(image, day_count)
    if loc.ok:
        return loc, "ok", ""
    n = len(loc.chain)
    if day_count < n <= day_count + MAX_EXTRA_ROWS:
        return loc, "needs_oracle", loc.reason
    return loc, "refused", loc.reason


def window_candidates(chain: list[int], day_count: int) -> list[list[int]]:
    """All contiguous `day_count`-long windows of an over-long chain."""
    return [chain[i:i + day_count] for i in range(len(chain) - day_count + 1)]


def boxes_for_centres(centres: list[int], loc: RowLocation, width: int, height: int) -> list[tuple[int, int, int, int]]:
    """Rebuild day boxes for chosen centres with the page's pitch and x-extent."""
    x0, _, x1, _ = loc.day_boxes[0] if loc.day_boxes else (round(0.09 * width), 0, round(0.94 * width), 0)
    half = loc.pitch / 2
    return [(x0, max(0, round(y - half)), x1, min(height, round(y + half))) for y in centres]


def examples_for_page(
    *, doc: str, page: int, period: str, sheet: dict | Sheet, image: Image.Image,
    boxes: list[tuple[int, int, int, int]], loc: RowLocation, out_dir: Path, manifest_dir: Path,
    is_gold: bool, scale: float = 2.0,
) -> list[RowExample]:
    day_count = day_count_of(period)
    assert len(boxes) == day_count, (len(boxes), day_count)
    by_day = rows_by_day(sheet)
    crops = crop_boxes(image, boxes, loc.skew_deg, scale=scale)
    out_dir.mkdir(parents=True, exist_ok=True)
    examples: list[RowExample] = []
    for day, (box, crop) in enumerate(zip(boxes, crops), start=1):
        row = by_day.get(day)
        if row is None:
            continue  # transcription has no row for this day: no label, no example
        data = png_bytes(crop)
        name = f"{doc}_{page:06d}_d{day:02d}.png"
        (out_dir / name).write_bytes(data)
        examples.append(RowExample(
            doc=doc, page=page, period=period, day=day, date=row["date"],
            image=str((out_dir / name).relative_to(manifest_dir)),
            sha256=hashlib.sha256(data).hexdigest(),
            cells={c: row["cells"].get(c) for c in COLUMNS},
            flags=dict(row.get("flags") or {}),
            box=tuple(box), pitch=loc.pitch, skew_deg=loc.skew_deg, is_gold=is_gold,
        ))
    return examples


def write_manifest(path: Path, examples: list[RowExample], reports: list[PageReport], meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "meta": meta,
        "n_examples": len(examples),
        "n_cells": sum(1 for e in examples for v in e.cells.values() if v is not None),
        "pages": [asdict(r) for r in reports],
        "examples": [asdict(e) for e in examples],
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))


def load_manifest(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def gold_page_ids(gold_dir: str | Path = "gold") -> frozenset[tuple[str, int]]:
    """Gold (doc, page) pairs read from the FROZEN gold set itself (MANIFEST
    checksums verified by load_gold), so the guard cannot drift from it."""
    ids = set()
    for s in load_gold(gold_dir):
        ids.add(("14", int(s.page)))  # v1 gold is docId 14 only; source field carries 'docvirt'
    return frozenset(ids)


def assert_no_gold_leakage(
    train_manifest: dict,
    gold_pages: frozenset[tuple[str, int]] = GOLD_PAGES,
    gold_image_hashes: frozenset[str] = frozenset(),
) -> None:
    """Tripwire: raise if any training example comes from a gold page (by
    id) or is pixel-identical to a gold crop (by sha256), or is flagged
    is_gold. The eval set is sacred; this must run before every training
    launch (scripts/g4_train.py hashes the manifest against it)."""
    bad: list[str] = []
    for e in train_manifest.get("examples", []):
        key = (str(e["doc"]), int(e["page"]))
        if key in gold_pages:
            bad.append(f"gold page in training set: doc {e['doc']} page {e['page']} day {e['day']}")
        if e.get("is_gold"):
            bad.append(f"is_gold example in training set: {e['image']}")
        if e.get("sha256") in gold_image_hashes:
            bad.append(f"training crop identical to a gold crop: {e['image']}")
    if bad:
        raise GoldLeakageError("; ".join(bad[:5]) + (f" (+{len(bad) - 5} more)" if len(bad) > 5 else ""))


def manifest_hash(manifest: dict) -> str:
    """Stable hash over (image sha256, doc, page, day) - what a training
    launch records and re-checks."""
    h = hashlib.sha256()
    for e in sorted(manifest["examples"], key=lambda e: (e["doc"], e["page"], e["day"])):
        h.update(f"{e['doc']}/{e['page']}/{e['day']}/{e['sha256']}\n".encode())
    return h.hexdigest()
