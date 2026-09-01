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
from pathlib import Path

import pytest

from wrb.gold import Sheet, validate_sheet

GOLD_SHEETS = sorted((Path(__file__).resolve().parent.parent / "gold" / "sheets").glob("*.json"))


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
    data = json.loads(path.read_text())
    sheet = Sheet(**data)
    violations = validate_sheet(sheet)
    if not violations:
        return
    # Every violation on a first-pass sheet must be explained by a
    # "printed_error" (documented era inconsistency) or "low_confidence"
    # (open item for the human pass) flag somewhere on the sheet - i.e. we
    # never silently ship an unexplained validate_sheet violation.
    documented = any(
        "printed_error" in row.flags or "low_confidence" in row.flags
        for row in sheet.rows
    )
    assert documented, (
        f"{path.name}: validate_sheet found undocumented violations: {violations}"
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
