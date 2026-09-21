"""Re-derive dataset verdicts from the stored model output, no model needed.

    python scripts/g4_rescore.py data/dataset/weather-rescue-brazil.jsonl

Every row keeps the model's raw text, so improving the parser or the QC rules
means rescoring, not re-reading 1200 pages. Keeps the pipeline honest too: the
reading and the judgement about it are separate artefacts.
"""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wrb import profile as prof  # noqa: E402
from wrb.profile import PADDED_TRAILING  # noqa: E402
from wrb.caption import load_volume_spans, period_outside_volume  # noqa: E402
from wrb.qc import (degenerate_row, direction_keys,  # noqa: E402
                    invalid_compass, spurious_duplicate_days)

# Re-derived here rather than carried over from the producer. Rescore rebuilds
# `problems` from the stored `raw`, which silently DROPPED anything the
# producer had added about the page rather than the row - and the first
# casualty was the period_suspect flag, written and wired end to end an hour
# before this rescore erased it. Doc 8 page 83 is captioned "Septembre 1893" in
# a volume that ends in 1885; its 22 rows arrived flagged and came out of the
# rescore with 13 of them usable.
#
# Preserving the producer's problems would work and is the wrong fix: a
# judgement that cannot be re-derived from what the row stores is a judgement
# this project cannot re-check. The row has its item and its period, so the
# volume span can speak for itself.
_SPANS = load_volume_spans()
from wrb.verify import apply_corrections, load_corrections  # noqa: E402
from wrb.qc import barometer_keys, pressure_implausible  # noqa: E402


def _station_altitudes() -> dict:
    """Station name as the dataset spells it -> altitude in metres.

    Only where the altitude is known; an absent one is absence of evidence and
    the check is skipped rather than failed.
    """
    import json as _j
    p = Path(__file__).resolve().parents[1] / "data" / "stations.json"
    if not p.exists():
        return {}
    out = {}
    for v in _j.loads(p.read_text()).values():
        if isinstance(v, dict) and v.get("dataset_name") and v.get("alt") is not None:
            out[v["dataset_name"]] = v["alt"]
    return out


_STATION_ALT = _station_altitudes()
import calendar  # noqa: E402
from collections import defaultdict  # noqa: E402


def day_rows_for_page(page_rows: list[dict], period: str, day_key: str,
                      pk: "prof.Profile" = None) -> tuple[set[int], bool]:
    """Which rows of a page are actually DATA rows, decided by what was read.

    The locator over-counts on a third of pages: the Revista prints a decade
    sub-total ("Dec.") and a month total ("Mez") in the day column, and pitch
    geometry cannot tell those from days. But the model reads the day number,
    and days form a run that either repeats or advances by one.

    Three things this must not assume, each learned from a page that broke it:

    * that the column is called "day" - Porto do Maranhao calls it "datas";
    * that the run starts at 1 - the locator often misses a page's first rows,
      and days 4..28 are 25 good rows plus a coverage gap, not 26 bad ones;
    * that a day appears once - Corumba prints two readings a day and marks the
      second with a ditto, so its column reads 1, », 2, », 3 ...

    A fourth, added for the Radcliffe tables: that the index is a day at all.
    Those rows are indexed by YEAR (1855..1879, one row each), which is the
    same shape of test - a consecutive run of a declared length inside a
    declared range - so the profile supplies the bounds and the expected count
    instead of `calendar` and the literal 1..31.
    """
    if pk is not None:
        want = pk.expected_rows(period)
        lo, hi = pk.index_range
    else:
        year, month = (int(x) for x in period.split("-")[:2])
        want = calendar.monthrange(year, month)[1]
        lo, hi = 1, 31
    days: list[int | None] = []
    last: int | None = None
    for r in page_rows:
        d = r.get("values", {}).get(day_key)
        if isinstance(d, str) and d.strip() == prof.DITTO:
            days.append(last)              # ditto = the same day again
        elif isinstance(d, (int, float)) and lo <= d <= hi:
            last = int(d)
            days.append(last)
        else:
            days.append(None)
    best: list[int] = []
    cur: list[int] = []
    for i, d in enumerate(days):
        if d is None:
            cur = []
            continue
        prev = days[cur[-1]] if cur else None
        if cur and prev is not None and d in (prev, prev + 1):
            cur.append(i)
        else:
            cur = [i]
        if len(cur) > len(best):
            best = list(cur)
    distinct = {days[i] for i in best}
    # "complete" is: the run covers every index the page should hold, and it
    # starts at the first one. For a day table that first index is 1; for a
    # year table it is the first year the page prints.
    first = 1 if pk is None or pk.index_kind == "day_of_month" else int(lo)
    return set(best), (len(distinct) == want and min(distinct, default=0) == first)



