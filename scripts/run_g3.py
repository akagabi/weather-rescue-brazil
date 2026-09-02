#!/usr/bin/env python3
"""G3 Task 1: self-consistency consensus (n reads, majority vote per cell)
+ validator-driven QC flagging, run against the frozen gold set with REAL
paid Gemini calls.

Same pipeline shape as scripts/run_g2.py (period call -> reconcile -> g2b
table call -> assemble), except the table call goes through
wrb.vlm.consensus_extract (n independent g2b calls at temperature>0,
majority-voted per cell) instead of a single extract() call, and the
assembled Sheet is then run through wrb.qc.flag_violations before scoring -
so the flags wrb.metrics.score() sees when computing flagged_recall reflect
BOTH consensus disagreement and validator violations (the plan's "final
per-cell uncertainty = consensus-disagreement OR validator-flag").

`expected_prev_for_sheet`, `image_png_bytes`, and the overall per-sheet
structure are copied from run_g2.py rather than imported, since run_g2.py
is that task's own artifact and this task's script should stand on its own
for the honesty-mandate paper trail.

Usage:
    python scripts/run_g3.py probe            # ONE sheet (page 41), n=3
    python scripts/run_g3.py full             # all 9 gold sheets, n=3
"""

import calendar
import io
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from wrb.costs import CapExceeded, CostMeter  # noqa: E402
from wrb.gold import Sheet, load_gold  # noqa: E402
from wrb.metrics import score  # noqa: E402
from wrb.qc import flag_violations  # noqa: E402
from wrb.vlm import (  # noqa: E402
    ExtractionParseError,
    assemble_sheet,
    consensus_extract,
    extract_period,
    reconcile_period,
    validate_day_sequence,
)

IMAGE_DIR = ROOT / "data" / "raw" / "docvirt" / "14"
LEDGER = ROOT / "data" / "ledger.json"
BENCH_DIR = ROOT / "bench" / "g3"
G2B_GATE_PATH = ROOT / "bench" / "g2" / "gemini-3.5-flash-g2b.json"

PROVIDER = "gemini-flash-full"
N_CONSENSUS = 3
TEMPERATURE = 0.7


