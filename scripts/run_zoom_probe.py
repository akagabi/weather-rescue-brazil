#!/usr/bin/env python3
"""G3 Task 1b Step 2: PAID 2-sheet probe of the multi-resolution zoom
cross-check (wrb/zoom.py) against the frozen gold set.

Picks the 2 gold sheets with the most residual wrong cells in
bench/g3/consensus-gold.json (the G3 Task 1 consensus+QC run, 99.06%
cell_acc / 36 wrong cells across all 9 sheets - see that file and
wrb/vlm.py's "Self-consistency consensus" module note for why those 36 are
invisible to both consensus-disagreement and wrb.qc's validators), runs
wrb.zoom.zoom_reread_sheet on each, and measures the zoom cross-check
against the KNOWN-wrong cells on those 2 sheets (computed directly against
the frozen gold, not against the consensus run's own self-report):

  - FLAG RECALL: of the known-wrong cells, how many did the full-vs-zoom
    disagreement (wrb.zoom.reconcile) flag as a SUSPECT?
  - FLAG PRECISION: of everything flagged as a SUSPECT, how many were
    actually wrong?
  - CORRECTION GAIN: replacing every flagged cell with its zoom value,
    what is the new cell_acc on these 2 sheets, compared against the
    consensus baseline cell_acc on the SAME 2 sheets?

Usage:
    python scripts/run_zoom_probe.py
"""

import io
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from wrb.costs import CapExceeded, CostMeter  # noqa: E402
from wrb.gold import Sheet, load_gold  # noqa: E402
from wrb.metrics import TOL, score  # noqa: E402
from wrb.zoom import reconcile, zoom_reread_sheet  # noqa: E402

IMAGE_DIR = ROOT / "data" / "raw" / "docvirt" / "14"
LEDGER = ROOT / "data" / "ledger.json"
BENCH_DIR = ROOT / "bench" / "g3"
CONSENSUS_GOLD_PATH = BENCH_DIR / "consensus-gold.json"
OUT_PATH = BENCH_DIR / "zoom-probe.json"

PROVIDER = "gemini-flash-full"


