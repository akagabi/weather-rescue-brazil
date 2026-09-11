"""Write the dataset out as C3S Station Exchange Format files.

    python scripts/g4_sef.py --out data/sef
    python scripts/g4_sef.py --out data/sef --include-flagged

One `.tsv` per (station, variable), which is what SEF requires. The spec asks
for uncertain cells to be FLAGGED, not dropped, so `--include-flagged` writes
the `flagged` rows too, carrying `qc=uncertain` in the per-observation Meta -
SEF has no quality-flag column and that is the C3S convention.

Read `wrb.sef`'s docstring before submitting anything: the format is verified
against the published spec, but the variable CODES and the station COORDINATES
are not, and both are isolated in `data/*.json` with flags saying so.
"""
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.sef import load_stations, load_variables, sef_filename, write_sef  # noqa: E402

MMHG_TO_HPA = 1.333224


def convert(kind, v):
    if v is None:
        return None
    if kind == "mmHg_to_hPa":
        return round(v * MMHG_TO_HPA, 3)
    return v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/dataset/weather-rescue-brazil.jsonl")
    ap.add_argument("--out", default="data/sef")
    ap.add_argument("--include-flagged", action="store_true")
    args = ap.parse_args()

    stations = load_stations()
    by_dataset_name = {s.get("dataset_name"): s for s in stations.values() if isinstance(s, dict)}
    spec = load_variables()["columns"]

    rows = [json.loads(l) for l in (ROOT / args.dataset).open() if l.strip()]
    wanted = ("checks_pass", "qc_clean") + (("flagged",) if args.include_flagged else ())
    series = defaultdict(list)          # (station_id, vbl, stat) -> rows
    skipped_station = set()
    meta_note = defaultdict(set)

    for r in rows:
        if r.get("verdict") not in wanted or not r.get("is_day_row"):
            continue
        st = by_dataset_name.get(r.get("station"))
        if st is None:
            skipped_station.add(r.get("station"))
            continue
        period = r.get("period") or ""
        try:
            year, month = int(period[:4]), int(period[5:7])
        except (ValueError, IndexError):
            continue
        day = r["values"].get("day") or r["values"].get("date") or r["values"].get("datas")
        if not isinstance(day, (int, float)):
            continue
        qc = "qc=uncertain" if r["verdict"] == "flagged" else ""
        for col, m in spec.items():
            v = r["values"].get(col)
            if v is None or not isinstance(v, (int, float)):
                continue
            series[(st["id"], m["vbl"], m["stat"])].append(
                (year, month, int(day), m.get("hour"), None, m["period"], convert(m["convert"], v), qc))
            if m["convert"] == "mmHg_to_hPa":
                meta_note[(st["id"], m["vbl"], m["stat"])].add("printed units mmHg")

    out = ROOT / args.out
    written = []
    for (sid, vbl, stat), srows in sorted(series.items()):
        st = next(s for s in stations.values() if isinstance(s, dict) and s["id"] == sid)
        m = next(m for m in spec.values() if m["vbl"] == vbl and m["stat"] == stat)
        srows.sort(key=lambda t: (t[0], t[1], t[2], t[3] or 0))
        meta = "|".join(sorted(meta_note[(sid, vbl, stat)]))
        name = sef_filename("wrb", sid, f"{srows[0][0]:04d}-{srows[0][1]:02d}-{srows[0][2]:02d}",
                            f"{srows[-1][0]:04d}-{srows[-1][1]:02d}-{srows[-1][2]:02d}", vbl, stat)
        write_sef(out / name, st, variable=vbl, stat=stat, units=m["units"], rows=srows, meta=meta)
        written.append((name, len(srows)))

    try:
        shown = out.relative_to(ROOT)
    except ValueError:
        shown = out
    print(f"{len(written)} SEF files -> {shown}")
    for n, k in written:
        print(f"   {n:52s} {k:5d} observations")
    if skipped_station:
        print(f"\nstation names with no entry in data/stations.json: {sorted(skipped_station)}")
    unverified = [s["id"] for s in stations.values() if isinstance(s, dict) and not s.get("verified")]
    if unverified:
        print(f"\ncoordinates written as NA (unverified in data/stations.json): {unverified}")
    print(f"\nvariable codes are UNVERIFIED - see wrb.sef's docstring before submitting")
    print("validate with dataresqc::check_sef before sending anything")


if __name__ == "__main__":
    main()
