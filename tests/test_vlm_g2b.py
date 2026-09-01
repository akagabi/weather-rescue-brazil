"""G2-B structural-error extraction strategy: schema-enforced output, the
day anchor + validator, the separate header/period call, and deterministic
barometer reconstruction wired into extract(strategy="g2b"). Every test
here is respx-mocked or pure - NO real API calls (see the module docstring
in wrb/vlm.py and docs/superpowers/plans/2026-09-01-weather-rescue-brazil-g2.md
Task 1: this task is FREE, paid probing is Task 2).
"""

import json

import httpx
import pytest
import respx

from wrb.costs import CostMeter
from wrb.gold import Sheet
from wrb.vlm import (
    _CELL_KEYS,
    ENDPOINTS,
    ExtractionParseError,
    G2BRow,
    G2BTable,
    assemble_sheet,
    extract,
    extract_period,
    g2b_response_schema,
    reconcile_period,
    validate_day_sequence,
)

GEMINI_PROVIDER = "gemini-flash-full"  # the controller-mandated gate provider


def _cells(**overrides):
    row = {k: 1.0 for k in _CELL_KEYS}
    row.update(overrides)
    return row


def _g2b_rows(n, **overrides_by_col):
    rows = []
    for d in range(1, n + 1):
        cells = _cells()
        for col, values in overrides_by_col.items():
            if d in values:
                cells[col] = values[d]
        rows.append({"day": d, "cells": cells, "flags": {}})
    return rows


# --- 1. schema-enforced structured output -----------------------------------


@respx.mock
def test_g2b_request_sends_response_schema_matching_day_count(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    ok_body = {
        "candidates": [{
            "content": {"parts": [{"text": json.dumps({"rows": _g2b_rows(31)})}]},
            "avgLogprobs": -0.05,
        }],
    }
    route = respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(200, json=ok_body))

    table = extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, strategy="g2b", day_count=31)

    sent = json.loads(route.calls.last.request.content)
    gen_cfg = sent["generationConfig"]
    assert gen_cfg["responseMimeType"] == "application/json"
    # Live-verified (Task 2 probe, 2026-09-01): the gate model
    # (gemini-3.5-flash) 400s the WHOLE g2b call with "Logprobs is not
    # enabled for this model" whenever either field is present - so
    # neither is ever sent (see _request_gemini_g2b's docstring).
    assert "responseLogprobs" not in gen_cfg
    assert "logprobs" not in gen_cfg
    schema = gen_cfg["responseSchema"]
    # The exact-31-row pin IS sent over the wire - live-verified (same
    # probe) that responseSchema, minItems/maxItems included, is not
    # implicated in the 400; only the logprobs fields were.
    assert schema["properties"]["rows"]["minItems"] == 31
    assert schema["properties"]["rows"]["maxItems"] == 31
    item_props = schema["properties"]["rows"]["items"]["properties"]
    assert set(_CELL_KEYS) <= set(item_props["cells"]["properties"])
    assert item_props["day"]["type"] == "INTEGER"
    # day is the anchor field: it must come first.
    assert schema["properties"]["rows"]["items"]["propertyOrdering"][0] == "day"

    assert isinstance(table, G2BTable)
    assert len(table.rows) == 31
    assert table.avg_logprobs == pytest.approx(-0.05)


def test_g2b_response_schema_omits_item_bounds_when_day_count_unknown():
    schema = g2b_response_schema(day_count=None)
    assert "minItems" not in schema["properties"]["rows"]
    assert "maxItems" not in schema["properties"]["rows"]


@respx.mock
def test_g2b_rejects_short_row_count_response(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    ok_body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"rows": _g2b_rows(5)})}]}}]}
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(200, json=ok_body))

    with pytest.raises(ExtractionParseError):
        extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, strategy="g2b", day_count=31)


@respx.mock
def test_g2b_rejects_off_shape_response(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    ok_body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"totally": "wrong shape"})}]}}]}
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(200, json=ok_body))

    with pytest.raises(ExtractionParseError):
        extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, strategy="g2b", day_count=31)


def test_g2b_strategy_rejects_non_gemini_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_ANTHROPIC_KEY", "test-personal-key-456")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    with pytest.raises(ValueError):
        extract(b"fake-image-bytes", "claude-haiku", meter, strategy="g2b", day_count=31)


