"""Publication profiles: schema-as-data. The decisive test is that the profile
for a layout the pipeline was never designed for (Corumba: 16 columns, two
readings a day, six free-text columns) round-trips its hand-read ground truth
with no code change."""

import json
from pathlib import Path

import pytest

from wrb.profile import Column, Profile, available, blank, from_dict, load

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT = ROOT / "bench" / "g4" / "corumba-holdout.json"


def test_three_layouts_ship():
    ids = available()
    assert {"revista-rio-1886", "revista-santacruz-1889", "corumba-1889"} <= set(ids)


def test_rio_and_santacruz_differ_by_the_evaporation_column():
    rio, sc = load("revista-rio-1886"), load("revista-santacruz-1889")
    assert rio.n_cells == 16 and sc.n_cells == 15
    assert set(rio.keys) - set(sc.keys) == {"evap_sol"}


def test_row_counts_follow_the_layout():
    rio, cor = load("revista-rio-1886"), load("corumba-1889")
    assert rio.expected_rows("1886-02") == 28          # days in month
    assert cor.expected_rows("1886-02") == 56          # two readings a day
    assert rio.expected_rows("1886-01") == 31


def test_target_parse_round_trip():
    p = load("revista-rio-1886")
    vals = {k: None for k in p.keys}
    vals.update(day=1, pressure=754.44, tmean=24.1, wind_dir="O. variavel", ozone=3.0)
    text = p.target(vals)
    assert text.count("|") == p.n_cells - 1
    back, problems = p.parse(text)
    assert problems == []
    assert back["day"] == 1 and back["pressure"] == 754.44
    assert back["wind_dir"] == "O. variavel" and back["tmax"] is None


def test_holdout_ground_truth_round_trips_under_its_profile():
    """The Corumba profile must express the hand-read row exactly."""
    p = load("corumba-1889")
    spec = json.loads(HOLDOUT.read_text())
    assert p.n_cells == len(spec["printed_columns"])
    for row in spec["rows"]:
        cells = row["cells"]
        text = " | ".join("null" if c is None else c for c in cells)
        values, problems = p.parse(text)
        assert problems == [], problems
        assert values["baro_fortin"] == float(cells[2])
        assert values["estado_ceo"] == cells[15]
        assert values[p.day_key] is not None


def test_ditto_marks_resolve_against_the_row_above():
    """Corumba prints the day once and dittos the second reading of that day."""
    p = load("corumba-1889")
    spec = json.loads(HOLDOUT.read_text())
    parsed = []
    for row in spec["rows"]:
        values, problems = p.parse(" | ".join("null" if c is None else c for c in row["cells"]))
        assert problems == [], problems
        parsed.append(values)
    assert parsed[1]["day"] == "»"                 # printed as a ditto
    resolved = p.resolve_dittos(parsed)
    assert resolved[0]["day"] == 1
    assert resolved[1]["day"] == 1                 # same day, second reading
    assert resolved[1]["hour"] == 4.0              # its own value, untouched


def test_parse_reports_a_short_row_instead_of_guessing():
    """One missing cell is padded at the tail - the common case is a blank last
    column - but the assumption is recorded, never silent."""
    from wrb.profile import PADDED_TRAILING
    p = load("corumba-1889")
    values, problems = p.parse(" | ".join(["1"] * 15))       # 15 cells, layout has 16
    assert PADDED_TRAILING in problems
    assert values["estado_ceo"] is None
    # anything further off is a real mismatch and says so
    _, problems = p.parse(" | ".join(["1"] * 12))
    assert any("expected 16" in x for x in problems)


def test_trailing_blank_extra_is_trimmed_quietly():
    p = load("corumba-1889")
    _, problems = p.parse(" | ".join(["1"] * 16 + ["null"]))
    assert problems == []


def test_violations_use_profile_ranges():
    p = load("revista-rio-1886")
    assert p.violations({"humidity": 80.0, "pressure": 754.0}) == []
    bad = p.violations({"humidity": 180.0})
    assert bad and "humidity" in bad[0]
    assert p.violations({"wind_dir": "anything"}) == []      # text is never range-checked


