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
# Balance DISTINCT examples, not just row counts. gen2 balanced rows (200 vs
# 40x5) and still learned the elided-barometer convention, because it saw 200
# distinct elided rows against 40 distinct full-barometer ones. Every
# non-barometer cell was perfect in both gen1 and gen2; the whole error was
# this one convention. See docs/g4-print-fidelity.md.
BALANCE_DISTINCT = True


def main() -> None:
    rng = random.Random(0)
    sc = prof.load("revista-santacruz-1889")
    examples = []

    # --- Santa-Cruz, from the API-labelled G4 set (docs 15/16, never doc 14) ---
    tm = load_manifest(G4 / "train_manifest.json")
    pool = [e for e in tm["examples"] if e["doc"] != "14"]
    rng.shuffle(pool)
    cor_n = len([e for e in load_manifest(G4 / "workbench_manifest.json")["examples"]
                 if e["profile"] == "corumba-1889"]) or PER_SIDE
    n_sc = min(cor_n, PER_SIDE) if BALANCE_DISTINCT else PER_SIDE
    for e in pool[:n_sc]:
        cells = dict(e["cells"])
        # the single Santa-Cruz evaporation column: the API put it in either
        # slot depending on the page (docs/g4-scale-demo.md section 3)
        evap = cells.get("evap_sombra")
        evap = cells.get("evap_sol") if evap is None else evap
        values = {k: cells.get(k) for k in sc.keys}
        values["day"] = e["day"]
        values["evap_sombra"] = evap
        values["wind_dir"] = (e.get("flags") or {}).get("wind_dir")
        # TARGETS MUST BE FAITHFUL TO PRINT. The API labels already carry the
        # barometer thousands restored (754.44 where the page prints 54.44);
        # teaching that taught the model to invent a leading 7, which it then
        # applied to an unrelated 1883 vapour table. See docs/g4-print-fidelity.md.
        values = sc.to_printed(values)
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
    sc_rows = [e for e in examples if e["profile"] == sc.id]
    for _ in range(reps - 1):
        examples.extend(dict(e) for e in sc_rows)
    print(f"Santa-Cruz {len(sc_rows)} DISTINCT rows x{reps} (15 cells, barometer elided) | "
          f"Corumba {len(cor_rows)} DISTINCT rows x{reps} (16 cells, barometer in full)")

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
