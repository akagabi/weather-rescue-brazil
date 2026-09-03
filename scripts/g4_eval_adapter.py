"""G4.4 helper - score a saved LoRA adapter on the row-level GOLD eval set
(and optionally the dev split), in a fresh inference-only process.

    python scripts/g4_eval_adapter.py --model qwen35 --adapter runs/g4/smoke1/epoch1 \
        [--dev] [--limit 0] [--out bench/g4/smoke1-epoch1.json]

Writes cell accuracy (exact numeric match, 14 columns, blanks must match)
plus per-page breakdown and the raw predictions, so the controller can
recompute independently from the file. R$0.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from g4_train import MODELS, build_batch, device, split_pages  # noqa: E402
from wrb.dataset import COLUMNS, load_manifest  # noqa: E402
from wrb.local_model import parse_row_target  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
G4 = ROOT / "data" / "g4"


def run(proc, model, examples, dev, limit=0):
    import torch
    from PIL import Image
    preds = []
    sample = examples[:limit] if limit else examples
    t0 = time.time()
    for e in sample:
        im = Image.open(G4 / e["image"]).convert("RGB")
        inp, _ = build_batch(proc, im, None, dev)
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=120, do_sample=False)
        text = proc.decode(out[0][n:], skip_special_tokens=True)
        cells, flags, problems = parse_row_target(text)
        preds.append({"doc": e["doc"], "page": e["page"], "day": e["day"], "text": text,
                      "cells": cells, "gold": e["cells"], "problems": problems})
        if hasattr(torch, "mps"):
            torch.mps.empty_cache()
    return preds, time.time() - t0


def summarize(preds):
    c = t = 0
    per_page = {}
    rows14 = 0
    for p in preds:
        key = f"{p['doc']}/{p['page']}"
        pc = pt = 0
        for col in COLUMNS:
            g, v = p["gold"].get(col), p["cells"].get(col)
            ok = (g is None and v is None) or (g is not None and v is not None and abs(g - v) < 0.005)
            pc += ok
            pt += 1
        c += pc
        t += pt
        rows14 += not any("tokens" in q for q in p["problems"])
        pp = per_page.setdefault(key, [0, 0])
        pp[0] += pc
        pp[1] += pt
    return {"rows": len(preds), "cells": t, "cell_acc": c / t if t else None, "rows_with_14": rows14,
            "per_page": {k: round(v[0] / v[1], 4) for k, v in per_page.items()}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=MODELS)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--dev-pages", default="15/60,16/159")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor
    dev = device()
    proc = AutoProcessor.from_pretrained(MODELS[args.model])
    base = AutoModelForImageTextToText.from_pretrained(MODELS[args.model], dtype=torch.bfloat16).to(dev)
    model = PeftModel.from_pretrained(base, args.adapter).to(dev)
    model.eval()
    gm = load_manifest(G4 / "gold_manifest.json")
    res = {"model": MODELS[args.model], "adapter": args.adapter}
    preds, secs = run(proc, model, gm["examples"], dev, args.limit)
    res["gold"] = {**summarize(preds), "s_per_row": round(secs / max(1, len(preds)), 2)}
    print("GOLD:", json.dumps(res["gold"]), flush=True)
    res["gold_predictions"] = preds
    if args.dev:
        tm = load_manifest(G4 / "train_manifest.json")
        dev_pages = {(p.split("/")[0], int(p.split("/")[1])) for p in args.dev_pages.split(",") if p}
        _, dev_ex = split_pages(tm["examples"], dev_pages)
        dpreds, dsecs = run(proc, model, dev_ex, dev, args.limit)
        res["dev"] = {**summarize(dpreds), "s_per_row": round(dsecs / max(1, len(dpreds)), 2)}
        res["dev_predictions"] = dpreds
        print("DEV:", json.dumps(res["dev"]), flush=True)
    out = Path(args.out) if args.out else ROOT / "bench" / "g4" / (Path(args.adapter).parent.name + "-" + Path(args.adapter).name + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
