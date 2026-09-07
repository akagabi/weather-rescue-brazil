"""Read a page and score it against the arithmetic the PAGE asserts.

    python scripts/g4_verify_page.py --adapter runs/g4/gen3/epoch2 \
        --profile rio-1883-thermo --doc 8 --page 25 --period 1883-02

Generic over publications: the checks live in the profile (`Profile.checks`),
so any table that states its own arithmetic - an oscillation that is max minus
min, a mean of its readings - validates itself with no human labelling. Rows
whose checks fail are exactly the rows a person should look at.
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from g4_train import INSTRUCTION_PRINTED  # noqa: E402
from wrb import profile as prof  # noqa: E402
from wrb.dataset import boxes_for_centres, crop_boxes, page_image_path  # noqa: E402
from wrb.rows import locate_day_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base", default="Qwen/Qwen3.5-2B")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--doc", required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--period", required=True)
    args = ap.parse_args()
    p = prof.load(args.profile)
    if not p.checks:
        raise SystemExit(f"profile {p.id} declares no checks")
    from PIL import Image
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor
    image = Image.open(page_image_path(ROOT, args.doc, args.page)).convert("RGB")
    loc = locate_day_rows(image, p.expected_rows(args.period))
    print(f"localiser: {len(loc.chain)} rows (expected {p.expected_rows(args.period)}), ok={loc.ok}")
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(args.base)
    m = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16).to(dev)
    m = PeftModel.from_pretrained(m, args.adapter).to(dev)
    m.eval()
    counts: Counter = Counter()
    clean = checked = 0
    rows = []
    for idx, y in enumerate(loc.chain):
        crop = crop_boxes(image, boxes_for_centres([y], loc, *image.size), loc.skew_deg, scale=2.0)[0]
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
        counts[len(text.split("|"))] += 1
        vals, problems = p.parse(text)
        fails = p.verify(vals)
        scoreable = any(isinstance(vals.get(c["result"]), (int, float)) for c in p.checks)
        if scoreable:
            checked += 1
            clean += not fails
        rows.append({"row": idx, "text": text, "problems": problems, "fails": fails,
                     "scoreable": scoreable})
        mark = "OK" if scoreable and not fails else ("FAIL " + "; ".join(fails) if scoreable else "n/a")
        print(f"row {idx:2}: {len(text.split('|')):2} cells  {mark}"[:150])
    print(f"\ncells emitted: {dict(sorted(counts.items()))} (profile expects {p.n_cells})")
    print(f"SELF-CHECK: {clean}/{checked} scoreable rows satisfy the page's own arithmetic"
          + (f" = {clean / checked:.3f}" if checked else ""))
    out = ROOT / "bench" / "g4" / f"verify-{args.doc}-{args.page}-{Path(args.adapter).parent.name}.json"
    out.write_text(json.dumps({"adapter": args.adapter, "profile": p.id, "doc": args.doc, "page": args.page,
                               "checked": checked, "clean": clean, "cell_counts": dict(counts),
                               "rows": rows}, indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
