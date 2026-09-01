"""VLM table-extraction harness: three providers, one constrained-JSON prompt.

No provider SDKs - raw httpx requests, same style as fetch_docreader.py, so
the whole request/response shape is visible and respx-mockable for tests.
Real API calls are OUT OF SCOPE for this task (Task 11 does that): every
test here is either pure (`_parse_response`) or respx-mocked.
"""

import base64
import json
import os
import re

import httpx
from pydantic import ValidationError

from wrb.costs import CostMeter
from wrb.gold import Sheet
from wrb.guard import assert_personal

USER_AGENT = "WeatherRescueBrazil/0.1 (open climate data rescue; contact: gabesuit@gmail.com)"


class ExtractionParseError(RuntimeError):
    """Raised by _parse_response when a VLM's text response cannot be
    recovered into a valid Sheet, even after fence-stripping and
    trailing-comma cleanup."""


# --- Cost model -------------------------------------------------------------
#
# We charge a CONSERVATIVE pre-call estimate against the CostMeter BEFORE
# issuing the request (see extract()), because we must never let a live API
# call happen uncounted. Per the brief: a single-page table image costs
# roughly 1.5k input tokens (image + short instruction text) and the model's
# JSON reply is budgeted at up to 2k output tokens (a full ~31-row/14-column
# month is a few hundred numbers - 2k tokens covers it with headroom).
ESTIMATED_INPUT_TOKENS = 1_500
ESTIMATED_OUTPUT_TOKENS = 2_000

# USD per 1,000,000 tokens. Sources checked 2026-08-31/09-01:
PRICES = {
    # https://ai.google.dev/gemini-api/docs/pricing - Gemini 2.5 Flash,
    # standard paid tier, image/text input.
    "gemini-flash": {"input": 0.30, "output": 2.50},
    # https://platform.claude.com/docs/en/about-claude/pricing - Claude
    # Haiku 4.5, base (non-cached) input/output rates.
    "claude-haiku": {"input": 1.00, "output": 5.00},
    # https://huggingface.co/docs/inference-providers/pricing - HF
    # Inference Providers pass through the underlying provider's compute
    # cost with no HF markup; there is no single published per-token rate
    # for Qwen2.5-VL specifically (billed per-provider, per-compute-time).
    # This is a deliberately conservative flat estimate in the same range
    # as comparable open-weight VLM serverless per-token rates on
    # HF-integrated providers (roughly $1-1.5/MTok blended, 2026-08); using
    # the higher end so we never under-charge the cap.
    "qwen-vl": {"input": 1.50, "output": 1.50},
}

ENDPOINTS = {
    "gemini-flash": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    "claude-haiku": "https://api.anthropic.com/v1/messages",
    "qwen-vl": "https://router.huggingface.co/v1/chat/completions",
}

ENV_VARS = {
    "gemini-flash": "WRB_GEMINI_KEY",
    "claude-haiku": "WRB_ANTHROPIC_KEY",
    "qwen-vl": "WRB_HF_TOKEN",
}

QWEN_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"


def estimate_cost_usd(provider: str) -> float:
    prices = PRICES[provider]
    return (
        ESTIMATED_INPUT_TOKENS / 1_000_000 * prices["input"]
        + ESTIMATED_OUTPUT_TOKENS / 1_000_000 * prices["output"]
    )


# --- Prompt ------------------------------------------------------------------

_SCHEMA_JSON = json.dumps(Sheet.model_json_schema())

SYSTEM_PROMPT = (
    "You are transcribing a printed 19th-century meteorological table from a "
    "scanned page. Transcribe faithfully to what is PRINTED on the page - "
    "never guess, infer, round, or \"correct\" a value that looks physically "
    "impossible; the literal printed glyph is always what is wanted, even "
    "when it looks wrong. "
    "Output ONLY JSON matching this schema (no prose, no markdown fences): "
    f"{_SCHEMA_JSON} "
    "Rules: "
    "1) If a cell is illegible, set it to null and add that column's key to "
    "the row's `flags` dict with the value \"uncertain\". "
    "2) Do NOT guess or silently correct an impossible value - transcribe it "
    "as printed and flag it instead. "
    "3) Decimal points, not commas: `70,9` in the source means `70.9`. "
    "4) The barometer columns elide the thousands+hundreds digits after the "
    "first row of the table; reconstruct the elided prefix from the anchor "
    "row (e.g. `51.69` on a table anchored at `754.44` means `751.69`) and "
    "record the reconstructed full value. "
    "5) Dates must be ISO format (YYYY-MM-DD). "
    "6) Wind DIRECTION text (e.g. \"SSE\", \"Variavel\") is not a numeric "
    "cell - put it verbatim in that row's flags[\"wind_dir\"], never in "
    "`cells`."
)


