"""G4.3 - LoRA fine-tune of a small VLM to read one table row (row crop ->
row target text, see wrb.local_model), on the M4 (MPS) or any single GPU.

    python scripts/g4_train.py --model paddle|qwen3vl|qwen35 --run smoke1 \
        [--epochs 3] [--lr 1e-4] [--rank 16] [--max-rows 0] [--dev-pages 15/60,16/159] \
        [--eval-gold] [--synthetic data/g4/synthetic_manifest.json]

Guards, in order, before a single step:
  1. the training manifest passes assert_no_gold_leakage (id + is_gold + sha
     against the gold crops) and its manifest_hash is recorded in the run;
  2. dev split = WHOLE pages held out (never rows of a page that is trained on);
  3. the vision encoder is frozen; LoRA only on the language model.
Model-agnostic: everything goes through the model's own chat template, so
the same script serves PaddleOCR-VL, Qwen3-VL and Qwen3.5. Plain torch loop
(no TRL) to avoid API churn and to control MPS memory.

Cost: R$0 on the M4. On a rented GPU state the cap before launching.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wrb.dataset import GOLD_PAGES, assert_no_gold_leakage, load_manifest, manifest_hash  # noqa: E402
from wrb.local_model import COLUMNS, parse_row_target, row_target  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
G4 = ROOT / "data" / "g4"
RUNS = ROOT / "runs" / "g4"
MODELS = {
    "paddle": "PaddlePaddle/PaddleOCR-VL-1.6",
    "qwen3vl": "Qwen/Qwen3-VL-2B-Instruct",
    "qwen35": "Qwen/Qwen3.5-2B",
}
LAYOUT_HINT = {
    "14": "Layout A: Imperial Observatorio (Rio, 1886), 14 colunas, COM a coluna de evaporação ao sol.",
}
DEFAULT_HINT = "Layout B: Observatorio de Santa-Cruz (1889-90), a coluna de evaporação ao sol é sempre null."
OVERSAMPLE = {"14": 4}  # smoke1 lesson: gold is all vol 14, training was 91% vols 15/16 -> tail columns shifted


def layout_hint(doc: str) -> str:
    return LAYOUT_HINT.get(str(doc), DEFAULT_HINT)


INSTRUCTION = ("Leia esta linha de tabela meteorológica impressa (século XIX). Responda com as 14 células "
               "numéricas na ordem das colunas, separadas por ' | ', 'null' para célula vazia, e no fim "
               "'dir=' com a direção do vento impressa. Transcreva fielmente o que está impresso.")


def device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def split_pages(examples: list[dict], dev_pages: set[tuple[str, int]]) -> tuple[list[dict], list[dict]]:
    train = [e for e in examples if (e["doc"], e["page"]) not in dev_pages]
    dev = [e for e in examples if (e["doc"], e["page"]) in dev_pages]
    return train, dev


def build_batch(proc, image, target: str | None, dev: str, hint: str = ""):
    """Tokenise prompt(+target) through the chat template; labels mask the
    prompt so loss is on the target only."""
    import torch
    user = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": INSTRUCTION + (" " + hint if hint else "")}]}]
    prompt = proc.apply_chat_template(user, add_generation_prompt=True, tokenize=True, return_dict=True,
                                      return_tensors="pt")
    if target is None:
        return prompt.to(dev), None
    full_msgs = user + [{"role": "assistant", "content": [{"type": "text", "text": target}]}]
    full = proc.apply_chat_template(full_msgs, add_generation_prompt=False, tokenize=True, return_dict=True,
                                    return_tensors="pt")
    n_prompt = prompt["input_ids"].shape[1]
    labels = full["input_ids"].clone()
    labels[:, :n_prompt] = -100
    return full.to(dev), labels.to(dev)


def cell_accuracy(proc, model, examples: list[dict], dev: str, max_new: int = 120,
                  limit: int = 0) -> dict:
    """Generate for each row, parse, compare to the row's cells (exact
    numeric match at 0.005; barometer compared on the printed low-order
    value, i.e. before thousands restoration, so the metric is pure reading)."""
    import torch
    model.eval()
    c = t = rows14 = 0
    t0 = time.time()
    sample = examples[:limit] if limit else examples
    for e in sample:
        from PIL import Image
        im = Image.open(G4 / e["image"]).convert("RGB")
        inp, _ = build_batch(proc, im, None, dev, layout_hint(e["doc"]))
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=max_new, do_sample=False)
        text = proc.decode(out[0][n:], skip_special_tokens=True)
        if dev == "mps":
            torch.mps.empty_cache()
        cells, _, problems = parse_row_target(text)
        rows14 += not any("tokens" in p for p in problems)
        for col in COLUMNS:
            t += 1
            g, v = e["cells"].get(col), cells.get(col)
            if g is None and v is None:
                c += 1
            elif g is not None and v is not None and abs(g - v) < 0.005:
                c += 1
    model.train()
    return {"rows": len(sample), "cells": t, "cell_acc": c / t if t else None, "rows_with_14": rows14,
            "s_per_row": round((time.time() - t0) / max(1, len(sample)), 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=MODELS)
    ap.add_argument("--run", required=True)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--max-rows", type=int, default=0, help="cap training rows (smoke runs)")
    ap.add_argument("--dev-pages", default="15/60,16/159")
    ap.add_argument("--eval-gold", action="store_true", help="also score the gold rows at the end")
    ap.add_argument("--eval-limit", type=int, default=0, help="cap rows per eval (0 = all)")
    ap.add_argument("--synthetic", default="", help="optional extra manifest (synthetic rows)")
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--oversample", action="store_true", help="repeat vol-14 rows x4 (OVERSAMPLE)")
    ap.add_argument("--oversample-factor", type=int, default=0, help="override the vol-14 repeat factor")
    ap.add_argument("--augment", action="store_true", help="on-the-fly photometric/geometric jitter on training crops (wrb.synth.jitter)")
    ap.add_argument("--no-hint", action="store_true", help="disable the per-volume layout hint")
    ap.add_argument("--save-every", type=int, default=20, help="checkpoint adapter+optimizer every N optimizer steps")
    ap.add_argument("--resume", default="", help="checkpoint dir (runs/g4/<run>/latest) to resume from")
    ap.add_argument("--stop-after-steps", type=int, default=0, help="debug: exit right after this optimizer step (tests resume)")
    args = ap.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    dev = device()
    out_dir = RUNS / args.run
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- guards -------------------------------------------------------------
    tm = load_manifest(G4 / "train_manifest.json")
    gm = load_manifest(G4 / "gold_manifest.json")
    assert_no_gold_leakage(tm, GOLD_PAGES, frozenset(e["sha256"] for e in gm["examples"]))
    tm_hash = manifest_hash(tm)
    dev_pages = {(p.split("/")[0], int(p.split("/")[1])) for p in args.dev_pages.split(",") if p}
    train_ex, dev_ex = split_pages(tm["examples"], dev_pages)
    if args.synthetic:
        sm = load_manifest(Path(args.synthetic))
        assert_no_gold_leakage(sm, GOLD_PAGES, frozenset(e["sha256"] for e in gm["examples"]))
        train_ex = train_ex + sm["examples"]
    if args.oversample:
        factor = {k: (args.oversample_factor or v) for k, v in OVERSAMPLE.items()}
        extra = [e for e in train_ex for _ in range(factor.get(str(e["doc"]), 1) - 1)]
        train_ex = train_ex + extra
    random.shuffle(train_ex)
    if args.max_rows:
        train_ex = train_ex[:args.max_rows]
    hint_for = (lambda doc: "") if args.no_hint else layout_hint
    print(f"device={dev} train_rows={len(train_ex)} dev_rows={len(dev_ex)} dev_pages={sorted(dev_pages)} "
          f"manifest_hash={tm_hash[:12]}", flush=True)

    # --- model -------------------------------------------------------------
    model_id = MODELS[args.model]
    proc = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.bfloat16).to(dev)
    for name, p in model.named_parameters():
        if any(k in name.lower() for k in ("vision", "visual", "image", "patch", "merger", "projector")):
            p.requires_grad_(False)
    lcfg = LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05, bias="none",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
                      exclude_modules=r".*(vision|visual|image|patch|merger|projector).*")
    if args.resume:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.resume, is_trainable=True)
    else:
        model = get_peft_model(model, lcfg)
    model.print_trainable_parameters()
    if hasattr(model, "gradient_checkpointing_enable"):
        try:
            model.gradient_checkpointing_enable()
            model.enable_input_require_grads()
        except Exception as e:  # noqa: BLE001
            print("gradient checkpointing unavailable:", e)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.0)
    steps_total = math.ceil(len(train_ex) * args.epochs / args.grad_accum)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 20) * max(0.05, 1 - s / max(1, steps_total)))

    log = {"args": vars(args), "model": model_id, "manifest_hash": tm_hash, "device": dev,
           "train_rows": len(train_ex), "dev_rows": len(dev_ex), "epochs": []}
    state = {"step": 0, "epoch": 1, "idx": 0, "order": None}
    if args.resume:
        ck = torch.load(Path(args.resume) / "train_state.pt", map_location="cpu", weights_only=False)
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        state = ck["state"]
        log = json.loads((Path(args.resume).parent / "log.json").read_text()) if (Path(args.resume).parent / "log.json").exists() else log
        print(f"RESUMED from {args.resume}: epoch {state['epoch']} idx {state['idx']} step {state['step']}", flush=True)
    else:
        print("pre-train dev:", ev0 := cell_accuracy(proc, model, dev_ex, dev, limit=args.eval_limit), flush=True)
        log["pre_train_dev"] = ev0

    def checkpoint(epoch: int, idx: int, order: list[int]) -> None:
        """Adapter + optimizer + scheduler + exact position in the epoch, so
        a kill at any point resumes from the last saved step."""
        ck_dir = out_dir / "latest"
        model.save_pretrained(ck_dir)
        torch.save({"opt": opt.state_dict(), "sched": sched.state_dict(),
                    "state": {"step": step, "epoch": epoch, "idx": idx, "order": order}}, ck_dir / "train_state.pt")
        (out_dir / "log.json").write_text(json.dumps(log, indent=1))

    # --- loop ---------------------------------------------------------------
    model.train()
    step = state["step"]
    t0 = time.time()
    for epoch in range(state["epoch"], args.epochs + 1):
        if state["order"] and epoch == state["epoch"]:  # non-empty order = resumed mid-epoch
            order = state["order"]
            start_idx = state["idx"]
            state["order"] = None
        else:
            order = list(range(len(train_ex)))
            random.Random(args.seed + epoch).shuffle(order)
            start_idx = 0
        losses = []
        opt.zero_grad()
        for i, k in enumerate(order, start=1):
            if i <= start_idx:
                continue
            if i == start_idx + 1 and start_idx:
                print(f"resuming mid-epoch {epoch} at row {i}/{len(order)}", flush=True)
            e = train_ex[k]
            im = Image.open(G4 / e["image"]).convert("RGB") if not e["image"].startswith("/") else Image.open(e["image"]).convert("RGB")
            if args.augment:
                from wrb.synth import jitter
                im = jitter(im, random)
            inp, labels = build_batch(proc, im, row_target(e["cells"], e.get("flags")), dev, hint_for(e["doc"]))
            out = model(**inp, labels=labels)
            (out.loss / args.grad_accum).backward()
            losses.append(out.loss.item())
            if i % args.grad_accum == 0 or i == len(order):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
                step += 1
                if dev == "mps":
                    torch.mps.empty_cache()  # smoke1 lesson: the MPS caching allocator grew to 13 GB and swapped
                if args.save_every and step % args.save_every == 0:
                    checkpoint(epoch, i, order)
                if args.stop_after_steps and step >= args.stop_after_steps:
                    print(f"STOP-AFTER-STEPS {step} (epoch {epoch} idx {i}) - checkpoint at {out_dir / 'latest'}", flush=True)
                    return
                if step % 10 == 0:
                    print(f"epoch {epoch} step {step}/{steps_total} loss {sum(losses[-args.grad_accum:]) / args.grad_accum:.4f} "
                          f"{(time.time() - t0) / 60:.1f} min", flush=True)
        model.save_pretrained(out_dir / f"epoch{epoch}")  # save BEFORE the slow eval: nothing is lost if killed here
        checkpoint(epoch + 1, 0, [])
        ev = cell_accuracy(proc, model, dev_ex, dev, limit=args.eval_limit)
        rec = {"epoch": epoch, "train_loss": (sum(losses) / len(losses)) if losses else None, "dev": ev,
               "minutes": round((time.time() - t0) / 60, 1)}
        log["epochs"].append(rec)
        print("EPOCH", json.dumps(rec), flush=True)
        (out_dir / "log.json").write_text(json.dumps(log, indent=1))
    if args.eval_gold:
        log["gold"] = cell_accuracy(proc, model, gm["examples"], dev, limit=args.eval_limit)
        print("GOLD rows (final adapter):", json.dumps(log["gold"]), flush=True)
    (out_dir / "log.json").write_text(json.dumps(log, indent=1))
    print("done", out_dir)


if __name__ == "__main__":
    main()