# --- 2. day anchor + validator ------------------------------------------------


def test_validate_day_sequence_clean_passes():
    table = G2BTable(rows=[G2BRow(day=d, cells={}, flags={}) for d in range(1, 32)])
    assert validate_day_sequence(table) == []


def test_validate_day_sequence_flags_a_shift_and_duplicate():
    rows = [G2BRow(day=d, cells={}, flags={}) for d in range(1, 32)]
    # simulate a shift: row index 10 (would be day 11) reads as day 12,
    # and the real day-12 row also still says day 12 -> a duplicate too.
    rows[10] = G2BRow(day=12, cells={}, flags={})
    table = G2BTable(rows=rows)

    violations = validate_day_sequence(table)

    assert violations
    assert any("11" in v for v in violations)  # expected day 11 not found as printed
    assert any("duplicat" in v.lower() for v in violations)


# --- 3. separate header/period call + reconcile -------------------------------


@respx.mock
def test_extract_period_parses_mocked_header(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"year": 1886, "month_name": "Janeiro"})}]}}]}
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(200, json=body))

    year, month = extract_period(b"fake-image-bytes", GEMINI_PROVIDER, meter)

    assert (year, month) == (1886, 1)
    assert meter.total() > 0.0


@respx.mock
def test_extract_period_charges_before_call_even_on_500(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    route = respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(500, json={"error": "boom"}))

    with pytest.raises(httpx.HTTPStatusError):
        extract_period(b"fake-image-bytes", GEMINI_PROVIDER, meter)

    assert route.called
    assert meter.total() > 0.0


def test_extract_period_raises_on_unknown_month_name(tmp_path, monkeypatch):
    from wrb.vlm import _parse_period_response

    with pytest.raises(ExtractionParseError):
        _parse_period_response(json.dumps({"year": 1886, "month_name": "Not A Month"}))


def test_reconcile_period_overrides_out_of_sequence_year():
    (year, month), flag = reconcile_period((1888, 1), expected_prev=(1885, 12))
    assert (year, month) == (1886, 1)
    assert flag is not None


def test_reconcile_period_overrides_out_of_sequence_month():
    (year, month), flag = reconcile_period((1886, 4), expected_prev=(1886, 1))
    assert (year, month) == (1886, 2)
    assert flag is not None


def test_reconcile_period_no_flag_when_in_sequence():
    (year, month), flag = reconcile_period((1886, 2), expected_prev=(1886, 1))
    assert (year, month) == (1886, 2)
    assert flag is None


def test_reconcile_period_december_year_rollover():
    (year, month), flag = reconcile_period((1887, 1), expected_prev=(1886, 12))
    assert (year, month) == (1887, 1)
    assert flag is None


def test_reconcile_period_flags_but_cannot_override_without_anchor():
    (year, month), flag = reconcile_period((1999, 5), expected_prev=None)
    assert flag is not None
    assert (year, month) == (1999, 5)  # unchanged - no anchor to correct from


# --- 4. deterministic barometer reconstruction wired into g2b extract --------


@respx.mock
def test_g2b_reconstructs_barometer_columns_from_low_order_digits(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    row = _cells(pressure=42.03, pressure_max=51.44, pressure_min=62.39)
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"rows": [{"day": 1, "cells": row, "flags": {}}]})}]}}]}
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(200, json=body))

    table = extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, strategy="g2b", day_count=1)

    r = table.rows[0]
    assert r.cells["pressure"] == pytest.approx(742.03)
    assert r.cells["pressure_max"] == pytest.approx(751.44)
    assert r.cells["pressure_min"] == pytest.approx(762.39)


# --- 5. logprobs ---------------------------------------------------------------


@respx.mock
def test_g2b_captures_avg_logprobs_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"rows": _g2b_rows(1)})}]}}]}
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(200, json=body))

    table = extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, strategy="g2b", day_count=1)

    assert table.avg_logprobs is None


