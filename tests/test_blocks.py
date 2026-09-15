"""A sheet with four stations on it, and the rule about inherited stations."""
import pytest

from wrb.blocks import blocks_for_page, resolve_stations

# docId 16 page 41: Sao Paulo, Bahia, Ouro Preto, Santa Cruz, top to bottom.
DECLARED = [
    {"header": [0.205, 0.225], "rows": [[0.321, 0.339], [0.340, 0.358],
                                        [0.359, 0.377], [0.384, 0.402]]},
    {"header": [0.440, 0.460], "rows": [[0.470, 0.488], [0.489, 0.507],
                                        [0.508, 0.526], [0.533, 0.551]]},
    {"header": [0.590, 0.610], "rows": [[0.620, 0.638], [0.639, 0.657],
                                        [0.658, 0.676], [0.683, 0.701]]},
    {"header": [0.735, 0.755], "rows": [[0.765, 0.783], [0.784, 0.802],
                                        [0.803, 0.821], [0.828, 0.846]]},
]
HEADERS = [
    "Estação, S. Paulo; Observador, Alberto Loefgren; Latitude, 23°36' S; "
    "Longitude, 3°28' W; Hora local, 8h29m27s; Alt. do Bar. 735m42",
    "Estação, Bahia (Capital); Observador, Dr. R. A. Pereira Guimarães; "
    "Latitude, S 12°58'27''; Long., E 4°37'40''; Hora local, 9h25m30s; Alt. do Bar. 64m",
    "Estação, Ouro Preto; Observador, Eulalio F. Pereira; Latitude, 20°28'5; "
    "Hora local, 9h; Alt. do Bar., 1145m",
    "Estação, Santa Cruz; Observador, J. N. C. Lousada; Latitude, 22°,56'; "
    "Longitude, 2m W; Hora local, 9h,9m; Alt. do Bar. 26m",
]


def test_four_blocks_of_four_rows():
    bs = blocks_for_page(DECLARED, 2461, 1630, (0.125, 0.318))
    assert len(bs) == 4
    assert all(len(b.row_boxes) == 4 for b in bs)
    assert not any(b.inherits_station for b in bs)


def test_boxes_share_the_band_and_stay_on_the_page():
    bs = blocks_for_page(DECLARED, 2461, 1630, (0.125, 0.318))
    for b in bs:
        for x0, y0, x1, y1 in b.row_boxes + [b.header_box]:
            assert 0 <= x0 < x1 <= 2461 and 0 <= y0 < y1 <= 1630
            assert (x0, x1) == (b.row_boxes[0][0], b.row_boxes[0][2])


def test_each_block_keeps_its_own_station():
    bs = blocks_for_page(DECLARED, 2461, 1630, (0.125, 0.318))
    st = resolve_stations(HEADERS)
    assert [s["station"] for s in st] == [
        "S. Paulo", "Bahia (Capital)", "Ouro Preto", "Santa Cruz"]
    assert all(s["station_source"] == "linha impressa do bloco" for s in st)
    assert st[0]["lon_deg"] == pytest.approx(-46.64, abs=0.01)


def test_a_block_with_no_header_inherits_the_one_above_and_says_so():
    """docId 15 page 142: the second block is Maceio's July under Maceio's June."""
    declared = [DECLARED[0], {"header": None, "rows": DECLARED[1]["rows"]}]
    bs = blocks_for_page(declared, 2461, 1630, (0.125, 0.318))
    st = resolve_stations([HEADERS[0], None])
    assert bs[1].inherits_station
    assert st[1]["station"] == "S. Paulo"
    assert st[1]["station_source"] == "herdada do bloco acima"
    assert st[1]["lon_deg"] == st[0]["lon_deg"]


def test_a_headerless_first_block_gets_no_station():
    """Nothing above it to inherit from - a gap to report, not one to fill."""
    bs = blocks_for_page([{"header": None, "rows": DECLARED[0]["rows"]}],
                         2461, 1630, (0.125, 0.318))
    st = resolve_stations([None])
    assert st[0]["station"] is None
    assert "sem bloco acima" in st[0]["station_source"]


def test_the_page_caption_never_supplies_the_station():
    """Three of four blocks on this form would get the wrong one."""
    bs = blocks_for_page(DECLARED, 2461, 1630, (0.125, 0.318))
    st = resolve_stations(HEADERS)
    assert len({s["station"] for s in st}) == 4


# --- the printed label is what decides a row --------------------------------

from wrb.blocks import blocks_from_labels, row_label  # noqa: E402


def test_dekad_labels_the_reader_actually_returns():
    for raw in ["1a | 697.68 | 22.84", "1ª | 1 | 2", "1º | 1 | 2", "1 | 1 | 2"]:
        assert row_label(raw) == "1", raw
    assert row_label("2a | 699.12") == "2"
    assert row_label("3a | 697.71") == "3"


