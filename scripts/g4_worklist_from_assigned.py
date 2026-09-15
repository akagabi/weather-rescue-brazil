"""Build a production worklist from assignments already on file.

    python scripts/g4_worklist_from_assigned.py --doc 5 \
        --out data/g4/worklist_annales_5b.json

The cell-count pass is the expensive step - it reads rows with the model - and
its answers are stored. When a page was assigned a profile but never produced,
nothing has to be read again: the assignment plus the period is a worklist
entry. Doc 5 has 26 such pages sitting in annales_assigned_5.json.

A period outside the volume's span is carried through and marked, never
dropped and never corrected (see wrb.caption.period_outside_volume).
"""
from __future__ import annotations

import argparse, collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.caption import load_volume_spans, period_outside_volume  # noqa: E402

STATION = {"5": "Imperial Observatório, Rio de Janeiro",
           "8": "Imperial Observatório, Rio de Janeiro"}


def produced() -> set[tuple[str, int]]:
    out = set()
    for f in (ROOT / "data" / "dataset").glob("*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out.add((str(r.get("item")), int(r.get("page", -1))))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sources", nargs="*", default=None)
    args = ap.parse_args()

    sources = args.sources or [str(p) for p in
                               (ROOT / "data" / "g4").glob("annales_assigned*.json")]
    done, spans = produced(), load_volume_spans()
    best: dict[int, dict] = {}
    for f in sorted(sources):
        j = json.loads(Path(f).read_text())
        items = j if isinstance(j, list) else sum(
            [v for v in j.values() if isinstance(v, list)], [])
        for r in items:
            if isinstance(r, dict) and r.get("page") is not None and r.get("profile"):
                best[int(r["page"])] = r

    pages, odd = [], 0
    for page, r in sorted(best.items()):
        if (args.doc, page) in done or not r.get("period"):
            continue
        entry = {"profile": r["profile"], "archive": "docvirt", "doc": args.doc,
                 "page": page, "period": r["period"],
                 "station": STATION.get(args.doc, ""),
                 "station_source": "legenda impressa",
                 "label": f"Annales {args.doc}/{page} {r['period']} {r['profile']}"}
        why = period_outside_volume(r["period"], args.doc, spans)
        if why:
            entry["period_suspect"] = why
            odd += 1
        pages.append(entry)

    Path(args.out).write_text(json.dumps({"pages": pages}, indent=1, ensure_ascii=False))
    print(f"doc {args.doc}: {len(pages)} pages already assigned and never produced"
          + (f", {odd} with a doubtful period" if odd else ""))
    for pid, n in collections.Counter(p["profile"] for p in pages).most_common():
        print(f"  {pid:<26} {n}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
