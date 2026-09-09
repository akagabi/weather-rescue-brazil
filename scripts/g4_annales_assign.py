"""Re-assign profiles for the 1883-85 Annales, fixing a counting bug.

    python scripts/g4_annales_assign.py

The first pass counted cells as len(text.split("|")), which also counts the
empty segments either side of a leading and trailing pipe. Every count came out
2 too high, so nothing matched and 236 of 250 meteorological pages were left
without a profile.

This pass re-reads one row per page and counts cells properly. It does not
re-read the captions: the months are already extracted and saved.

The volume turns out to hold more table types than the three we have profiles
for - wind direction by hour, cloud form by hour, and others - so pages whose
cell count matches nothing are recorded with their count and left alone rather
than forced into the nearest profile.
"""
from __future__ import annotations

import collections
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from g4_train import INSTRUCTION_PRINTED  # noqa: E402
from wrb.dataset import boxes_for_centres, crop_boxes  # noqa: E402
from wrb.rows import locate_day_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "docvirt" / "8"
SRC = ROOT / "data" / "g4" / "annales1883.json"
OUT = ROOT / "data" / "g4" / "annales_assigned.json"
BY_CELLS = {10: "rio-1883-barometre", 9: "rio-1883-vapeur", 13: "rio-1883-thermo"}
# The cell count alone is not enough: the hourly WIND table also has 13 cells
# (day plus six direction/force pairs), colliding with the thermometer table.
# They separate on content - a thermometer row is numbers, a wind row is
# compass points - so a row carrying three or more of these is not ours.
COMPASS = re.compile(r"\b(N|S|E|W|NE|NW|SE|SW|NNE|NNW|ENE|ESE|SSE|SSW|WNW|WSW)\b")


def n_cells(text: str) -> int:
    """Cells in a row, not the empty segments around the outer pipes."""
    return len([t for t in text.strip().strip("|").split("|")])


def main() -> None:
    from PIL import Image
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    src = json.loads(SRC.read_text())
    todo = [r for r in src if r.get("period") and "NOT_WEATHER" not in r["caption"].upper()]
    print(f"{len(todo)} páginas com período a reclassificar", flush=True)

    done = {}
    if OUT.exists():
        done = {str(r["page"]): r for r in json.loads(OUT.read_text())}
        print(f"retomando: {len(done)} já feitas", flush=True)

    base = "Qwen/Qwen3.5-2B"
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(base)
    model = AutoModelForImageTextToText.from_pretrained(base, dtype=torch.bfloat16).to(dev)
    model.eval()

    out = list(done.values())
    t0 = time.time()
    for i, r in enumerate(todo):
        if str(r["page"]) in done:
            continue
        im = Image.open(RAW / f"{r['page']:06d}.webp").convert("RGB")
        loc = locate_day_rows(im, 28)
        rec = dict(r)
        rec["cells"] = None
        rec["profile"] = None
        if loc.chain:
            crops = crop_boxes(im, boxes_for_centres(loc.chain, loc, *im.size),
                               loc.skew_deg, scale=2.0)
            msgs = [{"role": "user", "content": [{"type": "image", "image": crops[len(crops) // 2]},
                                                 {"type": "text", "text": INSTRUCTION_PRINTED}]}]
            inp = procr.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                            return_dict=True, return_tensors="pt").to(dev)
            n = inp["input_ids"].shape[1]
            with torch.no_grad():
                o = model.generate(**inp, max_new_tokens=160, do_sample=False)
            txt = procr.decode(o[0][n:], skip_special_tokens=True).split("<|im_end|>")[0].strip()
            if dev == "mps":
                torch.mps.empty_cache()
            rec["cells"] = n_cells(txt)
            rec["profile"] = BY_CELLS.get(rec["cells"])
            rec["sample_row"] = txt[:150]
            if rec["profile"] and len(COMPASS.findall(txt)) >= 3:
                rec["profile"] = None
                rec["rejected"] = "linha de rumos de vento, não de números"
        out.append(rec)
        if i % 10 == 0:
            OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
            print(f"  {i}/{len(todo)} {(time.time()-t0)/60:.1f}min p{rec['page']}: "
                  f"{rec['cells']} células -> {rec['profile']}", flush=True)

    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print("\ncontagem de células:", dict(collections.Counter(r["cells"] for r in out).most_common()))
    print("perfis:", dict(collections.Counter(r["profile"] for r in out)))

    wl = [{"profile": r["profile"], "archive": "docvirt", "doc": "8", "page": r["page"],
           "period": r["period"], "station": "Imperial Observatório, Rio de Janeiro",
           "station_source": "legenda impressa",
           "label": f"Annales 8/{r['page']} {r['period']} {r['profile']}"}
          for r in out if r["profile"]]
    p = ROOT / "data" / "g4" / "worklist_annales.json"
    p.write_text(json.dumps({"pages": wl}, indent=1, ensure_ascii=False))
    print("worklist:", len(wl), "páginas ->", p.relative_to(ROOT))


if __name__ == "__main__":
    main()