def test_the_month_row_however_the_compositor_set_it():
    for raw in ["Mez | 698.50", "Mez. | 1", "Mez.... | 698.5 | 23.03", "Mês | 1"]:
        assert row_label(raw) == "Mez", raw


def test_anything_else_is_not_a_data_row():
    for raw in ["Decadas | Barometro", "VENTOS (numero de vezes)", "", "| 1 | 2",
                "Chuva nos dias 2, 9, 10", "1145m | 1"]:
        assert row_label(raw) is None, raw


def test_blocks_are_complete_or_absent():
    labels = ["1", "2", "3", "Mez", "1", "2", "3", "Mez"]
    assert blocks_from_labels(labels) == [[0, 1, 2, 3], [4, 5, 6, 7]]


def test_half_a_block_is_worse_than_none():
    """Its Mez would be checked against the wrong three dekads."""
    assert blocks_from_labels(["1", "2", "3", "1", "2", "3", "Mez"]) == [[3, 4, 5, 6]]
    assert blocks_from_labels(["1", "2", "Mez"]) == []
    assert blocks_from_labels(["2", "3", "Mez"]) == []


def test_stray_rows_between_blocks_do_not_join_them():
    assert blocks_from_labels(["1", "2", "3", "Mez", "1", "2"]) == [[0, 1, 2, 3]]


# --- the band is a fraction of the table, not of the page -------------------

from wrb.blocks import band_from_rules  # noqa: E402


class _FakeRules:
    """An image whose vertical rules are wherever the test says they are."""
    def __init__(self, width, rules):
        self.width, self._rules = width, rules

    def convert(self, _mode):
        return self


def _patched(monkeypatch, width, rules):
    import wrb.rows as rows
    monkeypatch.setattr(rows, "ink_threshold", lambda g: 128)
    monkeypatch.setattr(rows, "vertical_rules",
                        lambda g, thr: [round(r * width) for r in rules])
    return _FakeRules(width, rules)


def test_the_same_span_gives_different_pixels_on_differently_margined_scans():
    """docId 16 p41's table starts at 0.133 of the width, 15 p126's at 0.102."""
    import pytest as _pt
    mp = _pt.MonkeyPatch()
    try:
        a = band_from_rules(_patched(mp, 2461, [0.1329, 0.8663]), (0.0, 0.253))
        b = band_from_rules(_patched(mp, 2468, [0.1021, 0.8938]), (0.0, 0.253))
    finally:
        mp.undo()
    assert a[0] == pytest.approx(0.1229, abs=1e-3)
    assert b[0] == pytest.approx(0.0921, abs=1e-3)
    # a band fixed on the first page would start 0.031 into the second's table,
    # which is where its `Decadas` column is
    assert a[0] - b[0] > 0.025


def test_a_page_whose_rules_do_not_bound_a_table_is_refused():
    """Not read at a guessed offset - docId 15 p199 finds only one edge."""
    import pytest as _pt
    mp = _pt.MonkeyPatch()
    try:
        assert band_from_rules(_patched(mp, 2468, [0.866, 0.8684]), (0.0, 0.253)) is None
        assert band_from_rules(_patched(mp, 2468, [0.4]), (0.0, 0.253)) is None
    finally:
        mp.undo()


# --- the same row detected twice --------------------------------------------

from wrb.blocks import dedupe_labels  # noqa: E402


def test_a_row_detected_twice_is_one_row():
    """Left alone this reads 1,1,2,2,3,3,Mez and the whole block is discarded."""
    labels = ["1", "1", "2", "2", "3", "3", "Mez"]
    kept = dedupe_labels(labels)
    assert [labels[i] for i in kept] == ["1", "2", "3", "Mez"]
    assert blocks_from_labels([labels[i] for i in kept]) == [[0, 1, 2, 3]]


def test_unlabelled_candidates_drop_out():
    labels = [None, "1", None, "2", "3", None, "Mez", None]
    assert [labels[i] for i in dedupe_labels(labels)] == ["1", "2", "3", "Mez"]


def test_the_fuller_read_wins_a_duplicate():
    labels = ["1", "1"]
    cells = {0: 2, 1: 6}
    assert dedupe_labels(labels, score=cells.get) == [1]
    assert dedupe_labels(labels, score={0: 6, 1: 2}.get) == [0]


def test_two_blocks_are_not_collapsed_into_one():
    """A Mez is followed by a 1, never by another Mez."""
    labels = ["1", "2", "3", "Mez", "1", "2", "3", "Mez"]
    assert [labels[i] for i in dedupe_labels(labels)] == labels
