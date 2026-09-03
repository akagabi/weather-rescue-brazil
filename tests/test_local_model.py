"""G4.2 local extractor: target format round-trip, tolerant parsing, and
the end-to-end plumbing (rows -> mocked reader -> G2BTable -> barometer
reconstruction -> Sheet) on the synthetic page from test_rows. No model."""

import io

import pytest
from PIL import Image

from tests.test_rows import _draw_page
from wrb.dataset import COLUMNS
from wrb.local_model import LocalExtractor, RowLocationError, parse_row_target, row_target
from wrb.metrics import score


def test_row_target_round_trip():
    cells = {c: None for c in COLUMNS}
    cells.update(pressure=54.44, pressure_max=56.18, pressure_min=52.6, tmean=24.1, tmax=27.3,
                 tmin=22.2, vapor=18.7, humidity=83.9, wind_force=2.4, cloudiness=8.0, precip=0.5,
                 evap_sol=2.7, evap_sombra=1.7, ozone=3.0)
    text = row_target(cells, {"wind_dir": "O. variavel"})
    assert text == ("54.44 | 56.18 | 52.6 | 24.1 | 27.3 | 22.2 | 18.7 | 83.9 | 2.4 | 8 | 0.5 | 2.7 | 1.7 | 3"
                    " | dir=O. variavel")
    back, flags, problems = parse_row_target(text)
    assert back == cells
    assert flags == {"wind_dir": "O. variavel"}
    assert problems == []


def test_parse_is_tolerant():
    cells, flags, problems = parse_row_target("1 | 2 | x | null | 5")
    assert cells["pressure"] == 1.0 and cells["pressure_min"] is None and cells["tmean"] is None
    assert cells["ozone"] is None
    assert any("tokens" in p for p in problems) and any("unparsable" in p for p in problems)
    cells, _, problems = parse_row_target(" | ".join(["1"] * 16))
    assert cells["ozone"] == 1.0 and any("extra" in p for p in problems)


class ScriptedReader:
    """Returns the gold row text for whichever row index is asked, in order."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def read_row(self, crop: Image.Image) -> str:
        assert crop.height < crop.width  # a row band, not a page
        t = self.texts[self.calls]
        self.calls += 1
        return t


def _sheet_rows(day_count: int):
    rows = []
    for d in range(1, day_count + 1):
        cells = {c: None for c in COLUMNS}
        cells.update(pressure=50 + d * 0.11, pressure_max=51 + d * 0.11, pressure_min=49 + d * 0.11,
                     tmean=20.0 + d * 0.1, tmax=25.0, tmin=18.0, vapor=15.0, humidity=80.0,
                     wind_force=3.0, cloudiness=5.0, precip=None, evap_sol=2.0, evap_sombra=1.0, ozone=2.0)
        rows.append(cells)
    return rows


def test_end_to_end_on_synthetic_page():
    im, _ = _draw_page(31, dec_rows=True)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    gold_rows = _sheet_rows(31)
    reader = ScriptedReader(row_target(c, {"wind_dir": "SSE"}) for c in gold_rows)
    ex = LocalExtractor(reader)
    sheet = ex.extract(buf.getvalue(), 31, year=1886, month=1, source="synthetic", bib="t", page=1,
                       station="test")
    assert reader.calls == 31
    assert [r.date for r in sheet.rows][:2] == ["1886-01-01", "1886-01-02"]
    # barometer thousands restored (as the API path does), other cells verbatim
    assert sheet.rows[0].cells["pressure"] == pytest.approx(750.11)
    assert sheet.rows[0].cells["tmean"] == pytest.approx(20.1)
    assert sheet.rows[0].flags["wind_dir"] == "SSE"
    # scores as a perfect sheet against a gold built from the same rows
    from wrb.gold import Row, Sheet
    gold = Sheet(source="synthetic", bib="t", page=1, station="test", period="1886-01", columns=list(COLUMNS),
                 rows=[Row(date=f"1886-01-{d:02d}", cells={**c, "pressure": c["pressure"] + 700,
                                                             "pressure_max": c["pressure_max"] + 700,
                                                             "pressure_min": c["pressure_min"] + 700})
                       for d, c in enumerate(gold_rows, start=1)])
    s = score(sheet, gold)
    assert s["cell_acc"] == 1.0 and s["structural_err_rate"] == 0.0


def test_refuses_when_rows_not_located():
    im, _ = _draw_page(31, dec_rows=False)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    with pytest.raises(RowLocationError):
        LocalExtractor(ScriptedReader([])).extract_table(buf.getvalue(), 45)
