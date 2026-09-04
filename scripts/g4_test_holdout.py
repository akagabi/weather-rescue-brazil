"""G4.6 - the generalisation test: read a HELD-OUT layout the model has never
seen, and score it against hand-read ground truth.

    python scripts/g4_test_holdout.py --adapter runs/g4/smoke5/epoch2 --printed
    python scripts/g4_test_holdout.py --adapter runs/g4/smoke4/epoch2          # fixed-schema baseline

Corumba (docvirt 16/72) is the held-out layout: 62 rows (two readings a day),
16 printed columns, instruments absent from the Revista, four free-text
columns. Ground truth for the first rows was read by hand and committed to
`bench/g4/corumba-holdout.json` BEFORE any model was asked, so this is a real
test and not a post-hoc story.

Scoring is deliberately blunt: for each printed cell, does the model's cell at
that position match the printed one (numbers within 0.005, text case-folded)?
A model that reads the glyphs but cannot follow an unseen column layout scores
near zero here even when every digit it emits is correct - which is exactly
the failure the schema-free target is meant to fix.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from g4_train import INSTRUCTION, INSTRUCTION_PRINTED, layout_hint  # noqa: E402
from wrb.dataset import boxes_for_centres, crop_boxes  # noqa: E402
from wrb.rows import locate_day_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "bench" / "g4" / "corumba-holdout.json"
PAGE = ROOT / "data" / "raw" / "docvirt" / "16" / "000072.webp"
N_ROWS = 62


def norm(tok: str) -> str:
    return re.sub(r"[\s.,]+$", "", tok.strip().lower())


def cell_match(pred: str | None, truth: str | None) -> bool:
    if truth is None:
        return pred is None or norm(pred or "") in ("", "null", "-", "...")
    if pred is None:
        return False
    p, t = norm(pred), norm(truth)
    if p == t:
        return True
    try:
        return abs(float(p.replace(",", ".")) - float(t.replace(",", "."))) < 0.005
    except ValueError:
        return p.replace(".", "").replace(",", "") == t.replace(".", "").replace(",", "")


def split_cells(text: str) -> list[str]:
    for stop in ("<|im_end|>", "<|endoftext|>", "</s>"):
        text = text.split(stop)[0]
    return [c.strip() for c in text.strip().strip("`").split("|")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True, help="LoRA dir, or an MLX model dir with --mlx")
    ap.add_argument("--printed", action="store_true", help="adapter was trained with the schema-free target")
    ap.add_argument("--base", default="Qwen/Qwen3.5-2B")
    ap.add_argument("--rows", type=int, default=0, help="also dump this many raw reads for eyeballing")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    spec = json.loads(SPEC.read_text())
    truth = {r["chain_index"]: r["cells"] for r in spec["rows"]}
    image = Image.open(PAGE).convert("RGB")
    loc = locate_day_rows(image, N_ROWS)
    if not loc.ok:
        print(f"row localisation failed: {loc.reason}")
        return
    print(f"localiser: {len(loc.chain)} rows found on the held-out page (pitch {loc.pitch}, skew {loc.skew_deg})")

    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    proc = AutoProcessor.from_pretrained(args.base)
    model = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16).to(dev)
    model = PeftModel.from_pretrained(model, args.adapter).to(dev)
    model.eval()
    instruction = INSTRUCTION_PRINTED if args.printed else INSTRUCTION
    hint = "" if args.printed else layout_hint("16")

    want = sorted(set(list(truth) + list(range(min(args.rows, len(loc.chain))))))
    results = []
    hit = tot = 0
    for idx in want:
        box = boxes_for_centres([loc.chain[idx]], loc, *image.size)
        crop = crop_boxes(image, box, loc.skew_deg, scale=2.0)[0]
        msgs = [{"role": "user", "content": [{"type": "image", "image": crop},
                                             {"type": "text", "text": instruction + (" " + hint if hint else "")}]}]
        inp = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                       return_dict=True, return_tensors="pt").to(dev)
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=120, do_sample=False)
        text = proc.decode(out[0][n:], skip_special_tokens=True)
        if dev == "mps":
            torch.mps.empty_cache()
        cells = split_cells(text)
        rec = {"row": idx, "n_cells": len(cells), "text": text.strip()}
        if idx in truth:
            t = truth[idx]
            marks = [cell_match(cells[i] if i < len(cells) else None, t[i]) for i in range(len(t))]
            rec.update(expected_cells=len(t), matched=sum(marks), marks=marks, truth=t, got=cells)
            hit += sum(marks)
            tot += len(t)
        results.append(rec)
        print(f"row {idx}: emitted {len(cells)} cells"
              + (f", matched {rec['matched']}/{rec['expected_cells']}" if idx in truth else ""))
        print(f"   got:  {' | '.join(cells)}"[:220])
        if idx in truth:
            print(f"   want: {' | '.join('null' if c is None else c for c in truth[idx])}"[:220])

    print(f"\nHELD-OUT CELL ACCURACY: {hit}/{tot} = {hit / tot:.3f}" if tot else "\nno scored rows")
    out = Path(args.out) if args.out else ROOT / "bench" / "g4" / f"holdout-{Path(args.adapter).parent.name}.json"
    out.write_text(json.dumps({"adapter": args.adapter, "printed": args.printed,
                               "cells_matched": hit, "cells_total": tot,
                               "accuracy": (hit / tot) if tot else None, "rows": results}, indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
