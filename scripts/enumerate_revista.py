#!/usr/bin/env python3
"""G3 Task 2b Step 1 (R$0): enumerate the PRIMARY monthly-table pages in
docIds 15 and 16 of the Revista do Observatorio on DocVirt.

The volume interleaves THREE page kinds:
  1. PRIMARY daily monthly-table (our target) - portrait, header
     "Resumo das observações meteorologicas feitas no Observatorio
     Astronomico no mez de <Mês> de <Ano>", a big bordered grid of ~13
     numeric columns x 28-31 day rows + Déc/Mez subtotal rows (see
     data/raw/docvirt/15/000195.webp = Novembro 1889).
  2. SUPPLEMENTARY station reduction tables ("Reducção das observações ...
     em <Cidade>, no mez de ...", e.g. Cuyabá) - scanned LANDSCAPE (wider
     than tall), a 4-reading-per-day schema (7h/10h/1h/4h). NOT the g2b
     target schema.
  3. PROSE narrative ("REVISTA DO OBSERVATORIO" running head, two columns
     of daily weather notes, signed e.g. "J. LOUZADA").

Two cheap, network-free discriminators separate these without a paid VLM
call: orientation (kind 2 is landscape; 1 and 3 are portrait) and vertical
ruled-line count in the central band (kind 1's dense grid draws many long
vertical rules; kind 3's prose draws ~1 column gutter). This script fetches
every page (CAPTCHA-free, >=2s apart, cache-aware) and emits a per-page
(orientation, n_vertical_rules) score plus a SHORTLIST of portrait pages
whose rule count crosses the grid threshold - the human then confirms the
month/year header on the shortlist with the free Read-tool vision, and the
confirmed (docId, page, period) rows become the transcription work list.

Usage:
    python scripts/enumerate_revista.py fetch      # fetch all pages 15+16
    python scripts/enumerate_revista.py detect     # score cached pages -> JSON
"""

import io
import json
import sys
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from wrb.cache import PageCache  # noqa: E402
from wrb.fetch_static import StaticFetcher  # noqa: E402

DATA_ROOT = ROOT / "data" / "raw"
COLLECTION = "obnacional"
ATTRIBUTION = "Biblioteca Digital de Obras Raras do Observatório Nacional"
OUT_PATH = ROOT / "bench" / "g3" / "revista-enum.json"

# Page counts from the Task 2a discovery (binary-searched to the 422 boundary).
DOC_PAGES = {"15": 200, "16": 176}

# Grid detector calibration (see module docstring). A "long vertical rule"
# is a column of the central table band that is dark for a large contiguous
# fraction of the page height. Primary tables have >=6 such rules (14
# columns -> ~13 inner rules + 2 border); prose has ~0-2.
_DARK_THRESHOLD = 200          # 8-bit gray; cream paper ~230+, ink well below
_BAND_Y_FRAC = (0.30, 0.85)    # vertical extent to test (skip header/footer)
_MIN_DARK_FRAC = 0.55          # a column counts as a rule if this fraction of
                               # the band rows are dark at that x
_GRID_SHORTLIST_MIN = 6        # >= this many rules on a PORTRAIT page -> table


def url_for(doc_id: str, page: int) -> str:
    return f"https://api.docvirt.com/v1/documents/{COLLECTION}/{doc_id}/{page}"


def fetch_all(fetcher: StaticFetcher) -> None:
    for doc_id, n_pages in DOC_PAGES.items():
        for page in range(1, n_pages + 1):
            cached = fetcher.cache.get("docvirt", doc_id, page, ext="webp")
            if cached is not None:
                continue
            try:
                fetcher.fetch("docvirt", doc_id, page, url_for(doc_id, page),
                              ext="webp", attribution=ATTRIBUTION)
                print(f"  fetched {doc_id}/{page}", flush=True)
            except httpx.HTTPStatusError as e:
                print(f"  {doc_id}/{page}: HTTP {e.response.status_code} - stop this doc", flush=True)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  {doc_id}/{page}: ERROR {type(e).__name__}: {e}", flush=True)


def n_vertical_rules(image_bytes: bytes) -> tuple[int, int, int]:
    """Return (width, height, n_long_vertical_rules) for a page image."""
    im = Image.open(io.BytesIO(image_bytes)).convert("L")
    w, h = im.size
    px = im.load()
    y0 = int(_BAND_Y_FRAC[0] * h)
    y1 = int(_BAND_Y_FRAC[1] * h)
    band_rows = y1 - y0
    # scan the central 90% width to skip the page margins
    x0, x1 = int(0.05 * w), int(0.95 * w)
    rules = 0
    x = x0
    prev_was_rule = False
    while x < x1:
        dark = 0
        for y in range(y0, y1):
            if px[x, y] < _DARK_THRESHOLD:
                dark += 1
        is_rule = (dark / band_rows) >= _MIN_DARK_FRAC
        # collapse adjacent dark columns (a thick rule spans a few px) into one
        if is_rule and not prev_was_rule:
            rules += 1
        prev_was_rule = is_rule
        x += 1
    return w, h, rules


def detect() -> None:
    cache = PageCache(DATA_ROOT)
    results = []
    shortlist = []
    for doc_id, n_pages in DOC_PAGES.items():
        for page in range(1, n_pages + 1):
            b = cache.get("docvirt", doc_id, page, ext="webp")
            if b is None:
                continue
            w, h, rules = n_vertical_rules(b)
            orient = "landscape" if w > h else "portrait"
            row = {"doc": doc_id, "page": page, "w": w, "h": h,
                   "orient": orient, "n_rules": rules}
            results.append(row)
            if orient == "portrait" and rules >= _GRID_SHORTLIST_MIN:
                shortlist.append({"doc": doc_id, "page": page, "n_rules": rules})
                print(f"  SHORTLIST {doc_id}/{page}: {rules} rules", flush=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "grid_shortlist_min": _GRID_SHORTLIST_MIN,
        "shortlist": shortlist,
        "per_page": results,
    }, indent=2))
    print(f"\n{len(shortlist)} shortlisted portrait-grid pages; wrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "detect"
    if mode == "fetch":
        fetcher = StaticFetcher(PageCache(DATA_ROOT), delay_s=2.0)
        fetch_all(fetcher)
    elif mode == "detect":
        detect()
    else:
        print(f"unknown mode {mode!r}; expected 'fetch' or 'detect'", file=sys.stderr)
        sys.exit(2)
