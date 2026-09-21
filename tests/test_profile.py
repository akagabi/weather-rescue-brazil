"""Publication profiles: schema-as-data. The decisive test is that the profile
for a layout the pipeline was never designed for (Corumba: 16 columns, two
readings a day, six free-text columns) round-trips its hand-read ground truth
with no code change."""

import json
from pathlib import Path

import pytest

from wrb import profile as prof
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


# --- the page's own monthly summary row -----------------------------------
# The newspaper tables print a month-total row ("Mez") carrying the month's
# MEAN per measurement column (max for the maxima, min for the minima, sum for
# rainfall) - measured on revista-rio-1886 doc 14 p41 1886-01, where the printed
# row reproduces the mean of that page's 31 day rows exactly (tmean 25.30,
# vapor 18.50) for 8 of its 14 columns. It is the only arithmetic available for
# the ~2000 rows whose profiles carry no per-row check.

from wrb.profile import Column, Profile


def _monthly_profile(**kw):
    return Profile(
        id="t", name="t",
        columns=[Column(key="day", label="Date", kind="day"),
                 Column(key="tmean", label="T", unit="C", range=(15, 35)),
                 Column(key="tmax", label="Tmax", unit="C", range=(18, 42)),
                 Column(key="tmin", label="Tmin", unit="C", range=(8, 30)),
                 Column(key="precip", label="Rain", unit="mm", range=(0, 300))],
        monthly={"markers": ["Mez", "Mois"], "aggregate": {"tmean": "mean", "tmax": "max",
                                                           "tmin": "min", "precip": "sum"}},
        **kw)


def test_summary_row_is_identified_by_the_word_the_page_prints():
    p = _monthly_profile()
    assert p.is_monthly_summary("Mez | 55.53 | 25.3 | 34.5 | 20.6 | 26.2") is True
    assert p.is_monthly_summary("Mois | 55.53 | 25.3") is True
    # a day row is never a summary, however its numbers look
    assert p.is_monthly_summary("20 | 55.53 | 25.3 | 34.5 | 20.6 | 26.2") is False


def test_verify_month_accepts_a_month_that_reproduces_its_printed_totals():
    p = _monthly_profile()
    # a ramp, so mean / max / min / sum are four DIFFERENT numbers and the
    # test cannot pass by applying one aggregation to all four columns
    days = [{"day": d, "tmean": 20.0 + d * 0.1, "tmax": 30.0 + d * 0.1,
             "tmin": 10.0 + d * 0.1, "precip": 1.0} for d in range(1, 11)]
    summary = {"tmean": 20.55, "tmax": 31.0, "tmin": 10.1, "precip": 10.0}
    assert p.verify_month(days, summary) == []


def test_verify_month_flags_the_column_that_does_not_reproduce():
    """The check's whole value: it names the column, not just the page. A
    shifted column is exactly the failure physical ranges cannot see, because
    both columns stay plausible."""
    p = _monthly_profile()
    days = [{"day": d, "tmean": 20.0 + d * 0.1, "tmax": 30.0 + d * 0.1,
             "tmin": 10.0 + d * 0.1, "precip": 1.0} for d in range(1, 11)]
    summary = {"tmean": 20.55, "tmax": 31.0, "tmin": 10.1, "precip": 999.0}
    fails = p.verify_month(days, summary)
    assert len(fails) == 1
    assert fails[0].startswith("precip")


def test_verify_month_skips_a_column_the_page_did_not_fully_print():
    """A mean over a gapped month cannot match the printed mean - that is
    absence of evidence, not evidence of an error."""
    p = _monthly_profile()
    days = [{"day": 1, "tmean": 20.0, "tmax": 30.0, "tmin": 10.0, "precip": 1.0},
            {"day": 2, "tmean": None, "tmax": 30.0, "tmin": 10.0, "precip": 1.0}]
    fails = p.verify_month(days, {"tmean": 20.0, "tmax": 30.0, "tmin": 10.0, "precip": 2.0})
    assert fails == []


def test_verify_month_ignores_a_column_it_has_no_convention_for():
    p = _monthly_profile()
    days = [{"day": d, "tmean": 20.0, "tmax": 30.0, "tmin": 10.0, "precip": 1.0} for d in range(1, 11)]
    fails = p.verify_month(days, {"tmean": 20.0, "tmax": 30.0, "tmin": 10.0, "precip": 10.0,
                                  "not_a_column": 12345.0})
    assert fails == []


