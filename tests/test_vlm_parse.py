import json

import httpx
import pytest
import respx

from wrb.costs import CapExceeded, CostMeter
from wrb.gold import Sheet
from wrb.vlm import (
    ENDPOINTS,
    MAX_ATTEMPTS,
    SYSTEM_PROMPT,
    _SCHEMA_JSON,
    ExtractionParseError,
    _extract_text_from_response,
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
def test_gemini_request_uses_header_auth_not_query_param(tmp_path, monkeypatch):
    """This key is header-auth only (?key= query param 403s for it, verified
    live) - lock in that the request carries X-goog-api-key and no ?key=."""
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    ok_body = {"candidates": [{"content": {"parts": [{"text": json.dumps(VALID_SHEET)}]}}]}
    route = respx.post(ENDPOINTS["gemini-flash"]).mock(return_value=httpx.Response(200, json=ok_body))

    extract(b"fake-image-bytes", "gemini-flash", meter)

    sent = route.calls.last.request
    assert sent.headers["X-goog-api-key"] == "test-personal-key-123"
    assert "key" not in sent.url.params


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


def test_parse_recovers_json_followed_by_extra_trailing_content():
    """Live Task 11 failure (sheet 14_142): a valid JSON object followed by
    more content (e.g. a duplicate/trailing block) raises json.loads'
    "Extra data" error even though the object itself is well-formed and
    trailing-comma cleanup can't fix it (nothing malformed to strip) - the
    raw_decode fallback should recover the first complete object."""
    text = json.dumps(VALID_SHEET) + "\n" + json.dumps({"unexpected": "trailing block"})
    s = _parse_response(text)
    assert isinstance(s, Sheet)
    assert s.rows[0].cells["tmax"] == 28.3


def test_parse_recovers_json_when_schema_echoed_before_real_data():
    """Live Task 11 failure (sheet 14_142, second occurrence): the model
    echoed the prompt's own embedded JSON Schema FIRST, then the real
    Sheet data as a second top-level JSON value - the opposite ordering
    from the "trailing extra content" case above. The naive "take the
    first parseable JSON value" fix (raw_decode from position 0) silently
    returns the schema dict itself here, which then fails Sheet validation
    with all-required-fields-missing. Every candidate must be tried."""
    text = _SCHEMA_JSON + "\n" + json.dumps(VALID_SHEET)
    s = _parse_response(text)
    assert isinstance(s, Sheet)
    assert s.rows[0].cells["tmax"] == 28.3


def test_parse_moves_non_numeric_cell_value_into_flags():
    """Live Task 11 failure (sheet 14_179): the model wrote a real printed
    annotation ("Gottas" - trace rainfall) directly into a numeric cells
    slot instead of using flags, matching the gold set's own convention
    for this exact case (precip: null, flags["precip"]: "gottas"). This
    must be recovered rather than raising ExtractionParseError - the
    reading itself was correct, only its slot was wrong."""
    sheet = {
        **VALID_SHEET,
        "rows": [{"date": "1886-01-01", "cells": {"tmax": 28.3, "tmin": "Gottas"},
                  "flags": {"wind_dir": "Variavel"}}],
    }
    s = _parse_response(json.dumps(sheet))
    assert isinstance(s, Sheet)
    assert s.rows[0].cells["tmin"] is None
    assert s.rows[0].flags["tmin"] == "Gottas"
    assert s.rows[0].flags["wind_dir"] == "Variavel"  # existing flags preserved


@respx.mock
def test_extract_retries_on_read_timeout_then_succeeds(tmp_path, monkeypatch):
    """Live Task 11 failure (sheet 14_57): a bare read timeout at the old
    60s ceiling. Should be retried like a 429/503, not raised immediately."""
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    monkeypatch.setattr("wrb.vlm.time.sleep", lambda *_a, **_k: None)
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")

    ok_body = {"candidates": [{"content": {"parts": [{"text": json.dumps(VALID_SHEET)}]}}]}
    route = respx.post(ENDPOINTS["gemini-flash"]).mock(
        side_effect=[
            httpx.ReadTimeout("timed out"),
            httpx.Response(200, json=ok_body),
        ]
    )

    sheet = extract(b"fake-image-bytes", "gemini-flash", meter)

    assert isinstance(sheet, Sheet)
    assert route.call_count == 2
    assert meter.total() == pytest.approx(estimate_cost_usd("gemini-flash"))


@respx.mock
def test_extract_read_timeout_exhausted_then_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    monkeypatch.setattr("wrb.vlm.time.sleep", lambda *_a, **_k: None)
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")

    route = respx.post(ENDPOINTS["gemini-flash"]).mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(httpx.ReadTimeout):
        extract(b"fake-image-bytes", "gemini-flash", meter)

    assert route.call_count == MAX_ATTEMPTS


@respx.mock
def test_extract_connect_error_not_retried(tmp_path, monkeypatch):
    """ConnectError stays fail-fast (not retried like ReadTimeout) - keeps
    a genuinely unreachable endpoint from burning the full retry budget."""
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")

    route = respx.post(ENDPOINTS["gemini-flash"]).mock(side_effect=httpx.ConnectError("no network"))

    with pytest.raises(httpx.ConnectError):
        extract(b"fake-image-bytes", "gemini-flash", meter)

    assert route.call_count == 1


def test_system_prompt_pins_exact_gold_cell_keys():
    """A live Task 11 probe run showed a zero-shot model invents its own
    plausible column-name synonyms (bar_mean, temp_mean, ...) when the
    prompt doesn't pin exact keys, which silently tanks cell_acc to ~0
    against the gold set's real keys (see wrb/metrics.py docstring) even
    when the transcription itself is fine. Lock in that every real gold
    key is named explicitly in the prompt."""
    for key in (
        "pressure", "pressure_max", "pressure_min", "tmean", "tmax", "tmin",
        "vapor", "humidity", "wind_force", "cloudiness", "precip",
        "evap_sol", "evap_sombra", "ozone",
    ):
        assert key in SYSTEM_PROMPT


def test_parse_fence_allows_trailing_prose_after_close():
    """Task 10 deferred minor: some models append a sentence after the
    closing ``` fence - that trailing prose must not break parsing."""
    text = "```json\n" + json.dumps(VALID_SHEET) + "\n```\nLet me know if you need anything else!"
    s = _parse_response(text)
    assert isinstance(s, Sheet)
    assert s.rows[0].cells["tmax"] == 28.3


def test_extract_text_from_response_raises_parse_error_on_malformed_envelope():
    """Task 10 deferred minor: a malformed 200 envelope (missing/wrong-shape
    key) must surface as ExtractionParseError, not a raw KeyError/IndexError."""
    with pytest.raises(ExtractionParseError):
        _extract_text_from_response("gemini-flash", {"candidates": []})
    with pytest.raises(ExtractionParseError):
        _extract_text_from_response("claude-haiku", {"unexpected": "shape"})
    with pytest.raises(ExtractionParseError):
        _extract_text_from_response("qwen-vl", {"choices": [{"message": {}}]})


@respx.mock
def test_extract_retries_on_429_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    monkeypatch.setattr("wrb.vlm.time.sleep", lambda *_a, **_k: None)
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")

    ok_body = {"candidates": [{"content": {"parts": [{"text": json.dumps(VALID_SHEET)}]}}]}
    route = respx.post(ENDPOINTS["gemini-flash"]).mock(
        side_effect=[
            httpx.Response(429, json={"error": "rate limited"}),
            httpx.Response(429, json={"error": "rate limited"}),
            httpx.Response(200, json=ok_body),
        ]
    )

    sheet = extract(b"fake-image-bytes", "gemini-flash", meter)

    assert isinstance(sheet, Sheet)
    assert route.call_count == 3
    # charged exactly once (before the first call), not once per retry.
    assert meter.total() == pytest.approx(estimate_cost_usd("gemini-flash"))


@respx.mock
def test_extract_retries_exhausted_then_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    monkeypatch.setattr("wrb.vlm.time.sleep", lambda *_a, **_k: None)
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")

    route = respx.post(ENDPOINTS["gemini-flash"]).mock(
        return_value=httpx.Response(503, json={"error": "overloaded"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        extract(b"fake-image-bytes", "gemini-flash", meter)

    assert route.call_count == MAX_ATTEMPTS


@respx.mock
def test_extract_does_not_retry_non_retryable_status(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    monkeypatch.setattr("wrb.vlm.time.sleep", lambda *_a, **_k: None)
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")

    route = respx.post(ENDPOINTS["gemini-flash"]).mock(
        return_value=httpx.Response(403, json={"error": "forbidden"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        extract(b"fake-image-bytes", "gemini-flash", meter)

    assert route.call_count == 1


def test_extract_respects_cost_cap_before_any_call(tmp_path, monkeypatch):
    """A near-exhausted meter must raise CapExceeded and must not attempt a
    network call at all (no respx route registered here on purpose - a real
    request would error loudly rather than silently succeed)."""
    monkeypatch.setenv("WRB_HF_TOKEN", "test-personal-key-789")
    tiny_cap = estimate_cost_usd("qwen-vl") / 2
    meter = CostMeter(cap_usd=tiny_cap, ledger=tmp_path / "ledger.json")

    with pytest.raises(CapExceeded):
        extract(b"fake-image-bytes", "qwen-vl", meter)
