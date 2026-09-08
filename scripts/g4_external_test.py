"""The first test in this project graded by someone else's answer key.

    python scripts/g4_external_test.py --adapter runs/g4/gen3/epoch2 --case rain

Every earlier measurement was self-graded: our gold set is our own labels, and
the checksum test asks whether the model's numbers close the model's own parse.
Here the truth comes from Oxford. The Radcliffe Observatory's printed tables
(Internet Archive, 1881) and Oxford's modern published series
(geog.ox.ac.uk) describe the SAME observations, digitised independently more
than a century apart.

The two series are not numerically identical - Oxford homogenised theirs - so
the test is not equality but CONSISTENCY: fit a single scale (rain) or offset
(temperature) across all cells, then ask how many cells sit on it. A misread
digit cannot sit on a line fitted by every other cell, so residual outliers
localise transcription errors without anyone reading the page.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from g4_train import INSTRUCTION_PRINTED  # noqa: E402
from wrb import profile as prof  # noqa: E402
from wrb.dataset import boxes_for_centres, crop_boxes  # noqa: E402
from wrb.rows import locate_day_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

CASES = {
    "rain": {
        "profile": "radcliffe-rain-1851-1879",
        "image": "data/raw/ia/astronomicaland03obsegoog/000123.jpg",
        "reference": "oxf_rain.csv",
        "years": (1851, 1879),
        "relation": "scale",     # printed inches * 25.4 vs published mm
        "convert": lambda v: v * 25.4,
        "unit_printed": "in", "unit_reference": "mm",
        "title": "Radcliffe Table IV, monthly rain 1851-1879 vs Oxford published mm",
    },
    "drybulb": {
        "profile": "radcliffe-drybulb-1855-1879",
        "image": "data/raw/ia/astronomicaland03obsegoog/000121.jpg",
        "reference": "oxf_t.csv",
        "years": (1855, 1879),
        "relation": "offset",    # (F-32)/1.8 vs published mean-of-max-min C
        "convert": lambda v: (v - 32.0) / 1.8,
        "unit_printed": "F", "unit_reference": "C",
        "title": "Radcliffe Table II, dry bulb 1855-1879 vs Oxford published Tmean",
    },
}


def read_reference(path: Path, years: tuple[int, int]) -> dict[int, dict[str, float]]:
    """Oxford publishes YYYY,Jan..Dec,Annual with a few banner lines on top."""
    out: dict[int, dict[str, float]] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh):
            if not row or not row[0].strip().isdigit():
                continue
            y = int(row[0])
            if not (years[0] <= y <= years[1]):
                continue
            vals = {}
            for i, m in enumerate(MONTHS, start=1):
                cell = row[i].strip() if i < len(row) else ""
                if cell:
                    try:
                        vals[m] = float(cell)
                    except ValueError:
                        pass
            out[y] = vals
    return out


def transcribe(image_path: Path, p, adapter: str, base: str, limit: int = 0) -> list[dict]:
    from PIL import Image
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor

    image = Image.open(image_path).convert("RGB")
    want = p.expected_rows("")
    loc = locate_day_rows(image, want, **p.geometry())
    print(f"located {len(loc.chain)} rows (expected {want}), ok={loc.ok}, skew={loc.skew_deg:.3f}deg")
    if not loc.chain:
        raise SystemExit("no rows located")
    crops = crop_boxes(image, boxes_for_centres(loc.chain, loc, *image.size), loc.skew_deg, scale=2.0)
    if limit:
        crops = crops[:limit]

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(base)
    model = AutoModelForImageTextToText.from_pretrained(base, dtype=torch.bfloat16).to(dev)
    model = PeftModel.from_pretrained(model, adapter).to(dev)
    model.eval()

    rows = []
    for i, crop in enumerate(crops):
        msgs = [{"role": "user", "content": [{"type": "image", "image": crop},
                                             {"type": "text", "text": INSTRUCTION_PRINTED}]}]
        inp = procr.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                        return_dict=True, return_tensors="pt").to(dev)
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            o = model.generate(**inp, max_new_tokens=200, do_sample=False)
        text = procr.decode(o[0][n:], skip_special_tokens=True).split("<|im_end|>")[0].strip()
        if dev == "mps":
            torch.mps.empty_cache()
        values, problems = p.parse(text)
        rows.append({"row": i, "raw": text, "values": values, "problems": problems})
        print(f"  row {i:2d}: {text[:96]}", flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base", default="Qwen/Qwen3.5-2B")
    ap.add_argument("--case", choices=sorted(CASES), required=True)
    ap.add_argument("--refdir", default="/private/tmp/claude-501/-Users-bueno-detail/"
                                        "03aa8294-398f-4419-bfc6-dedee8ad0e1d/scratchpad")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    case = CASES[args.case]
    p = prof.load(case["profile"])
    ref = read_reference(Path(args.refdir) / case["reference"], case["years"])
    print(f"\n{case['title']}")
    print(f"reference: {len(ref)} years, {sum(len(v) for v in ref.values())} monthly values\n")

    rows = transcribe(ROOT / case["image"], p, args.adapter, args.base, args.limit)

    # pair every transcribed cell with the published one for the same year+month
    pairs = []
    for r in rows:
        y = r["values"].get("year")
        try:
            y = int(float(y))
        except (TypeError, ValueError):
            continue
        if y not in ref:
            continue
        for m in MONTHS:
            got, want = r["values"].get(m), ref[y].get(m)
            if not isinstance(got, (int, float)) or want is None:
                continue
            pairs.append({"year": y, "month": m, "printed": float(got),
                          "converted": case["convert"](float(got)), "published": want})

    if not pairs:
        raise SystemExit("no cells could be paired - check the year column")

    if case["relation"] == "scale":
        for q in pairs:
            q["stat"] = q["published"] / q["converted"] if q["converted"] else float("nan")
    else:
        for q in pairs:
            q["stat"] = q["published"] - q["converted"]
    good = [q["stat"] for q in pairs if q["stat"] == q["stat"]]
    centre = statistics.median(good)
    spread = statistics.median([abs(s - centre) for s in good]) or 1e-9
    for q in pairs:
        q["residual_mad"] = abs(q["stat"] - centre) / spread

    OUT = 6.0   # robust z: >6 median-absolute-deviations from the fitted relation
    agree = [q for q in pairs if q["residual_mad"] <= OUT]
    bad = sorted((q for q in pairs if q["residual_mad"] > OUT),
                 key=lambda q: -q["residual_mad"])

    rel = "ratio published/printed" if case["relation"] == "scale" else "offset published-printed"
    print(f"\n{'='*72}\nEXTERNAL AGREEMENT — {case['title']}\n{'='*72}")
    print(f"cells compared            {len(pairs)}")
    print(f"fitted {rel:<24} {centre:.4f}  (MAD {spread:.4f})")
    print(f"cells ON the relation     {len(agree)}/{len(pairs)} = {len(agree)/len(pairs):.1%}")
    print(f"cells OFF (suspect)       {len(bad)}")
    for q in bad[:15]:
        print(f"   {q['year']} {q['month']}: printed {q['printed']}{case['unit_printed']}"
              f" -> {q['converted']:.2f}, Oxford {q['published']}{case['unit_reference']}"
              f"  (z={q['residual_mad']:.1f})")

    out = Path(args.out) if args.out else ROOT / "bench" / "g4" / f"external-{args.case}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"case": args.case, "title": case["title"], "adapter": args.adapter,
                               "n_cells": len(pairs), "fitted_centre": centre, "mad": spread,
                               "on_relation": len(agree), "agreement": len(agree)/len(pairs),
                               "suspects": bad, "rows": rows}, indent=1, ensure_ascii=False))
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
