"""Compare the production run against an independent second reading.

    python scripts/g4_simultaneas_check.py data/dataset/simultaneas.jsonl

`data/g4/second_read/simultaneas.json` holds five station blocks - twenty rows,
a hundred cells - transcribed from the same scans separately from the
production run. Where the two agree the cell is probably right; where they
differ one of them is wrong and that cell is worth a person's time. This is
NOT human verification and nothing it touches is marked verified.

It reports agreement per column, because that is what localises a fault: a
reader that transposes digits fails everywhere at once, a band that is a
column out fails in one place.
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

COLUMNS = ["baro", "t_secco", "t_maxima", "t_minima", "humidade"]
SECOND = ROOT / "data" / "g4" / "second_read" / "simultaneas.json"


def close(a, b, key) -> bool:
    if a is None or b is None:
        return False
    # The reader drops trailing zeros the compositor set (25.6 for 25.60), so
    # equality is on the number, not the string. Nothing here is rounded.
    return abs(float(a) - float(b)) < (0.005 if key != "baro" else 0.005)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    args = ap.parse_args()

    ref = json.loads(SECOND.read_text())
    rows = [json.loads(l) for l in Path(args.dataset).read_text().splitlines() if l.strip()]
    by = {}
    for r in rows:
        by.setdefault((str(r["item"]), int(r["page"]), str(r.get("station"))), {})[str(r["row"])] = r

    per_col = {c: [0, 0] for c in COLUMNS}
    misses, unmatched = [], []
    for blk in ref["blocks"]:
        key = (blk["doc"], blk["page"], blk["station"])
        got = by.get(key)
        if got is None:
            near = [k for k in by if k[0] == blk["doc"] and k[1] == blk["page"]]
            unmatched.append((key, near))
            continue
        for label, want in blk["rows"].items():
            row = got.get(label)
            if row is None:
                misses.append((key, label, "row not produced"))
                continue
            vals = row.get("values") or {}
            for col, w in zip(COLUMNS, want):
                per_col[col][1] += 1
                if close(vals.get(col), w, col):
                    per_col[col][0] += 1
                else:
                    misses.append((key, label, f"{col}: run {vals.get(col)} vs second read {w}"))

    print(f"{len(ref['blocks'])} blocks in the second reading\n")
    for k, near in unmatched:
        print(f"  BLOCK NOT PRODUCED: {k[0]}/{k[1]} {k[2]}   produced on that page: "
              f"{[n[2] for n in near]}")
    total_ok = sum(v[0] for v in per_col.values())
    total = sum(v[1] for v in per_col.values())
    print()
    for col, (ok, n) in per_col.items():
        bar = f"{ok}/{n}" if n else "-"
        print(f"  {col:<10} {bar:>8}  {100*ok/n:5.1f}%" if n else f"  {col:<10}      -")
    print(f"\n  {'TOTAL':<10} {total_ok}/{total}  "
          f"{(100*total_ok/total if total else 0):.1f}% cell agreement")
    if misses:
        print(f"\n{len(misses)} disagreements:")
        for k, label, why in misses[:40]:
            print(f"  {k[0]}/{k[1]} {k[2]} row {label}: {why}")


if __name__ == "__main__":
    main()