def image_png_bytes(page: int) -> bytes:
    webp_path = IMAGE_DIR / f"{page:06d}.webp"
    img = Image.open(webp_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _cell_match(gold_val, pred_val) -> bool:
    if gold_val is None and pred_val is None:
        return True
    if gold_val is None or pred_val is None:
        return False
    return abs(gold_val - pred_val) <= TOL


def known_wrong_cells(pred_sheet: Sheet, gold_sheet: Sheet) -> set[tuple[int, str]]:
    """(day, col) pairs where the consensus prediction disagrees with the
    frozen gold by more than wrb.metrics.TOL - the ground truth this probe
    measures the zoom flagger against. Independently re-derived here
    (not read off bench/g3/consensus-gold.json's own aggregate), per the
    task's honesty mandate: every headline number is recomputed against
    gold, not trusted from a prior run's self-report."""
    pred_by_date = {r.date: r for r in pred_sheet.rows}
    wrong: set[tuple[int, str]] = set()
    for grow in gold_sheet.rows:
        day = int(grow.date.split("-")[2])
        prow = pred_by_date.get(grow.date)
        for col in gold_sheet.columns:
            gval = grow.cells.get(col)
            pval = prow.cells.get(col) if prow is not None else None
            if not _cell_match(gval, pval):
                wrong.add((day, col))
    return wrong


def consensus_cells_by_day(pred_sheet: Sheet) -> dict[int, dict]:
    return {int(r.date.split("-")[2]): dict(r.cells) for r in pred_sheet.rows}


def pick_probe_pages(consensus_gold: dict, gold_sheets: dict[int, Sheet], n: int = 2) -> list[int]:
    """The `n` gold pages with the most known-wrong cells in the G3
    consensus run, computed fresh against gold (see known_wrong_cells) -
    NOT read off consensus-gold.json's own per-sheet cell_acc, so this
    selection is independently verifiable."""
    counts = []
    for entry in consensus_gold["per_sheet"]:
        if "pred" not in entry:
            continue
        page = entry["page"]
        pred_sheet = Sheet(**entry["pred"])
        gold_sheet = gold_sheets[page]
        n_wrong = len(known_wrong_cells(pred_sheet, gold_sheet))
        counts.append((n_wrong, page))
    counts.sort(reverse=True)
    return [page for _, page in counts[:n]]


def run_probe_on_sheet(page: int, pred_sheet: Sheet, gold_sheet: Sheet, meter: CostMeter) -> dict:
    day_count = len(gold_sheet.rows)
    img_bytes = image_png_bytes(page)

    zoom_cells, zoom_errors = zoom_reread_sheet(img_bytes, PROVIDER, meter, day_count)

    cons_cells = consensus_cells_by_day(pred_sheet)
    suspects = reconcile(cons_cells, zoom_cells, tol=TOL)

    known_wrong = known_wrong_cells(pred_sheet, gold_sheet)
    suspect_pairs = {(s["day"], s["col"]) for s in suspects}

    true_positive_pairs = suspect_pairs & known_wrong
    flag_recall = (len(true_positive_pairs) / len(known_wrong)) if known_wrong else None
    flag_precision = (len(true_positive_pairs) / len(suspect_pairs)) if suspect_pairs else None

    # CORRECTION GAIN: apply every suspect's proposed (zoom) value on top
    # of the consensus prediction, rescore against gold.
    corrected_by_day = {d: dict(c) for d, c in cons_cells.items()}
    for s in suspects:
        corrected_by_day.setdefault(s["day"], {})[s["col"]] = s["proposed_value"]
    corrected_rows = [
        {"date": f"{gold_sheet.period}-{day:02d}", "cells": cells, "flags": {}}
        for day, cells in corrected_by_day.items()
    ]
    corrected_sheet = Sheet(
        source=gold_sheet.source, bib=gold_sheet.bib, page=gold_sheet.page,
        station=gold_sheet.station, period=gold_sheet.period,
        columns=gold_sheet.columns, rows=corrected_rows,
    )
    baseline_score = score(pred_sheet, gold_sheet)
    corrected_score = score(corrected_sheet, gold_sheet)

    return {
        "page": page,
        "gold_period": gold_sheet.period,
        "day_count": day_count,
        "zoom_read_errors": zoom_errors,
        "n_zoom_rows_read": len(zoom_cells),
        "known_wrong_cells": sorted([f"day{d}:{c}" for d, c in known_wrong]),
        "n_known_wrong": len(known_wrong),
        "suspects": suspects,
        "n_suspects": len(suspects),
        "true_positive_suspects": sorted([f"day{d}:{c}" for d, c in true_positive_pairs]),
        "flag_recall": flag_recall,
        "flag_precision": flag_precision,
        "baseline_cell_acc": baseline_score["cell_acc"],
        "corrected_cell_acc": corrected_score["cell_acc"],
        "correction_gain": corrected_score["cell_acc"] - baseline_score["cell_acc"],
    }


def _load_existing_per_sheet() -> dict[int, dict]:
    """page -> result entry from a previous (possibly interrupted) run's
    output file - lets this script RESUME instead of re-spending on a page
    that already completed, same reasoning as scripts/run_g3.py's
    `_load_existing_per_sheet`."""
    if not OUT_PATH.exists():
        return {}
    data = json.loads(OUT_PATH.read_text())
    return {e["page"]: e for e in data.get("per_sheet", [])}


def main() -> None:
    consensus_gold = json.loads(CONSENSUS_GOLD_PATH.read_text())
    gold_sheets = {s.page: s for s in load_gold()}

    probe_pages = pick_probe_pages(consensus_gold, gold_sheets, n=2)
    print(f"probe pages (most known-wrong cells, re-derived against gold): {probe_pages}", flush=True)

    pred_by_page = {
        e["page"]: Sheet(**e["pred"]) for e in consensus_gold["per_sheet"] if "pred" in e
    }

    done_by_page = _load_existing_per_sheet()
    remaining_pages = [p for p in probe_pages if p not in done_by_page]
    if done_by_page:
        print(f"RESUME: {sorted(done_by_page)} already completed in {OUT_PATH} - skipping; "
              f"{remaining_pages} remaining.", flush=True)

    meter = CostMeter(cap_usd=10.0, ledger=LEDGER)
    ledger_before = meter.total()
    print(f"ledger total before zoom probe: US${ledger_before:.4f}", flush=True)

    per_sheet = [done_by_page[p] for p in probe_pages if p in done_by_page]
    for page in remaining_pages:
        print(f"--- page {page} ---", flush=True)
        try:
            result = run_probe_on_sheet(page, pred_by_page[page], gold_sheets[page], meter)
        except CapExceeded:
            raise
        print(f"  known_wrong={result['n_known_wrong']} suspects={result['n_suspects']} "
              f"flag_recall={result['flag_recall']} flag_precision={result['flag_precision']} "
              f"baseline_cell_acc={result['baseline_cell_acc']:.4f} "
              f"corrected_cell_acc={result['corrected_cell_acc']:.4f} "
              f"correction_gain={result['correction_gain']:+.4f}", flush=True)
        per_sheet.append(result)
        # Persist after every sheet, same crash-safety reasoning as run_g3.py.
        BENCH_DIR.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps({
            "provider": PROVIDER,
            "probe_pages": probe_pages,
            "per_sheet": per_sheet,
            "ledger_total_usd": meter.total(),
        }, indent=2))

    ledger_total = meter.total()
    print(f"ledger total after zoom probe: US${ledger_total:.4f} "
          f"(delta US${ledger_total - ledger_before:.4f})", flush=True)

    total_known_wrong = sum(r["n_known_wrong"] for r in per_sheet)
    total_tp = sum(len(r["true_positive_suspects"]) for r in per_sheet)
    total_suspects = sum(r["n_suspects"] for r in per_sheet)
    agg_flag_recall = (total_tp / total_known_wrong) if total_known_wrong else None
    agg_flag_precision = (total_tp / total_suspects) if total_suspects else None

    total_cells = sum(
        score(pred_by_page[r["page"]], gold_sheets[r["page"]])["n_cells"] for r in per_sheet
    )
    baseline_correct = sum(
        round(score(pred_by_page[r["page"]], gold_sheets[r["page"]])["cell_acc"]
              * score(pred_by_page[r["page"]], gold_sheets[r["page"]])["n_cells"])
        for r in per_sheet
    )
    corrected_correct = sum(
        round(r["corrected_cell_acc"] * score(pred_by_page[r["page"]], gold_sheets[r["page"]])["n_cells"])
        for r in per_sheet
    )
    agg_baseline_cell_acc = baseline_correct / total_cells
    agg_corrected_cell_acc = corrected_correct / total_cells

    aggregate = {
        "n_sheets": len(per_sheet),
        "total_known_wrong": total_known_wrong,
        "total_suspects": total_suspects,
        "total_true_positive_suspects": total_tp,
        "flag_recall": agg_flag_recall,
        "flag_precision": agg_flag_precision,
        "baseline_cell_acc": agg_baseline_cell_acc,
        "corrected_cell_acc": agg_corrected_cell_acc,
        "correction_gain": agg_corrected_cell_acc - agg_baseline_cell_acc,
    }
    print(f"AGGREGATE: {json.dumps(aggregate, indent=2)}", flush=True)

    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "provider": PROVIDER,
        "probe_pages": probe_pages,
        "aggregate": aggregate,
        "per_sheet": per_sheet,
        "ledger_total_usd": ledger_total,
    }, indent=2))
    print(f"wrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
