"""Self-validating test: score the model against the TABLE'S OWN arithmetic.

    python scripts/g4_checksum_test.py --adapter runs/g4/gen3/epoch2 --doc 8 --page 15 --period 1883-01

Some printed tables carry internal checksums - here, each row's Moyenne is the
mean of its seven readings. That lets a whole page be validated with NO hand
labelling: read every row, then ask whether the model's own numbers close the
arithmetic the 1883 typesetter did.

It is a weaker claim than gold (a row could be wrong in a way that still sums),
but it is unbiased, needs no human, and scales to as many pages as we can
fetch - which is exactly what checking generality at scale requires.
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
    ap.add_argument("--profile", default="rio-1883-vapeur")
    ap.add_argument("--doc", required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--tol", type=float, default=0.006)
    args = ap.parse_args()

    p = prof.load(args.profile)
    reading_keys = [c.key for c in p.columns if c.kind == "number" and c.key != "moyenne"]
    from PIL import Image
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor
    image = Image.open(page_image_path(ROOT, args.doc, args.page)).convert("RGB")
    want_rows = p.expected_rows(args.period)
    loc = locate_day_rows(image, want_rows)
    print(f"localiser: {len(loc.chain)} rows (expected {want_rows}), pitch {loc.pitch}, ok={loc.ok}")
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(args.base)
    m = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16).to(dev)
    m = PeftModel.from_pretrained(m, args.adapter).to(dev)
    m.eval()

    closed = checked = 0
    counts: Counter = Counter()
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
        readings = [vals.get(k) for k in reading_keys]
        mean_of = vals.get("moyenne")
        rec = {"row": idx, "text": text, "problems": problems}
        if all(isinstance(v, (int, float)) for v in readings) and isinstance(mean_of, (int, float)):
            mean = sum(readings) / len(readings)
            ok = abs(mean - mean_of) < args.tol
            checked += 1
            closed += ok
            rec.update(mean=round(mean, 4), printed=mean_of, closes=ok)
            print(f"row {idx:2}: mean {mean:.4f} vs printed {mean_of} -> {'OK' if ok else 'NO'}")
        else:
            rec["closes"] = None
            print(f"row {idx:2}: incomplete ({len(text.split('|'))} cells) - cannot check")
        rows.append(rec)
    print(f"\ncell counts emitted: {dict(sorted(counts.items()))} (profile expects {p.n_cells})")
    print(f"CHECKSUM: {closed}/{checked} rows close the page's own arithmetic"
          + (f" = {closed / checked:.3f}" if checked else ""))
    print(f"rows scoreable: {checked}/{len(loc.chain)}")
    out = ROOT / "bench" / "g4" / f"checksum-{args.doc}-{args.page}-{Path(args.adapter).parent.name}.json"
    out.write_text(json.dumps({"adapter": args.adapter, "profile": p.id, "doc": args.doc,
                               "page": args.page, "period": args.period,
                               "rows_located": len(loc.chain), "scoreable": checked,
                               "closed": closed, "cell_counts": dict(counts), "rows": rows},
                              indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
