"""A small local app for verifying dataset rows against the page they came from.

    python -m wrb.verify_serve          ->  http://127.0.0.1:8766

It shows one row at a time: the row's crop from the scanned page, beside the
values the dataset claims for it. You mark each one correct or wrong; the
running error rate is the number this project has never had - every accuracy
figure so far is measured on the frozen gold, which is NOT part of the dataset.

Judgements are appended to `data/verify/verdicts.jsonl`, one JSON object per
line, so the work survives a restart and can be rescored by `wrb.verify`.

Binds to localhost only: a personal tool over local images, not a service.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from PIL import Image

from wrb import profile as prof
from wrb.dataset import boxes_for_centres, crop_boxes, png_bytes
from wrb.rows import locate_day_rows
from wrb.verify import build_queue, summarise_verdicts

ROOT = Path(__file__).resolve().parents[2]
UI = Path(__file__).resolve().parent / "verify.html"
DATASET = ROOT / "data" / "dataset" / "weather-rescue-brazil.jsonl"
VERDICTS = ROOT / "data" / "verify" / "verdicts.jsonl"

app = FastAPI(title="Weather Rescue Brazil — verification")

_queue: list[dict] | None = None
_boxes: dict[tuple, list] = {}          # (profile, item, page) -> row boxes


def load_queue(per_profile: int = 8, seed: int = 0) -> list[dict]:
    global _queue
    if _queue is None:
        rows = [json.loads(l) for l in DATASET.open() if l.strip()]
        _queue = build_queue(rows, per_profile=per_profile, seed=seed)
    return _queue


def page_path(item: str, page: int) -> Path:
    p = ROOT / "data" / "raw" / "docvirt" / str(item) / f"{page:06d}.webp"
    if not p.exists():
        raise HTTPException(404, f"no scan for doc {item} page {page}")
    return p


def page_location(p: prof.Profile, item: str, page: int, period: str):
    """Locate the page's rows exactly as production does.

    Cached per page: localisation is the expensive half (~1-3 s) and one page
    contributes several rows to the queue.
    """
    key = (p.id, item, page)
    if key not in _boxes:
        im = Image.open(page_path(item, page)).convert("RGB")
        _boxes[key] = locate_day_rows(im, p.expected_rows(period), **p.geometry())
    return _boxes[key]


def crop_png(profile_id: str, item: str, page: int, period: str, row: int, height: float = 2.2) -> bytes:
    """The crop the MODEL saw for this row.

    Not a fresh crop of my own: `g4_produce.py` takes its crops from
    `loc.chain` via boxes_for_centres/crop_boxes, and `row` in the dataset is
    that crop's index. Reproducing a different crop would mean the verifier was
    judging something the model never looked at - and the whole point here is
    to check the reading against the paper. Tall enough (2.2 pitches) to show
    the day number and the row's neighbours for context.
    """
    p = prof.load(profile_id)
    im = Image.open(page_path(item, page)).convert("RGB")
    loc = page_location(p, item, page, period)
    boxes = boxes_for_centres(loc.chain, loc, *im.size)
    if not (0 <= row < len(boxes)):
        raise HTTPException(404, f"row {row} not located on {item}/{page} ({len(boxes)} found)")
    x0, y0, x1, y1 = boxes[row]
    extra = int((y1 - y0) * (height - 1.0) / 2)
    box = (max(0, x0), max(0, y0 - extra), min(im.width, x1), min(im.height, y1 + extra))
    crops = crop_boxes(im, [box], loc.skew_deg, scale=2.0)
    return png_bytes(_tile(crops[0]))


TILE_W = 1750


def _tile(c: Image.Image) -> Image.Image:
    """Stack a very wide row crop into tiles, instead of letting the browser
    shrink a 2700x90 strip until the digits are illegible.

    These tables run to 16 columns across a full broadsheet page, so a row
    crop has an aspect ratio near 30:1 - scaled to fit a window, the figures
    become unreadable, which defeats the entire exercise. Tiling keeps every
    digit at full resolution.
    """
    if c.width <= TILE_W:
        return c
    n = (c.width + TILE_W - 1) // TILE_W
    pad = 8
    out = Image.new("RGB", (TILE_W, (c.height + pad) * n), (255, 255, 255))
    for i in range(n):
        piece = c.crop((i * TILE_W, 0, min(c.width, (i + 1) * TILE_W), c.height))
        out.paste(piece, (0, i * (c.height + pad)))
    return out


def page_png(item: str, page: int) -> bytes:
    im = Image.open(page_path(item, page)).convert("RGB")
    scale = min(1.0, 2200 / im.width)
    if scale < 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    return png_bytes(im)


def read_judgements() -> list[dict]:
    if not VERDICTS.exists():
        return []
    return [json.loads(l) for l in VERDICTS.open() if l.strip()]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return UI.read_text()


@app.get("/api/queue")
def queue() -> dict:
    q = load_queue()
    judged = {j["id"]: j for j in read_judgements()}
    return {"queue": q, "judged": judged, "stats": summarise_verdicts(list(judged.values()))}


@app.get("/api/crop")
def crop(profile: str, item: str, page: int, period: str, row: int) -> Response:
    return Response(crop_png(profile, item, page, period, row), media_type="image/png")


@app.get("/api/page")
def page_image(item: str, page: int) -> Response:
    return Response(page_png(item, page), media_type="image/png")


@app.post("/api/verdict")
def verdict(payload: dict) -> dict:
    entry = {k: payload.get(k) for k in ("id", "profile", "item", "page", "row", "period", "verdict", "note")}
    if entry["id"] is None or entry["verdict"] not in ("ok", "wrong", "skip"):
        raise HTTPException(400, "need an id and a verdict of ok/wrong/skip")
    VERDICTS.parent.mkdir(parents=True, exist_ok=True)
    with VERDICTS.open("a") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    judged = {j["id"]: j for j in read_judgements()}
    return {"stats": summarise_verdicts(list(judged.values()))}


def main() -> None:
    import uvicorn
    q = load_queue()
    print(f"{len(q)} rows to verify ->  http://127.0.0.1:8766")
    print(f"judgements append to {VERDICTS.relative_to(ROOT)}")
    uvicorn.run(app, host="127.0.0.1", port=8766, log_level="warning")


if __name__ == "__main__":
    main()