@respx.mock
def test_g2b_never_sends_logprobs_fields_in_a_single_call(tmp_path, monkeypatch):
    """Live-verified (Task 2 probe, 2026-09-01): gemini-3.5-flash (the
    controller-mandated gate model) 400s the WHOLE g2b table call with
    {"error": {"message": "Logprobs is not enabled for this model"}}
    whenever `responseLogprobs`/`logprobs` are present in generationConfig
    - there is no partial/soft-reject to recover from, so the fix is to
    never send either field, not to retry after a 400. This exercises the
    real (non-mocked-400) happy path end to end and asserts it took exactly
    one HTTP attempt and one ledger charge."""
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    ok_body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"rows": _g2b_rows(1)})}]}}]}
    route = respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(200, json=ok_body))

    table = extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, strategy="g2b", day_count=1)

    assert isinstance(table, G2BTable)
    assert len(table.rows) == 1
    assert table.avg_logprobs is None
    assert route.call_count == 1
    sent_cfg = json.loads(route.calls[0].request.content)["generationConfig"]
    assert "responseLogprobs" not in sent_cfg
    assert "logprobs" not in sent_cfg
    assert len(meter.items) == 1


@respx.mock
def test_g2b_raises_immediately_on_400_no_retry(tmp_path, monkeypatch):
    """A 400 is not in RETRYABLE_STATUS_CODES (see _request_with_retry) -
    it must fail fast with exactly one HTTP attempt, never be swallowed or
    retried. This guards against reintroducing the removed
    catch-and-retry-without-logprobs fallback for some OTHER 400 cause."""
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    route = respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(
        return_value=httpx.Response(400, json={"error": {"message": "Request contains an invalid argument"}}),
    )

    with pytest.raises(httpx.HTTPStatusError):
        extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, strategy="g2b", day_count=1)

    assert route.call_count == 1


# --- charging (mirrors the existing zero_shot charge-before-call contract) ---


@respx.mock
def test_g2b_extract_charges_before_call_even_on_500(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    assert meter.total() == 0.0
    route = respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(return_value=httpx.Response(500, json={"error": "boom"}))

    with pytest.raises(httpx.HTTPStatusError):
        extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, strategy="g2b", day_count=31)

    assert route.called
    assert meter.total() > 0.0


# --- assemble_sheet: stitches the day-only g2b table + reconciled period ------
# into a real Sheet - the main table call is no longer the date's source of
# truth (fix #3), so something has to combine them; this is that something.


def test_assemble_sheet_builds_iso_dates_from_period_and_day():
    table = G2BTable(rows=[
        G2BRow(day=1, cells={"tmax": 28.3}, flags={}),
        G2BRow(day=2, cells={"tmax": 29.0}, flags={"wind_dir": "SSE"}),
    ])

    sheet = assemble_sheet(
        table, year=1886, month=1,
        source="docvirt", bib="14", page=41, station="s", columns=["tmax"],
    )

    assert isinstance(sheet, Sheet)
    assert sheet.period == "1886-01"
    assert sheet.rows[0].date == "1886-01-01"
    assert sheet.rows[1].date == "1886-01-02"
    assert sheet.rows[1].flags["wind_dir"] == "SSE"


def test_assemble_sheet_uses_row_day_not_positional_index():
    """Coordinator fix (post Task-1-approval): this is the load-bearing
    anti-cheat property of the whole day-anchor design (fix #2) - if
    assemble_sheet silently fell back to a row's POSITION in the list
    instead of its own `.day` field, a dropped/shifted row would produce a
    Sheet with plausible-looking but WRONG dates instead of surfacing the
    gap, turning the day anchor into theater. Give it a table with a day
    GAP (day 5 missing entirely - as if the model's row for day 5 failed
    to parse and was dropped) and assert the built dates track `.day`,
    not the row's index in the list."""
    table = G2BTable(rows=[
        G2BRow(day=1, cells={"tmax": 28.3}, flags={}),
        G2BRow(day=5, cells={"tmax": 30.0}, flags={}),
    ])

    sheet = assemble_sheet(
        table, year=1886, month=1,
        source="docvirt", bib="14", page=41, station="s", columns=["tmax"],
    )

    assert [r.date for r in sheet.rows] == ["1886-01-01", "1886-01-05"]
    # the failure mode this guards against: positional indexing would give
    # ["1886-01-01", "1886-01-02"] instead.
    assert sheet.rows[1].date != "1886-01-02"


def test_zero_shot_strategy_is_unaffected_default():
    """The old zero-shot path must remain the default and behave exactly as
    before Task 1 - strategy="g2b" is strictly additive."""
    import inspect

    assert inspect.signature(extract).parameters["strategy"].default == "zero_shot"
