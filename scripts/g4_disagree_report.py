"""Turn the two-scale disagreement records into something a person can act on.

    python scripts/g4_disagree_report.py

Reads `data/verify/disagreements.jsonl` (written by `g4_disagree.py`) and
reports, per page and overall:

  * how many rows the two reads disagree about, split into the two classes that
    mean something - a value that moved into a neighbouring column (`shift`),
    and a same-column value that differs (`changed`). A cell that is simply
    blank in one read and filled in the other is ignored: the model omits blank
    cells freely and that carries no information.
  * whether the page should be treated as a whole. A page where most rows
    disagree is not a list of suspect cells, it is a page the model cannot read
    stably, and the useful output is to say so rather than emit 31 "suspects".
  * whether the human-found errors are among the flagged cells. That is the
    only test of this method that exists: the method was built to find exactly
    what a person found by hand, so it either reproduces those two or it does
    not work.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "data" / "verify" / "disagreements.jsonl"
CORRECTIONS = ROOT / "data" / "verify" / "corrections.jsonl"
# A page needs a threshold: one row in ten disagreeing is a reading signal,
# half the page is a page-level failure with a different remedy.
PAGE_UNSTABLE = 0.5


def main() -> None:
    rows = [json.loads(l) for l in RECORDS.open() if l.strip()] if RECORDS.exists() else []
    rows = [r for r in rows if not r.get("page_record")]
    if not rows:
        print("no records yet")
        return

    per_page: dict = defaultdict(lambda: {"n": 0, "shift": 0, "changed": 0, "cells": Counter()})
    for r in rows:
        k = (str(r["item"]), int(r["page"]))
        p = per_page[k]
        p["n"] += 1
        if r["shifts"]:
            p["shift"] += 1
        if r["changed"]:
            p["changed"] += 1
        for s in r["shifts"]:
            p["cells"][s] += 1
        for c in r["changed"]:
            p["cells"][c["col"]] += 1

    unstable, suspects = [], []
    for k, p in sorted(per_page.items()):
        frac = max(p["shift"], p["changed"]) / max(1, p["n"])
        if frac >= PAGE_UNSTABLE:
            unstable.append((k, p))
        else:
            for r in rows:
                if (str(r["item"]), int(r["page"])) == k and (r["shifts"] or r["changed"]):
                    suspects.append(r)

    print(f"{len(rows)} rows read twice on {len(per_page)} pages\n")
    print("PAGES THE MODEL CANNOT READ STABLY (most rows disagree between scales)")
    if not unstable:
        print("   none")
    for k, p in unstable:
        print(f"   {k[0]}/{k[1]}: {p['n']} rows, shift {p['shift']}, changed {p['changed']}")
        print(f"        worst cells: {p['cells'].most_common(4)}")
    print(f"\nSUSPECT ROWS on otherwise stable pages: {len(suspects)}")
    by_cell = Counter()
    for s in suspects:
        for x in s["shifts"]:
            by_cell[x] += 1
        for c in s["changed"]:
            by_cell[c["col"]] += 1
    for cell, n in by_cell.most_common(12):
        print(f"   {n:4d}  {cell}")

    # THE ONLY REAL TEST: does this reproduce what a human found by hand?
    if CORRECTIONS.exists():
        corr = [json.loads(l) for l in CORRECTIONS.open() if l.strip()]
        flagged = {(str(r["item"]), int(r["page"]), int(r["row"])): r for r in rows}
        print(f"\nDOES IT FIND THE HUMAN ERRORS? ({len(corr)} known)")
        for c in corr:
            prof, item, page, row = c["id"].split("/")
            rec = flagged.get((item, int(page), int(row)))
            if rec is None:
                print(f"   {c['id']}: not in the run")
                continue
            hits = c["field"] in rec["changed"] or any(c["field"] in s for s in rec["shifts"])
            print(f"   {c['id']} field={c['field']}: "
                  f"{'FLAGGED' if (rec['shifts'] or rec['changed']) else 'not flagged'}"
                  f"{' - and names the field' if hits else ''}"
                  f"   shifts={rec['shifts']} changed={[x['col'] for x in rec['changed']]}")


if __name__ == "__main__":
    main()
