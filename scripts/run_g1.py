#!/usr/bin/env python3
"""Task 11: run the real G1 VLM benchmark against the frozen gold set.

Real, paid API calls. Spend is hard-capped at US$10 by CostMeter
(data/ledger.json) - the cap is armor, not budget; the CostMeter's
charge-before-call design means a call that would bust the cap never goes
out. Gemini is the primary/gate provider (billing enabled, header-auth key
per Task 11 corrections in src/wrb/vlm.py); HF/Qwen-VL is attempted
best-effort only, see `hf-probe` mode.

Usage:
    python scripts/run_g1.py probe          # gemini-flash on 2 sheets
    python scripts/run_g1.py full           # gemini-flash on all 9 sheets,
                                             # writes bench/g1/gemini.json
    python scripts/run_g1.py hf-probe       # qwen-vl (HF router) on 1 sheet,
                                             # best-effort, does not gate G1
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
from wrb.metrics import score  # noqa: E402
from wrb.vlm import ExtractionParseError, extract  # noqa: E402

IMAGE_DIR = ROOT / "data" / "raw" / "docvirt" / "14"
LEDGER = ROOT / "data" / "ledger.json"
BENCH_DIR = ROOT / "bench" / "g1"


def image_png_bytes(sheet: Sheet) -> bytes:
    """The frozen source images are .webp; vlm.py's request bodies declare
    image/png for every provider, so convert here rather than change the
    harness's provider-facing mime assumption."""
    webp_path = IMAGE_DIR / f"{sheet.page:06d}.webp"
    img = Image.open(webp_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_provider(provider: str, sheets: list[Sheet], meter: CostMeter) -> list[dict]:
    results = []
    for sheet in sheets:
        gold_file = f"14_{sheet.page}.json"
        entry: dict = {"gold_file": gold_file, "period": sheet.period, "page": sheet.page}
        try:
            img_bytes = image_png_bytes(sheet)
            pred = extract(img_bytes, provider, meter)
        except CapExceeded:
            raise
        except ExtractionParseError as e:
            entry["error"] = f"ExtractionParseError: {e}"
            results.append(entry)
            print(f"  {sheet.period} ({gold_file}): PARSE ERROR: {e}")
            continue
        except Exception as e:  # noqa: BLE001 - deliberately broad: log and move on
            entry["error"] = f"{type(e).__name__}: {e}"
            results.append(entry)
            print(f"  {sheet.period} ({gold_file}): ERROR: {type(e).__name__}: {e}")
            continue

        s = score(pred, sheet)
        entry["scores"] = s
        entry["pred"] = pred.model_dump()
        results.append(entry)
        print(
            f"  {sheet.period} ({gold_file}): cell_acc={s['cell_acc']:.3f} "
            f"structural_err_rate={s['structural_err_rate']:.3f} "
            f"flagged_recall={s['flagged_recall']:.3f} n_cells={s['n_cells']}"
        )
    return results


def aggregate(results: list[dict]) -> dict:
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
    # cell_acc: micro-average (weighted by each sheet's cell count) - a fair
    # per-cell accuracy across the whole benchmark, not skewed by sheets
    # with fewer rows.
    cell_acc = total_correct / total_cells if total_cells else 1.0
    # structural_err_rate / flagged_recall: macro-average (simple mean of
    # per-sheet rates) - each sheet is one independent "page" trial.
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


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    sheets = load_gold()
    sheets.sort(key=lambda s: s.page)

    meter = CostMeter(cap_usd=10.0, ledger=LEDGER)
    print(f"ledger total before run: US${meter.total():.4f}")

    if mode == "probe":
        probe_sheets = sheets[:2]
        print(f"PROBE: gemini-flash on {len(probe_sheets)} sheets: "
              f"{[s.period for s in probe_sheets]}")
        results = run_provider("gemini-flash", probe_sheets, meter)
        print(f"ledger total after probe: US${meter.total():.4f}")
        n_ok = sum(1 for r in results if "scores" in r)
        if n_ok < len(probe_sheets):
            print("PROBE FAILED - not all sheets parsed/scored. STOPPING before full run.")
            sys.exit(1)
        print("PROBE OK.")

    elif mode == "full":
        print(f"FULL: gemini-flash on all {len(sheets)} sheets")
        results = run_provider("gemini-flash", sheets, meter)
        agg = aggregate(results)
        print(f"ledger total after full run: US${meter.total():.4f}")
        print(f"aggregate: {json.dumps(agg, indent=2)}")

        BENCH_DIR.mkdir(parents=True, exist_ok=True)
        out = {"provider": "gemini-flash", "aggregate": agg, "per_sheet": results,
               "ledger_total_usd": meter.total()}
        out_path = BENCH_DIR / "gemini.json"
        out_path.write_text(json.dumps(out, indent=2))
        print(f"wrote {out_path}")

    elif mode == "retry":
        pages = {int(p) for p in sys.argv[2:]}
        if not pages:
            print("usage: run_g1.py retry <page> [<page> ...]", file=sys.stderr)
            sys.exit(2)
        prior = json.loads((BENCH_DIR / "gemini.json").read_text())
        retry_sheets = [s for s in sheets if s.page in pages]
        print(f"RETRY: gemini-flash on pages {sorted(pages)}: "
              f"{[s.period for s in retry_sheets]}")
        new_results = run_provider("gemini-flash", retry_sheets, meter)
        print(f"ledger total after retry: US${meter.total():.4f}")

        by_page = {r["page"]: r for r in prior["per_sheet"]}
        for r in new_results:
            by_page[r["page"]] = r
        merged = [by_page[s.page] for s in sheets]
        agg = aggregate(merged)
        print(f"aggregate after merge: {json.dumps(agg, indent=2)}")

        out = {"provider": "gemini-flash", "aggregate": agg, "per_sheet": merged,
               "ledger_total_usd": meter.total()}
        out_path = BENCH_DIR / "gemini.json"
        out_path.write_text(json.dumps(out, indent=2))
        print(f"wrote {out_path}")

    elif mode == "hf-probe":
        probe_sheets = sheets[:1]
        print(f"HF-PROBE (best-effort, does not gate G1): qwen-vl on "
              f"{len(probe_sheets)} sheet: {[s.period for s in probe_sheets]}")
        try:
            results = run_provider("qwen-vl", probe_sheets, meter)
        except CapExceeded as e:
            print(f"HF-PROBE: CapExceeded: {e}")
            sys.exit(1)
        print(f"ledger total after hf-probe: US${meter.total():.4f}")
        n_ok = sum(1 for r in results if "scores" in r)
        print("HF-PROBE OK." if n_ok else "HF-PROBE FAILED (see error above) - documented, skipped.")

    else:
        print(f"unknown mode {mode!r}; expected probe|full|hf-probe", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
