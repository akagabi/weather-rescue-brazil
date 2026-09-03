"""G4.2 - zero-shot row reads with candidate base models on gold row crops.

    python scripts/g4_zero_shot.py --model paddle|qwen3vl|qwen35 [--rows 40]

Same strict token-order scoring as scripts/g4_baselines.py (14 numeric
tokens or the row is a structural miss). Purpose: pick the base model on a
NUMBER before any training, and measure speed/memory on the M4. Writes
bench/g4/zero_shot-<model>.json. R$0.
"""

from __future__ import annotations

import argparse
import json
import random
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from g4_baselines import parse_numbers, score_row  # noqa: E402
from wrb.dataset import load_manifest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
G4 = ROOT / "data" / "g4"
MODELS = {
    "paddle": ("PaddlePaddle/PaddleOCR-VL-1.6", "OCR:"),
    "qwen3vl": ("Qwen/Qwen3-VL-2B-Instruct", None),
    "qwen35": ("Qwen/Qwen3.5-2B", None),
}
PROMPT = ("Transcreva fielmente os números impressos nesta linha de tabela meteorológica, da esquerda "
          "para a direita, separados por ' | '. Ignore o número do dia (o primeiro à esquerda) e a "
          "direção do vento; use 'null' para célula vazia. Só a lista.")


def load(model_id: str):
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor
    proc = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.bfloat16).to("mps")
    return proc, model


def generate(proc, model, image, text: str, max_new: int = 160) -> tuple[str, int, int]:
    import torch
    msgs = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": text}]}]
    inp = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, return_dict=True,
                                   return_tensors="pt").to("mps")
    n = inp["input_ids"].shape[1]
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=max_new, do_sample=False)
    gen = out[0][n:]
    return proc.decode(gen, skip_special_tokens=True), n, len(gen)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=MODELS)
    ap.add_argument("--rows", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    model_id, fixed_prompt = MODELS[args.model]
    from PIL import Image
    t0 = time.time()
    proc, model = load(model_id)
    load_s = time.time() - t0
    gm = load_manifest(G4 / "gold_manifest.json")
    sample = random.Random(args.seed).sample(gm["examples"], min(args.rows, len(gm["examples"])))
    c = t = ok = 0
    in_tok = out_tok = 0
    samples = []
    t1 = time.time()
    for e in sample:
        im = Image.open(G4 / e["image"]).convert("RGB")
        text, n_in, n_out = generate(proc, model, im, fixed_prompt or PROMPT)
        in_tok += n_in
        out_tok += n_out
        vals = parse_numbers(text)
        if len(vals) == 15 and vals[0] == e["day"]:
            vals = vals[1:]
        cc, tt, good = score_row(vals, e["cells"])
        c += cc
        t += tt
        ok += good
        if len(samples) < 5:
            samples.append({"day": e["day"], "page": e["page"], "text": text[:200],
                            "gold": [e["cells"][k] for k in e["cells"]]})
    gen_s = time.time() - t1
    res = {"model": model_id, "prompt": fixed_prompt or PROMPT, "rows": len(sample), "cells": t,
           "cell_acc": c / t if t else None, "rows_with_14_tokens": ok,
           "load_s": round(load_s, 1), "s_per_row": round(gen_s / len(sample), 2),
           "avg_in_tokens": in_tok // len(sample), "avg_out_tokens": out_tok // len(sample),
           "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 2**20,
           "samples": samples}
    path = ROOT / "bench" / "g4" / f"zero_shot-{args.model}.json"
    path.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in res.items() if k != "samples"}, indent=1))
    for s in samples:
        print(s)


if __name__ == "__main__":
    main()