def image_png_bytes(sheet: Sheet) -> bytes:
    webp_path = IMAGE_DIR / f"{sheet.page:06d}.webp"
    img = Image.open(webp_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def expected_prev_for_sheet(sheet: Sheet) -> tuple[int, int]:
    year, month = (int(p) for p in sheet.period.split("-"))
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _flagged_and_total_cells(pred_sheet: Sheet, gold_sheet: Sheet) -> tuple[int, int]:
    """(flagged_cell_count, n_cells) over the SAME (date, column) grid
    wrb.metrics.score() iterates - counts a cell as flagged if the
    predicted row (when present) has flags[col] containing "uncertain",
    regardless of whether that cell is actually right or wrong. This is
    the numerator/denominator for "fraction of cells flagged uncertain" -
    a separate number from score()'s flagged_recall, which is scoped to
    only the WRONG cells."""
    pred_by_date = {r.date: r for r in pred_sheet.rows}
    flagged = 0
    total = 0
    for grow in gold_sheet.rows:
        prow = pred_by_date.get(grow.date)
        for col in gold_sheet.columns:
            total += 1
            if prow is not None and "uncertain" in prow.flags.get(col, "").lower():
                flagged += 1
    return flagged, total


def run_g3_on_sheet(sheet: Sheet, meter: CostMeter) -> dict:
    gold_file = f"14_{sheet.page}.json"
    entry: dict = {"gold_file": gold_file, "gold_period": sheet.period, "page": sheet.page}

    img_bytes = image_png_bytes(sheet)

    raw_year, raw_month = extract_period(img_bytes, PROVIDER, meter)
    entry["period_read_raw"] = f"{raw_year:04d}-{raw_month:02d}"
    expected_prev = expected_prev_for_sheet(sheet)
    (year, month), period_flag = reconcile_period((raw_year, raw_month), expected_prev=expected_prev)
    entry["period_reconciled"] = f"{year:04d}-{month:02d}"
    entry["period_flag"] = period_flag

    day_count = calendar.monthrange(year, month)[1]
    table = consensus_extract(img_bytes, PROVIDER, meter, day_count=day_count,
                               n=N_CONSENSUS, temperature=TEMPERATURE)
    entry["day_sequence_violations"] = validate_day_sequence(table)

    pred_sheet = assemble_sheet(
        table, year=year, month=month,
        source=sheet.source, bib=sheet.bib, page=sheet.page,
        station=sheet.station, columns=sheet.columns,
    )
    pred_sheet = flag_violations(pred_sheet)

    s = score(pred_sheet, sheet)
    entry["scores"] = s
    flagged, total = _flagged_and_total_cells(pred_sheet, sheet)
    entry["flagged_cells"] = flagged
    entry["total_cells"] = total
    entry["fraction_flagged"] = flagged / total if total else 0.0
    entry["pred"] = pred_sheet.model_dump()
    return entry


def run_g3(sheets: list[Sheet], meter: CostMeter, on_sheet_done=None) -> list[dict]:
    """Run run_g3_on_sheet over `sheets` in order. `on_sheet_done`, when
    given, is called with each sheet's result entry (success or error)
    IMMEDIATELY after that sheet finishes - used by main() to persist
    progress to disk after every sheet rather than only at the very end, so
    a mid-run kill (observed live: the first `full` attempt was killed with
    no output ever flushed through a `tail`-piped stdout, losing an entire
    run's results even though the CostMeter ledger had already been
    charged) does not throw away already-completed sheets' work."""
    results: list[dict] = []
    for sheet in sheets:
        gold_file = f"14_{sheet.page}.json"
        try:
            entry = run_g3_on_sheet(sheet, meter)
        except CapExceeded:
            raise
        except (ExtractionParseError, RuntimeError) as e:
            print(f"  {sheet.period} ({gold_file}): ERROR: {type(e).__name__}: {e}", flush=True)
            entry = {"gold_file": gold_file, "gold_period": sheet.period,
                     "page": sheet.page, "error": f"{type(e).__name__}: {e}"}
            results.append(entry)
            if on_sheet_done:
                on_sheet_done(entry)
            continue
        except Exception as e:  # noqa: BLE001 - log and move on, same as run_g2.py
            print(f"  {sheet.period} ({gold_file}): ERROR: {type(e).__name__}: {e}", flush=True)
            entry = {"gold_file": gold_file, "gold_period": sheet.period,
                     "page": sheet.page, "error": f"{type(e).__name__}: {e}"}
            results.append(entry)
            if on_sheet_done:
                on_sheet_done(entry)
            continue

        s = entry["scores"]
        print(f"  {sheet.period} ({gold_file}): cell_acc={s['cell_acc']:.4f} "
              f"structural_err_rate={s['structural_err_rate']:.4f} "
              f"flagged_recall={s['flagged_recall']:.4f} "
              f"fraction_flagged={entry['fraction_flagged']:.4f} "
              f"day_violations={len(entry['day_sequence_violations'])}", flush=True)
        results.append(entry)
        if on_sheet_done:
            on_sheet_done(entry)
    return results


def aggregate(results: list[dict]) -> dict:
    scored = [r for r in results if "scores" in r]
    n_sheets = len(results)
    n_scored = len(scored)
    if n_scored == 0:
        return {"cell_acc": 0.0, "structural_err_rate": 0.0, "flagged_recall": 0.0,
                "fraction_flagged": 0.0, "n_sheets": n_sheets, "n_sheets_scored": 0,
                "n_sheets_errored": n_sheets}
    total_cells = sum(r["scores"]["n_cells"] for r in scored)
    total_correct = sum(r["scores"]["cell_acc"] * r["scores"]["n_cells"] for r in scored)
    cell_acc = total_correct / total_cells if total_cells else 1.0
    structural_err_rate = sum(r["scores"]["structural_err_rate"] for r in scored) / n_scored

    total_wrong = sum(round(r["scores"]["n_cells"] * (1 - r["scores"]["cell_acc"])) for r in scored)
    total_flagged_wrong = sum(
        round(r["scores"]["n_cells"] * (1 - r["scores"]["cell_acc"]) * r["scores"]["flagged_recall"])
        for r in scored
    )
    flagged_recall_micro = (total_flagged_wrong / total_wrong) if total_wrong else 0.0

    total_flagged_cells = sum(r["flagged_cells"] for r in scored)
    total_all_cells = sum(r["total_cells"] for r in scored)
    fraction_flagged = total_flagged_cells / total_all_cells if total_all_cells else 0.0

    return {
        "cell_acc": cell_acc,
        "structural_err_rate": structural_err_rate,
        "flagged_recall_macro": sum(r["scores"]["flagged_recall"] for r in scored) / n_scored,
        "flagged_recall_micro": flagged_recall_micro,
        "fraction_flagged": fraction_flagged,
        "n_sheets": n_sheets,
        "n_sheets_scored": n_scored,
        "n_sheets_errored": n_sheets - n_scored,
        "n_cells_total": total_cells,
        "total_wrong_cells": total_wrong,
        "total_flagged_wrong_cells": total_flagged_wrong,
    }


def _load_existing_per_sheet(out_path: Path) -> dict[int, dict]:
    """page -> result entry, from a previous (possibly interrupted) run's
    output file - lets `full` mode RESUME instead of re-spending on a sheet
    that already completed successfully (has a "scores" key). A sheet that
    only recorded an error is retried."""
    if not out_path.exists():
        return {}
    data = json.loads(out_path.read_text())
    return {e["page"]: e for e in data.get("per_sheet", []) if "scores" in e}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if mode not in ("probe", "full"):
        print(f"unknown mode {mode!r}; expected 'probe' or 'full'", file=sys.stderr)
        sys.exit(2)

    all_sheets = {s.page: s for s in load_gold()}

    if mode == "probe":
        sheets = [all_sheets[41]]
    else:
        sheets = sorted(load_gold(), key=lambda s: s.page)

    out_name = "consensus-probe.json" if mode == "probe" else "consensus-gold.json"
    out_path = BENCH_DIR / out_name

    done_by_page = _load_existing_per_sheet(out_path) if mode == "full" else {}
    remaining = [s for s in sheets if s.page not in done_by_page]
    if done_by_page:
        print(f"RESUME: {len(done_by_page)} sheet(s) already completed in {out_path} "
              f"(pages {sorted(done_by_page)}) - skipping; {len(remaining)} remaining.")

    meter = CostMeter(cap_usd=10.0, ledger=LEDGER)
    ledger_before = meter.total()
    print(f"ledger total before {mode} run: US${ledger_before:.4f}", flush=True)
    print(f"{mode.upper()}: {PROVIDER} consensus (n={N_CONSENSUS}, temp={TEMPERATURE}) on "
          f"{len(remaining)} sheet(s): {[s.period for s in remaining]} "
          f"(pages {[s.page for s in remaining]})", flush=True)

    all_results_by_page: dict[int, dict] = dict(done_by_page)
    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    def persist(entry: dict) -> None:
        """Called after EVERY sheet (success or error) - rewrites the full
        output file from everything known so far, so a kill mid-run loses
        at most the sheet in flight, never earlier ones."""
        all_results_by_page[entry["page"]] = entry
        ordered = [all_results_by_page[p] for p in sorted(all_results_by_page)]
        agg = aggregate(ordered)
        out = {
            "provider": PROVIDER,
            "strategy": "g2b+consensus+qc",
            "n_consensus": N_CONSENSUS,
            "temperature": TEMPERATURE,
            "aggregate": agg,
            "per_sheet": ordered,
            "ledger_total_usd": meter.total(),
        }
        out_path.write_text(json.dumps(out, indent=2))

    results = run_g3(remaining, meter, on_sheet_done=persist)
    ledger_total = meter.total()
    print(f"ledger total after {mode} run: US${ledger_total:.4f} "
          f"(delta US${ledger_total - ledger_before:.4f})", flush=True)

    final_results = [all_results_by_page[p] for p in sorted(all_results_by_page)]
    agg = aggregate(final_results)
    print(f"aggregate: {json.dumps(agg, indent=2)}", flush=True)
    print(f"wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
