"""G4.0 - naive baselines on the row-level GOLD eval set (R$0, local).

    python scripts/g4_baselines.py [--vlm-rows N]

Baseline A: tesseract (plain off-the-shelf OCR, psm 7 single line) on each
gold row crop. Numeric tokens are taken in reading order; a row is scored
cell-by-cell against the frozen gold ONLY when exactly 14 numeric tokens
come out (then token i -> gold column i); any other count is a structural
miss and every cell of that row counts as wrong. Barometer values printed
without the leading "7" are restored with `restore_thousands`, exactly as
the g2b pipeline does, so the comparison is on reading, not on that rule.

Baseline B (optional, --vlm-rows N): the un-fine-tuned local VLM
(Qwen3-VL-2B-Instruct) zero-shot on N sampled gold rows with the same
token-order scoring - the floor a fine-tune must beat.

Numbers are written to bench/g4/baselines.json.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wrb.dataset import COLUMNS, load_manifest  # noqa: E402
from wrb.reconstruct import restore_thousands  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
G4 = ROOT / "data" / "g4"
NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def parse_numbers(text: str) -> list[float]:
    """Numeric tokens in reading order; ',' decimal accepted; non-numeric
    words (wind direction, 'Gottas') and dotted blanks are skipped."""
    out = []
    for tok in NUM.findall(text.replace("|", " ")):
        try:
            out.append(float(tok.replace(",", ".")))
        except ValueError:
            pass
    return out


def score_row(values: list[float], gold_cells: dict[str, float | None]) -> tuple[int, int, bool]:
    """(correct, total, structural_ok). Token i -> COLUMNS[i] only when
    exactly 14 tokens were read; barometer thousands restored."""
    total = len(COLUMNS)
    if len(values) != total:
        return 0, total, False
    correct = 0
    for col, v in zip(COLUMNS, values):
        if col.startswith("pressure") and v < 100:
            v = restore_thousands(v)
        g = gold_cells.get(col)
        if g is not None and abs(g - v) < 0.005:
            correct += 1
    return correct, total, True


def tesseract_line(png: Path) -> str:
    r = subprocess.run(["tesseract", str(png), "stdout", "--psm", "7", "-l", "eng"],
                       capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def run_tesseract(examples: list[dict]) -> dict:
    c = t = rows_ok = 0
    t0 = time.time()
    for e in examples:
        text = tesseract_line(G4 / e["image"])
        cc, tt, ok = score_row(parse_numbers(text), e["cells"])
        c += cc
        t += tt
        rows_ok += ok
    return {"method": "tesseract --psm 7, tokens in order", "rows": len(examples), "cells": t,
            "cell_acc": c / t if t else None, "rows_with_14_tokens": rows_ok, "seconds": round(time.time() - t0, 1)}


def run_vlm(examples: list[dict], n: int, seed: int = 0) -> dict:
    import torch
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor
    model_id = "Qwen/Qwen3-VL-2B-Instruct"
    proc = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.bfloat16).to("mps")
    sample = random.Random(seed).sample(examples, min(n, len(examples)))
    prompt = ("Transcreva fielmente os números impressos nesta linha de tabela meteorológica, da esquerda "
              "para a direita, separados por ' | '. Ignore o número do dia (o primeiro à esquerda) e a "
              "direção do vento; use 'null' para célula vazia. Só a lista.")
    c = t = rows_ok = 0
    t0 = time.time()
    for e in sample:
        im = Image.open(G4 / e["image"]).convert("RGB")
        msgs = [{"role": "user", "content": [{"type": "image", "image": im}, {"type": "text", "text": prompt}]}]
        inp = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, return_dict=True,
                                       return_tensors="pt").to("mps")
        k = inp["input_ids"].shape[1]
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=120, do_sample=False)
        text = proc.decode(out[0][k:], skip_special_tokens=True)
        vals = parse_numbers(text)
        if len(vals) == 15 and vals[0] == e["day"]:
            vals = vals[1:]  # model echoed the day number despite the prompt
        cc, tt, ok = score_row(vals, e["cells"])
        c += cc
        t += tt
        rows_ok += ok
    return {"method": f"{model_id} zero-shot, tokens in order", "rows": len(sample), "cells": t,
            "cell_acc": c / t if t else None, "rows_with_14_tokens": rows_ok, "seconds": round(time.time() - t0, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vlm-rows", type=int, default=0)
    args = ap.parse_args()
    gm = load_manifest(G4 / "gold_manifest.json")
    ex = gm["examples"]
    out = {"gold_rows": len(ex), "gold_cells_nonempty": gm["n_cells"],
           "reference": {"g2b_single_shot_cell_acc": 0.9885, "g2b_consensus_cell_acc": 0.9906,
                         "note": "recomputed 2026-09-03 from bench/g2/gemini-3.5-flash-g2b.json and bench/g3/revista-full.json vs frozen gold, 3822 cells"}}
    out["tesseract"] = run_tesseract(ex)
    print("tesseract:", out["tesseract"], flush=True)
    if args.vlm_rows:
        out["vlm_zero_shot"] = run_vlm(ex, args.vlm_rows)
        print("vlm zero-shot:", out["vlm_zero_shot"], flush=True)
    path = ROOT / "bench" / "g4" / "baselines.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    print("wrote", path)


if __name__ == "__main__":
    main()
