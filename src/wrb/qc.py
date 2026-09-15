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

import re
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


# --- pressure against the station's own printed altitude ---------------------
#
# A barometer range wide enough for this corpus is nearly useless. The
# `Resumo mensal das observacoes simultaneas` form runs from Bahia at 64 m to
# Ouro Preto at 1145 m, so the declared range has to span 560-790 mmHg, and a
# reading of 598 sits comfortably inside it while being 65 mmHg below anything
# Ouro Preto can produce.
#
# The form prints each station's `Alt. do Bar.` in its own header, which turns
# the loose range into a tight one: the barometric formula gives the pressure
# that altitude implies, and a real reading sits within a few mmHg of it
# (weather moves sea-level pressure by about +/-15 mmHg at the extremes).
#
# Measured against the printed pages, with the 25 mmHg window below:
#
#     Bahia        64 m   expect 754   printed 756-760   ok
#     Santa Cruz   26 m   expect 758   printed 756-758   ok
#     Maceio       10 m   expect 759   printed 762-765   ok
#     S. Paulo    735 m   expect 696   printed 697-704   ok
#     Ouro Preto 1145 m   expect 663   printed 665.65    ok
#                                      printed 598.32    65 BELOW - flagged
#
# This does not correct anything. It says which cell to look at.
SEA_LEVEL_MM = 760.0
SCALE_HEIGHT_M = 8434.0


def pressure_for_altitude(alt_m: float) -> float:
    """Station pressure the barometric formula implies, in mmHg."""
    import math
    return SEA_LEVEL_MM * math.exp(-float(alt_m) / SCALE_HEIGHT_M)


def pressure_implausible(baro_mm, alt_m, tol: float = 25.0) -> str | None:
    """A reason string when a barometer reading cannot belong to that altitude.

    None when it is plausible, when either input is missing, or when the
    altitude is not a number - an absent altitude is absence of evidence, and
    this check is only ever available where the page printed one.
    """
    if not isinstance(baro_mm, (int, float)) or not isinstance(alt_m, (int, float)):
        return None
    want = pressure_for_altitude(alt_m)
    off = baro_mm - want
    if abs(off) <= tol:
        return None
    return (f"barometro {baro_mm} mmHg is {off:+.1f} from the {want:.0f} that "
            f"{alt_m:.0f} m implies (tolerance {tol})")


# --- one printed row read twice ---------------------------------------------
#
# Row candidates are proposed generously and a tall ink run is split rather
# than dropped, so a crop can straddle two printed rows. When it does, the
# reader returns the label of one and the numbers of the other, and the result
# is a row that is confidently wrong and looks like every other row.
#
# Measured on docId 15 page 142, Maceio's July block. The page prints
#
#     1a  765.67  24.9  25.0  20.1  78.6
#     2a  766.60  24.9  25.1  18.6  76.1
#     3a  767.00  24.6  24.8  18.8  78.1
#
# and the run produced 1a correctly, 3a correctly, and for `2a` the figures
# 767.09  24.8  24.9  18.9  78.1 - the third row again, a whisker off. The
# second dekad was never read and nothing downstream could tell: every value
# is in range, and the block's month check still passes because two of the
# three dekads are right.
#
# What gives it away is that no two dekads of a real block sit this close. The
# tightest genuine pair measured across these pages differs by 1.2 in some
# column; this one differs by at most 0.2 in any.
NEAR_DUPLICATE_MAX = 0.5


def near_duplicate_rows(rows: list[dict], keys: list[str],
                        max_diff: float = NEAR_DUPLICATE_MAX) -> list[tuple[int, int]]:
    """Pairs of rows so alike they must be the same printed row read twice.

    Compares only the columns both rows carry a number for, and needs at least
    two of them - a pair agreeing on one column is a coincidence, not evidence.
    """
    out = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            diffs = [abs(rows[i][k] - rows[j][k]) for k in keys
                     if isinstance(rows[i].get(k), (int, float))
                     and isinstance(rows[j].get(k), (int, float))]
            if len(diffs) >= 2 and max(diffs) < max_diff:
                out.append((i, j))
    return out


# --- the wind table's only available validator -------------------------------
#
# rio-1883-vento prints no summary column, so it has no arithmetic to check
# itself against: its QC is the force range (0-6) and nothing else. That is
# thin for a layout about to gain a lot of rows.
#
# But a direction cell is not free text. It is a point of the compass, or the
# mark the page uses for calm, and anything else is a misread - a "27" that
# belongs in the neighbouring force column, a fragment of the row above, a
# stray letter. This costs nothing and needs no human.
#
# Deliberately permissive about CASE and about the compositor's variants (N.E.,
# NE, ne), and about the several things printed for calm: the point is to catch
# a cell that is not a direction at all, not to normalise spelling.
COMPASS_POINTS = {
    "n", "nne", "ne", "ene", "e", "ese", "se", "sse",
    "s", "ssw", "sw", "wsw", "w", "wnw", "nw", "nnw",
    # the Annales set W as O (oeste) on some sheets
    "o", "oso", "so", "sso", "no", "nno", "ono", "eno",
}
CALM_MARKS = {"0", "c", "calma", "calme", "calm", "-", "--", "\u2014", ""}
# The Revista records a wind that shifted, or one with no settled direction, and
# both are readings: `NW, SSE` is two points in one cell and `Variavel` is the
# absence of one. A first version of this check rejected both and flagged 1,063
# published rows that are perfectly good - more rows than the layout it was
# written for contains. A validator that does not know its publication's
# notation is not a validator.
VARIABLE_MARKS = {"var", "varvel", "variavel", "variavel", "variable", "vari"}


def invalid_compass(values: dict, dir_keys: list[str]) -> list[str]:
    """Direction cells holding something that is not a direction at all.

    Accepts a point of the compass, a mark for calm, a mark for variable, and
    any comma-separated combination of those - the Revista prints `NW, SSE` for
    a wind that shifted during the interval.
    """
    out = []
    for key in dir_keys:
        v = values.get(key)
        if v is None:
            continue
        raw = str(v).strip()
        # split on commas AND whitespace: the compositor sets both
        # "Var., SSE" and "Var. SSE"
        parts = [t.strip().lower().replace(".", "")
                 for t in re.split(r"[,;/\s]+|\be\b", raw) if t.strip()] or [""]
        if all(t in CALM_MARKS or t in COMPASS_POINTS or t in VARIABLE_MARKS
               for t in parts):
            continue
        out.append(f"{key}={v!r} is not a compass point")
    return out


def direction_keys(profile) -> list[str]:
    """A profile's wind-direction columns, asked of the profile.

    Text columns whose key ends in `_dir`, which is how every wind layout in
    this project names them; a layout that names them otherwise gets an empty
    list and no check, rather than a wrong one.
    """
    return [c.key for c in profile.columns
            if c.kind == "text" and c.key.endswith("_dir")]