# --- a maximum must not fall below its own minimum -------------------------
# The 1883 thermometer page prints a maximum and a minimum per thermometer
# (in-shelter, unsheltered). Both are checked against their printed
# oscillation, but that check SKIPS when the oscillation cell is blank - and
# two rows reached `checks_pass` with sansabri_max 7.5 and sansabri_min 39.2,
# which is impossible for any two readings of one instrument.

def _pair_profile():
    return Profile(id="t", name="t",
                   columns=[Column(key="day", label="D", kind="day"),
                            Column(key="tmax", label="Max", unit="C", range=(-40, 60)),
                            Column(key="tmin", label="Min", unit="C", range=(-40, 60))],
                   checks=[{"kind": "atleast", "result": "tmax", "of": ["tmin"]}])


def test_atleast_accepts_a_max_above_its_minimum():
    p = _pair_profile()
    assert p.verify({"day": 1, "tmax": 30.0, "tmin": 20.0}) == []


def test_atleast_flags_a_max_below_its_minimum():
    p = _pair_profile()
    fails = p.verify({"day": 1, "tmax": 7.5, "tmin": 39.2})
    assert len(fails) == 1
    assert "tmax" in fails[0] and "tmin" in fails[0]


def test_atleast_accepts_equal_values():
    """Two readings of one instrument can genuinely coincide."""
    p = _pair_profile()
    assert p.verify({"day": 1, "tmax": 20.0, "tmin": 20.0}) == []


def test_atleast_is_skipped_when_either_cell_is_missing():
    p = _pair_profile()
    assert p.verify({"day": 1, "tmax": None, "tmin": 20.0}) == []
    assert p.verify({"day": 1, "tmax": 30.0, "tmin": None}) == []


