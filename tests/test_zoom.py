"""Multi-resolution zoom cross-check (G3 Task 1b): crop geometry and
border detection are pure PIL (no network); the zoom-reread call is
respx-mocked, same style as tests/test_vlm_g2b.py; `reconcile` is a pure
dict diff. No real API calls in this file - see wrb/zoom.py's module
docstring for the design and docs/superpowers/sdd/.../task-1b-report.md
for the live-verified paid probe (Task 1b Step 2)."""

import io
import json

import httpx
import pytest
import respx
from PIL import Image, ImageDraw

from wrb.costs import CapExceeded, CostMeter
from wrb.vlm import ENDPOINTS, ExtractionParseError
from wrb.zoom import (
    _parse_zoom_row_response,
    crop_row_bands,
    detect_table_borders,
    reconcile,
    row_band_geometry,
    zoom_read_row,
    zoom_reread_sheet,
)

GEMINI_PROVIDER = "gemini-flash-full"


# --- 1. Crop geometry (pure) --------------------------------------------------


def test_row_band_geometry_produces_n_bands_in_day_order():
    boxes = row_band_geometry((1000, 2000), day_count=31, border_top=500, border_bottom=1600)
    assert len(boxes) == 31
    # Monotonically increasing y0 (day order, top to bottom), all within bounds.
    y0s = [b[1] for b in boxes]
    assert y0s == sorted(y0s)
    for x0, y0, x1, y1 in boxes:
        assert 0 <= x0 < x1 <= 1000
        assert 0 <= y0 < y1 <= 2000


def test_row_band_geometry_varies_with_day_count():
    """A shorter month (28 days) packs the same ruled interval into fewer,
    taller-pitched bands than a 31-day month."""
    boxes28 = row_band_geometry((1000, 2000), day_count=28, border_top=500, border_bottom=1600)
    boxes31 = row_band_geometry((1000, 2000), day_count=31, border_top=500, border_bottom=1600)
    assert len(boxes28) == 28
    assert len(boxes31) == 31
    pitch28 = boxes28[1][1] - boxes28[0][1]
    pitch31 = boxes31[1][1] - boxes31[0][1]
    assert pitch28 > pitch31 > 0


def test_row_band_geometry_rejects_zero_day_count():
    with pytest.raises(ValueError):
        row_band_geometry((1000, 2000), day_count=0, border_top=500, border_bottom=1600)


def _synthetic_table_page(width=1000, height=2519, border_top=665, border_bottom=1597):
    """A blank page with two solid horizontal rules drawn across the
    row-detector's column band (_ROW_COL_X_FRAC of the page width) at known
    y-positions - stands in for the two ruled lines bracketing a real
    table's day rows (see wrb/zoom.py's module docstring)."""
    img = Image.new("RGB", (width, height), color=(230, 225, 190))  # light cream, like the real scans
    draw = ImageDraw.Draw(img)
    x0, x1 = round(0.1552 * width), round(0.2090 * width)
    draw.line([(x0, border_top), (x1, border_top)], fill=(40, 40, 30), width=2)
    draw.line([(x0, border_bottom), (x1, border_bottom)], fill=(40, 40, 30), width=2)
    return img


def test_detect_table_borders_finds_synthetic_ruled_lines():
    img = _synthetic_table_page(border_top=665, border_bottom=1597)
    top, bottom = detect_table_borders(img)
    assert abs(top - 665) <= 1
    assert abs(bottom - 1597) <= 1


def test_crop_row_bands_produces_n_upscaled_pngs():
    img = _synthetic_table_page(border_top=665, border_bottom=1597)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    crops = crop_row_bands(buf.getvalue(), day_count=30, scale=4.0)
    assert len(crops) == 30

    boxes = row_band_geometry(img.size, 30, 665, 1597)
    for crop_bytes, box in zip(crops, boxes):
        crop_img = Image.open(io.BytesIO(crop_bytes))
        assert crop_img.format == "PNG"
        expected_w = round((box[2] - box[0]) * 4.0)
        expected_h = round((box[3] - box[1]) * 4.0)
        assert crop_img.width == expected_w
        assert crop_img.height == expected_h


def test_crop_row_bands_accepts_explicit_borders_skipping_auto_detect():
    """An explicit border_top/border_bottom is used as-is, with no
    auto-detection - a blank page (no ruled lines at all) would otherwise
    make detect_table_borders() return meaningless positions."""
    img = Image.new("RGB", (1000, 2000), color=(230, 225, 190))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    crops = crop_row_bands(buf.getvalue(), day_count=5, border_top=665, border_bottom=1597)
    assert len(crops) == 5


# --- 2. Zoom re-read parsing (pure) + request (respx-mocked) -----------------


