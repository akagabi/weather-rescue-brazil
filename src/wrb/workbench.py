"""Transcription workbench: a local web tool for labelling and reviewing any
ruled table, driven entirely by `wrb.profile`.

    python -m wrb.workbench            # then open http://127.0.0.1:8765

Nothing here knows about the Revista. A publication is a profile (its printed
columns) plus page images; the same screen serves Corumba, a Santa-Cruz sheet,
or a publication added tomorrow. The loop it exists to support:

    type ~50 rows with the image in front of you   ->  a labelled set
    train a small adapter on them                  ->  the model drafts
    correct only what QC flags                     ->  more labels, better model

Everything is local: the browser is the interface, the model runs on this
machine, no data leaves it.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from wrb import profile as prof
from wrb.dataset import boxes_for_centres, crop_boxes, page_image_path
from wrb.rows import locate_day_rows

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "labels"
RAW = ROOT / "data" / "raw" / "docvirt"


# --------------------------------------------------------------------------
# storage: one JSON per (profile, doc, page); plain files, easy to inspect,
# diff and feed straight into training.
# --------------------------------------------------------------------------
def label_path(profile_id: str, doc: str, page: int) -> Path:
    return LABELS / profile_id / f"{doc}_{page:06d}.json"


def load_labels(profile_id: str, doc: str, page: int) -> dict:
    p = label_path(profile_id, doc, page)
    return json.loads(p.read_text()) if p.exists() else {"rows": {}}


def save_labels(profile_id: str, doc: str, page: int, data: dict) -> Path:
    p = label_path(profile_id, doc, page)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    return p


def label_stats(profile_id: str) -> dict:
    d = LABELS / profile_id
    rows = 0
    pages = 0
    if d.exists():
        for f in d.glob("*.json"):
            data = json.loads(f.read_text())
            n = sum(1 for r in data.get("rows", {}).values() if any(v not in (None, "") for v in r.values()))
            if n:
                pages += 1
                rows += n
    return {"pages": pages, "rows": rows}


# --------------------------------------------------------------------------
# page geometry, cached per (doc, page, expected rows)
# --------------------------------------------------------------------------
@dataclass
class PageState:
    doc: str
    page: int
    period: str
    profile_id: str
    boxes: list = field(default_factory=list)
    skew: float = 0.0
    ok: bool = False
    reason: str = ""


_pages: dict[tuple, PageState] = {}
_lock = threading.Lock()


def page_state(profile_id: str, doc: str, page: int, period: str) -> PageState:
    key = (profile_id, doc, page, period)
    with _lock:
        if key in _pages:
            return _pages[key]
    p = prof.load(profile_id)
    st = PageState(doc=doc, page=page, period=period, profile_id=profile_id)
    img_path = page_image_path(ROOT, doc, page)
    if not img_path.exists():
        st.reason = f"no image at {img_path.relative_to(ROOT)}"
    else:
        image = Image.open(img_path).convert("RGB")
        want = p.expected_rows(period)
        loc = locate_day_rows(image, want)
        st.skew = loc.skew_deg
        if loc.ok:
            st.boxes = [list(b) for b in loc.day_boxes]
            st.ok = True
        else:
            # still offer whatever chain was found, so a human can work with it
            st.boxes = [list(b) for b in boxes_for_centres(loc.chain, loc, *image.size)] if loc.chain else []
            st.reason = loc.reason
    with _lock:
        _pages[key] = st
    return st


def row_crop_png(doc: str, page: int, box: list, skew: float, scale: float = 1.6) -> bytes:
    image = Image.open(page_image_path(ROOT, doc, page)).convert("RGB")
    crop = crop_boxes(image, [tuple(box)], skew, scale=scale)[0]
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def discover_pages(doc: str) -> list[int]:
    d = RAW / doc
    return sorted(int(f.stem) for f in d.glob("*.webp")) if d.exists() else []


def known_periods() -> dict:
    """(doc, page) -> period, from the transcribed bench file when present, so
    the workbench can pre-fill the month a page covers."""
    f = ROOT / "bench" / "g3" / "revista-full.json"
    if not f.exists():
        return {}
    out = {}
    for p in json.loads(f.read_text()).get("per_sheet", []):
        if p.get("period"):
            out[f"{p['doc']}/{int(p['page'])}"] = p["period"]
    return out


# --------------------------------------------------------------------------
# training kick-off (fire and forget; the log is the progress view)
# --------------------------------------------------------------------------
_train: dict = {"running": False, "log": "", "cmd": ""}


def start_training(profile_id: str, run: str, epochs: int = 2) -> dict:
    if _train["running"]:
        return {"started": False, "why": "a training run is already going"}
    stats = label_stats(profile_id)
    if stats["rows"] < 20:
        return {"started": False, "why": f"only {stats['rows']} labelled rows; label ~50 first"}
    log = ROOT / "runs" / "g4" / run / "train.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ROOT / "scripts" / "g4_train.py"), "--model", "qwen35",
           "--run", run, "--epochs", str(epochs), "--printed", "--save-every", "20"]
    _train.update(running=True, log=str(log), cmd=" ".join(cmd))

    def _run():
        with open(log, "w") as fh:
            subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
        _train["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "log": str(log.relative_to(ROOT)), "rows": stats["rows"]}


def training_status() -> dict:
    out = dict(_train)
    p = Path(_train["log"]) if _train["log"] else None
    if p and p.exists():
        tail = p.read_text().splitlines()[-12:]
        out["tail"] = [ln for ln in tail if ln.strip()]
    return out
