"""Validator-driven QC flagging (G3 Task 1): pure tests, no network - see
src/wrb/qc.py's module docstring for the design rationale (the model's own
self-flag rate is ~0, so flag_violations is the external trigger)."""

from wrb.gold import Row, Sheet
from wrb.qc import degenerate_row, flag_violations


def make(rows, totals=None, cols=("tmax", "tmin")):
    return Sheet(source="docvirt", bib="14", page=99, station="Rio de Janeiro - Imperial Observatorio",
                 period="1886-01", columns=list(cols), rows=rows, printed_totals=totals)


def test_clean_sheet_gets_no_new_flags():
    rows = [Row(date=f"1886-01-{d:02d}", cells={"tmax": 20.0, "tmin": 10.0}, flags={}) for d in (1, 2, 3)]
    out = flag_violations(make(rows))
    assert all(r.flags == {} for r in out.rows)


def test_flags_physical_range_violation():
    rows = [Row(date="1886-01-01", cells={"tmax": 999.0, "tmin": 10.0}, flags={})]
    out = flag_violations(make(rows))
    assert out.rows[0].flags.get("tmax") == "uncertain"
    assert "tmin" not in out.rows[0].flags


def test_flags_tmin_gt_tmax_both_cells():
    rows = [Row(date="1886-01-01", cells={"tmax": 10.0, "tmin": 20.0}, flags={})]
    out = flag_violations(make(rows))
    assert out.rows[0].flags.get("tmax") == "uncertain"
    assert out.rows[0].flags.get("tmin") == "uncertain"


def test_flags_mez_checksum_violation_on_every_contributing_row():
    rows = [Row(date=f"1886-01-{d:02d}", cells={"tmax": 20.0, "tmin": 10.0}, flags={}) for d in (1, 2)]
    out = flag_violations(make(rows, totals={"tmax_mean": 999.0}))
    assert out.rows[0].flags.get("tmax") == "uncertain"
    assert out.rows[1].flags.get("tmax") == "uncertain"
    # tmin was never part of the printed total - untouched by this check.
    assert "tmin" not in out.rows[0].flags


def test_mez_checksum_within_tolerance_is_not_flagged():
    rows = [Row(date=f"1886-01-{d:02d}", cells={"tmax": 20.0, "tmin": 10.0}, flags={}) for d in (1, 2)]
    out = flag_violations(make(rows, totals={"tmax_mean": 20.0}))
    assert all(r.flags == {} for r in out.rows)


def test_flags_day_sequence_gap_on_every_cell_in_the_shifted_row():
    # day 2 is missing entirely - row index 1 (0-indexed) is printed as day 3.
    rows = [
        Row(date="1886-01-01", cells={"tmax": 20.0, "tmin": 10.0}, flags={}),
        Row(date="1886-01-03", cells={"tmax": 21.0, "tmin": 11.0}, flags={}),
    ]
    out = flag_violations(make(rows))
    assert out.rows[1].flags.get("tmax") == "uncertain"
    assert out.rows[1].flags.get("tmin") == "uncertain"
    # the first row's own day (1) matches its position - not itself flagged
    # by the sequence check (no range/checksum violation here either).
    assert out.rows[0].flags == {}


def test_flags_duplicated_day_on_both_rows():
    rows = [
        Row(date="1886-01-01", cells={"tmax": 20.0, "tmin": 10.0}, flags={}),
        Row(date="1886-01-01", cells={"tmax": 21.0, "tmin": 11.0}, flags={}),
    ]
    out = flag_violations(make(rows))
    assert out.rows[0].flags.get("tmax") == "uncertain"
    assert out.rows[1].flags.get("tmax") == "uncertain"


def test_preserves_preexisting_flags():
    rows = [Row(date="1886-01-01", cells={"tmax": 20.0, "tmin": 10.0}, flags={"wind_dir": "SSE"})]
    out = flag_violations(make(rows))
    assert out.rows[0].flags.get("wind_dir") == "SSE"


def test_does_not_mutate_input_sheet():
    rows = [Row(date="1886-01-01", cells={"tmax": 999.0, "tmin": 10.0}, flags={})]
    s = make(rows)
    flag_violations(s)
    assert s.rows[0].flags == {}


# --- degenerate rows -------------------------------------------------------
# The model sometimes collapses a row into a repeated constant. The real case
# (revista-rio-1886 doc 14 p140, 1886-06) came back as fifteen consecutive 1s
# and reached `checks_pass`, because every value sits inside the profile's
# declared range and an all-equal row cannot contradict its own ordering.

def test_degenerate_row_catches_the_real_p140_row():
    vals = {"day": 20, "pressure": 701.0, "pressure_max": 701.0, "pressure_min": 701.0,
            "tmean": 1.0, "tmax": 1.0, "tmin": 1.0, "vapor": 1.0, "humidity": 1.0,
            "wind_force": 1.0, "cloudiness": 1.0, "precip": 1.0, "evap_sol": 1.0,
            "evap_sombra": 1.0}
    assert degenerate_row(vals) is True


def test_normal_row_is_not_degenerate():
    vals = {"tmean": 25.3, "tmax": 30.1, "tmin": 20.5, "humidity": 77.8, "pressure": 755.5,
            "vapor": 18.5, "ozone": 2.8, "wind_force": 4.4, "cloudiness": 4.5}
    assert degenerate_row(vals) is False


def test_sparse_row_is_not_degenerate():
    """Fewer than `min_cols` values carries no evidence - do not call it."""
    assert degenerate_row({"tmean": 1.0, "tmax": 1.0, "tmin": 1.0}) is False


def test_day_column_does_not_count_toward_the_evidence():
    """The day number is a sequence index, not a measurement: a row of twelve
    1s must still be degenerate even though `day` would add a 13th value."""
    vals = {"day": 7, "a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0, "e": 1.0, "f": 1.0, "g": 1.0, "h": 1.0}
    assert degenerate_row(vals) is True


def test_nulls_do_not_count_toward_the_evidence():
    """Only real numbers count; nulls are absence, not agreement."""
    vals = {"a": 1.0, "b": 1.0, "c": 1.0, "d": None, "e": None, "f": None, "g": None, "h": None}
    assert degenerate_row(vals) is False
