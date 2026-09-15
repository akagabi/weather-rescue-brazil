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


# --- pressure against the station's own printed altitude --------------------

from wrb.qc import pressure_for_altitude, pressure_implausible  # noqa: E402

# (altitude printed on the page, barometer figures printed in the block)
PRINTED = [
    ("Bahia", 64, [756.1, 758.3, 759.2, 757.8, 761.8, 759.4, 759.8, 760.3]),
    ("Santa Cruz", 26, [756.22, 758.83, 757.03, 757.36]),
    ("Maceió", 10, [762.82, 764.27, 764.82, 763.64, 764.49, 766.25, 766.99]),
    ("S. Paulo", 735, [697.68, 699.12, 697.71, 698.50, 701.40, 703.88, 704.27]),
    ("Ouro Preto", 1145, [665.65]),
]


def test_every_printed_reading_is_plausible_at_its_printed_altitude():
    for name, alt, readings in PRINTED:
        for v in readings:
            assert pressure_implausible(v, alt) is None, f"{name} {v} at {alt}m"


def test_the_ouro_preto_outlier_is_caught():
    """598.32 sits inside the declared 560-790 range and cannot be real."""
    why = pressure_implausible(598.32, 1145)
    assert why is not None and "598.32" in why


def test_a_sea_level_reading_at_a_mountain_station_is_caught():
    assert pressure_implausible(760.0, 1145) is not None


def test_the_formula_matches_the_stations():
    assert pressure_for_altitude(0) == 760.0
    assert round(pressure_for_altitude(735)) == 697
    assert round(pressure_for_altitude(1145)) == 664


def test_a_missing_altitude_is_not_a_failure():
    """Absence of evidence: the check only exists where the page printed one."""
    assert pressure_implausible(598.32, None) is None
    assert pressure_implausible(None, 1145) is None


# --- one printed row read twice ---------------------------------------------

from wrb.qc import near_duplicate_rows  # noqa: E402

KEYS = ["baro", "t_secco", "t_maxima", "t_minima", "humidade"]


def _rows(*vals):
    return [dict(zip(KEYS, v)) for v in vals]


def test_the_maceio_july_block_as_produced():
    """Row `2a` came back carrying row 3's figures; the real 2a was lost."""
    got = _rows((765.67, 24.9, 25.0, 20.1, 78.6),
                (767.09, 24.8, 24.9, 18.9, 78.1),
                (767.00, 24.6, 24.8, 18.8, 78.1))
    assert near_duplicate_rows(got, KEYS) == [(1, 2)]


def test_the_same_block_as_printed_is_clean():
    printed = _rows((765.67, 24.9, 25.0, 20.1, 78.6),
                    (766.60, 24.9, 25.1, 18.6, 76.1),
                    (767.00, 24.6, 24.8, 18.8, 78.1))
    assert near_duplicate_rows(printed, KEYS) == []


def test_genuinely_close_dekads_are_not_flagged():
    """Cidade do Rio Grande's November barometer moves 0.02 between dekads."""
    close = _rows((760.46, 18.67, None, None, 79.4),
                  (760.44, 19.78, None, None, 75.5))
    assert near_duplicate_rows(close, KEYS) == []


def test_one_matching_column_is_a_coincidence_not_evidence():
    assert near_duplicate_rows(_rows((760.0, None, None, None, None),
                                     (760.1, None, None, None, None)), KEYS) == []


# --- elided hundreds, restored from the block's own printed altitude --------

def test_the_printed_altitude_restores_an_elided_barometer():
    """On docId 16 page 41 Bahia prints 755.7 in full and Santa Cruz prints
    56.22 for 756.22, on the same sheet. One declared band cannot serve both
    those stations and Ouro Preto at 1145 m; the printed altitude can."""
    from wrb.reconstruct import restore_thousands

    for printed, alt, want in [(56.22, 26, 756.22), (58.83, 26, 758.83),
                               (57.03, 26, 757.03), (98.5, 735, 698.5)]:
        p = pressure_for_altitude(alt)
        assert restore_thousands(printed, (p - 30.0, p + 30.0)) == want


def test_it_refuses_rather_than_guesses_when_the_band_holds_no_candidate():
    import pytest
    from wrb.reconstruct import restore_thousands

    p = pressure_for_altitude(26)
    with pytest.raises(ValueError):
        restore_thousands(10.0, (p - 30.0, p + 30.0))   # 710 and 810 both out


def test_a_sea_level_band_would_have_mangled_ouro_preto():
    """Why the band is per block and not per column."""
    from wrb.reconstruct import restore_thousands

    assert restore_thousands(65.65, (730.0, 790.0)) == 765.65      # wrong station
    p = pressure_for_altitude(1145)
    assert restore_thousands(65.65, (p - 30.0, p + 30.0)) == 665.65


# --- the wind table's only available validator ------------------------------

from wrb.qc import direction_keys, invalid_compass  # noqa: E402


def _vento():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from wrb import profile as prof
    return prof.load("rio-1883-vento")


def test_the_profile_names_its_own_direction_columns():
    keys = direction_keys(_vento())
    assert len(keys) == 7, keys
    assert all(k.endswith("_dir") for k in keys)


def test_every_compass_point_the_pages_print():
    keys = direction_keys(_vento())
    row = dict(zip(keys, ["N", "NNE", "SW", "E.N.E.", "o", "calma", "0"]))
    assert invalid_compass(row, keys) == []


def test_a_force_figure_in_a_direction_cell_is_caught():
    """The failure this exists for: a cell shifted from the column beside it."""
    keys = direction_keys(_vento())
    row = dict(zip(keys, ["N", "27", "SW", "3.5", None, "NE", "S"]))
    bad = invalid_compass(row, keys)
    assert len(bad) == 2
    assert "27" in bad[0] and "3.5" in bad[1]


def test_a_fragment_of_the_row_above_is_caught():
    keys = direction_keys(_vento())
    assert invalid_compass({keys[0]: "Mez"}, keys)
    assert invalid_compass({keys[0]: "17.31"}, keys)


def test_an_empty_cell_is_not_a_failure():
    keys = direction_keys(_vento())
    assert invalid_compass({keys[0]: None, keys[1]: ""}, keys) == []
