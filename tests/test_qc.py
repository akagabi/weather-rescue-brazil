"""Validator-driven QC flagging (G3 Task 1): pure tests, no network - see
src/wrb/qc.py's module docstring for the design rationale (the model's own
self-flag rate is ~0, so flag_violations is the external trigger)."""

from wrb.gold import Row, Sheet
from wrb.qc import flag_violations


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
