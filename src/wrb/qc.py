"""Validator-driven QC flagging (G3 Task 1): the EXTERNAL uncertainty
trigger that complements wrb.vlm.consensus_extract's disagreement flag.

The G2-B gate (bench/g2/gemini-3.5-flash-g2b.json) shows the model's own
`flags[col]="uncertain"` self-flag rate is ~0 (aggregate flagged_recall is
0.0) - the model almost never marks its own wrong reads as uncertain, even
when the printed value is physically impossible or breaks the sheet's own
Mez (month) checksum. `flag_violations` below runs an independent,
deterministic check over an already-assembled Sheet and marks every cell
that participates in one of these violations `uncertain`:

  - a physical-range violation (wrb.gold.RANGES)
  - Tmin <= Tmax
  - a Mez (month) printed-total checksum mismatch (wrb.gold.TOL)
  - a day-sequence violation (a row's date doesn't match its expected
    1-indexed position in the sheet, or a duplicated day-of-month) - the
    Sheet-shaped (ISO `date` string) equivalent of
    wrb.vlm.validate_day_sequence, which works on a pre-assembly G2BTable's
    `day` field instead.

This module deliberately reimplements the physical-range/Tmin<=Tmax/Mez
checks at PER-CELL granularity (rather than parsing wrb.gold.validate_sheet's
human-readable violation strings back into (date, column) pairs) using the
exact same constants (RANGES, TOL) and conditions - so the set of sheets this
flags as "has a violation" is identical to validate_sheet's, just resolved
down to which cell(s) caused it. Final per-cell uncertainty (not computed
here) is consensus-disagreement OR this validator flag - see the G3 plan.
"""

from wrb.gold import RANGES, Row, Sheet, TOL

# Columns that index a row rather than measure it: a day number (or a year, in
# the Oxford tables where rows are years) is a sequence position, so agreement
# between it and a measurement means nothing.
INDEX_KEYS = {"day", "date", "dates", "hour", "year"}


def degenerate_row(values: dict, *, min_cols: int = 8, max_distinct: int = 2,
                   index_keys: set[str] | None = None) -> bool:
    """True when a row's measurements have collapsed to a repeated constant.

    Not every wrong row is an out-of-range one. The model occasionally emits a
    single value repeated across the whole row - the real case (doc 14 p140,
    1886-06) came back as fifteen consecutive 1s, `raw` = "20 | 1 | 1 | ...".
    Every cell sits inside the profile's declared range, and a row whose values
    are all equal cannot contradict its own `order` check, so it reached
    `checks_pass` - the strongest tier - while being entirely fabricated.

    Nothing but the row's own shape can catch this: the numbers are plausible
    one by one, and the only evidence is that they agree too well.

    `min_cols` is the point below which agreement is not evidence (three equal
    cells happen by chance); `max_distinct` is the point above which the row is
    carrying real information. Nulls are absence, not agreement, and are not
    counted. Index columns (day/date/hour/year) are excluded for the same
    reason.
    """
    skip = INDEX_KEYS if index_keys is None else index_keys
    vals = [v for k, v in values.items()
            if k not in skip and isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(vals) < min_cols:
        return False
    return len(set(vals)) <= max_distinct


def _row_day(date_str: str) -> int:
    return int(date_str.split("-")[2])


def _day_sequence_violation_dates(rows: list[Row]) -> set[str]:
    """Dates whose row's day-of-month doesn't match its 1-indexed position
    in `rows`, or that share a duplicated day-of-month with another row -
    the Sheet-shaped equivalent of wrb.vlm.validate_day_sequence."""
    violations: set[str] = set()
    seen: dict[int, str] = {}
    for i, row in enumerate(rows):
        day = _row_day(row.date)
        expected = i + 1
        if day != expected:
            violations.add(row.date)
        if day in seen:
            violations.add(row.date)
            violations.add(seen[day])
        else:
            seen[day] = row.date
    return violations


def flag_violations(sheet: Sheet) -> Sheet:
    """Return a NEW Sheet (the input is not mutated) with `flags[col] =
    "uncertain"` added to every cell that participates in a physical-range,
    Tmin<=Tmax, Mez-checksum, or day-sequence violation. Pre-existing flags
    on each row (e.g. a model's own self-flag, or consensus_extract's
    disagreement flag) are preserved."""
    rows = [Row(date=r.date, cells=dict(r.cells), flags=dict(r.flags)) for r in sheet.rows]

    # 1) Tmin<=Tmax and physical range, per cell.
    for row in rows:
        tmax, tmin = row.cells.get("tmax"), row.cells.get("tmin")
        if tmax is not None and tmin is not None and tmax < tmin:
            row.flags["tmax"] = "uncertain"
            row.flags["tmin"] = "uncertain"
        for col, val in row.cells.items():
            lo_hi = RANGES.get(col)
            if val is not None and lo_hi and not (lo_hi[0] <= val <= lo_hi[1]):
                row.flags[col] = "uncertain"

    # 2) Mez (month) printed-total checksum: a mismatch implicates every row
    # that contributed a value to that column's computed mean/sum - the
    # checksum can't localize to a single day, only to the column.
    if sheet.printed_totals:
        for key, printed in sheet.printed_totals.items():
            parts = key.rsplit("_", 1)
            if len(parts) != 2:
                continue
            col, kind = parts
            vals = [r.cells[col] for r in rows if r.cells.get(col) is not None]
            if not vals:
                continue
            calc = (sum(vals) / len(vals)) if kind == "mean" else sum(vals)
            if abs(calc - printed) > TOL:
                for row in rows:
                    if row.cells.get(col) is not None:
                        row.flags[col] = "uncertain"

    # 3) day-sequence violation: the whole row's date alignment is suspect,
    # not one column, so every cell in that row is flagged.
    violation_dates = _day_sequence_violation_dates(rows)
    for row in rows:
        if row.date in violation_dates:
            for col in row.cells:
                row.flags[col] = "uncertain"

    return Sheet(
        source=sheet.source, bib=sheet.bib, page=sheet.page,
        station=sheet.station, period=sheet.period,
        columns=sheet.columns, rows=rows,
        printed_totals=sheet.printed_totals,
    )
