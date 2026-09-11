"""Assemble per-document productions into the published dataset.

    python scripts/g4_merge.py --out data/dataset/weather-rescue-brazil.jsonl \
        data/dataset/doc14.jsonl data/dataset/doc15.jsonl data/dataset/doc16.jsonl \
        --worklist data/g4/worklist_14.json --worklist data/g4/worklist.json

Then re-judge the result - always, and last:

    python scripts/g4_rescore.py data/dataset/weather-rescue-brazil.jsonl

The two steps stay separate on purpose: the reading and the judgement about it
are different artefacts (see wrb.merge and g4_rescore's docstrings). Rescore
assigns `is_day_row`, re-derives every verdict from the stored `raw`, and is
what makes a merged file's tiers mean anything.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.merge import apply_station, merge, summarise  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+", help="produced .jsonl files, any order")
    ap.add_argument("--out", required=True)
    ap.add_argument("--worklist", action="append", default=[],
                    help="worklist JSON(s) carrying each page's station (repeatable)")
    args = ap.parse_args()

    sources = [read_jsonl(Path(s)) for s in args.sources]
    rows = merge(sources)
    print(f"merged {len(sources)} file(s) -> {len(rows)} rows")

    pages: list[dict] = []
    for w in args.worklist:
        pages.extend(json.loads(Path(w).read_text()).get("pages", []))
    touched = apply_station(rows, pages) if pages else 0
    print(f"station applied to {touched} rows from {len(pages)} worklist page(s)")
    if rows and not any(r.get("station") for r in rows):
        print("  WARNING: no row carries a station - were the worklists passed?")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.with_suffix(out.suffix + ".partial").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    out.with_suffix(out.suffix + ".partial").replace(out)

    stats = summarise(rows)
    (out.with_suffix(".summary.json")).write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))
    try:
        shown = out.relative_to(ROOT)
    except ValueError:
        shown = out          # --out outside the repo is legal
    print(f"wrote {shown} (+ .summary.json)")
    print(f"\nnow re-judge it:\n  .venv/bin/python scripts/g4_rescore.py {args.out}")


if __name__ == "__main__":
    main()
