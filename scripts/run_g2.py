#!/usr/bin/env python3
"""G2-B: run the schema+anchor+header+barometer extraction strategy against
the frozen gold set, real paid Gemini calls (see src/wrb/vlm.py's g2b
strategy and docs/superpowers/plans/2026-09-01-weather-rescue-brazil-g2.md).

Task 2 of that plan is a 2-sheet PAID PROBE (checkpoint before any full run):
this script's `probe` mode runs exactly the 2 structurally-worst sheets from
the G1 gate (bench/g1/gemini-flash.json, the gemini-3.5-flash zero-shot run)
and compares g2b's cell_acc/structural_err_rate against that same G1
baseline on those same 2 sheets. Task 3 (`full` mode) runs all 9 gold
sheets, gated on the probe having cleared its checkpoint bar (a separate
controller decision - see the plan's Task 2 checkpoint note).

Anchoring `reconcile_period`: the 9 curated gold sheets and their periods
are KNOWN metadata (frozen gold, gold/SELECTION.md) - 1885-12, 1886-01,
-02, -03, -04, -05, -07, -09, -11 - NOT something this script has to infer
by chaining one sheet's (possibly wrong, possibly errored) model output
into the next sheet's expected value. Each sheet's `expected_prev` is
therefore derived directly from that sheet's OWN known gold period (one
calendar month before it - see `expected_prev_for_sheet`), independently
of every other sheet. This is a deliberate correction from an earlier
version of this script that instead threaded the previous sheet's
model-derived reconciled period through the loop as `expected_prev`,
resetting it to `None` on any per-sheet exception - which meant one bad
sheet mid-run silently lost the anchor for every sheet after it, even
though the correct expected period for those later sheets was never in
question (it's curated gold metadata, known before any call is made).
`reconcile_period` itself is unchanged: it still only FLAGS (and, when an
anchor is given, overrides) a period the MODEL's own header-read call
disagrees with - what changed is where the anchor comes from.

Usage:
    python scripts/run_g2.py probe                # the Task 2 2-sheet probe
    python scripts/run_g2.py probe <page> [<page> ...]   # override which pages
    python scripts/run_g2.py full                  # the Task 3 9-sheet run
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
from wrb.vlm import (  # noqa: E402
    ExtractionParseError,
    assemble_sheet,
    extract,
    extract_period,
    reconcile_period,
    validate_day_sequence,
)

IMAGE_DIR = ROOT / "data" / "raw" / "docvirt" / "14"
LEDGER = ROOT / "data" / "ledger.json"
BENCH_DIR = ROOT / "bench" / "g2"
G1_GATE_PATH = ROOT / "bench" / "g1" / "gemini-flash.json"

# The controller-mandated gate provider (gemini-3.5-flash) - see
# src/wrb/vlm.py ENDPOINTS's "gemini-flash-full" entry and its notes on why
# "gemini-flash-latest" itself is not used (persistent 503s for this key).
PROVIDER = "gemini-flash-full"

# Task 2's probe set, per the plan: the 2 sheets with the worst
# structural_err_rate under gemini-3.5-flash zero-shot (bench/g1/gemini-flash.json).
# 14_41 (1886-01) is the known wrong-year sheet (structural_err_rate=1.0);
# 14_22 (1885-12) is the next-worst (0.032) - see this run's own printed
# G1-baseline table for the exact numbers, re-derived from the gate file at
# run time rather than hardcoded here. Listed in chronological (page) order
# so reconcile_period has a real prior-sheet anchor for 14_41.
DEFAULT_PROBE_PAGES = [22, 41]


def image_png_bytes(sheet: Sheet) -> bytes:
    """Same conversion as run_g1.py: the frozen source images are .webp;
    vlm.py's request bodies declare image/png for every provider."""
    webp_path = IMAGE_DIR / f"{sheet.page:06d}.webp"
    img = Image.open(webp_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def load_g1_baseline() -> dict[str, dict]:
    """gold_file -> {"cell_acc":..., "structural_err_rate":...} from the G1
    gate file (gemini-3.5-flash zero-shot), the fixed comparison point for
    this probe."""
    data = json.loads(G1_GATE_PATH.read_text())
    out = {}
    for entry in data["per_sheet"]:
        if "scores" in entry:
            out[entry["gold_file"]] = {
                "cell_acc": entry["scores"]["cell_acc"],
                "structural_err_rate": entry["scores"]["structural_err_rate"],
            }
    return out


def worst_structural_sheets(baseline: dict[str, dict], n: int) -> list[str]:
    ranked = sorted(baseline.items(), key=lambda kv: -kv[1]["structural_err_rate"])
    return [gold_file for gold_file, _ in ranked[:n]]


def expected_prev_for_sheet(sheet: Sheet) -> tuple[int, int]:
    """The `reconcile_period` anchor for `sheet`, derived from that sheet's
    OWN known gold period (`sheet.period`, e.g. "1886-01") - one calendar
    month earlier - rather than from any other sheet's model output.

    The 9 curated gold sheets and their periods are known metadata (frozen
    gold; see gold/SELECTION.md), not something inferred at run time by
    chaining sheet-to-sheet: this is what lets each sheet's reconciliation
    be independent of whether an earlier sheet in the run errored out."""
    year, month = (int(p) for p in sheet.period.split("-"))
    if month == 1:
        return year - 1, 12
    return year, month - 1


def run_g2b_on_sheet(sheet: Sheet, meter: CostMeter) -> dict:
    """Run the full g2b pipeline (period call -> reconcile -> table call ->
    barometer reconstruction -> assemble) on one sheet and score it against
    gold. `reconcile_period`'s anchor comes from this sheet's own known gold
    period (`expected_prev_for_sheet`), not from any other sheet's model
    output - so this function's result never depends on what happened, or
    failed, on any other sheet in the run."""
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
    table = extract(img_bytes, PROVIDER, meter, strategy="g2b", day_count=day_count)
    entry["avg_logprobs"] = table.avg_logprobs
    entry["day_sequence_violations"] = validate_day_sequence(table)

    pred_sheet = assemble_sheet(
        table, year=year, month=month,
        source=sheet.source, bib=sheet.bib, page=sheet.page,
        station=sheet.station, columns=sheet.columns,
    )
    s = score(pred_sheet, sheet)
    entry["scores"] = s
    entry["pred"] = pred_sheet.model_dump()
    return entry


def run_g2b(sheets: list[Sheet], meter: CostMeter) -> list[dict]:
    """Run run_g2b_on_sheet over `sheets` in order, logging and recording an
    error entry (never raising, except CapExceeded) per sheet - since each
    sheet's reconciliation anchor is independent (expected_prev_for_sheet),
    a mid-run failure on one sheet cannot corrupt any other sheet's result."""
    results: list[dict] = []
    for sheet in sheets:
        gold_file = f"14_{sheet.page}.json"
        try:
            entry = run_g2b_on_sheet(sheet, meter)
        except CapExceeded:
            raise
        except ExtractionParseError as e:
            print(f"  {sheet.period} ({gold_file}): PARSE ERROR: {e}")
            results.append({"gold_file": gold_file, "gold_period": sheet.period,
                             "page": sheet.page, "error": f"ExtractionParseError: {e}"})
            continue
        except Exception as e:  # noqa: BLE001 - log and move on, same as run_g1.py
            print(f"  {sheet.period} ({gold_file}): ERROR: {type(e).__name__}: {e}")
            results.append({"gold_file": gold_file, "gold_period": sheet.period,
                             "page": sheet.page, "error": f"{type(e).__name__}: {e}"})
            continue

        s = entry["scores"]
        print(f"  {sheet.period} ({gold_file}): cell_acc={s['cell_acc']:.4f} "
              f"structural_err_rate={s['structural_err_rate']:.4f} "
              f"period_read={entry['period_read_raw']} "
              f"reconciled={entry['period_reconciled']} "
              f"flag={entry['period_flag']!r} "
              f"day_violations={len(entry['day_sequence_violations'])} "
              f"avg_logprobs={entry['avg_logprobs']}")
        results.append(entry)
    return results


def aggregate(results: list[dict]) -> dict:
    """Same convention as run_g1.py's aggregate(): cell_acc is a
    micro-average (weighted by each sheet's cell count); structural_err_rate
    and flagged_recall are macro-averages (simple mean across sheets)."""
    scored = [r["scores"] for r in results if "scores" in r]
    n_sheets = len(results)
    n_scored = len(scored)
    if n_scored == 0:
        return {
            "cell_acc": 0.0, "structural_err_rate": 0.0, "flagged_recall": 0.0,
            "n_sheets": n_sheets, "n_sheets_scored": 0, "n_sheets_errored": n_sheets,
        }
    total_cells = sum(s["n_cells"] for s in scored)
    total_correct = sum(s["cell_acc"] * s["n_cells"] for s in scored)
    cell_acc = total_correct / total_cells if total_cells else 1.0
    structural_err_rate = sum(s["structural_err_rate"] for s in scored) / n_scored
    flagged_recall = sum(s["flagged_recall"] for s in scored) / n_scored
    return {
        "cell_acc": cell_acc,
        "structural_err_rate": structural_err_rate,
        "flagged_recall": flagged_recall,
        "n_sheets": n_sheets,
        "n_sheets_scored": n_scored,
        "n_sheets_errored": n_sheets - n_scored,
        "n_cells_total": total_cells,
    }


def print_before_after(results: list[dict], baseline: dict[str, dict]) -> None:
    print()
    print(f"{'sheet':<12} {'G1 cell_acc':>12} {'g2b cell_acc':>13} "
          f"{'G1 struct_err':>14} {'g2b struct_err':>15}")
    for r in results:
        gold_file = r["gold_file"]
        b = baseline.get(gold_file, {"cell_acc": float("nan"), "structural_err_rate": float("nan")})
        if "scores" in r:
            g2b_acc = r["scores"]["cell_acc"]
            g2b_struct = r["scores"]["structural_err_rate"]
        else:
            g2b_acc = g2b_struct = float("nan")
        print(f"{gold_file:<12} {b['cell_acc']:>12.4f} {g2b_acc:>13.4f} "
              f"{b['structural_err_rate']:>14.4f} {g2b_struct:>15.4f}")
    print()


def checkpoint_verdict(results: list[dict]) -> bool:
    """The plan's Task 2 auto-proceed bar: GOOD iff EVERY probe sheet has
    structural_err_rate < 0.03 (~0) AND cell_acc >= 0.95. Any sheet that
    errored (no "scores" key) counts as a failure, not a pass by omission."""
    for r in results:
        if "scores" not in r:
            return False
        s = r["scores"]
        if s["structural_err_rate"] >= 0.03 or s["cell_acc"] < 0.95:
            return False
    return True


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if mode not in ("probe", "full"):
        print(f"unknown mode {mode!r}; expected 'probe' or 'full'", file=sys.stderr)
        sys.exit(2)

    if mode == "full":
        sheets = load_gold()
        sheets.sort(key=lambda s: s.page)

        meter = CostMeter(cap_usd=10.0, ledger=LEDGER)
        print(f"ledger total before full run: US${meter.total():.4f}")
        print(f"FULL: {PROVIDER} (g2b) on all {len(sheets)} sheets: "
              f"{[s.period for s in sheets]} (pages {[s.page for s in sheets]})")

        results = run_g2b(sheets, meter)
        ledger_total = meter.total()
        print(f"ledger total after full run: US${ledger_total:.4f}")

        agg = aggregate(results)
        print(f"aggregate: {json.dumps(agg, indent=2)}")

        BENCH_DIR.mkdir(parents=True, exist_ok=True)
        out = {
            "provider": PROVIDER,
            "strategy": "g2b",
            "aggregate": agg,
            "per_sheet": results,
            "ledger_total_usd": ledger_total,
        }
        out_path = BENCH_DIR / "gemini-3.5-flash-g2b.json"
        out_path.write_text(json.dumps(out, indent=2))
        print(f"wrote {out_path}")
        return

    pages = [int(p) for p in sys.argv[2:]] if len(sys.argv) > 2 else DEFAULT_PROBE_PAGES

    baseline = load_g1_baseline()
    if len(sys.argv) <= 2:
        worst = worst_structural_sheets(baseline, 2)
        print(f"G1 zero-shot worst-structural_err_rate sheets: {worst}")
        derived_pages = [int(g.split("_")[1].split(".")[0]) for g in worst]
        if sorted(derived_pages) != sorted(pages):
            print(f"NOTE: derived worst-2 pages {derived_pages} differ from "
                  f"DEFAULT_PROBE_PAGES {pages} - using derived set.")
            pages = derived_pages

    all_sheets = {s.page: s for s in load_gold()}
    probe_sheets = [all_sheets[p] for p in sorted(pages)]

    meter = CostMeter(cap_usd=10.0, ledger=LEDGER)
    print(f"ledger total before probe: US${meter.total():.4f}")
    print(f"PROBE: {PROVIDER} (g2b) on {len(probe_sheets)} sheets: "
          f"{[s.period for s in probe_sheets]} (pages {[s.page for s in probe_sheets]})")

    results = run_g2b(probe_sheets, meter)

    ledger_total = meter.total()
    print(f"ledger total after probe: US${ledger_total:.4f}")

    print_before_after(results, baseline)

    good = checkpoint_verdict(results)
    print(f"CHECKPOINT BAR: structural_err_rate < 0.03 AND cell_acc >= 0.95 on EVERY probe sheet.")
    print(f"PROBE VERDICT: {'GOOD - proceed to Task 3' if good else 'NOT-GOOD - STOP, escalate to owner'}")

    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "provider": PROVIDER,
        "strategy": "g2b",
        "probe_pages": [s.page for s in probe_sheets],
        "g1_baseline_source": str(G1_GATE_PATH.relative_to(ROOT)),
        "per_sheet": results,
        "ledger_total_usd": ledger_total,
        "checkpoint_good": good,
    }
    out_path = BENCH_DIR / "probe.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
