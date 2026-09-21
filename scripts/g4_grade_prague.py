"""Grade the Prague transcription against ECA&D - exact, with no fitted relation.

    python scripts/g4_grade_prague.py <produced.jsonl>

Unlike the Oxford test, this needs no fitted scale or offset: ECA&D reproduces
the printed page digit for digit, so a cell either matches or it does not.
Reports the days the page prints a NUMBER separately from the whole month,
because dry days are the large majority and a score over all cells is mostly
a score for getting blanks right.

Keyed on the day the READER reports.

The first version keyed on row POSITION, assuming row i is day i+1. That is
false whenever the locator misses a page's first row - June 1903 starts at
day 2 - and it silently scored that whole month at zero, which made a real
improvement look like a regression and was reported as one twice before
anyone looked at a raw row.
"""
import json, sys
SP = "/tmp/claude-501/-Users-bueno-detail/32883333-025c-44d0-a4ce-6cbfd878ef46/scratchpad"
eca = {}
for line in open(f"{SP}/RR_STAID000027.txt", encoding="utf-8", errors="replace"):
    p = [x.strip() for x in line.split(",")]
    if len(p) < 5 or not p[2].isdigit() or not p[2].startswith("1903"):
        continue
    v = int(p[3])
    eca[(int(p[2][4:6]), int(p[2][6:8]))] = None if v == -9999 else v / 10.0

rows = [json.loads(l) for l in open(sys.argv[1])]
by = {}
for r in rows:
    by.setdefault(r["period"], []).append(r)
print(f"{'month':>8} {'rows':>5} {'exact':>9} {'wet':>8} {'no day':>7}")
tot = ok = wt = wok = noday = 0
for per in sorted(by):
    m = int(per[5:7]); rs = by[per]
    mo = mok = mw = mwok = mnd = 0
    for r in rs:
        d = r["values"].get("tag")
        if not isinstance(d, (int, float)) or isinstance(d, bool):
            mnd += 1; continue
        ref = eca.get((m, int(d)))
        if ref is None: continue
        got = r["values"].get("niederschlag")
        got = 0.0 if got is None else got
        mo += 1; good = abs(got - ref) < 0.05; mok += good
        if ref > 0: mw += 1; mwok += good
    tot += mo; ok += mok; wt += mw; wok += mwok; noday += mnd
    print(f"{per:>8} {len(rs):5d} {mok:4d}/{mo:<4d} {mwok:3d}/{mw:<4d} {mnd:7d}")
print(f"\nEXACT  {ok}/{tot} = {ok/max(1,tot):.1%}     on days the page prints a value: "
      f"{wok}/{wt} = {wok/max(1,wt):.1%}     rows with no readable day: {noday}")