def test_parse_zoom_row_response_applies_barometer_reconstruction():
    text = json.dumps({"day": 5, "cells": {"pressure": 51.69, "tmax": 28.0}})
    cells = _parse_zoom_row_response(text, expected_day=5)
    assert cells["pressure"] == pytest.approx(751.69)
    assert cells["tmax"] == pytest.approx(28.0)


def test_parse_zoom_row_response_rejects_day_mismatch():
    text = json.dumps({"day": 6, "cells": {"tmax": 28.0}})
    with pytest.raises(ExtractionParseError, match="day=6.*expected day=5"):
        _parse_zoom_row_response(text, expected_day=5)


def test_parse_zoom_row_response_rejects_unparseable_text():
    with pytest.raises(ExtractionParseError):
        _parse_zoom_row_response("not json at all", expected_day=1)


@respx.mock
def test_zoom_read_row_sends_schema_and_charges_meter(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    ok_body = {"candidates": [{"content": {"parts": [{"text": json.dumps(
        {"day": 3, "cells": {"tmax": 29.5, "pressure": 54.10}}
    )}]}}]}
    route = respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(200, json=ok_body))

    cells = zoom_read_row(b"fake-crop-bytes", GEMINI_PROVIDER, meter, day=3)

    assert cells["tmax"] == pytest.approx(29.5)
    # 54.10 low-order digits reconstructed against the 700s barometer range.
    assert cells["pressure"] == pytest.approx(754.10)
    assert meter.total() > 0

    sent = json.loads(route.calls.last.request.content)
    assert "EXACTLY 3" in sent["system_instruction"]["parts"][0]["text"]
    schema = sent["generationConfig"]["responseSchema"]
    assert schema["properties"]["day"]["type"] == "INTEGER"
    assert "tmax" in schema["properties"]["cells"]["properties"]


@respx.mock
def test_zoom_read_row_propagates_cap_exceeded_before_network_call(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=0.0, ledger=tmp_path / "ledger.json")  # any charge exceeds a 0 cap
    route = respx.post(ENDPOINTS[GEMINI_PROVIDER])
    with pytest.raises(CapExceeded):
        zoom_read_row(b"fake-crop-bytes", GEMINI_PROVIDER, meter, day=1)
    assert not route.called


@respx.mock
def test_zoom_reread_sheet_skips_a_failing_row_and_keeps_the_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")

    img = _synthetic_table_page(border_top=665, border_bottom=1597)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    def make_body(day, ok=True):
        if ok:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(
                {"day": day, "cells": {"tmax": 20.0 + day}}
            )}]}}]})
        # day 2's reply reports the WRONG day -> rejected by _parse_zoom_row_response.
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(
                {"day": 99, "cells": {"tmax": 1.0}}
        )}]}}]})

    responses = [make_body(day, ok=(day != 2)) for day in range(1, 4)]
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(side_effect=responses)

    cells_by_day, errors = zoom_reread_sheet(buf.getvalue(), GEMINI_PROVIDER, meter, day_count=3)

    assert set(cells_by_day) == {1, 3}
    assert cells_by_day[1]["tmax"] == pytest.approx(21.0)
    assert cells_by_day[3]["tmax"] == pytest.approx(23.0)
    assert len(errors) == 1
    assert "day 2" in errors[0]


# --- 3. Reconciliation (pure) --------------------------------------------------


def test_reconcile_flags_disagreeing_cell_and_passes_agreeing_one():
    consensus = {1: {"tmax": 28.0, "pressure": 751.6}}
    zoom = {1: {"tmax": 28.02, "pressure": 751.9}}  # tmax within TOL; pressure beyond it

    suspects = reconcile(consensus, zoom, tol=0.05)

    assert len(suspects) == 1
    s = suspects[0]
    assert s["day"] == 1
    assert s["col"] == "pressure"
    assert s["consensus_value"] == pytest.approx(751.6)
    assert s["zoom_value"] == pytest.approx(751.9)
    assert s["proposed_value"] == pytest.approx(751.9)


def test_reconcile_skips_a_day_missing_from_the_zoom_read():
    consensus = {1: {"tmax": 28.0}, 2: {"tmax": 30.0}}
    zoom = {1: {"tmax": 28.0}}  # day 2's zoom re-read failed and is simply absent

    suspects = reconcile(consensus, zoom, tol=0.05)

    assert suspects == []


def test_reconcile_treats_none_vs_value_as_a_disagreement():
    consensus = {1: {"precip": None}}
    zoom = {1: {"precip": 2.6}}

    suspects = reconcile(consensus, zoom, tol=0.05)

    assert len(suspects) == 1
    assert suspects[0]["consensus_value"] is None
    assert suspects[0]["proposed_value"] == pytest.approx(2.6)


def test_reconcile_none_vs_none_agrees():
    consensus = {1: {"precip": None}}
    zoom = {1: {"precip": None}}

    assert reconcile(consensus, zoom, tol=0.05) == []
