"""Build the balanced training set for the generality experiment.

Train on Santa-Cruz (15 printed cells) + Corumba (16 printed cells), BALANCED,
with Rio (16 cells, and the only layout with human-verified gold) held out
completely. If the model then emits 16 cells for a Rio page it has never seen,
it is reading the column count off the image instead of from memory - which is
the exact failure documented in docs/g4-generalisation.md.

Balance is the variable under test: smoke5 already trained on both 15- and
16-cell layouts and still always emitted 15, because 91% of its rows were the
15-cell one.
"""
from __future__ import annotations

import hashlib
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wrb import profile as prof  # noqa: E402
from wrb.dataset import load_manifest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
G4 = ROOT / "data" / "g4"
OUT = G4 / "generality_manifest.json"
PER_SIDE = 200


def main() -> None:
    rng = random.Random(0)
    sc = prof.load("revista-santacruz-1889")
    examples = []

    # --- Santa-Cruz, from the API-labelled G4 set (docs 15/16, never doc 14) ---
    tm = load_manifest(G4 / "train_manifest.json")
    pool = [e for e in tm["examples"] if e["doc"] != "14"]
    rng.shuffle(pool)
    for e in pool[:PER_SIDE]:
        cells = dict(e["cells"])
        # the single Santa-Cruz evaporation column: the API put it in either
        # slot depending on the page (docs/g4-scale-demo.md section 3)
        evap = cells.get("evap_sombra")
        evap = cells.get("evap_sol") if evap is None else evap
        values = {k: cells.get(k) for k in sc.keys}
        values["day"] = e["day"]
        values["evap_sombra"] = evap
        values["wind_dir"] = (e.get("flags") or {}).get("wind_dir")
        examples.append({"profile": sc.id, "doc": e["doc"], "page": e["page"], "row": e["day"],
                         "image": e["image"], "sha256": e["sha256"],
                         "target": sc.target(values), "cells": cells, "day": e["day"],
                         "is_gold": False})

    # --- Corumba, hand-read in the workbench, oversampled to match ---------
    cor = prof.load("corumba-1889")
    wb = load_manifest(G4 / "workbench_manifest.json")
    cor_rows = [e for e in wb["examples"] if e["profile"] == cor.id]
    if not cor_rows:
        raise SystemExit("no Corumba labels; label them in the workbench first")
    reps = max(1, round(PER_SIDE / len(cor_rows)))
    for _ in range(reps):
        examples.extend(dict(e) for e in cor_rows)
    print(f"Santa-Cruz {PER_SIDE} rows (15 cells) | Corumba {len(cor_rows)} rows x{reps} "
          f"= {len(cor_rows) * reps} (16 cells)")

    rng.shuffle(examples)
    doc = {"meta": {"experiment": "generality: train on 15- and 16-cell layouts, balanced; hold out Rio",
                    "held_out": "revista-rio-1886 (doc 14) entirely",
                    "per_side": PER_SIDE, "corumba_reps": reps},
           "n_examples": len(examples), "examples": examples}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    counts: dict[str, int] = {}
    for e in examples:
        n = len(e["target"].split("|"))
        counts[f"{n} cells"] = counts.get(f"{n} cells", 0) + 1
    assert not any(e["doc"] == "14" for e in examples), "Rio leaked into the training set"
    print(f"wrote {OUT.relative_to(ROOT)}: {len(examples)} rows, {counts}")


if __name__ == "__main__":
    main()
