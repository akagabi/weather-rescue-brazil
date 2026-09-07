"""The blind test: a fourth layout, ground truth committed before asking.

    python scripts/g4_blind_test.py --adapter runs/g4/gen1/epoch2

Porto do Maranhao (docvirt 14/159): 12 printed columns. The model was trained
only on 15- and 16-cell layouts, so the headline is again the CELL COUNT -
12 means it read the table, anything else means it guessed.
"""
from __future__ import annotations
import argparse, json, re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from g4_train import INSTRUCTION_PRINTED  # noqa: E402
from wrb import profile as prof  # noqa: E402
from wrb.dataset import boxes_for_centres, crop_boxes  # noqa: E402
from wrb.rows import locate_day_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "bench" / "g4" / "maranhao-blind.json"
PAGE = ROOT / "data" / "raw" / "docvirt" / "14" / "000159.webp"


def norm(t):
    return re.sub(r"[\s.,]+$", "", str(t).strip().lower())


def match(pred, truth):
    if truth is None:
        return pred is None or norm(pred or "") in ("", "null", "-", "...", "......")
    if pred is None:
        return False
    a, b = norm(pred), norm(truth)
    if a == b:
        return True
    try:
        return abs(float(a.replace(",", ".")) - float(b.replace(",", "."))) < 0.005
    except ValueError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base", default="Qwen/Qwen3.5-2B")
    args = ap.parse_args()
    spec = json.loads(SPEC.read_text())
    p = prof.load(spec["profile"])
    from PIL import Image
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor
    image = Image.open(PAGE).convert("RGB")
    loc = locate_day_rows(image, p.expected_rows("1886-02"))
    print(f"localiser: {len(loc.chain)} rows found (expected {p.expected_rows('1886-02')}), "
          f"pitch {loc.pitch}, skew {loc.skew_deg}, ok={loc.ok}")
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(args.base)
    m = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16).to(dev)
    m = PeftModel.from_pretrained(m, args.adapter).to(dev)
    m.eval()
    hit = tot = 0
    counts = Counter()
    out_rows = []
    for r in spec["rows"]:
        idx = r["row"]
        if idx >= len(loc.chain):
            continue
        crop = crop_boxes(image, boxes_for_centres([loc.chain[idx]], loc, *image.size), loc.skew_deg, scale=2.0)[0]
        msgs = [{"role": "user", "content": [{"type": "image", "image": crop},
                                             {"type": "text", "text": INSTRUCTION_PRINTED}]}]
        inp = procr.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                        return_dict=True, return_tensors="pt").to(dev)
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            o = m.generate(**inp, max_new_tokens=140, do_sample=False)
        text = procr.decode(o[0][n:], skip_special_tokens=True).split("<|im_end|>")[0].strip()
        if dev == "mps":
            torch.mps.empty_cache()
        cells = [c.strip() for c in text.split("|")]
        counts[len(cells)] += 1
        marks = [match(cells[i] if i < len(cells) else None, r["cells"][i]) for i in range(len(r["cells"]))]
        hit += sum(marks)
        tot += len(marks)
        out_rows.append({"row": idx, "n_cells": len(cells), "matched": sum(marks),
                         "of": len(marks), "got": cells, "want": r["cells"]})
        print(f"row {idx}: {len(cells)} cells, {sum(marks)}/{len(marks)}")
        print(f"   got:  {' | '.join(cells)}"[:200])
        print(f"   want: {' | '.join('null' if c is None else c for c in r['cells'])}"[:200])
    print(f"\nprofile expects {p.n_cells} cells | EMITTED: {dict(sorted(counts.items()))}")
    print(f"BLIND CELL ACCURACY: {hit}/{tot} = {hit / tot:.3f}")
    out = ROOT / "bench" / "g4" / f"blind-{Path(args.adapter).parent.name}.json"
    out.write_text(json.dumps({"adapter": args.adapter, "profile": p.id, "expected_cells": p.n_cells,
                               "cell_counts": dict(counts), "matched": hit, "total": tot,
                               "accuracy": hit / tot, "rows": out_rows}, indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
