"""The variant registry: every adapter this project has trained, in one table.

The goal is not one model. It is being able to train, measure and compare
SEVERAL - a LoRA rank sweep, another base model, a different balance of
layouts - and to do it cheaply enough that the comparison is routine.

That needs the variants to be enumerable. Today they are not: which adapters
exist, what each was trained on and what each measured lives across
`runs/**/log.json`, `models/**/train_log.json` and prose in `docs/`, so
"which one should I compare against" is answered from memory. `collect` reads
them into one place.

The rule this module keeps: **report what was measured, or nothing.** A variant
whose accuracy was never evaluated reports `None` and prints as a dash. Filling
that in from a nearby run - "smoke4 got 99.08%, so this one is probably about
that" - is how a comparison table stops meaning anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Variant:
    name: str
    path: Path
    base: str | None = None
    train_rows: int | None = None
    dev_rows: int | None = None
    epochs: int | None = None
    rank: int | None = None
    # The MEASURED accuracy: what a committed evaluation found, on the frozen
    # gold, with this adapter. This is the number to compare variants on.
    gold_cell_acc: float | None = None
    # The train log's own `gold` field, which is a check taken DURING training -
    # smoke4 reads 0.9545 there against a final 0.9908. Kept because it is real
    # information about the run, but never presented as the variant's accuracy.
    in_training_gold: float | None = None

    @property
    def measured(self) -> bool:
        return self.gold_cell_acc is not None


def _from_log(path: Path) -> Variant | None:
    try:
        rec = json.loads(path.read_text())
    except (OSError, ValueError):
        # a training run killed mid-save leaves half a file. Skipping it is
        # right; guessing at it is not.
        return None
    args = rec.get("args") or {}
    gold = rec.get("gold") or {}
    return Variant(
        name=path.parent.name,
        path=path.parent,
        base=rec.get("model"),
        train_rows=rec.get("train_rows"),
        dev_rows=rec.get("dev_rows"),
        epochs=args.get("epochs"),
        rank=args.get("rank"),
        in_training_gold=gold.get("cell_acc"),
    )


def _final_evaluations(root: Path) -> dict[str, float]:
    """variant name -> measured cell accuracy, from `bench/**/*-final-gold.json`.

    Those artifacts name the adapter they measured (`runs/g4/smoke4/epoch2`), so
    the link to a variant is explicit rather than guessed from the filename.
    """
    out: dict[str, float] = {}
    for path in sorted(Path(root).glob("**/*-final-gold.json")):
        try:
            rec = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        adapter = str(rec.get("adapter") or "")
        acc = (rec.get("gold") or {}).get("cell_acc")
        if not adapter or acc is None:
            continue
        # runs/g4/smoke4/epoch2 -> smoke4 ; models/g4/qwen35-lora-smoke2-epoch2 -> that name
        parts = [q for q in adapter.split("/") if q]
        for cand in (parts[-2] if len(parts) >= 2 else "", parts[-1] if parts else ""):
            if cand:
                out.setdefault(cand, acc)
    return out


def _canonical(name: str) -> str:
    """The two layouts the adapters were saved under are the same variant.

    `runs/` writes `smoke4`, `models/` writes `qwen35-lora-smoke4-epoch2`, and
    the -final-gold artifacts name the adapter path. Without a canonical name a
    table lists the same model twice, one of them always unmeasured.
    """
    n = name
    for pre in ("qwen35-lora-", "qwen35-"):
        if n.startswith(pre):
            n = n[len(pre):]
    for suf in ("-epoch2", "-epoch3", "-epoch1"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n


def collect(root: Path) -> list[Variant]:
    """Every adapter with a training log under `root`, sorted by name.

    Duplicate names across directories (a run logged under both `runs/` and
    `models/`) collapse to one entry, and the MEASURED accuracy is attached from
    the committed final evaluation.
    """
    final = _final_evaluations(root)
    found: dict[str, Variant] = {}
    for pattern in ("**/log.json", "**/train_log.json"):
        for path in sorted(Path(root).glob(pattern)):
            v = _from_log(path)
            if v is None:
                continue
            v.name = _canonical(v.name)
            v.gold_cell_acc = final.get(v.name)
            found[v.name] = v
    return [found[k] for k in sorted(found)]


def format_table(variants: list[Variant]) -> str:
    if not variants:
        return "no variants with a training log found"
    head = (f"{'variant':<16} {'rows':>5} {'ep':>3} {'final gold':>11} "
            f"{'in-train':>9}")
    lines = [head, "-" * len(head)]
    for v in variants:
        final = f"{v.gold_cell_acc:.4f}" if v.measured else "—"
        train = f"{v.in_training_gold:.4f}" if v.in_training_gold is not None else "—"
        lines.append(f"{v.name:<16} {str(v.train_rows):>5} {str(v.epochs):>3} "
                     f"{final:>11} {train:>9}")
    measured = sum(1 for v in variants if v.measured)
    lines.append("")
    lines.append(f"{len(variants)} variants, {measured} with a FINAL measurement, "
                 f"{len(variants) - measured} unmeasured")
    lines.append("")
    lines.append("final gold = committed evaluation on the frozen gold set (bench/*-final-gold.json).")
    lines.append("in-train   = the log's own check DURING training, a different number:")
    lines.append("             smoke4 reads 0.9545 there and 0.9908 finally. Never quote it as accuracy.")
    lines.append("— means never evaluated, not zero.")
    return "\n".join(lines)
