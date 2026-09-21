"""Swap a page's rows for a better read of the SAME page.

    python scripts/g4_replace_pages.py --dataset data/dataset/weather-rescue-brazil.jsonl \
        --new data/dataset/recovered43.rescored.jsonl --out data/dataset/next.jsonl

`g4_merge` concatenates and drops duplicates on the full provenance key, first
occurrence wins. That is right for assembling separate documents and wrong for
this: a page re-read after a localisation fix produces rows at the SAME
(profile, item, page) with DIFFERENT row indices, so merging the two keeps the
old rows, adds the new ones that happen to sit past the old row count, and
publishes the same printed line twice under two indices. Fifteen pages went
through that before anyone looked.

The criterion for replacing is COVERAGE, not quality: how many distinct printed
day numbers the read accounts for. Choosing the read with the better verdicts
would be choosing by the score, which is how you end up believing a change that
only reorganised the same errors. Coverage is a fact about the page - a read
that accounts for 31 of its days saw more of it than one that accounts for 9 -
and on the pages this was built for the two criteria happened to agree, which
is worth knowing but is not the reason.

A page is replaced when the new read covers strictly more days, and on a TIE
when it carries fewer rows per day it covers. That tiebreak is also a fact and
not a score: a read holding 31 rows for 22 distinct days is carrying 9 rows
that are not data rows, whatever verdicts they happen to get. Regressions keep
what is already published.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb import profile as prof  # noqa: E402


def page_key(r: dict) -> tuple[str, str, int]:
    return (r["profile"], str(r.get("item")), int(r["page"]))


def days_covered(rows: list[dict], cache: dict) -> set[int]:
    """Distinct printed day numbers the read accounts for."""
    out: set[int] = set()
    for r in rows:
        p = cache.setdefault(r["profile"], prof.load(r["profile"]))
        d = (r.get("values") or {}).get(p.day_key)
        if isinstance(d, (int, float)) and not isinstance(d, bool) and 1 <= d <= 31:
            out.add(int(d))
    return out


def read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--new", required=True, help="a re-read of pages already in the dataset")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = read(Path(args.dataset))
    fresh = read(Path(args.new))
    cache: dict = {}

    by_old: dict = defaultdict(list)
    for r in base:
        by_old[page_key(r)].append(r)
    by_new: dict = defaultdict(list)
    for r in fresh:
        by_new[page_key(r)].append(r)

    replace, keep, absent = [], [], []
    for k, rows in sorted(by_new.items()):
        if k not in by_old:
            absent.append(k)
            continue
        od, nd = days_covered(by_old[k], cache), days_covered(rows, cache)
        if len(nd) > len(od):
            better = True
        elif len(nd) == len(od) and nd:
            # Same coverage: prefer the read with less padding around it. On a
            # layout printing one row per day, 31 rows for 22 days means 9 of
            # them are not days.
            better = (len(rows) / len(nd)) < (len(by_old[k]) / max(1, len(od))) - 1e-9
        else:
            better = False
        (replace if better else keep).append((k, len(od), len(nd)))

    print(f"{len(by_new)} page(s) in the new read")
    print(f"  {len(replace)} cover more printed days and will REPLACE what is published")
    for k, o, n in replace:
        extra = "" if n > o else (f"  (same days, {len(by_old[k])} rows -> {len(by_new[k])})")
        print(f"      {k[1]}/{k[2]:<6} {k[0]:22s} {o:3d} -> {n:3d} days{extra}")
    if keep:
        print(f"  {len(keep)} do not, and are left alone")
        for k, o, n in keep:
            print(f"      {k[1]}/{k[2]:<6} {k[0]:22s} {o:3d} -> {n:3d} days")
    if absent:
        print(f"  {len(absent)} are not in the dataset at all - use g4_merge for those, not this")
        for k in absent:
            print(f"      {k[1]}/{k[2]} {k[0]}")

    drop = {k for k, _, _ in replace}
    out = [r for r in base if page_key(r) not in drop]
    # CARRY THE STATION OVER. A re-read comes out of `g4_produce`, which does
    # not know the station - it is applied later by `g4_merge --worklist`, and
    # this tool is not merge. Replacing a page therefore silently dropped the
    # station from every row on it, and after three re-read passes 1,165 rows
    # (382 of them usable) had no station at all: a tenth of the usable data,
    # useless to anyone downstream, and invisible because a row with no
    # station looks exactly like a row that never had one.
    restored = 0
    for k in drop:
        was = next((r.get("station") for r in by_old[k] if r.get("station")), None)
        src = next((r.get("station_source") for r in by_old[k] if r.get("station_source")), None)
        for r in by_new[k]:
            if was and not r.get("station"):
                r["station"] = was
                if src:
                    r["station_source"] = src
                restored += 1
        out.extend(by_new[k])
    if restored:
        print(f"station carried over from the replaced rows onto {restored} new row(s)")
    out.sort(key=lambda r: (str(r.get("item")), int(r["page"]), r.get("profile", ""), int(r["row"])))

    removed = len(base) - sum(1 for r in base if page_key(r) not in drop)
    added = sum(len(by_new[k]) for k in drop)
    print(f"\n{len(base)} rows in, {removed} replaced by {added}, {len(out)} out")
    if args.dry_run:
        print("dry run - nothing written")
        return
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    try:
        shown = p.relative_to(ROOT)
    except ValueError:
        shown = p
    print(f"wrote {shown}\n\nnow re-judge it:\n  python scripts/g4_rescore.py {shown}")


if __name__ == "__main__":
    main()
