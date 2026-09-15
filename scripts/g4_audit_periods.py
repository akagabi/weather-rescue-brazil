"""Re-derive every produced page's period from its printed caption.

    python scripts/g4_audit_periods.py                 # report
    python scripts/g4_audit_periods.py --write         # rewrite the dataset

A page's `period` is its observation month: it dates every row on the page and
it sets how many day-rows the producer expects. It was parsed from the caption
by a matcher that looked for month names by substring, and "Rio de Janeiro"
contains "janeiro" - so Annales captions reading "du mois de Mars 1883 ... DE
RIO DE JANEIRO" were recorded as month 01. This finds every page whose stored
period disagrees with its caption under the fixed matcher (wrb.caption).

It only ever moves a period to what the PAGE PRINTS, and it only ever changes
the MONTH: the bug was month-only, and the caption's year is the less reliable
of the two. Doc 15 page 109 is why - the model read its heading as "MEZ DE
MARÇO DE 1859" where the volume is the 1889 Revista, so trusting the caption's
year would have moved a correct 1889-03 back thirty years. Year disagreements
are reported as a finding and not acted on. Pages whose caption is missing, or
too ambiguous for the fixed matcher, are listed and left alone.
"""
from __future__ import annotations

import argparse, collections, glob, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.caption import match_period  # noqa: E402

DATASET = ROOT / "data" / "dataset" / "weather-rescue-brazil.jsonl"


def captions() -> dict[tuple[str, int], str]:
    """(item, page) -> the caption read off that page, from every stage-A file."""
    out: dict[tuple[str, int], str] = {}
    for f in sorted(glob.glob(str(ROOT / "data" / "g4" / "identified*.json"))
                    + glob.glob(str(ROOT / "data" / "g4" / "annales*.json"))):
        try:
            j = json.loads(Path(f).read_text())
        except Exception:
            continue
        items = j if isinstance(j, list) else sum(
            [v for v in j.values() if isinstance(v, list)], [])
        # the doc is not always on the record (annales_assigned.json is doc 8),
        # so fall back to the document the filename names
        stem = Path(f).stem
        default = "5" if stem.endswith("_5") or "doc5" in stem else "8"
        for r in items:
            if not isinstance(r, dict) or "page" not in r or not r.get("caption"):
                continue
            doc = str(r.get("doc", r.get("item", default)))
            out.setdefault((doc, int(r["page"])), r["caption"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dataset", default=str(DATASET))
    args = ap.parse_args()

    caps = captions()
    rows = [json.loads(l) for l in Path(args.dataset).read_text().splitlines() if l.strip()]
    pages = collections.OrderedDict()
    for r in rows:
        pages.setdefault((str(r["item"]), int(r["page"])), []).append(r)

    fixed, nocap, ambiguous, year_odd, agree = [], [], [], [], 0
    for (item, page), prs in pages.items():
        stored = prs[0]["period"]
        cap = caps.get((item, page))
        if not cap:
            nocap.append((item, page, stored, len(prs)))
            continue
        got = match_period(cap)
        if got is None:
            ambiguous.append((item, page, stored, cap))
            continue
        cap_year, cap_month = got.split("-")
        year = str(stored).split("-")[0]          # the month only; see the docstring
        if cap_year != year:
            year_odd.append((item, page, stored, got))
        want = f"{year}-{cap_month}"
        if want != stored:
            fixed.append((item, page, stored, want, len(prs), cap))
        else:
            agree += 1

    for item, page, was, now, n, cap in fixed:
        print(f"  {item}/{page:<5} {was} -> {now}  ({n} rows) | {cap.replace(chr(10),' ')[:68]}")
    print(f"\n{len(pages)} produced pages: {agree} agree, {len(fixed)} WRONG, "
          f"{len(ambiguous)} caption too ambiguous, {len(nocap)} no caption on file")
    for item, page, stored, got in year_odd:
        print(f"  note: {item}/{page} caption year {got.split('-')[0]} != stored "
              f"{str(stored).split('-')[0]} - year left alone")
    print(f"rows affected: {sum(n for *_, n, _ in fixed)}")

    if not args.write:
        print("\nreport only - re-run with --write to correct the dataset")
        return
    bad = {(i, p): now for i, p, _, now, _, _ in fixed}
    for r in rows:
        k = (str(r["item"]), int(r["page"]))
        if k in bad:
            r["period_as_published"] = r["period"]
            r["period"] = bad[k]
    tmp = Path(args.dataset + ".partial")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    tmp.replace(args.dataset)
    print(f"\nrewrote {args.dataset}: {sum(n for *_, n, _ in fixed)} rows re-dated")


if __name__ == "__main__":
    main()
