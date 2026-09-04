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


def resolve_window(oracle: DayOracle, image: Image.Image, loc, day_count: int,
                   min_match: float = 0.8) -> list[int] | None:
    """Pick the day_count-long window of an over-long chain by reading the
    printed day number of EVERY chain row once, then choosing the offset
    whose reads best match 1..day_count. Robust to a few misreads (a lone
    thin '1' is the classic one): accept when >= min_match of the rows in
    the window agree with their expected day."""
    width, height = image.size
    boxes = boxes_for_centres(loc.chain, loc, width, height)
    crops = crop_boxes(image, boxes, loc.skew_deg, scale=2.0)
    reads = [oracle.read_day(c) for c in crops]
    best, best_off = -1, None
    for off in range(len(loc.chain) - day_count + 1):
        hits = sum(1 for k in range(day_count) if reads[off + k] == k + 1)
        if hits > best:
            best, best_off = hits, off
    if best_off is None or best < min_match * day_count:
        print(f"  oracle reads {reads} -> best {best}/{day_count} at offset {best_off}", flush=True)
        return None
    return loc.chain[best_off:best_off + day_count]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-oracle", action="store_true", help="skip the VLM oracle (refuse over-long chains, no verify)")
    ap.add_argument("--verify", type=int, default=3, help="rows per accepted page whose day number the oracle re-reads")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
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
        is_gold = (doc, page) in GOLD_PAGES
        day_count = day_count_of(period)
        image = Image.open(page_image_path(ROOT, doc, page)).convert("RGB")
        loc, status, reason = locate_page(image, day_count)
        rep = PageReport(doc=doc, page=page, period=period, day_count=day_count, status=status,
                         reason=reason, chain=list(loc.chain))
        centres = loc.chain if status == "ok" else None
        if status == "needs_oracle" and oracle is not None:
            centres = resolve_window(oracle, image, loc, day_count)
            rep.status = "ok_oracle" if centres else "refused"
            if not centres:
                rep.reason = f"oracle could not find a window starting at day 1: {reason}"
        elif status == "needs_oracle":
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
        if oracle is not None and args.verify:
            days = sorted(rng.sample(range(1, day_count + 1), min(args.verify, day_count)))
            crops = crop_boxes(image, [boxes[d - 1] for d in days], loc.skew_deg)
            for d, c in zip(days, crops):
                got = oracle.read_day(c)
                verify.append({"doc": doc, "page": page, "day": d, "read": got, "match": got == d})
        print(f"{doc}_{page} {period} {rep.status} rows={len(exs)} pitch={loc.pitch} skew={loc.skew_deg}"
              + (" GOLD(eval)" if is_gold else ""), flush=True)

    meta = {"source": str(BENCH.relative_to(ROOT)), "built_at": time.strftime("%Y-%m-%d %H:%M"),
            "oracle": None if oracle is None else {"model": ORACLE_MODEL, "calls": oracle.calls},
            "verify": {"n": len(verify), "mismatches": [v for v in verify if not v["match"]]}}
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
    print(f"verify: {len(verify)} day reads, {sum(1 for v in verify if not v['match'])} mismatches; "
          f"oracle calls {oracle.calls if oracle else 0}; {time.time() - t0:.0f}s")
    print("leakage guard: PASS")


if __name__ == "__main__":
    main()
