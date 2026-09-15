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

It also settles where a failed MONTH check belongs. That check spans a block -
the printed Mez against the mean of the three dekads - so it cannot say which
row is wrong. Flagging all four would throw away three dekads because a summary
disagrees; flagging none would let a block that does not close pass silently.
The month row is the one the page asserts, so the month row is the one flagged,
and the dekads keep their own verdict and carry the block's `month_check` so a
consumer can see it did not close.

It recalibrates nothing and corrects nothing: a row that fails is flagged with
the reason and the cell to look at.
"""
from __future__ import annotations

import argparse, collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.qc import (near_duplicate_rows, pressure_for_altitude,  # noqa: E402
                    pressure_implausible)
from wrb.reconstruct import restore_thousands  # noqa: E402
from wrb.stations import canonical_station  # noqa: E402

COLUMNS = ["baro", "t_secco", "t_maxima", "t_minima", "humidade"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--tol", type=float, default=25.0)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    path = Path(args.dataset)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    # The hundreds digit is elided in some blocks and not in others. On docId
    # 16 page 41 Bahia prints 755.7 in full and Santa Cruz prints 56.22 for
    # 756.22, on the same sheet. The usual machinery restores from a single
    # declared band per column, which cannot work here: the stations run from
    # sea level to Ouro Preto at 1145 m, so one band wide enough for all of
    # them is wide enough to be ambiguous.
    #
    # The block's own printed altitude settles it. The barometric formula gives
    # the pressure that altitude implies and restore_thousands is asked for the
    # unique candidate within 30 mmHg of it - and refuses, rather than guesses,
    # if there is not exactly one.
    # The printed name stays; a canonical id sits beside it so the same station
    # set two ways - "Bahia, Capital" and "Bahia (Capital)" both appear in this
    # run's output - counts once.
    for r in rows:
        r["station_id"] = canonical_station(r.get("station"))

    restored = 0
    for r in rows:
        v = (r.get("values") or {}).get("baro")
        alt = r.get("station_bar_alt_m")
        if isinstance(v, (int, float)) and v < 200 and isinstance(alt, (int, float)):
            want = pressure_for_altitude(alt)
            try:
                full = restore_thousands(float(v), (want - 30.0, want + 30.0))
            except ValueError:
                r["problems"] = list(r.get("problems") or []) + [
                    f"baro {v} is elided and no unique value near the "
                    f"{want:.0f} mmHg that {alt:.0f} m implies"]
                r["verdict"] = "flagged"
            else:
                r.setdefault("values_as_printed", dict(r["values"]))
                r["values_as_printed"]["baro"] = v
                r["values"]["baro"] = full
                r["baro_restored_from"] = v
                restored += 1

    hit, month_flagged = [], 0
    for r in rows:
        # the block's arithmetic belongs to the row that asserts it
        if r.get("month_check") and str(r.get("row")) == "Mez":
            r["verdict"] = "flagged"
            month_flagged += 1
        why = pressure_implausible((r.get("values") or {}).get("baro"),
                                   r.get("station_bar_alt_m"), tol=args.tol)
        r["pressure_check"] = why
        if why:
            hit.append(r)
            if why not in r.get("problems", []):
                r["problems"] = list(r.get("problems") or []) + [why]
            r["verdict"] = "flagged"

    # One printed row read twice. A crop that straddles two rows returns the
    # label of one and the numbers of the other, and the row it displaced is
    # never read at all - see wrb.qc.near_duplicate_rows for the measured case.
    blocks: dict[tuple, list] = {}
    for r in rows:
        if str(r.get("row")) != "Mez":
            blocks.setdefault((r["item"], r["page"], r.get("block")), []).append(r)
    dupes = 0
    for key, rr in blocks.items():
        for i, j in near_duplicate_rows([r.get("values") or {} for r in rr], COLUMNS):
            why = (f"near_duplicate_row: rows {rr[i].get('row')} and "
                   f"{rr[j].get('row')} of this block are the same reading; one "
                   f"printed row was read twice and another was not read")
            for r in (rr[i], rr[j]):
                if why not in (r.get("problems") or []):
                    r["problems"] = list(r.get("problems") or []) + [why]
                r["verdict"] = "flagged"
            dupes += 1

    checked = sum(1 for r in rows if isinstance(r.get("station_bar_alt_m"), (int, float))
                  and isinstance((r.get("values") or {}).get("baro"), (int, float)))
    verd = collections.Counter(r["verdict"] for r in rows)
    print(f"{len(rows)} rows, {checked} with both a barometer figure and a printed altitude")
    print(f"{month_flagged} month rows flagged because their block's arithmetic "
          f"did not close")
    print(f"{dupes} near-duplicate dekad pairs (one printed row read twice)")
    print(f"{restored} elided barometer readings restored from the block's "
          f"printed altitude")
    print(f"{len(hit)} implausible for their station's altitude")
    for r in hit[:25]:
        print(f"  {r['item']}/{r['page']} blk{r['block']} {r['row']:<4} "
              f"{str(r.get('station'))[:22]:<22} {r['pressure_check']}")
    ids = collections.Counter(r.get("station_id") for r in rows)
    print(f"\n{len([k for k in ids if k])} stations: "
          + ", ".join(f"{k} ({v})" for k, v in ids.most_common() if k))
    print(f"verdicts: {dict(verd)}")
    if args.write:
        tmp = path.with_suffix(path.suffix + ".partial")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        tmp.replace(path)
        print(f"rewrote {path}")
    else:
        print("report only - re-run with --write")


if __name__ == "__main__":
    main()
