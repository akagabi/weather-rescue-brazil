"""G4.5 - score an MLX-converted (optionally quantized) model on the gold rows.
    python scripts/g4_eval_mlx.py --model runs/g4/mlx-smoke4-q4 [--limit 0] [--out bench/g4/mlx-q4-gold.json]
Same metric as g4_eval_adapter (exact cell match, blanks must match)."""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src")); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from g4_eval_adapter import summarize
from g4_train import INSTRUCTION, layout_hint
from wrb.local_model import parse_row_target
ROOT = Path(__file__).resolve().parents[1]; G4 = ROOT / "data" / "g4"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--model", required=True); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=""); ap.add_argument("--max-tokens", type=int, default=80); args = ap.parse_args()
    from mlx_vlm import load, generate
    from mlx_vlm.prompt_utils import apply_chat_template
    model, proc = load(args.model)
    gm = json.load(open(G4 / "gold_manifest.json"))["examples"]
    sample = gm[:args.limit] if args.limit else gm
    preds = []; t0 = time.time()
    for e in sample:
        prompt = apply_chat_template(proc, model.config, INSTRUCTION + " " + layout_hint(e["doc"]), num_images=1)
        out = generate(model, proc, prompt, [str(G4 / e["image"])], max_tokens=args.max_tokens, verbose=False)
        text = out.text if hasattr(out, "text") else str(out)
        cells, flags, problems = parse_row_target(text)
        preds.append({"doc": e["doc"], "page": e["page"], "day": e["day"], "text": text, "cells": cells, "gold": e["cells"], "problems": problems})
    secs = time.time() - t0
    res = {"model": args.model, "gold": {**summarize(preds), "s_per_row": round(secs / max(1, len(preds)), 2)}, "gold_predictions": preds}
    print("GOLD:", json.dumps(res["gold"]), flush=True)
    out = Path(args.out) if args.out else ROOT / "bench" / "g4" / (Path(args.model).name + "-gold.json")
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False)); print("wrote", out)

if __name__ == "__main__":
    main()
