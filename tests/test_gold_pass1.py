"""
Locks the schema-correctness of the Task 9 first-pass gold draft
(gold/sheets/*.json). This is NOT the freeze test (that is Task 9 Step 4 /
a later task) - it only guarantees every sheet in the current draft parses
against wrb.gold.Sheet and validates clean, except for cells explicitly
documented as printed-era inconsistencies ("printed_error") or open
low-confidence items ("low_confidence") that a human pass (gold/REVIEW_
QUEUE.md) still needs to resolve.
"""
import json
import re
from pathlib import Path

import pytest

from wrb.gold import Sheet, validate_sheet

GOLD_SHEETS = sorted((Path(__file__).resolve().parent.parent / "gold" / "sheets").glob("*.json"))


def _violation_columns(violation: str) -> list[str]:
    """
    Map a validate_sheet() violation string back to the data column(s) it is
    about, so a documentation flag can be checked for actually covering it
    (rather than just existing somewhere on the sheet).
    """
    m = re.match(r"printed (\w+)_(?:mean|sum)=", violation)
    if m:
        return [m.group(1)]
    m = re.search(r"^\S+: tmax .* < tmin", violation)
    if m:
        return ["tmax", "tmin"]
    m = re.search(r"^\S+: (\w+)=.* outside physical range", violation)
    if m:
        return [m.group(1)]
    return []


def test_gold_sheets_dir_is_not_empty():
    assert GOLD_SHEETS, "expected gold/sheets/*.json to exist - run the Task 9 build first"


@pytest.mark.parametrize("path", GOLD_SHEETS, ids=lambda p: p.stem)
def test_sheet_parses_against_schema(path):
    data = json.loads(path.read_text())
    sheet = Sheet(**data)
    assert sheet.rows, f"{path.name}: sheet has no rows"
    assert sheet.bib and sheet.page and sheet.period, f"{path.name}: missing identifying fields"


@pytest.mark.parametrize("path", GOLD_SHEETS, ids=lambda p: p.stem)
def test_sheet_validates_clean_or_documented(path):
    """
    Per-VIOLATION rigor, not per-sheet: it is not enough for *some* row on
    the sheet to carry a printed_error/low_confidence flag (a sheet could
    have two unrelated violations and only one of them documented, and the
    old per-sheet check would have let the second slip through silently).
    Every specific validate_sheet() violation must map to a documentation
    flag that plausibly covers it - the violated aggregate's column name
    (the part before _mean/_sum, or the raw column for a range/ordering
    violation) must appear in the text of some printed_error/low_confidence
    flag on that sheet (a "sheet-level: ..." flag counts - it's still just
    flag text on a row).
    """
    data = json.loads(path.read_text())
    sheet = Sheet(**data)
    violations = validate_sheet(sheet)
    if not violations:
        return

    flag_texts = [
        text
        for row in sheet.rows
        for text in (row.flags.get("printed_error"), row.flags.get("low_confidence"))
        if text
    ]
    haystack = " | ".join(flag_texts).lower()

    undocumented = []
    for v in violations:
        cols = _violation_columns(v)
        if not cols or not any(col.lower() in haystack for col in cols):
            undocumented.append(v)

    assert not undocumented, (
        f"{path.name}: validate_sheet violation(s) not covered by any "
        f"printed_error/low_confidence flag naming the violated column: {undocumented}"
    )


def test_every_row_has_a_wind_direction_flag():
    # wind direction is stored in flags (cells is dict[str, float | None] and
    # can't hold the free-text "NW, SSE" style value) - guard the convention.
    for path in GOLD_SHEETS:
        sheet = Sheet(**json.loads(path.read_text()))
        for row in sheet.rows:
            assert "wind_dir" in row.flags, f"{path.name} {row.date}: missing wind_dir flag"


def test_total_gold_cell_count_matches_report():
    total = 0
    for path in GOLD_SHEETS:
        sheet = Sheet(**json.loads(path.read_text()))
        total += sum(len(r.cells) for r in sheet.rows)
    # 9 sheets x (14 cols x rows) - see task-9-report.md for the breakdown.
    assert total == 3822, f"gold cell count drifted: {total} (update this test and the report together)"
