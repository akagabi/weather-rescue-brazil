"""Re-judge the `Resumo mensal` rows from what is already stored.

    python scripts/g4_simultaneas_rescore.py data/dataset/simultaneas.jsonl

Every row keeps its `raw` and its block's printed `station_bar_alt_m`, so the
verdicts can be re-derived with no model and no images - the same bet the rest
of the project makes (see wrb.freeze). This adds the check that needs the
station's own altitude:

A barometer range wide enough for this form is nearly useless. It runs from
Bahia at 64 m to Ouro Preto at 1145 m, so the declared range spans 560-790
mmHg and Ouro Preto's printed 598.32 sits comfortably inside it while being 65
mmHg below anything that altitude can produce. The printed altitude turns that
loose range into a tight one.

It also recalibrates nothing and corrects nothing: a row that fails is flagged
with the reason and the cell to look at.
"""
from __future__ import annotations

import argparse, collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.qc import pressure_implausible  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--tol", type=float, default=25.0)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    path = Path(args.dataset)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    hit = []
    for r in rows:
        why = pressure_implausible((r.get("values") or {}).get("baro"),
                                   r.get("station_bar_alt_m"), tol=args.tol)
        r["pressure_check"] = why
        if why:
            hit.append(r)
            if why not in r.get("problems", []):
                r["problems"] = list(r.get("problems") or []) + [why]
            r["verdict"] = "flagged"

    checked = sum(1 for r in rows if isinstance(r.get("station_bar_alt_m"), (int, float))
                  and isinstance((r.get("values") or {}).get("baro"), (int, float)))
    verd = collections.Counter(r["verdict"] for r in rows)
    print(f"{len(rows)} rows, {checked} with both a barometer figure and a printed altitude")
    print(f"{len(hit)} implausible for their station's altitude")
    for r in hit[:25]:
        print(f"  {r['item']}/{r['page']} blk{r['block']} {r['row']:<4} "
              f"{str(r.get('station'))[:22]:<22} {r['pressure_check']}")
    print(f"\nverdicts: {dict(verd)}")
    if args.write:
        tmp = path.with_suffix(path.suffix + ".partial")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        tmp.replace(path)
        print(f"rewrote {path}")
    else:
        print("report only - re-run with --write")


if __name__ == "__main__":
    main()
