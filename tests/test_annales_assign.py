"""The cell-count assignment's two collisions, and the bug in one of them."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _mod():
    sys.argv = ["g4_annales_assign"]
    spec = importlib.util.spec_from_file_location(
        "annales_assign", ROOT / "scripts" / "g4_annales_assign.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def assign(cells: int, row: str) -> str | None:
    """The profile decision, lifted out of the model loop."""
    m = _mod()
    profile = m.BY_CELLS.get(cells)
    if profile and len(m.COMPASS.findall(row)) >= 3:
        if cells == 15:
            pass
        elif cells == 13:
            profile = "rio-1883-vento"
        else:
            profile = None
    return profile


WIND_ROW = "1 | NE | 2 | SW | 3 | N | 1 | SE | 2 | E | 1 | NW | 2 | S | 1"
TEMP_ROW = "1 | 27.9 | 22.0 | 5.9 | 36.4 | 21.0 | 15.4 | 3.3 | 1.2 | 24.1 | 22.8 | 23.0 | 21.7"


def test_a_fifteen_cell_wind_page_is_wind():
    """It went `15 celulas -> None`: rejected for looking like wind. Doc 8 page
    19 is the first page of the backlog and it was the first casualty."""
    assert assign(15, WIND_ROW) == "rio-1883-vento"


def test_a_thirteen_cell_page_full_of_rhumbs_is_wind_not_temperature():
    """13 collides between the thermometer and the hourly wind table."""
    assert assign(13, WIND_ROW) == "rio-1883-vento"


def test_a_thirteen_cell_page_of_numbers_stays_the_thermometer():
    assert assign(13, TEMP_ROW) == "rio-1883-thermo"


def test_a_barometer_page_full_of_rhumbs_is_neither():
    """Ten cells is the barometer; rhumbs there mean the count is wrong."""
    assert assign(10, WIND_ROW) is None


def test_the_counts_that_have_no_collision():
    assert assign(10, TEMP_ROW) == "rio-1883-barometre"
    assert assign(9, TEMP_ROW) == "rio-1883-vapeur"
    assert assign(99, TEMP_ROW) is None


def test_cells_counts_the_cells_not_the_pipes():
    """The first pass counted len(split("|")) and every count came out 2 high,
    so nothing matched and 236 of 250 pages were left without a profile."""
    m = _mod()
    assert m.n_cells("| 1 | 27.9 | 22.0 |") == 3
    assert m.n_cells("1 | 27.9 | 22.0") == 3
