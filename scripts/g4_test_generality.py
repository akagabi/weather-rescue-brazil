"""The generality test: does the model read the column count off the IMAGE?

    python scripts/g4_test_generality.py --adapter runs/g4/gen1/epoch3

Trained on Santa-Cruz (15 printed cells) and Corumba (16 cells), balanced,
with Rio held out entirely. Rio prints 16 cells. So:

  * the headline number is the DISTRIBUTION OF CELL COUNTS the model emits on
    Rio rows it has never seen. 16 means it looked; 15 means it guessed from
    the layout it saw most, which is the failure in docs/g4-generalisation.md;
  * accuracy is scored against the frozen human-verified gold, mapped through
    the Rio profile, and is only meaningful once the count is right.

Rio gold is the right test set precisely because it is the one layout with
human-verified truth AND the one the model was never shown.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from g4_train import INSTRUCTION_PRINTED  # noqa: E402
from wrb import profile as prof  # noqa: E402
from wrb.dataset import load_manifest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
G4 = ROOT / "data" / "g4"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base", default="Qwen/Qwen3.5-2B")
    ap.add_argument("--rows", type=int, default=60)
    ap.add_argument("--profile", default="revista-rio-1886")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    import torch
    from peft import PeftModel
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor

    p = prof.load(args.profile)
    gm = load_manifest(G4 / "gold_manifest.json")
    sample = gm["examples"][:args.rows]
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(args.base)
    model = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16).to(dev)
    model = PeftModel.from_pretrained(model, args.adapter).to(dev)
    model.eval()

    counts: Counter = Counter()
    hit = tot = 0
    preds = []
    for e in sample:
        im = Image.open(G4 / e["image"]).convert("RGB")
        msgs = [{"role": "user", "content": [{"type": "image", "image": im},
                                             {"type": "text", "text": INSTRUCTION_PRINTED}]}]
        inp = procr.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                        return_dict=True, return_tensors="pt").to(dev)
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=140, do_sample=False)
        text = procr.decode(out[0][n:], skip_special_tokens=True)
        if dev == "mps":
            torch.mps.empty_cache()
        values, problems = p.parse(text)
        # the model reads what is PRINTED; elided digits go back in code, which
        # is the production path (docs/g4-print-fidelity.md)
        values = p.from_printed(values)
        n_cells = len([c for c in text.split("<|im_end|>")[0].split("|")])
        counts[n_cells] += 1
        # score the numeric columns against the frozen gold
        row_hit = 0
        for key in p.numeric_keys:
            g, v = e["cells"].get(key), values.get(key)
            ok = (g is None and v is None) or (g is not None and v is not None and abs(g - float(v)) < 0.005)
            row_hit += ok
            tot += 1
        hit += row_hit
        preds.append({"page": e["page"], "day": e["day"], "n_cells": n_cells,
                      "text": text.split("<|im_end|>")[0].strip(),
                      "matched": row_hit, "of": len(p.numeric_keys)})

    print(f"\nprofile {p.id}: {p.n_cells} printed cells expected")
    print("CELL COUNTS EMITTED:", dict(sorted(counts.items())))
    right = counts.get(p.n_cells, 0)
    print(f"  rows with the right count: {right}/{len(sample)} = {right / len(sample):.0%}")
    print(f"CELL ACCURACY vs frozen gold: {hit}/{tot} = {hit / tot:.4f}")
    for q in preds[:5]:
        print(f"  p{q['page']} d{q['day']}: {q['n_cells']} cells, {q['matched']}/{q['of']} | {q['text'][:110]}")
    out = Path(args.out) if args.out else ROOT / "bench" / "g4" / f"generality-{Path(args.adapter).parent.name}.json"
    out.write_text(json.dumps({"adapter": args.adapter, "profile": p.id,
                               "expected_cells": p.n_cells, "cell_counts": dict(counts),
                               "right_count_frac": right / len(sample),
                               "cell_accuracy": hit / tot, "rows": preds}, indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
