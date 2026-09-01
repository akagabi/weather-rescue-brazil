import json
from pathlib import Path

from wrb.gold import Sheet, Row
from wrb.metrics import score

GOLD_KEYS = [
    "pressure", "pressure_max", "pressure_min", "tmean", "tmax", "tmin",
    "vapor", "humidity", "wind_force", "cloudiness", "precip",
    "evap_sol", "evap_sombra", "ozone",
]


def sheet(cells_list):
    rows = [Row(date=f"1870-05-{i+1:02d}", cells=c, flags={}) for i, c in enumerate(cells_list)]
    return Sheet(source="hdbn", bib="x", page=1, station="s", period="1870-05",
                 columns=["tmax", "tmin"], rows=rows)


def test_perfect_scores_one():
    g = sheet([{"tmax": 20.0, "tmin": 10.0}])
    assert score(g, g)["cell_acc"] == 1.0


def test_row_shift_flagged_as_structural():
    g = sheet([{"tmax": 20.0, "tmin": 10.0}, {"tmax": 22.0, "tmin": 12.0}])
    p = sheet([{"tmax": 22.0, "tmin": 12.0}, {"tmax": 20.0, "tmin": 10.0}])  # swapped rows
    s = score(p, g)
    assert s["cell_acc"] < 1.0 and s["structural_err_rate"] > 0


def test_within_tolerance_counts_as_match():
    g = sheet([{"tmax": 20.0, "tmin": 10.0}])
    p = sheet([{"tmax": 20.04, "tmin": 9.96}])
    s = score(p, g)
    assert s["cell_acc"] == 1.0


def test_both_none_is_a_match_one_none_is_a_miss():
    g = sheet([{"tmax": None, "tmin": 10.0}])
    p_match = sheet([{"tmax": None, "tmin": 10.0}])
    p_miss = sheet([{"tmax": 5.0, "tmin": 10.0}])
    assert score(p_match, g)["cell_acc"] == 1.0
    assert score(p_miss, g)["cell_acc"] < 1.0


def test_missing_date_in_pred_is_structural_error():
    g = sheet([{"tmax": 20.0, "tmin": 10.0}, {"tmax": 22.0, "tmin": 12.0}])
    rows = [Row(date="1870-05-01", cells={"tmax": 20.0, "tmin": 10.0}, flags={})]
    p = Sheet(source="hdbn", bib="x", page=1, station="s", period="1870-05",
              columns=["tmax", "tmin"], rows=rows)  # second date missing entirely
    s = score(p, g)
    assert s["structural_err_rate"] > 0


def test_flagged_wrong_cell_counts_toward_flagged_recall():
    """Uses the gold set's REAL cell keys (see gold/SELECTION.md column legend).
    A wrong cell that the model itself flagged 'uncertain' on that column
    should be counted as recalled by flagged_recall; an unflagged wrong cell
    should not."""
    g_row = Row(date="1886-01-01", cells={k: 1.0 for k in GOLD_KEYS}, flags={"wind_dir": "Variavel"})
    gold = Sheet(source="docvirt", bib="14", page=41, station="s", period="1886-01",
                 columns=GOLD_KEYS, rows=[g_row])

    pred_cells = dict(g_row.cells)
    pred_cells["tmax"] = 99.0  # wrong, flagged uncertain
    pred_cells["tmin"] = 99.0  # wrong, NOT flagged
    p_row = Row(date="1886-01-01", cells=pred_cells,
                flags={"wind_dir": "Variavel", "tmax": "uncertain"})
    pred = Sheet(source="docvirt", bib="14", page=41, station="s", period="1886-01",
                 columns=GOLD_KEYS, rows=[p_row])

    s = score(pred, gold)
    # 2 wrong cells, 1 of them flagged uncertain -> recall == 0.5
    assert s["flagged_recall"] == 0.5


def test_scores_against_real_frozen_gold_sheet():
    path = Path(__file__).parent.parent / "gold" / "sheets" / "14_41.json"
    gold = Sheet(**json.loads(path.read_text()))
    s = score(gold, gold)
    assert s["cell_acc"] == 1.0
    assert s["structural_err_rate"] == 0.0
    assert s["n_cells"] == len(gold.columns) * len(gold.rows)