def _build_client_and_charge(provider: str, meter: CostMeter) -> tuple[str, str]:
    """Validate provider, assert_personal() on endpoint + env var value, and
    charge the meter's conservative pre-call estimate. Returns (endpoint,
    api_key). Raises CapExceeded (propagated from meter.charge) BEFORE any
    network call is made if this would bust the cap."""
    if provider not in PRICES:
        raise ValueError(f"unknown provider {provider!r}; expected one of {sorted(PRICES)}")

    endpoint = ENDPOINTS[provider]
    assert_personal(endpoint)

    env_name = ENV_VARS[provider]
    assert_personal(env_name)
    api_key = os.environ.get(env_name, "")
    assert_personal(api_key)

    meter.charge(f"{provider} extract call (image~{ESTIMATED_INPUT_TOKENS}tok, "
                 f"out~{ESTIMATED_OUTPUT_TOKENS}tok)", estimate_cost_usd(provider))

    return endpoint, api_key


def _image_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _request_gemini(endpoint: str, api_key: str, image_bytes: bytes) -> httpx.Response:
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/png",
                                  "data": base64.b64encode(image_bytes).decode("ascii")}},
            ],
        }],
    }
    return httpx.post(endpoint, params={"key": api_key}, json=body,
                       headers={"User-Agent": USER_AGENT}, timeout=60)


def _request_claude(endpoint: str, api_key: str, image_bytes: bytes) -> httpx.Response:
    body = {
        "model": "claude-haiku-4-5",
        "max_tokens": ESTIMATED_OUTPUT_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                              "data": base64.b64encode(image_bytes).decode("ascii")}},
                {"type": "text", "text": "Transcribe this table to JSON per the schema."},
            ],
        }],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "User-Agent": USER_AGENT,
    }
    return httpx.post(endpoint, json=body, headers=headers, timeout=60)


def _request_qwen(endpoint: str, api_key: str, image_bytes: bytes) -> httpx.Response:
    body = {
        "model": QWEN_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": SYSTEM_PROMPT},
                {"type": "image_url", "image_url": {"url": _image_data_url(image_bytes)}},
            ],
        }],
        "max_tokens": ESTIMATED_OUTPUT_TOKENS,
    }
    headers = {"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT}
    return httpx.post(endpoint, json=body, headers=headers, timeout=60)


_REQUESTERS = {
    "gemini-flash": _request_gemini,
    "claude-haiku": _request_claude,
    "qwen-vl": _request_qwen,
}


def _extract_text_from_response(provider: str, data: dict) -> str:
    if provider == "gemini-flash":
        return data["candidates"][0]["content"]["parts"][0]["text"]
    if provider == "claude-haiku":
        return data["content"][0]["text"]
    if provider == "qwen-vl":
        return data["choices"][0]["message"]["content"]
    raise ValueError(f"unknown provider {provider!r}")


_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _parse_response(text: str) -> Sheet:
    """Parse a VLM's raw text reply into a Sheet: strip markdown code
    fences if present, json.loads, and if that fails, retry once after
    stripping trailing commas (a common small-model JSON mistake). Raises
    ExtractionParseError on anything still unrecoverable."""
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()

    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        cleaned = _TRAILING_COMMA_RE.sub(r"\1", stripped)
        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ExtractionParseError(f"could not parse VLM response as JSON: {e}") from e

    try:
        return Sheet(**obj)
    except (ValidationError, TypeError) as e:
        raise ExtractionParseError(f"VLM response JSON does not match Sheet schema: {e}") from e


def extract(image_bytes: bytes, provider: str, meter: CostMeter) -> Sheet:
    """Extract a Sheet from a table image using the named provider.

    Charges `meter` with a conservative pre-call cost estimate BEFORE the
    network request is issued (so a call that would bust the R$ cap never
    goes out at all - see CostMeter.charge / CapExceeded). Every endpoint
    URL and env-var name/value is passed through assert_personal() at
    client-construction time so a Desert Ant identifier can never leak into
    a personal-billing call.
    """
    endpoint, api_key = _build_client_and_charge(provider, meter)

    response = _REQUESTERS[provider](endpoint, api_key, image_bytes)
    response.raise_for_status()

    data = response.json()
    text = _extract_text_from_response(provider, data)
    return _parse_response(text)
