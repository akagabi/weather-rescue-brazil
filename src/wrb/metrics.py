"""Scoring a predicted (VLM-extracted) Sheet against a frozen gold Sheet.

Cell keys used throughout are the gold set's REAL cell keys (see
gold/SELECTION.md "Column mapping / legend"): pressure, pressure_max,
pressure_min, tmean, tmax, tmin, vapor, humidity, wind_force, cloudiness,
precip, evap_sol, evap_sombra, ozone - plus the `wind_dir` row-level flag
(not a numeric cell, so it is never scored here). `score()` is generic over
whatever columns a Sheet declares, so it also works for smaller/synthetic
sheets used in tests.
"""

from wrb.gold import Row, Sheet

TOL = 0.05  # a predicted cell matches gold if abs(pred - gold) <= TOL

# A row counts as a "structural error" (the row/column-shift signature - an
# entire row landed on the wrong date, or got scrambled against a
# neighbouring row) if either:
#   - its date is missing from the prediction entirely, or
#   - at least 3 of its cells are wrong together.
# Real gold sheets always have 14 columns, so the literal ">=3 wrong cells"
# threshold from the brief applies as written. For sheets with fewer than 3
# columns (as in some tests) that literal threshold could never fire even
# when every single cell in the row is wrong, so the threshold is capped at
# the row's own cell count: min(3, n_columns). A tiny table where *all* of
# its cells are wrong is exactly the "whole row is garbage" signature this
# metric exists to catch.
STRUCTURAL_WRONG_CELLS = 3


def _cell_match(gold_val: float | None, pred_val: float | None) -> bool:
    if gold_val is None and pred_val is None:
        return True
    if gold_val is None or pred_val is None:
        return False
    return abs(gold_val - pred_val) <= TOL


def _row_flagged_uncertain(row: Row | None, col: str) -> bool:
    if row is None:
        return False
    return "uncertain" in row.flags.get(col, "").lower()


def score(pred: Sheet, gold: Sheet) -> dict:
    pred_by_date: dict[str, Row] = {r.date: r for r in pred.rows}

    n_cells = 0
    correct_cells = 0
    wrong_cells = 0
    flagged_wrong_cells = 0
    structural_error_rows = 0

    for grow in gold.rows:
        prow = pred_by_date.get(grow.date)
        row_wrong = 0

        for col in gold.columns:
            n_cells += 1
            gval = grow.cells.get(col)
            pval = prow.cells.get(col) if prow is not None else None
            if _cell_match(gval, pval):
                correct_cells += 1
            else:
                wrong_cells += 1
                row_wrong += 1
                if _row_flagged_uncertain(prow, col):
                    flagged_wrong_cells += 1

        wrong_threshold = min(STRUCTURAL_WRONG_CELLS, len(gold.columns))
        if prow is None or row_wrong >= wrong_threshold:
            structural_error_rows += 1

    n_rows = len(gold.rows)
    return {
        "cell_acc": (correct_cells / n_cells) if n_cells else 1.0,
        "structural_err_rate": (structural_error_rows / n_rows) if n_rows else 0.0,
        "flagged_recall": (flagged_wrong_cells / wrong_cells) if wrong_cells else 0.0,
        "n_cells": n_cells,
    }