def test_blank_profile_from_column_labels():
    p = blank("novo-jornal", "Novo Jornal", ["Dia", "Barômetro", "Temperatura"])
    assert p.keys == ["dia", "barometro", "temperatura"]
    assert p.column("dia").kind == "day"
    assert p.n_cells == 3


def test_profile_serialises_round_trip(tmp_path):
    p = load("corumba-1889")
    path = p.save(tmp_path / "x.json")
    again = from_dict(json.loads(path.read_text()))
    assert again.keys == p.keys
    assert again.column("baro_fortin").range == p.column("baro_fortin").range


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        Column(key="x", label="X", kind="nonsense")


def test_missing_profile_is_explicit():
    with pytest.raises(FileNotFoundError):
        load("does-not-exist")


def test_verify_supports_a_sum_check() -> None:
    """A rainfall table asserts Yearly Sum = the 12 months added, not averaged."""
    p = blank("t-sum", "t", ["Year", "Jan", "Feb", "Sum"])
    p.checks = [{"kind": "sum", "result": "sum", "of": ["jan", "feb"]}]
    assert p.verify({"year": 1851, "jan": 2.0, "feb": 3.0, "sum": 5.0}) == []
    bad = p.verify({"year": 1851, "jan": 2.0, "feb": 3.0, "sum": 2.5})
    assert bad and "sum gives 5.0000" in bad[0]


def test_verify_rejects_a_mean_outside_its_own_min_and_max() -> None:
    """A printed mean below its printed minimum is impossible, not merely odd:
    this is the only arithmetic the Brazilian day-rows carry."""
    p = blank("t-order", "t", ["Day", "Min", "Mean", "Max"])
    p.checks = [{"kind": "order", "result": "mean", "of": ["min", "max"]}]
    assert p.verify({"day": 1, "min": 755.5, "mean": 756.5, "max": 757.6}) == []
    bad = p.verify({"day": 1, "min": 755.56, "mean": 706.56, "max": 757.62})
    assert bad and "outside" in bad[0]


def test_day_run_survives_a_ditto_and_a_late_start() -> None:
    """Two things real pages do that a naive 1..N walk gets wrong: Corumba
    marks its second daily reading with a ditto, and the locator often misses
    a page's opening rows, so the run starts at 4 rather than 1."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from g4_rescore import day_rows_for_page
    rows = [{"values": {"d": 4}}, {"values": {"d": "»"}}, {"values": {"d": 5}},
            {"values": {"d": "Mez"}}, {"values": {"d": 10}}]
    keep, complete = day_rows_for_page(rows, "1889-01", "d")
    assert keep == {0, 1, 2}          # the ditto belongs to day 4
    assert not complete               # January needs 31 days, starting at 1


def test_1883_hourly_profiles_all_declare_their_mean_check() -> None:
    """Barometre and vapeur both print Moyenne as the mean of the seven daily
    readings on the same row. Leaving the check undeclared silently downgrades
    verified rows to merely plausible ones."""
    for pid in ("rio-1883-barometre", "rio-1883-vapeur"):
        p = load(pid)
        assert p.checks, f"{pid} declara nenhum check"
        assert p.checks[0]["kind"] == "mean" and p.checks[0]["result"] == "moyenne"
        assert len(p.checks[0]["of"]) == 7


def test_parses_a_sign_separated_from_its_number() -> None:
    """The 1883 barometer prints its oscillation as "+ 0.35" and "— 1.23",
    with a space after the sign and an em-dash standing in for the minus."""
    p = blank("t-sign", "t", ["Date", "Oscillation"])
    p.column("oscillation").range = (-20.0, 20.0)
    vals, probs = p.parse("1 | + 0.35")
    assert vals["oscillation"] == 0.35 and not probs
    vals, probs = p.parse("2 | — 1.23")
    assert vals["oscillation"] == -1.23 and not probs
