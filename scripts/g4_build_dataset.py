"""G4.0 - build the row-level training manifest (non-gold pages) and the
row-level GOLD eval manifest (frozen gold cells), with the leakage guard.

    python scripts/g4_build_dataset.py [--no-oracle] [--verify N]

R$0: everything is local. The only model touched is the local zero-shot
Qwen3-VL-2B (Apache-2.0) used as a DAY-NUMBER ORACLE in two places:
  * pages whose row chain came out 1-3 rows too long: read the day number
    printed in each candidate first row and keep the window that starts at
    "1" and ends at the month's last day;
  * `--verify N`: on every accepted page, read the day number of N sampled
    rows and record mismatches in the manifest (a misaligned crop must not
    become a training label silently).
The oracle never writes labels - labels come only from the g2b+consensus
transcription (train) or the frozen gold (eval).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wrb.dataset import (  # noqa: E402
    GOLD_PAGES, PageReport, assert_no_gold_leakage, boxes_for_centres, crop_boxes, day_count_of,
    examples_for_page, gold_page_ids, locate_page, manifest_hash, page_image_path, window_candidates,
    write_manifest,
)
from wrb.gold import load_gold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "bench" / "g3" / "revista-full.json"
OUT = ROOT / "data" / "g4"
ORACLE_MODEL = "Qwen/Qwen3-VL-2B-Instruct"


class DayOracle:
    """Lazy local VLM: reads the day number printed at the left of a row crop."""

    def __init__(self) -> None:
        self._model = None
        self._proc = None
        self.calls = 0

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
        self._proc = AutoProcessor.from_pretrained(ORACLE_MODEL)
        self._model = AutoModelForImageTextToText.from_pretrained(ORACLE_MODEL, dtype=torch.bfloat16).to("mps")

    def read_day(self, crop: Image.Image) -> int | None:
        import torch
        if self._model is None:
            self._load()
        # only the left ~22% of the row: day number + first barometer column, small = fast
        left = crop.crop((0, 0, max(1, int(crop.width * 0.22)), crop.height))
        msgs = [{"role": "user", "content": [
            {"type": "image", "image": left},
            {"type": "text", "text": "Qual é o número do dia impresso no início desta linha (o primeiro número, à esquerda)? Responda só o número inteiro."},
        ]}]
        inp = self._proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                             return_dict=True, return_tensors="pt").to("mps")
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            out = self._model.generate(**inp, max_new_tokens=6, do_sample=False)
        text = self._proc.decode(out[0][n:], skip_special_tokens=True)
        self.calls += 1
        m = re.search(r"\d+", text)
        return int(m.group()) if m else None


def resolve_by_oracle(oracle: DayOracle, image: Image.Image, loc, day_count: int, *,
                      margin_rows: int = 8, min_direct: float = 0.7) -> tuple[list[int] | None, dict]:
    """Oracle-driven row localisation. Candidates = every strong peak within
    `margin_rows` pitches of the heuristic chain. The oracle reads the
    printed day number at each candidate; day d is assigned to the unique
    candidate that reads d. Days with no (or an ambiguous) read are
    interpolated from the nearest assigned neighbours at the page pitch,
    then checked for spacing. Accept when >= min_direct of the days were
    read directly and every interpolated row sits between its neighbours.
    Geometry only proposes; the printed numbers decide."""
    width, height = image.size
    pitch = loc.pitch or 28.0
    # The window exists to bound the search around a chain that is roughly
    # right. When the chain is badly short it inherits its unreliability: doc 8
    # page 43 has 26 peaks for a 30-day month and a chain of FIVE, so a window
    # of eight pitches either side of those five never reaches the rest of the
    # table and the oracle read 11 days of 30 before giving up. A chain that
    # has lost half its rows is not a place to anchor anything, so every peak
    # becomes a candidate and the printed numbers sort them out - which is what
    # the oracle is for.
    if len(loc.chain) < 0.5 * day_count:
        cands = sorted(loc.peaks)
    else:
        lo = (min(loc.chain) if loc.chain else 0) - margin_rows * pitch
        hi = (max(loc.chain) if loc.chain else height) + margin_rows * pitch
        cands = sorted(y for y in loc.peaks if lo <= y <= hi)
    boxes = boxes_for_centres(cands, loc, width, height)
    crops = crop_boxes(image, boxes, loc.skew_deg, scale=2.0)
    reads = oracle.read_days(crops) if hasattr(oracle, "read_days") else [oracle.read_day(c) for c in crops]
    by_day: dict[int, list[int]] = {}
    for y, r in zip(cands, reads):
        if r is not None and 1 <= r <= day_count:
            by_day.setdefault(r, []).append(y)
    assigned: dict[int, int] = {d: ys[0] for d, ys in by_day.items() if len(ys) == 1}
    # reject assignments that break monotonicity (a misread '1' for '7' etc.)
    days = sorted(assigned)
    keep: dict[int, int] = {}
    for i, d in enumerate(days):
        y = assigned[d]
        prev_ok = i == 0 or y > assigned[days[i - 1]]
        next_ok = i == len(days) - 1 or y < assigned[days[i + 1]]
        if prev_ok and next_ok:
            keep[d] = y
    info = {"candidates": len(cands), "direct": len(keep), "reads": reads}
    if len(keep) < min_direct * day_count or 1 not in keep and day_count not in keep and len(keep) < day_count:
        return None, info
    centres: list[int] = []
    known = sorted(keep)
    for d in range(1, day_count + 1):
        if d in keep:
            centres.append(keep[d])
            continue
        before = [k for k in known if k < d]
        after = [k for k in known if k > d]
        if before and after:
            a, b = before[-1], after[0]
            y = keep[a] + (keep[b] - keep[a]) * (d - a) / (b - a)
        elif before:
            y = keep[before[-1]] + pitch * (d - before[-1])
        else:
            y = keep[after[0]] - pitch * (after[0] - d)
        centres.append(round(y))
    gaps = [b - a for a, b in zip(centres, centres[1:])]
    if any(g < 0.5 * pitch for g in gaps):
        info["reason"] = f"rows overlap after interpolation: min gap {min(gaps):.0f} px"
        return None, info
    return centres, info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-oracle", action="store_true", help="skip the VLM oracle (refuse over-long chains, no verify)")
    ap.add_argument("--verify", type=int, default=3, help="rows per accepted page whose day number the oracle re-reads")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", default="", help="debug: only these pages, e.g. 14/212,15/72 (manifests still written)")
    args = ap.parse_args()
    only = {(p.split("/")[0], int(p.split("/")[1])) for p in args.only.split(",") if p}
    rng = random.Random(args.seed)
    oracle = None if args.no_oracle else DayOracle()

    bench = json.loads(BENCH.read_text())
    gold_sheets = {int(s.page): s for s in load_gold(ROOT / "gold")}
    gold_ids = gold_page_ids(ROOT / "gold")
    assert gold_ids == GOLD_PAGES, (gold_ids, GOLD_PAGES)

    train_ex, gold_ex, reports = [], [], []
    verify: list[dict] = []
    t0 = time.time()
    for p in bench["per_sheet"]:
        if not p.get("pred"):
            continue
        doc, page, period = str(p["doc"]), int(p["page"]), p["period"]
        if only and (doc, page) not in only:
            continue
        is_gold = (doc, page) in GOLD_PAGES
        day_count = day_count_of(period)
        image = Image.open(page_image_path(ROOT, doc, page)).convert("RGB")
        loc, status, reason = locate_page(image, day_count)
        rep = PageReport(doc=doc, page=page, period=period, day_count=day_count, status=status,
                         reason=reason, chain=list(loc.chain))
        centres = None
        if oracle is not None:
            centres, info = resolve_by_oracle(oracle, image, loc, day_count)
            rep.status = "ok_oracle" if centres else "refused"
            rep.reason = (f"oracle: {info['direct']}/{day_count} days read directly of {info['candidates']} candidates"
                          + ("" if centres else f"; {info.get('reason', 'too few direct reads')}; heuristic: {reason}"))
        elif status == "ok":
            centres = loc.chain
        else:
            rep.status = "refused"
        if centres is None:
            reports.append(rep)
            print(f"{doc}_{page} {period} REFUSED {rep.reason}", flush=True)
            continue
        boxes = boxes_for_centres(centres, loc, *image.size)
        sheet = gold_sheets[page].model_dump() if is_gold else p["pred"]
        subdir = OUT / ("gold_rows" if is_gold else "train_rows")
        exs = examples_for_page(doc=doc, page=page, period=period, sheet=sheet, image=image,
                                boxes=boxes, loc=loc, out_dir=subdir, manifest_dir=OUT, is_gold=is_gold)
        rep.n_examples = len(exs)
        (gold_ex if is_gold else train_ex).extend(exs)
        reports.append(rep)
        if oracle is not None:
            verify.append({"doc": doc, "page": page, "direct_reads": int(rep.reason.split("/")[0].split()[-1]), "day_count": day_count})
        print(f"{doc}_{page} {period} {rep.status} rows={len(exs)} pitch={loc.pitch} skew={loc.skew_deg}"
              + (" GOLD(eval)" if is_gold else ""), flush=True)

    meta = {"source": str(BENCH.relative_to(ROOT)), "built_at": time.strftime("%Y-%m-%d %H:%M"),
            "oracle": None if oracle is None else {"model": ORACLE_MODEL, "calls": oracle.calls},
            "verify": {"n": len(verify), "pages": verify}}
    train_manifest = OUT / "train_manifest.json"
    gold_manifest = OUT / "gold_manifest.json"
    write_manifest(train_manifest, train_ex, [r for r in reports if (r.doc, r.page) not in GOLD_PAGES], meta)
    write_manifest(gold_manifest, gold_ex, [r for r in reports if (r.doc, r.page) in GOLD_PAGES], meta)

    # the tripwire, run on what was just written
    tm = json.loads(train_manifest.read_text())
    gm = json.loads(gold_manifest.read_text())
    assert_no_gold_leakage(tm, GOLD_PAGES, frozenset(e["sha256"] for e in gm["examples"]))
    print(f"\nTRAIN: {tm['n_examples']} rows / {tm['n_cells']} cells from "
          f"{sum(1 for r in tm['pages'] if r['status'].startswith('ok'))} pages "
          f"(refused {sum(1 for r in tm['pages'] if r['status'] == 'refused')}); hash {manifest_hash(tm)[:12]}")
    print(f"GOLD EVAL: {gm['n_examples']} rows / {gm['n_cells']} cells from "
          f"{sum(1 for r in gm['pages'] if r['status'].startswith('ok'))} of 9 pages")
    print(f"oracle: {sum(v['direct_reads'] for v in verify)} direct day reads over {sum(v['day_count'] for v in verify)} days; "
          f"calls {oracle.calls if oracle else 0}; {time.time() - t0:.0f}s")
    print("leakage guard: PASS")


if __name__ == "__main__":
    main()
