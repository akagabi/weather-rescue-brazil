"""G4.5 - SCALE DEMO: run the offline engine over whole pages, end to end.

    python scripts/g4_run_pages.py --model runs/g4/mlx-smoke4-q8 [--pages 14/22,15/44] [--out bench/g4/scale-demo.json]

Per page: oracle-driven row localisation (same as the dataset builder) →
one MLX read per row → G2BTable → barometer reconstruction → assemble_sheet
→ qc.flag_violations. Reports, per page: wall time split (localise / read /
assemble), refusal, and
  * gold pages: cell accuracy vs the frozen gold (wrb.metrics.score);
  * non-gold pages: agreement with the API transcription (bench/g3), which is
    not truth but a free consistency check (~99% expected if both are right).
Everything is local; per-page cost is electricity. No network.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from g4_build_dataset import DayOracle, resolve_by_oracle  # noqa: E402
from g4_train import INSTRUCTION, layout_hint  # noqa: E402
from wrb.dataset import COLUMNS, boxes_for_centres, crop_boxes, day_count_of, page_image_path  # noqa: E402
from wrb.gold import Sheet, load_gold  # noqa: E402
from wrb.local_model import parse_row_target  # noqa: E402
from wrb.metrics import score  # noqa: E402
from wrb.qc import flag_violations  # noqa: E402
from wrb.rows import locate_day_rows  # noqa: E402
from wrb.vlm import G2BRow, G2BTable, _apply_barometer_reconstruction, assemble_sheet  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "bench" / "g3" / "revista-full.json"


class MlxRowReader:
    def __init__(self, model_path: str, max_tokens: int = 80) -> None:
        from mlx_vlm import load
        self.model, self.proc = load(model_path)
        self.max_tokens = max_tokens
        self.calls = 0

    def read_row(self, crop: Image.Image, hint: str) -> str:
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template
        prompt = apply_chat_template(self.proc, self.model.config, INSTRUCTION + " " + hint, num_images=1)
        out = generate(self.model, self.proc, prompt, [crop], max_tokens=self.max_tokens, verbose=False)
        self.calls += 1
        return out.text if hasattr(out, "text") else str(out)


def agreement(pred: Sheet, ref: dict) -> dict:
    ref_rows = {r["date"]: r["cells"] for r in ref["rows"]}
    c = t = 0
    for row in pred.rows:
        rc = ref_rows.get(row.date)
        if rc is None:
            continue
        for col in COLUMNS:
            t += 1
            a, b = row.cells.get(col), rc.get(col)
            c += (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 0.005)
    return {"cells": t, "agree": c / t if t else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--pages", default="", help="subset like 14/22,15/44 (default: all transcribed pages)")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    only = {(p.split("/")[0], int(p.split("/")[1])) for p in args.pages.split(",") if p}

    bench = json.loads(BENCH.read_text())
    gold = {int(s.page): s for s in load_gold(ROOT / "gold")}
    oracle = DayOracle()
    reader = MlxRowReader(args.model)
    results = []
    t_all = time.time()
    for p in bench["per_sheet"]:
        if not p.get("pred"):
            continue
        doc, page, period = str(p["doc"]), int(p["page"]), p["period"]
        if only and (doc, page) not in only:
            continue
        year, month = (int(x) for x in period.split("-"))
        day_count = day_count_of(period)
        image = Image.open(page_image_path(ROOT, doc, page)).convert("RGB")
        rec = {"doc": doc, "page": page, "period": period, "is_gold": page in gold and doc == "14"}
        t0 = time.time()
        loc = locate_day_rows(image, day_count)
        centres, info = resolve_by_oracle(oracle, image, loc, day_count)
        rec["t_localise_s"] = round(time.time() - t0, 1)
        rec["direct_day_reads"] = info.get("direct")
        if centres is None:
            rec["status"] = "refused"
            rec["reason"] = info.get("reason", "too few direct day reads")
            results.append(rec)
            print(f"{doc}_{page} {period} REFUSED ({rec['t_localise_s']}s) {rec['reason']}", flush=True)
            continue
        boxes = boxes_for_centres(centres, loc, *image.size)
        crops = crop_boxes(image, boxes, loc.skew_deg, scale=2.0)
        t1 = time.time()
        rows = []
        n_problems = 0
        for day, crop in enumerate(crops, start=1):
            cells, flags, problems = parse_row_target(reader.read_row(crop, layout_hint(doc)))
            if problems:
                n_problems += 1
                flags["parse"] = "; ".join(problems)
            rows.append(G2BRow(day=day, cells=cells, flags=flags))
        rec["t_read_s"] = round(time.time() - t1, 1)
        t2 = time.time()
        table = _apply_barometer_reconstruction(G2BTable(rows=rows))
        sheet = assemble_sheet(table, year=year, month=month, source="docvirt", bib=f"obnacional/{doc}",
                               page=page, station=p["pred"]["station"], columns=list(COLUMNS))
        sheet = flag_violations(sheet)
        rec["t_assemble_s"] = round(time.time() - t2, 2)
        rec["t_page_s"] = round(time.time() - t0, 1)
        rec["rows_with_parse_problems"] = n_problems
        rec["qc_flags"] = sum(1 for r in sheet.rows for k in r.flags if k not in ("wind_dir", "parse"))
        if rec["is_gold"]:
            s = score(sheet, gold[page])
            rec["gold"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()}
        else:
            rec["api_agreement"] = agreement(sheet, p["pred"])
        rec["status"] = "ok"
        rec["sheet"] = sheet.model_dump()
        results.append(rec)
        tag = f"gold cell_acc={rec['gold']['cell_acc']}" if rec["is_gold"] else f"api agree={rec['api_agreement']['agree']:.4f}"
        print(f"{doc}_{page} {period} ok {rec['t_page_s']}s (loc {rec['t_localise_s']} / read {rec['t_read_s']}) {tag} qc_flags={rec['qc_flags']}", flush=True)

    ok = [r for r in results if r["status"] == "ok"]
    gold_res = [r for r in ok if r["is_gold"]]
    nong = [r for r in ok if not r["is_gold"]]
    total_s = time.time() - t_all
    summary = {
        "model": args.model, "pages": len(results), "ok": len(ok), "refused": len(results) - len(ok),
        "wall_s": round(total_s), "pages_per_hour": round(3600 * len(results) / total_s, 1),
        "mean_page_s": round(sum(r["t_page_s"] for r in ok) / max(1, len(ok)), 1),
        "mean_localise_s": round(sum(r["t_localise_s"] for r in ok) / max(1, len(ok)), 1),
        "mean_read_s": round(sum(r["t_read_s"] for r in ok) / max(1, len(ok)), 1),
        "gold_cell_acc_micro": (sum(r["gold"]["cell_acc"] * r["gold"]["n_cells"] for r in gold_res)
                                / max(1, sum(r["gold"]["n_cells"] for r in gold_res))) if gold_res else None,
        "gold_pages": len(gold_res),
        "api_agreement_micro": (sum(r["api_agreement"]["agree"] * r["api_agreement"]["cells"] for r in nong)
                                / max(1, sum(r["api_agreement"]["cells"] for r in nong))) if nong else None,
        "nongold_pages": len(nong), "cost_usd": 0.0, "network_calls": 0,
    }
    print("SUMMARY", json.dumps(summary), flush=True)
    out = Path(args.out) if args.out else ROOT / "bench" / "g4" / "scale-demo.json"
    out.write_text(json.dumps({"summary": summary, "pages": results}, indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