def resolve_page_days(pk, page_rows: list[dict], day_key: str) -> dict:
    """Which rows of a page carry a ditto in the day column, and what it means.

    Returns {index of the row in `page_rows`: the day it actually is}. Corumba
    prints two readings a day and writes the day once, dittoeing the second -
    so half of that station's rows published `day: "»"` until this existed
    (`resolve_dittos` had been written and tested but never wired in). A
    consumer could not say which day those rows were.

    The resolved value belongs in `values` (conventions undone in code); the
    printed `»` stays in `values_as_printed`, which must remain faithful.
    """
    out: dict[int, object] = {}
    for i, fixed in enumerate(pk.resolve_dittos([dict(r["values"]) for r in page_rows])):
        if fixed.get(day_key) != page_rows[i]["values"].get(day_key):
            out[i] = fixed[day_key]
    return out


def main() -> None:
    src = Path(sys.argv[1])
    rows = [json.loads(l) for l in src.open()]
    cache: dict[str, prof.Profile] = {}
    # Cells a person has read against the page and found misread. Applied
    # here so a correction survives re-scoring and stays distinguishable
    # from a model reading (see wrb.verify.apply_corrections).
    corr_path = src.parent.parent / "verify" / "corrections.jsonl"
    corr = load_corrections(corr_path)
    # Say so when there are none. The path is relative to the dataset file, so
    # rescoring a copy somewhere else finds no corrections and silently
    # publishes the model's original reading - while the row still carries the
    # `corrections` note and `human_verified: true` saying it was fixed. Two
    # hand-checked cells were reverted exactly this way.
    if not corr:
        print(f"WARNING: no corrections found at {corr_path} - "
              f"every human correction will be dropped from this file")
    else:
        print(f"{sum(len(v) for v in corr.values())} human correction(s) from {corr_path.name}")
    stats: Counter = Counter()
    # first pass: parse every row, so the day sequence can be read off the page
    for r in rows:
        p = cache.setdefault(r["profile"], prof.load(r["profile"]))
        vals, _ = p.parse(r["raw"])
        r["values"] = p.from_printed(vals)
    by_page: dict = defaultdict(list)
    for r in rows:
        by_page[(r["item"], r["page"], r["period"])].append(r)
    # A ditto mark in the day column means "the same day as the line above" -
    # Corumba prints two readings a day and dittos the second. `resolve_dittos`
    # has been in wrb.profile (with a test) since the profile work, but NOTHING
    # in the production path ever called it, so 31 of that page's 62 rows
    # published `day: "»"` and a consumer could not tell which day they were.
    # The resolution belongs in `values` (conventions undone in code), not in
    # `values_as_printed`, which must stay faithful to what the page shows.
    resolved_day: dict[int, object] = {}
    # An integer part the page omitted because it had not changed since the
    # cell ABOVE. Like a ditto, this cannot be resolved from one row - it is a
    # property of the column down the page - so it is settled here and applied
    # to `values` (conventions undone in code), never to `values_as_printed`.
    resolved_carry: dict[int, dict] = {}
    # A row index the reader lost, recovered from the page's own sequence.
    # Recorded on the row, never silent: the value did not come off the page.
    resolved_index: dict[int, int] = {}

    is_day: dict[int, bool] = {}
    page_complete: dict[int, bool] = {}
    day_key_of: dict[int, str] = {}
    monthly: dict[int, list[str]] = {}
    dupe_day: dict[int, object] = {}
    for key, prs in by_page.items():
        pk = cache.setdefault(prs[0]["profile"], prof.load(prs[0]["profile"]))
        day_key = next((c.key for c in pk.columns if c.kind == "day"), "day")
        # BEFORE the day-run test, which is what the filled index is for: a
        # page with six unreadable years has no run long enough to certify
        # itself, and eighteen rows that read perfectly were being called
        # `not_a_day_row` because of the six.
        for i, idx in pk.resolve_index_sequence(
                [dict(r["values"]) for r in prs]).items():
            resolved_index[id(prs[i])] = idx
            prs[i]["values"][day_key] = idx
        keep, complete = day_rows_for_page(prs, key[2], day_key, pk)
        for i, r in enumerate(prs):
            is_day[id(r)] = i in keep
            page_complete[id(r)] = complete
            day_key_of[id(r)] = day_key
        # The page's printed month-total row, if the reader captured it: judged
        # against the day rows it summarises. Recorded, not enforced - see the
        # module docstring. On today's artefact this fires on very few pages,
        # because the locator usually drops the summary row; it costs nothing
        # and it starts working the moment a pass reads those rows.
        summary = next((r for r in prs if pk.is_monthly_summary(r.get("raw") or "")), None)
        if summary is not None and pk.monthly:
            fails = pk.verify_month([r["values"] for i, r in enumerate(prs) if i in keep],
                                    summary["values"])
            for r in prs:
                monthly[id(r)] = fails
        for i, day in resolve_page_days(pk, prs, day_key).items():
            resolved_day[id(prs[i])] = day
        if any(c.elided_carry for c in pk.columns):
            for i, fixed in enumerate(pk.resolve_column_carry(
                    [dict(r["values"]) for r in prs])):
                diff = {k: v for k, v in fixed.items() if v != prs[i]["values"].get(k)}
                if diff:
                    resolved_carry[id(prs[i])] = diff
        # A candidate that is not a data row can still be read, assigned a day
        # and produced. Doc 8 page 43's first row claimed date 10 and held
        # "02 | 01" where a direction and a force belong, while the real day 10
        # sat in its place further down. The page's own dates give it away.
        # Both claimants are flagged: which is real is a question for the
        # checks that look at content, and deleting the wrong one is worse.
        # Only where the layout prints ONE row per day. Corumba prints two -
        # page 16/72 holds 62 rows for 31 days, each day twice - so a repeated
        # day there is the form working correctly, and 20 of its rows were
        # flagged before this guard existed.
        if day_key and pk.rows_per_page == "days_in_month":
            # AFTER resolve_page_days, not before: Corumba prints ditto marks
            # in its day column and those legitimately repeat until resolved.
            # Checking the raw parse would flag every ditto page.
            resolved = [{"values": {day_key: resolved_day.get(
                id(r), (r.get("values") or {}).get(day_key))}} for r in prs]
            for i in spurious_duplicate_days(resolved, day_key):
                dupe_day[id(prs[i])] = resolved[i]["values"].get(day_key)

    out = src.with_name(src.stem + ".rescored.jsonl").open("w")
    for r in rows:
        p = cache.setdefault(r["profile"], prof.load(r["profile"]))
        values, problems = p.parse(r["raw"])
        markers = dict(getattr(p, "last_markers", {}) or {})
        restored = p.from_printed(values)
        if id(r) in resolved_carry:
            restored.update(resolved_carry[id(r)])
        if id(r) in resolved_index:
            restored[day_key_of[id(r)]] = resolved_index[id(r)]
        if id(r) in resolved_day:
            restored[day_key_of[id(r)]] = resolved_day[id(r)]
        rid = f"{r['profile']}/{r.get('item')}/{r['page']}/{r['row']}"
        had = apply_corrections({'values': restored}, corr.get(rid))
        viol = p.violations(restored)
        fails = p.verify(restored) if p.checks else []
        # A row whose measurements have collapsed to a repeated constant is
        # fabricated, not merely wrong: fifteen 1s on doc 14 p140 reached
        # `checks_pass` because every cell sat inside the profile's range and a
        # row of equal values cannot contradict its own ordering. Shape is the
        # only thing that can catch it, so it is a hard problem.
        if degenerate_row(restored, index_keys={day_key_of[id(r)], "year"}):
            problems = problems + ["degenerate_row: measurements collapsed to a repeated value"]
        # The wind layout prints no summary column and so has no arithmetic to
        # check itself against: without this its whole QC is the force range.
        # A direction cell is not free text, and a cell holding a force figure
        # or a fragment of the row above is a misread this can name.
        dkeys = direction_keys(p)
        if dkeys:
            problems = problems + invalid_compass(restored, dkeys)
        # A barometer reading its station's altitude cannot produce. This
        # existed in wrb.qc and was called ONLY by a test, so it never touched
        # a verdict - the same way `resolve_dittos` sat written and unwired
        # while half of Corumba published a ditto mark as its day. Three rows
        # of doc 15 page 89 read 781.6 mmHg, about 1042 hPa, which Rio does
        # not do at any altitude; they were `checks_pass` because all three of
        # mean, max and min misread the same leading digit, so the row agreed
        # with itself.
        alt = (_STATION_ALT.get(r.get("station")) if r.get("station") else None)
        if alt is not None:
            for bkey in barometer_keys(p):
                why = pressure_implausible(restored.get(bkey), alt)
                if why:
                    problems = problems + [f"pressure_implausible: {bkey} {why}"]
        if id(r) in dupe_day:
            problems = problems + [
                f"duplicate_day: another row on this page also claims day "
                f"{dupe_day[id(r)]}; one of them is not a data row"]
        why = period_outside_volume(r.get("period"), str(r.get("item")), _SPANS)
        if why:
            problems = problems + [f"period_suspect: {why}"]
        hard = [x for x in problems if not prof.is_soft_problem(x)]
        scoreable = bool(p.checks) and any(isinstance(restored.get(c["result"]), (int, float)) for c in p.checks)
        # A page whose located row count does not equal the days in its month has
        # picked up rows that are not days - the Revista prints a decade sub-total
        # ("Dec.") and a month total ("Mez") in the same column, and the locator
        # takes them for days. Those rows ARE plausible numbers in plausible
        # ranges, so no per-row check can catch them; only the page-level count
        # can. Until the page closes, none of its rows may be called usable.
        # geometry may over-count, but the day numbers the model read settle it
        page_ok = page_complete[id(r)]
        row_is_day = is_day[id(r)]
        if not row_is_day:
            problems = problems + ["not_a_day_row"]
        if id(r) in resolved_index:
            problems = problems + [
                f"index_from_page_sequence: the printed index was unreadable; "
                f"{resolved_index[id(r)]} comes from this page's own row order"]
        if not page_ok:
            # a coverage gap, not a correctness one: the row's date is fixed by its
            # neighbours in the consecutive run, so it stays usable and says so
            problems = problems + ["page_day_sequence_incomplete"]
        verdict = ("flagged" if not row_is_day
                   else "checks_pass" if scoreable and not fails and not viol and not hard
                   else "qc_clean" if not viol and not hard and not fails
                   else "flagged")
        r["is_day_row"] = row_is_day
        # `publication` used to be copied from the profile's name at production
        # time, which froze a mutable field: renaming two profiles yesterday (from
        # station names to layout names, fixing the provenance bug) left rows
        # produced before and after the rename carrying different strings for the
        # SAME source. Nine publications appeared where five exist. Derive it here
        # instead, so it always matches the profile the row actually used.
        r["publication"] = p.name
        r.update(values_as_printed=values, values=restored, markers=markers, verdict=verdict,
                 padded_trailing=PADDED_TRAILING in problems, problems=problems,
                 range_violations=viol, check_failures=fails,
                 monthly_check=monthly.get(id(r), []))
        if had:
            r["human_verified"] = True
            r["corrections"] = had
        stats[verdict] += 1
        stats["padded"] += PADDED_TRAILING in problems
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
    out.close()
    usable = stats["checks_pass"] + stats["qc_clean"]
    print(f"{len(rows)} rows -> {dict(stats)}")
    print(f"usable (checks_pass + qc_clean): {usable}/{len(rows)} = {usable / len(rows):.1%}")
    print("wrote", src.with_name(src.stem + ".rescored.jsonl").name)


if __name__ == "__main__":
    main()
