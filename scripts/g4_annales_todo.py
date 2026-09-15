"""Collect the Annales pages a sweep found and nothing has produced.

    python scripts/g4_annales_todo.py --doc 8 --out data/g4/annales_todo_8.json

The Annales caption names a month but not an instrument, so it cannot say which
of the six sheets a page is (wrb.caption.is_annales). g4_annales_assign.py
settles that by counting cells; this gathers its input - every page of a volume
that a sweep read as a weather table and no produced dataset already contains.

A period outside the volume's own span is kept and MARKED, not dropped: the
month may be right and only the year misread (doc 8 page 83 is captioned
"Septembre 1893" in a volume that ends in 1885), and a page thrown away for a
bad year is a page nobody looks at again.
"""
from __future__ import annotations

import argparse, glob, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.caption import load_volume_spans, period_outside_volume  # noqa: E402


def produced_pages() -> set[tuple[str, int]]:
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
    args = ap.parse_args()

    done = produced_pages()
    spans = load_volume_spans()
    seen: dict[int, dict] = {}
    for f in sorted(glob.glob(str(ROOT / "data" / "g4" / "identified*.json"))):
        for r in json.loads(Path(f).read_text()):
            if not isinstance(r, dict) or not r.get("caption"):
                continue
            if str(r.get("doc", r.get("item"))) != args.doc:
                continue
            seen[int(r["page"])] = r

    todo, odd = [], 0
    for page, r in sorted(seen.items()):
        if (args.doc, page) in done or not r.get("is_weather_table"):
            continue
        rec = {"doc": args.doc, "page": page, "caption": r["caption"],
               "period": r.get("period"), "profile": None, "n_cells": None}
        why = period_outside_volume(rec["period"], args.doc, spans)
        if why:
            rec["period_suspect"] = why
            odd += 1
        todo.append(rec)

    Path(args.out).write_text(json.dumps(todo, indent=1, ensure_ascii=False) + "\n")
    with_period = sum(1 for r in todo if r.get("period"))
    print(f"doc {args.doc}: {len(seen)} pages with a caption, "
          f"{len(todo)} unproduced weather pages")
    print(f"  {with_period} carry a period, {odd} of those outside the volume's span")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