def test_rescore_resolves_a_dittoe_day_instead_of_publishing_the_mark() -> None:
    """Corumba prints the day once and dittos the second reading of it, so half
    that station's rows published `day: "»"` - a consumer could not say which
    day they were. `resolve_dittos` existed and was tested but was never wired
    into the production path. Found by reading the verification app, not code.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from g4_rescore import resolve_page_days
    p = load("corumba-1889")
    page = [
        {"values": {"day": 1, "hour": 10.0}},
        {"values": {"day": "»", "hour": 4.0}},      # same day, second reading
        {"values": {"day": 2, "hour": 10.0}},
        {"values": {"day": "»", "hour": 4.0}},
    ]
    got = resolve_page_days(p, page, "day")
    assert got == {1: 1, 3: 2}
    # the hour column carries its own value on both readings - nothing to
    # resolve there, and the helper must report only the rows that changed
    assert 0 not in got and 2 not in got


def test_rescore_reports_nothing_when_a_page_has_no_ditto() -> None:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from g4_rescore import resolve_page_days
    p = load("corumba-1889")
    page = [{"values": {"day": 1, "hour": 10.0}}, {"values": {"day": 2, "hour": 10.0}}]
    assert resolve_page_days(p, page, "day") == {}


def test_the_dekadal_summary_is_TWO_profiles_not_one() -> None:
    """The Revista's monthly-by-decade summary is two stacked tables on one page
    that share the decade row labels - but they are separate tables, and no
    contiguous crop contains one row of both. So it is two profiles, not one
    50-column profile: that was the first attempt and it cannot be cropped."""
    upper, lower = load("revista-mensal-baroterm"), load("revista-mensal-estado")
    # barometro(7) + termometro(7) + psychrometro(2) + hygrometro(1) + label.
    # This said 17 and omitted the Saussure hygrometer, which is the last column
    # the page prints - the same miscount the profile carried, which is why no
    # page in doc 5 ever matched it by cell count. Checked against the header of
    # doc 5 page 437.
    assert upper.n_cells == 18
    assert lower.n_cells == 34      # estado(8) + 16 wind directions + force(9) + label
    for p in (upper, lower):
        assert p.expected_rows("1882-10") == 4      # 1a, 2a, 3a, Mez - NOT days
        assert p.rows_per_page == "fixed:4"


def test_the_upper_block_round_trips() -> None:
    p = load("revista-mensal-baroterm")
    vals = {c.key: None for c in p.columns}
    vals.update(decada="2a", baro_media=762.13, baro_data_max="13-15",
                t_media=18.60, t_maxima=20.50, humidade=85.47, tensao=13.4)
    back, problems = p.parse(p.target(vals))
    assert problems == []
    assert back["baro_media"] == 762.13 and back["t_media"] == 18.60
    assert back["humidade"] == 85.47 and back["tensao"] == 13.4
    # the extreme dates are TEXT: the page prints a day or a RANGE ("13-15"),
    # which the first version of this profile declared numeric and dropped
    assert back["baro_data_max"] == "13-15"


def test_the_lower_block_round_trips() -> None:
    p = load("revista-mensal-estado")
    vals = {c.key: None for c in p.columns}
    vals.update(decada="Mez", dias_limpos=7, dias_nublados=25, dias_chuva=9,
                chuva=96.8, vento_N=2, vento_NO=2, forca_moderado=26, forca_calma=1)
    back, problems = p.parse(p.target(vals))
    assert problems == []
    assert back["dias_limpos"] == 7 and back["dias_chuva"] == 9 and back["chuva"] == 96.8
    assert back["vento_N"] == 2 and back["forca_moderado"] == 26


def test_the_workbench_passes_the_profiles_declared_geometry_to_the_locator(monkeypatch):
    """A profile's geometry fields were silently ignored by the review UI.

    `page_state` called `locate_day_rows(image, want)` with no `**p.geometry()`,
    so probe_x_frac, table_x_frac, table_y_frac and row_bands never reached the
    detector there - the Oxford-era table_x_frac fix included. On a fixed-row
    form that meant the UI showed the detector's wrong guess instead of the rows
    the profile declares.
    """
    import wrb.workbench as wb
    import wrb.rows as rows_mod
    seen = {}

    def spy(image, want, **kw):
        seen.update(kw)
        return rows_mod.RowLocation([], [], {}, pitch=1.0, ink_threshold=0, skew_deg=0.0,
                                    rules=[], day_col=(0, 0), chain=[], ok=False, reason="spy")

    monkeypatch.setattr(wb, "locate_day_rows", spy)
    monkeypatch.setattr(wb, "page_image_path", lambda root, doc, page: _FakePath())
    monkeypatch.setattr(wb.Image, "open", _fake_image)
    wb._pages.clear()
    wb.page_state("revista-mensal-baroterm", "5", 451, "1882-10")
    assert seen.get("row_bands"), f"row_bands did not reach the locator: {seen}"
    assert seen.get("table_y_frac"), f"table_y_frac did not reach the locator: {seen}"


class _FakePath:
    def exists(self) -> bool:
        return True


def _fake_image(*a, **k):
    from PIL import Image as _I
    return _I.new("RGB", (100, 100), (255, 255, 255))


# --- a month row whose cell order was lost ----------------------------------

def _simultaneas():
    from wrb import profile as prof
    return prof.load("revista-resumo-simultaneas")


DEKADS = [
    {"baro": 697.68, "t_secco": 22.84, "t_maxima": 25.13, "t_minima": 17.97, "humidade": 80.1},
    {"baro": 699.12, "t_secco": 24.04, "t_maxima": 26.90, "t_minima": 18.52, "humidade": 77.3},
    {"baro": 697.71, "t_secco": 22.02, "t_maxima": 25.60, "t_minima": 18.50, "humidade": 82.3},
]


def test_a_reversed_month_row_still_checks_out():
    """The numbers are all there and correct; only the order was lost."""
    p = _simultaneas()
    p.monthly["tolerance"] = {"baro": 0.6, "t_secco": 0.3, "t_maxima": 0.3,
                              "t_minima": 0.5, "humidade": 0.8}
    printed = [79.9, 19.67, 25.88, 23.03, 698.50]          # reversed
    fails = p.verify_month_unordered(DEKADS, printed)
    assert [f.split(":")[0] for f in fails] == ["t_minima"]


def test_a_month_row_from_another_block_does_not_match():
    p = _simultaneas()
    p.monthly["tolerance"] = {"baro": 0.6, "t_secco": 0.3, "t_maxima": 0.3,
                              "t_minima": 0.5, "humidade": 0.8}
    printed = [763.64, 26.9, 26.9, 21.1, 80.9]             # Maceió's, not São Paulo's
    assert len(p.verify_month_unordered(DEKADS, printed)) >= 3


def test_each_printed_number_is_spent_once():
    """Two columns cannot both claim the same figure."""
    p = _simultaneas()
    p.monthly["tolerance"] = {k: 50.0 for k in
                              ("baro", "t_secco", "t_maxima", "t_minima", "humidade")}
    assert p.verify_month_unordered(DEKADS, [698.5]) != []


# --- Radcliffe: a table whose rows are years, not days -------------------
# Every convention below was added for the Oxford tables and each is gated on
# the profile declaring it, so no Brazilian layout can be affected. The tests
# assert both halves: that the repair fires where it should, and that it stays
# out of the way where it should not.

def test_index_range_defaults_to_days_but_follows_the_profile():
    day = prof.load("rio-1883-thermo")
    assert day.index_range == (1.0, 31.0)
    assert day.index_kind == "day_of_month"
    year = prof.load("radcliffe-drybulb-1855-1879")
    assert year.index_range == (1855.0, 1879.0)
    assert year.index_kind == "year"


def test_year_split_into_two_tokens_is_rejoined():
    """The old-style `1856` comes back as `18 | 56`, one cell too many."""
    p = prof.load("radcliffe-drybulb-1855-1879")
    v, problems = p.parse("18 | 56 | 39.7 | 42.0 | 38.8 | 46.7 | 48.7 | 57.6 | 60.9 "
                          "| 62.7 | 54.4 | 50.3 | 41.7 | 40.4 | 48.66")
    assert v["year"] == 1856
    assert v["jan"] == 39.7 and v["dec"] == 40.4
    assert any("two tokens" in x for x in problems)
    # and the page's own arithmetic closes, which is the real proof
    assert p.verify(v) == []
    # recorded, but not a reason to distrust the row
    assert all(prof.is_soft_problem(x) for x in problems)


def test_a_legible_year_is_never_rejoined():
    p = prof.load("radcliffe-drybulb-1855-1879")
    v, problems = p.parse("1863 | 22.365 | 1.08 | 2.01 | 2.961 | 2.721 | 2.648 | 2.657 "
                          "| 0.657 | 0.941 | 1.414 | 0.672 | 0.76 | 3.411 | 40.886")
    assert v["year"] == 1863
    assert not any("two tokens" in x for x in problems)


def test_day_layouts_are_untouched_by_the_index_repairs():
    """The repairs need a declared index range; no daily profile has one."""
    for pid in prof.available():
        p = prof.load(pid)
        if p.index_kind != "day_of_month":
            continue
        col = next((c for c in p.columns if c.kind == "day"), None)
        assert col is None or col.range is None, f"{pid} would now be re-segmented"


def test_raised_decimal_point_parses():
    """British scientific printing sets the decimal separator high."""
    p = prof.load("radcliffe-1855-1879")
    v, problems = p.parse("1855 | 29·969 | 29·563 | 29·498 | 29·893 | 29·642 "
                          "| 29·801 | 29·698 | 29·803 | 29·926 | 29·456 "
                          "| 29·819 | 29·687 | 29·730")
    assert problems == []
    assert v["jan"] == 29.969 and v["yearly_mean"] == 29.73


def test_elided_integer_part_carries_down_the_column():
    """Radcliffe prints the integer part only when it changes, per COLUMN.

    The witness is the page's own Yearly Mean, which equals the mean of the
    twelve restored months and does not under any other reading.
    """
    p = prof.load("radcliffe-1855-1879")
    raws = [
        "1855 | 29·969 | 29·563 | 29·498 | 29·893 | 29·642 | 29·801 | 29·698 "
        "| 29·803 | 29·926 | 29·456 | 29·819 | 29·687 | 29·730",
        "1856 | ·404 | ·840 | ·972 | ·554 | ·621 | ·831 | ·784 | ·691 | ·600 "
        "| ·936 | ·876 | ·584 | ·724",
        "1857 | ·589 | ·891 | ·651 | ·583 | ·732 | ·790 | ·792 | ·786 | ·724 "
        "| ·640 | ·898 | 30·100 | ·765",
    ]
    rows = p.resolve_column_carry([p.parse(t)[0] for t in raws])
    assert rows[1]["jan"] == 29.404          # carried from 29.969 above it
    assert rows[2]["dec"] == 30.1            # printed its own, so it resets
    for r in rows:
        assert p.verify(r) == [], r
    # the carry runs DOWN the column: December's 30 does not reach the mean
    assert rows[2]["yearly_mean"] == 29.765


def test_a_dropped_raised_point_is_restored_into_the_declared_range():
    """When the reader loses the point entirely, `404` can only be 29.404."""
    p = prof.load("radcliffe-1855-1879")
    first = p.parse("1855 | 29·969 | 29·563 | 29·498 | 29·893 | 29·642 | 29·801 "
                    "| 29·698 | 29·803 | 29·926 | 29·456 | 29·819 | 29·687 | 29·730")[0]
    second = p.parse("1856 | 404 | 840 | 972 | 554 | 621 | 831 | 784 | 691 | 600 "
                     "| 936 | 876 | 584 | 724")[0]
    rows = p.resolve_column_carry([first, second])
    assert rows[1]["jan"] == 29.404
    assert p.verify(rows[1]) == []


def test_an_unreadable_index_is_filled_only_when_the_page_agrees():
    p = prof.load("radcliffe-drybulb-1855-1879")
    rows = [{"year": 1855}, {"year": 18}, {"year": 1857}, {"year": 1858}, {"year": 18}]
    assert p.resolve_index_sequence(rows) == {1: 1856, 4: 1859}
    # witnesses that disagree about the offset fill nothing at all
    disagree = [{"year": 1855}, {"year": 18}, {"year": 1860}, {"year": 1858}]
    assert p.resolve_index_sequence(disagree) == {}
    # and fewer than three witnesses is not a page speaking, it is a guess
    assert p.resolve_index_sequence([{"year": 1855}, {"year": 18}]) == {}


def test_index_fill_never_runs_on_a_daily_layout():
    p = prof.load("rio-1883-thermo")
    assert p.resolve_index_sequence([{"dates": d} for d in (1, 2, None, 4, 5)]) == {}


def test_an_empty_cell_at_a_printed_rule_is_dropped():
    """Table I double-rules before Yearly Mean; the reader takes it for a column."""
    p = prof.load("radcliffe-1855-1879")
    v, problems = p.parse("1858 | 30·108 | ·787 | ·715 | ·719 | ·727 | ·864 | ·733 "
                          "| ·769 | ·801 | ·792 | ·688 | null | 29·721 | ·785")
    assert any("rules a line" in x for x in problems)
    assert v["dec"] == 29.721 and v["yearly_mean"] == 0.785
    assert all(prof.is_soft_problem(x) for x in problems)


# --- a blank cell that means zero ---------------------------------------

def test_a_blank_is_a_gap_by_default_and_the_column_is_skipped():
    """A mean over a month with holes cannot match, and failing it would be
    punishing absence of evidence. Unchanged behaviour."""
    p = prof.load("revista-rio-1886")
    rows = [{"precip": 1.0}, {"precip": None}, {"precip": 2.0}]
    assert p.verify_month(rows, {"precip": 99.0}) == []


def test_a_column_may_declare_that_blank_means_zero():
    """Prague prints an ellipsis for a dry day, so 23 of 31 cells are blank.
    Skipping the column disabled the only check that could see it."""
    p = prof.load("prague-klementinum-1903")
    assert "niederschlag" in (p.monthly.get("blank_is_zero") or [])
    rows = [{"niederschlag": v} for v in (1.0, None, None, 0.6, None)]
    assert p.verify_month(rows, {"niederschlag": 1.6}) == []
    fails = p.verify_month(rows, {"niederschlag": 12.8})
    assert fails and "sum of the day rows" in fails[0]


def test_the_printed_sum_catches_a_displaced_cell():
    """The point of the convention: reading a blank as 0 is only safe because
    a number that was dropped or slid into the wrong column stops the page's
    own sum closing. This is the real 1903-01 failure - the Tagesmittel slid
    into the rainfall slot on two rows."""
    p = prof.load("prague-klementinum-1903")
    good = [{"niederschlag": v} for v in (None, 1.0, 0.6, 0.2, 4.9, None, 3.8, 0.1, 1.1, 1.1)]
    assert p.verify_month(good, {"niederschlag": 12.8}) == []
    displaced = [dict(r) for r in good]
    displaced[0]["niederschlag"] = 4.0        # a Tagesmittel where a blank belongs
    assert p.verify_month(displaced, {"niederschlag": 12.8})
