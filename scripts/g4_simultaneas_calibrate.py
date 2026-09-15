"""Set the month-row tolerances from the pages, not from a guess.

    python scripts/g4_simultaneas_calibrate.py data/dataset/simultaneas.jsonl

The `Mez` row of this form does not close exactly on its three dekads. It is
computed from all the daily observations while the dekads are rounded means of
10, 10 and 11 days, so a few tenths of disagreement is the form's normal state
and a tolerance tight enough for the Revista's daily pages flags every row
here. The profile therefore carries a per-column `monthly.tolerance`, and this
is what those numbers should come from.

It reports, per column, the distribution of |printed - mean of the dekads| over
every block whose month row was read in order, and proposes a tolerance that
admits the bulk of it. Two things it deliberately does NOT do: it does not fit
the tolerance to include every observation, because the outliers are what the
check exists to catch; and it does not write the profile, because widening a
tolerance is a decision about what the project is willing to call clean.
"""
from __future__ import annotations

import argparse, collections, json, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb import profile as prof  # noqa: E402

PROFILE = "revista-resumo-simultaneas"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--quantile", type=float, default=0.90,
                    help="share of blocks a proposed tolerance should admit")
    args = ap.parse_args()

    p = prof.load(PROFILE)
    agg = [k for k, v in (p.monthly.get("aggregate") or {}).items() if v == "mean"]
    rows = [json.loads(l) for l in Path(args.dataset).read_text().splitlines() if l.strip()]

    blocks: dict[tuple, dict] = {}
    for r in rows:
        blocks.setdefault((r["item"], r["page"], r["block"]), {})[str(r["row"])] = r

    diffs: dict[str, list[float]] = collections.defaultdict(list)
    n_ordered = 0
    for key, rr in blocks.items():
        mez = rr.get("Mez")
        if mez is None or mez.get("month_check_kind") != "ordered":
            continue
        dek = [rr.get(x) for x in ("1", "2", "3")]
        if any(d is None for d in dek):
            continue
        n_ordered += 1
        for col in agg:
            vals = [(d.get("values") or {}).get(col) for d in dek]
            printed = (mez.get("values") or {}).get(col)
            if printed is None or any(not isinstance(v, (int, float)) for v in vals):
                continue
            diffs[col].append(abs(printed - sum(vals) / len(vals)))

    print(f"{len(blocks)} blocks, {n_ordered} with a month row read in column order\n")
    if not n_ordered:
        print("Nothing to calibrate: no month row was read in order. The unordered "
              "check is what ran, and it uses the same tolerances.")
        return
    print(f"  {'column':<11}{'n':>4}{'median':>9}{'p90':>9}{'max':>9}   proposed")
    proposal = {}
    for col in agg:
        d = sorted(diffs[col])
        if not d:
            print(f"  {col:<11}   0        -        -        -   (no data)")
            continue
        q = d[min(len(d) - 1, int(args.quantile * len(d)))]
        want = round(max(0.05, q * 1.5), 2)
        proposal[col] = want
        print(f"  {col:<11}{len(d):>4}{statistics.median(d):>9.3f}{q:>9.3f}"
              f"{d[-1]:>9.3f}   {want:>6.2f}")
    print(f"\nproposed monthly.tolerance: {json.dumps(proposal)}")
    print("\nNot written. Widening a tolerance decides what this project calls clean,\n"
          "and the outliers it would swallow are what the check exists to catch.")


if __name__ == "__main__":
    main()
