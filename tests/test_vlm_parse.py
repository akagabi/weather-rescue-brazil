import json

import httpx
import pytest
import respx

from wrb.costs import CapExceeded, CostMeter
from wrb.gold import Sheet
from wrb.vlm import (
    ENDPOINTS,
    ExtractionParseError,
    _parse_response,
    estimate_cost_usd,
    extract,
)

VALID_SHEET = {
    "source": "docvirt", "bib": "14", "page": 41, "station": "s", "period": "1886-01",
    "columns": ["tmax", "tmin"],
    "rows": [{"date": "1886-01-01", "cells": {"tmax": 28.3, "tmin": 21.3}, "flags": {"wind_dir": "Variavel"}}],
}


def test_parse_fenced_json_returns_sheet():
    text = "```json\n" + json.dumps(VALID_SHEET) + "\n```"
    s = _parse_response(text)
    assert isinstance(s, Sheet)
    assert s.rows[0].cells["tmax"] == 28.3


def test_parse_plain_fence_no_language_tag():
    text = "```\n" + json.dumps(VALID_SHEET) + "\n```"
    s = _parse_response(text)
    assert isinstance(s, Sheet)


def test_parse_trailing_comma_variant_returns_sheet():
    # trailing comma before both a closing '}' and a closing ']'
    bad_json = (
        '{"source": "docvirt", "bib": "14", "page": 41, "station": "s", '
        '"period": "1886-01", "columns": ["tmax", "tmin",], '
        '"rows": [{"date": "1886-01-01", "cells": {"tmax": 28.3, "tmin": 21.3,}, '
        '"flags": {"wind_dir": "Variavel"},},]}'
    )
    s = _parse_response(bad_json)
    assert isinstance(s, Sheet)
    assert s.rows[0].cells["tmin"] == 21.3


def test_parse_garbage_raises_extraction_parse_error():
    with pytest.raises(ExtractionParseError):
        _parse_response("this is not json at all, sorry")


def test_parse_valid_json_but_wrong_schema_raises():
    with pytest.raises(ExtractionParseError):
        _parse_response(json.dumps({"totally": "wrong shape"}))


@respx.mock
def test_extract_charges_before_call_even_on_500(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    assert meter.total() == 0.0

    route = respx.post(ENDPOINTS["gemini-flash"]).mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        extract(b"fake-image-bytes", "gemini-flash", meter)

    assert route.called
    assert meter.total() == pytest.approx(estimate_cost_usd("gemini-flash"))


@respx.mock
def test_extract_charge_happens_even_if_request_never_reaches_route(tmp_path, monkeypatch):
    """The charge must land BEFORE the network call is issued at all - not
    just before the response is read. Simulate a connect error."""
    monkeypatch.setenv("WRB_ANTHROPIC_KEY", "test-personal-key-456")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")

    respx.post(ENDPOINTS["claude-haiku"]).mock(side_effect=httpx.ConnectError("no network"))

    with pytest.raises(httpx.ConnectError):
        extract(b"fake-image-bytes", "claude-haiku", meter)

    assert meter.total() == pytest.approx(estimate_cost_usd("claude-haiku"))


def test_extract_respects_cost_cap_before_any_call(tmp_path, monkeypatch):
    """A near-exhausted meter must raise CapExceeded and must not attempt a
    network call at all (no respx route registered here on purpose - a real
    request would error loudly rather than silently succeed)."""
    monkeypatch.setenv("WRB_HF_TOKEN", "test-personal-key-789")
    tiny_cap = estimate_cost_usd("qwen-vl") / 2
    meter = CostMeter(cap_usd=tiny_cap, ledger=tmp_path / "ledger.json")

    with pytest.raises(CapExceeded):
        extract(b"fake-image-bytes", "qwen-vl", meter)
