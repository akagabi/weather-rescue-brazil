"""Compare the production run against an independent second reading.

    python scripts/g4_simultaneas_check.py data/dataset/simultaneas.jsonl

`data/g4/second_read/simultaneas.json` holds thirteen station blocks - 52 rows,
260 cells - transcribed from the same scans separately from the production
run, across three pages of two documents. Where the two agree the cell is probably right; where they
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
    """Agreement on the value, including agreement that there is none.

    A blank cell is a reading too: Cidade do Rio Grande prints no maximum or
    minimum temperature for two of its months, and a run that invented numbers
    there would be wrong in a way a value-only comparison could not see.
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    # The reader drops trailing zeros the compositor set (25.6 for 25.60), so
    # equality is on the number, not the string. Nothing here is rounded.
    return abs(float(a) - float(b)) < 0.005


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    args = ap.parse_args()

    ref = json.loads(SECOND.read_text())

    rows = [json.loads(l) for l in Path(args.dataset).read_text().splitlines() if l.strip()]
    # Keyed by the block's POSITION on its page, not by its station name. Two
    # blocks on one sheet can carry the same station - docId 15 page 142 holds
    # Maceio's June and Maceio's July - and keying by name collapsed them, so
    # the run's July was compared against this file's June and twenty cells
    # were reported wrong when every one of them was right.
    by = {}
    for r in rows:
        by.setdefault((str(r["item"]), int(r["page"]), int(r.get("block", 0))), {})[str(r["row"])] = r

    # Matching a block of this file to a block of the run is its own problem,
    # and two obvious answers are both wrong.
    #
    # By POSITION fails the moment the run misses a block: on docId 16 page 90
    # it produced two of the four, and position compared its October against
    # this file's November and called thirty correct cells wrong.
    #
    # By CONTENT alone fails exactly where it matters: docId 16 page 41's
    # S. Paulo block was produced with 687.68 where the page prints 697.68, so
    # content pushes it away from the very block it should be compared with -
    # the check would quietly stop looking at the row it exists to catch.
    #
    # So: by STATION first, which the run reads off the page independently of
    # the numbers, and by content only to separate two blocks of the SAME
    # station on one sheet (Cidade do Rio Grande prints three).
    from wrb.stations import canonical_station

    def _row1(rowmap):
        r = rowmap.get("1")
        return (r.get("values") or {}) if r else {}

    def _distance(rowmap, want):
        got = _row1(rowmap)
        d = [abs(got[c] - w) for c, w in zip(COLUMNS, want)
             if isinstance(got.get(c), (int, float)) and isinstance(w, (int, float))]
        return sum(d) / len(d) if d else float("inf")

    # Assignment is GLOBAL, not first-come. Cidade do Rio Grande prints three
    # months on docId 16 page 90 and the run produced one of them; taking the
    # fixture blocks in order handed that one to November when its figures are
    # October's, and reported twenty correct cells wrong. Every same-station
    # pairing is scored first and the closest pairs claim each other.
    pairs = []
    for blk in ref["blocks"]:
        want_id = canonical_station(blk["station"])
        for k, rowmap in by.items():
            if k[0] != blk["doc"] or k[1] != blk["page"]:
                continue
            if canonical_station(next((r.get("station") for r in rowmap.values()), None)) \
                    != want_id:
                continue
            pairs.append((_distance(rowmap, blk["rows"].get("1", [])), id(blk), k))
    matched: dict[int, tuple] = {}
    taken: set[tuple] = set()
    for _d, bid, k in sorted(pairs, key=lambda t: t[0]):
        if bid in matched or k in taken:
            continue
        matched[bid] = k
        taken.add(k)

    per_col = {c: [0, 0] for c in COLUMNS}
    misses, unmatched, not_emitted = [], [], []
    for blk in ref["blocks"]:
        key = matched.get(id(blk))
        got = by.get(key) if key else None
        if got is None:
            near = [k for k in by if k[0] == blk["doc"] and k[1] == blk["page"]]
            unmatched.append(((blk["doc"], blk["page"], blk["station"]), near))
            continue
        key = (blk["doc"], blk["page"], blk["station"])
        produced_station = next((r.get("station") for r in got.values()), None)
        if produced_station and produced_station.split(",")[0].strip() != \
                blk["station"].split(",")[0].strip():
            misses.append(((blk["doc"], blk["page"], blk["station"]), "-",
                           f"station: run {produced_station!r} vs second read "
                           f"{blk['station']!r}"))
        for label, want in blk["rows"].items():
            row = got.get(label)
            if row is None:
                # A month row the producer declined to emit is not a
                # disagreement about a value: the run says so, in
                # month_row_read, and a row whose columns are unknown is not
                # data. Counted apart so the headline number means what it says.
                (not_emitted if label == "Mez" else misses).append(
                    (key, label, "row not produced"))
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
    if not_emitted:
        print(f"\n{len(not_emitted)} month rows the run declined to emit "
              f"(read out of column order; the block's arithmetic was still "
              f"checked as a set)")
    if misses:
        print(f"\n{len(misses)} disagreements:")
        for k, label, why in misses[:40]:
            print(f"  {k[0]}/{k[1]} {k[2]} row {label}: {why}")


if __name__ == "__main__":
    main()
