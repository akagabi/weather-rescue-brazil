#!/usr/bin/env python3
"""G3 Task 2b Step 2/3: the REAL full-Revista transcription run.

Runs the validated g2b + self-consistency-consensus + validator-QC pipeline
(+ optional multi-resolution zoom-flagger) over every PRIMARY monthly daily
table in docIds 14, 15, 16 of the Revista do Observatorio, persisting each
sheet's result to bench/g3/revista-full.json so the run is RESUMABLE (a
completed (doc,page) is skipped on rerun - congestion never loses work).

Work list: bench/g3/revista-worklist.json, a list of
    {"doc": "15", "page": 195, "period": "1889-11", "is_gold": false}
built in Step 1 (enumerate_revista.py + free Read-tool vision to confirm the
"Resumo das observações ... no mez de <Mês> de <Ano>" header/period).

For the 9 docId-14 GOLD tables the consensus predictions already exist in
bench/g3/consensus-gold.json (Task 1) - those are REUSED (no new spend) and
their cell_acc vs the frozen gold is recorded as an external-validity check.
Every NON-gold table is run fresh here.

Per sheet recorded: reconciled period (+ raw period read + reconcile flag),
transcribed values (the assembled Sheet), the flagged-suspect list (cells
flagged "uncertain" by consensus-disagreement OR wrb.qc validators), zoom
suspects (when the zoom-flagger ran), day-sequence violations, and
wrb.gold.validate_sheet violations. Gold tables additionally record cell_acc.

HONESTY: cell_acc for gold is recomputed here against the frozen gold via
wrb.metrics.score, not copied from consensus-gold.json's own aggregate.

Usage:
    python scripts/run_revista_full.py prove <page> [<page> ...]  # 2-3 non-gold pages
    python scripts/run_revista_full.py full                        # whole work list
Env: WRB_GEMINI_KEY (see task keyfile). Provider gemini-flash-full.
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
from wrb.gold import Sheet, load_gold, validate_sheet  # noqa: E402
from wrb.metrics import TOL, score  # noqa: E402
from wrb.qc import flag_violations  # noqa: E402
from wrb.vlm import (  # noqa: E402
    ExtractionParseError,
    assemble_sheet,
    consensus_extract,
    extract_period,
    reconcile_period,
    validate_day_sequence,
)
from wrb.zoom import reconcile as zoom_reconcile  # noqa: E402
from wrb.zoom import zoom_reread_sheet  # noqa: E402

DATA_ROOT = ROOT / "data" / "raw" / "docvirt"
LEDGER = ROOT / "data" / "ledger.json"
BENCH_DIR = ROOT / "bench" / "g3"
WORKLIST_PATH = BENCH_DIR / "revista-worklist.json"
CONSENSUS_GOLD_PATH = BENCH_DIR / "consensus-gold.json"
OUT_PATH = BENCH_DIR / "revista-full.json"

PROVIDER = "gemini-flash-full"
N_CONSENSUS = 3
TEMPERATURE = 0.7

# docId 14's row-band zoom geometry (wrb/zoom.py) is calibrated ONLY to the
# docId-14 Imperial-Observatorio layout (pages 22/75). docId 15/16 tables
# insert Déc (decada) subtotal rows between day groups, which shifts the
# per-row band geometry - so the zoom-flagger is scoped to docId 14 by
# default (see the Task 2b prove-small finding). Consensus-disagreement and
# validator flags remain the primary suspect signal on all docs.
ZOOM_DOCS_DEFAULT = {"14"}

STATION_BY_DOC = {
    "14": "Rio de Janeiro - Imperial Observatorio",
    "15": "Rio de Janeiro - Observatorio Astronomico",
    "16": "Rio de Janeiro - Observatorio Astronomico",
}
COLUMNS = [
    "pressure", "pressure_max", "pressure_min", "tmean", "tmax", "tmin",
    "vapor", "humidity", "wind_force", "cloudiness", "precip",
    "evap_sol", "evap_sombra", "ozone",
]


def image_png_bytes(doc: str, page: int) -> bytes:
    webp = DATA_ROOT / doc / f"{page:06d}.webp"
    img = Image.open(webp).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def prev_month(period: str) -> tuple[int, int]:
    y, m = int(period[:4]), int(period[5:7])
    return (y - 1, 12) if m == 1 else (y, m - 1)


def flagged_cells(sheet: Sheet) -> list[dict]:
    """Every cell flagged 'uncertain' (consensus-disagreement OR a wrb.qc
    validator) - the human-review suspect list."""
    out = []
    for r in sheet.rows:
        for col, reason in r.flags.items():
            if col == "wind_dir":
                continue
            if "uncertain" in reason.lower() or "ambiguous" in reason.lower():
                out.append({"date": r.date, "col": col, "reason": reason})
    return out


def _load_gold_map() -> dict[int, Sheet]:
    try:
        return {s.page: s for s in load_gold()}
    except Exception:
        return {}


def _load_consensus_gold() -> dict[int, dict]:
    if not CONSENSUS_GOLD_PATH.exists():
        return {}
    d = json.loads(CONSENSUS_GOLD_PATH.read_text())
    return {e["page"]: e for e in d.get("per_sheet", []) if "pred" in e}


def run_gold_item(item: dict, cons_gold: dict[int, dict], gold_map: dict[int, Sheet]) -> dict:
    """Reuse the Task-1 consensus prediction for a gold page (no new spend);
    recompute cell_acc vs frozen gold here (honesty mandate)."""
    page = item["page"]
    cg = cons_gold[page]
    pred_sheet = Sheet(**cg["pred"])
    gold_sheet = gold_map[page]
    s = score(pred_sheet, gold_sheet)
    fc = flagged_cells(pred_sheet)
    return {
        "doc": item["doc"], "page": page, "period": item["period"], "is_gold": True,
        "source": "reused:consensus-gold.json",
        "period_reconciled": pred_sheet.period,
        "n_rows": len(pred_sheet.rows),
        "cell_acc": s["cell_acc"],
        "n_cells": s["n_cells"],
        "structural_err_rate": s["structural_err_rate"],
        "flagged_suspects": fc,
        "n_flagged_suspects": len(fc),
        "zoom_suspects": [],
        "n_zoom_suspects": 0,
        "day_sequence_violations": [],
        "validate_sheet_violations": validate_sheet(pred_sheet),
        "pred": pred_sheet.model_dump(),
    }


def run_paid_item(item: dict, meter: CostMeter, gold_map: dict[int, Sheet],
                  zoom_docs: set[str]) -> dict:
    doc, page, period = item["doc"], item["page"], item["period"]
    img = image_png_bytes(doc, page)

    raw_year, raw_month = extract_period(img, PROVIDER, meter)
    (year, month), period_flag = reconcile_period(
        (raw_year, raw_month), expected_prev=prev_month(period))
    day_count = calendar.monthrange(year, month)[1]

    table = consensus_extract(img, PROVIDER, meter, day_count=day_count,
                              n=N_CONSENSUS, temperature=TEMPERATURE)
    day_violations = validate_day_sequence(table)

    pred_sheet = assemble_sheet(
        table, year=year, month=month, source="docvirt", bib=doc, page=page,
        station=STATION_BY_DOC[doc], columns=COLUMNS)
    pred_sheet = flag_violations(pred_sheet)

    fc = flagged_cells(pred_sheet)

    zoom_suspects: list[dict] = []
    zoom_errors: list[str] = []
    if doc in zoom_docs:
        cons_by_day = {int(r.date.split("-")[2]): dict(r.cells) for r in pred_sheet.rows}
        zoom_cells, zoom_errors = zoom_reread_sheet(img, PROVIDER, meter, day_count)
        zoom_suspects = zoom_reconcile(cons_by_day, zoom_cells, tol=TOL)

    entry = {
        "doc": doc, "page": page, "period": period, "is_gold": False,
        "source": "fresh-run",
        "period_read_raw": f"{raw_year:04d}-{raw_month:02d}",
        "period_reconciled": f"{year:04d}-{month:02d}",
        "period_flag": period_flag,
        "n_rows": len(pred_sheet.rows),
        "flagged_suspects": fc,
        "n_flagged_suspects": len(fc),
        "zoom_suspects": zoom_suspects,
        "n_zoom_suspects": len(zoom_suspects),
        "zoom_read_errors": zoom_errors,
        "n_zoom_read_errors": len(zoom_errors),
        "day_sequence_violations": day_violations,
        "validate_sheet_violations": validate_sheet(pred_sheet),
        "pred": pred_sheet.model_dump(),
    }
    # external validity if this non-gold page happens to have gold (it won't,
    # but keep the check general)
    if page in gold_map and gold_map[page].period == pred_sheet.period:
        s = score(pred_sheet, gold_map[page])
        entry["cell_acc"] = s["cell_acc"]
        entry["n_cells"] = s["n_cells"]
    return entry


def _load_existing() -> dict[str, dict]:
    if not OUT_PATH.exists():
        return {}
    d = json.loads(OUT_PATH.read_text())
    return {f"{e['doc']}_{e['page']}": e for e in d.get("per_sheet", [])
            if "error" not in e}


def _key(item: dict) -> str:
    return f"{item['doc']}_{item['page']}"


def persist(done: dict[str, dict], meter: CostMeter, zoom_docs: set[str]) -> None:
    ordered = sorted(done.values(), key=lambda e: (e["doc"], e["page"]))
    gold = [e for e in ordered if e.get("is_gold")]
    periods = [e["period_reconciled"] for e in ordered if e.get("period_reconciled")]
    agg = {
        "n_tables": len(ordered),
        "n_gold": len(gold),
        "n_fresh": len(ordered) - len(gold),
        "year_span": (f"{min(periods)}..{max(periods)}" if periods else None),
        "total_flagged_suspects": sum(e.get("n_flagged_suspects", 0) for e in ordered),
        "total_zoom_suspects": sum(e.get("n_zoom_suspects", 0) for e in ordered),
        "gold_cell_acc_micro": (
            sum(e["cell_acc"] * e["n_cells"] for e in gold if "cell_acc" in e)
            / sum(e["n_cells"] for e in gold if "cell_acc" in e)
        ) if any("cell_acc" in e for e in gold) else None,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "provider": PROVIDER, "strategy": "g2b+consensus+qc+zoom",
        "n_consensus": N_CONSENSUS, "temperature": TEMPERATURE,
        "zoom_docs": sorted(zoom_docs),
        "aggregate": agg,
        "ledger_total_usd": meter.total(),
        "per_sheet": ordered,
    }, indent=2))


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    worklist = json.loads(WORKLIST_PATH.read_text())["work"]

    if mode == "prove":
        pages = {int(p) for p in sys.argv[2:]}
        worklist = [w for w in worklist if w["page"] in pages and not w["is_gold"]]
        zoom_docs = {w["doc"] for w in worklist}  # test zoom on whatever docs the probe pages hit
    elif mode == "full":
        zoom_docs = ZOOM_DOCS_DEFAULT
    else:
        print(f"unknown mode {mode!r}; expected 'prove' or 'full'", file=sys.stderr)
        sys.exit(2)

    gold_map = _load_gold_map()
    cons_gold = _load_consensus_gold()
    done = _load_existing() if mode == "full" else {}
    if done:
        print(f"RESUME: {len(done)} table(s) already done - skipping.", flush=True)

    meter = CostMeter(cap_usd=10.0, ledger=LEDGER)
    before = meter.total()
    print(f"ledger before: US${before:.4f}; provider={PROVIDER}; zoom_docs={sorted(zoom_docs)}", flush=True)

    remaining = [w for w in worklist if _key(w) not in done]
    print(f"{mode.upper()}: {len(remaining)} table(s) to run "
          f"(of {len(worklist)} in list; {len(done)} already done).", flush=True)

    for item in remaining:
        k = _key(item)
        try:
            if item["is_gold"]:
                if item["page"] not in cons_gold:
                    raise RuntimeError(f"gold page {item['page']} missing from consensus-gold.json")
                entry = run_gold_item(item, cons_gold, gold_map)
            else:
                entry = run_paid_item(item, meter, gold_map, zoom_docs)
        except CapExceeded:
            print(f"  {k}: CAP EXCEEDED - persisting and stopping.", flush=True)
            persist(done, meter, zoom_docs)
            raise
        except (ExtractionParseError, RuntimeError, FileNotFoundError) as e:
            print(f"  {k} ({item['period']}): ERROR {type(e).__name__}: {e}", flush=True)
            entry = {"doc": item["doc"], "page": item["page"], "period": item["period"],
                     "is_gold": item["is_gold"], "error": f"{type(e).__name__}: {e}"}
            # errors are NOT stored in `done` (so a rerun retries them), but we
            # still surface them in the file
            done_with_err = dict(done)
            done_with_err[k] = entry
            persist(done_with_err, meter, zoom_docs)
            continue

        done[k] = entry
        msg = (f"cell_acc={entry['cell_acc']:.4f} " if "cell_acc" in entry else "")
        print(f"  {k} ({entry.get('period_reconciled', item['period'])}): "
              f"rows={entry.get('n_rows')} {msg}"
              f"flagged={entry.get('n_flagged_suspects')} "
              f"zoom_suspects={entry.get('n_zoom_suspects')} "
              f"zoom_errs={entry.get('n_zoom_read_errors', 0)} "
              f"validate_viol={len(entry.get('validate_sheet_violations', []))} "
              f"day_viol={len(entry.get('day_sequence_violations', []))}", flush=True)
        persist(done, meter, zoom_docs)

    total = meter.total()
    print(f"ledger after: US${total:.4f} (delta US${total - before:.4f})", flush=True)
    print(f"wrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
