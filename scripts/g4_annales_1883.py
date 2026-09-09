"""Identify and transcribe the Annales de l'Observatoire Impérial (doc 8, 1883).

    python scripts/g4_annales_1883.py

This volume prints THREE different daily tables per month, all under the same
title "Observations météorologiques du mois de X 1883":

    rio-1883-barometre  10 cells  7 readings/day, thousands elided (700mm +)
    rio-1883-vapeur      9 cells  7 readings/day, vapour tension
    rio-1883-thermo     13 cells  thermometers, rain, evaporation, ozone

The caption cannot separate them reliably (the thermo page carries no
subtitle), so the profile is chosen by READING ONE ROW and counting the cells
the model emits. The three counts are distinct, which is what makes this safe.
The month still comes from the caption.

Resumable: rerun and it skips pages already identified.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from g4_train import INSTRUCTION_PRINTED  # noqa: E402
from wrb import profile as prof  # noqa: E402
from wrb.rows import (PROBE_X_FRAC, find_peaks, ink_threshold, pitch_candidates,  # noqa: E402
                      row_profile, vertical_rules, locate_day_rows)
from wrb.dataset import boxes_for_centres, crop_boxes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "docvirt" / "8"
OUT = ROOT / "data" / "g4" / "annales1883.json"

MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
          "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10,
          "novembre": 11, "decembre": 12}
BY_CELLS = {10: "rio-1883-barometre", 9: "rio-1883-vapeur", 13: "rio-1883-thermo"}


def strip(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")


def candidates() -> list[int]:
    from PIL import Image
    out = []
    for p in sorted(RAW.glob("*.webp")):
        try:
            im = Image.open(p).convert("L")
        except Exception:
            continue
        thr = ink_threshold(im)
        if len(vertical_rules(im, thr)) < 4:
            continue
        x0, x1 = int(im.width * PROBE_X_FRAC[0]), int(im.width * PROBE_X_FRAC[1])
        pr, _ = row_profile(im, x0, x1, thr)
        c = pitch_candidates(pr)
        if c and len(find_peaks(pr, c[0])) >= 15:
            out.append(int(p.stem))
    return out


def main() -> None:
    from PIL import Image
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    seen: dict[str, dict] = {}
    if OUT.exists():
        seen = {str(r["page"]): r for r in json.loads(OUT.read_text())}
        print(f"retomando: {len(seen)} páginas já identificadas", flush=True)

    pages = candidates()
    print(f"{len(pages)} páginas candidatas em doc 8", flush=True)

    base = "Qwen/Qwen3.5-2B"
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(base)
    model = AutoModelForImageTextToText.from_pretrained(base, dtype=torch.bfloat16).to(dev)
    model.eval()

    def gen(img, prompt, n_tok):
        msgs = [{"role": "user", "content": [{"type": "image", "image": img},
                                             {"type": "text", "text": prompt}]}]
        inp = procr.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                        return_dict=True, return_tensors="pt").to(dev)
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            o = model.generate(**inp, max_new_tokens=n_tok, do_sample=False)
        txt = procr.decode(o[0][n:], skip_special_tokens=True).split("<|im_end|>")[0].strip()
        if dev == "mps":
            torch.mps.empty_cache()
        return txt

    ask = ("This is a page from an 1883 French scientific annual. If it holds a table of "
           "daily meteorological observations, reply with its title line naming the month "
           "and year. If it is prose or any other kind of table, reply exactly NOT_WEATHER.")

    results = list(seen.values())
    t0 = time.time()
    for i, page in enumerate(pages):
        if str(page) in seen:
            continue
        path = RAW / f"{page:06d}.webp"
        im = Image.open(path).convert("RGB")
        small = im if im.width <= 1000 else im.resize(
            (1000, max(1, int(im.height * 1000 / im.width))), Image.LANCZOS)
        cap = gen(small, ask, 80)
        rec = {"page": page, "caption": cap, "profile": None, "period": None, "n_cells": None}
        if "NOT_WEATHER" not in cap.upper():
            c = strip(cap)
            year = re.search(r"\b(188\d)\b", c)
            month = next((n for name, n in MONTHS.items() if name in c), None)
            if year and month:
                rec["period"] = f"{int(year.group(1)):04d}-{month:02d}"
            # the caption cannot tell the three layouts apart: read one row and
            # count the cells the model emits. 9, 10 and 13 are distinct.
            loc = locate_day_rows(im, 28)
            if loc.chain:
                crops = crop_boxes(im, boxes_for_centres(loc.chain, loc, *im.size),
                                   loc.skew_deg, scale=2.0)
                txt = gen(crops[len(crops) // 2], INSTRUCTION_PRINTED, 160)
                n_cells = len([t for t in txt.split("|")])
                rec["n_cells"] = n_cells
                rec["profile"] = BY_CELLS.get(n_cells)
                rec["sample_row"] = txt[:120]
        results.append(rec)
        if i % 10 == 0:
            OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False))
            print(f"  {i}/{len(pages)}  {(time.time()-t0)/60:.1f}min  p{page}: "
                  f"{rec['profile']} {rec['period']} | {cap[:52]}", flush=True)

    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    ok = [r for r in results if r["profile"] and r["period"]]
    import collections
    print(f"\n{len(ok)}/{len(results)} páginas com perfil E período")
    print(collections.Counter(r["profile"] for r in results))

    wl = [{"profile": r["profile"], "archive": "docvirt", "doc": "8", "page": r["page"],
           "period": r["period"], "station": "Imperial Observatório, Rio de Janeiro",
           "station_source": "legenda impressa",
           "label": f"Annales 8/{r['page']} {r['period']} {r['profile']}"} for r in ok]
    p = ROOT / "data" / "g4" / "worklist_annales1883.json"
    p.write_text(json.dumps({"pages": wl}, indent=1, ensure_ascii=False))
    print("worklist:", p.relative_to(ROOT), len(wl), "páginas")


if __name__ == "__main__":
    main()
