"""VLM table-extraction harness: three providers, one constrained-JSON prompt.

No provider SDKs - raw httpx requests, same style as fetch_docreader.py, so
the whole request/response shape is visible and respx-mockable for tests.
Real API calls are OUT OF SCOPE for this task (Task 11 does that): every
test here is either pure (`_parse_response`) or respx-mocked.
"""

import base64
import json
import os
import random
import re
import time

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
    # standard paid tier, image/text input. NOTE: "gemini-flash" (this
    # entry) actually points at gemini-flash-lite-latest as of Task 11
    # (see ENDPOINTS below - gemini-flash-latest was persistently 503 for
    # this key) - the lite tier is normally cheaper than this rate, so
    # using the full-Flash number here is a deliberately conservative
    # overestimate for the lite run, consistent with this module's
    # charge-before-call design (never undercharge the cap).
    "gemini-flash": {"input": 0.30, "output": 2.50},
    # Same rate, used for the separate "gemini-flash-full" provider (the
    # actual non-lite Flash tier - see ENDPOINTS) added when Task 11's
    # review required a full-flash gate number alongside the lite one.
    "gemini-flash-full": {"input": 0.30, "output": 2.50},
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
    # NOTE (Task 11, verified live 2026-08-31/09-01): this Gemini key is a
    # NEW "AQ."-format key. It 403s against the ?key= query-param auth style
    # and against the explicit gemini-2.0/2.5-flash model ids (404, "no
    # longer available to new users"). It only works with header auth
    # (X-goog-api-key, see _request_gemini).
    #
    # Model id deviation from the Task 11 brief: "gemini-flash-latest" was
    # verified live by the controller before this run, but during the
    # actual run it returned a sustained 503 "This model is currently
    # experiencing high demand" for this key across many spaced-out
    # attempts (well past the 5-attempt/62s retry budget below - this was
    # not a jitter blip). "gemini-flash-lite-latest" (currently aliasing
    # gemini-3.5-flash-lite), same key, confirmed working incl. vision
    # input via direct curl, so the run uses that instead. Documented in
    # bench/g1 + the Task 11 report as a live-verified deviation, not a
    # silent swap.
    "gemini-flash": "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent",
    # "gemini-flash-full": the controller-mandated gate provider. Re-verified
    # live 2026-09-01 (Task 11 review round): "gemini-flash-latest" is
    # STILL persistently 503 ("high demand") for this key - confirmed via
    # direct curl minutes apart, and again through the harness's own
    # 8-attempt/generous-backoff retry (see MAX_ATTEMPTS/_BACKOFF_BASE_SECONDS
    # below) exhausting without a single non-503 response. Falling back to
    # "gemini-3.5-flash" (a current, stable, non-lite Flash model per the
    # live model list - NOT a "-latest" alias, so it isn't subject to
    # whatever routing is overloading gemini-flash-latest specifically),
    # confirmed working incl. vision input via direct curl. If Google
    # resolves the gemini-flash-latest outage, swap this one line back.
    "gemini-flash-full": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent",
    "claude-haiku": "https://api.anthropic.com/v1/messages",
    "qwen-vl": "https://router.huggingface.co/v1/chat/completions",
}

ENV_VARS = {
    "gemini-flash": "WRB_GEMINI_KEY",
    "gemini-flash-full": "WRB_GEMINI_KEY",
    "claude-haiku": "WRB_ANTHROPIC_KEY",
    "qwen-vl": "WRB_HF_TOKEN",
}

# Both Gemini providers speak the same request/response shape regardless of
# which model id the endpoint URL points at.
_GEMINI_PROVIDERS = {"gemini-flash", "gemini-flash-full"}

QWEN_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"

# A full table image + ~2k-token JSON reply occasionally runs past 60s on a
# loaded endpoint (observed live, Task 11: sheet 14_57 ReadTimeout at 60s) -
# 120s gives real headroom without masking a truly hung connection.
REQUEST_TIMEOUT_SECONDS = 120


def estimate_cost_usd(provider: str) -> float:
    prices = PRICES[provider]
    return (
        ESTIMATED_INPUT_TOKENS / 1_000_000 * prices["input"]
        + ESTIMATED_OUTPUT_TOKENS / 1_000_000 * prices["output"]
    )


# --- Prompt ------------------------------------------------------------------

_SCHEMA_JSON = json.dumps(Sheet.model_json_schema())

# The gold set's real cell keys (see wrb/metrics.py module docstring and
# gold/SELECTION.md "Column mapping / legend"). Sheet.rows[].cells is a
# generic dict[str, float | None] in the pydantic schema, so the JSON
# Schema embedded below carries no information about which literal key
# strings to use per column - a live Task 11 probe run (2026-09-01) showed
# a zero-shot model fills in its own plausible English synonyms instead
# (bar_mean/temp_mean/vapour_tension/... instead of
# pressure/tmean/vapor/...), which silently pushes cell_acc to ~0 and
# structural_err_rate to 1.0 for every row - not because the transcription
# is wrong, but because score() (wrb/metrics.py) looks up cells by exact
# key against gold.columns. Pinning the exact keys here is what actually
# lets G1 measure transcription accuracy instead of key-naming luck; see
# the Task 11 report for this as a documented finding, not a silent tweak.
_CELL_KEYS = [
    "pressure", "pressure_max", "pressure_min", "tmean", "tmax", "tmin",
    "vapor", "humidity", "wind_force", "cloudiness", "precip",
    "evap_sol", "evap_sombra", "ozone",
]

SYSTEM_PROMPT = (
    "You are transcribing a printed 19th-century meteorological table from a "
    "scanned page. Transcribe faithfully to what is PRINTED on the page - "
    "never guess, infer, round, or \"correct\" a value that looks physically "
    "impossible; the literal printed glyph is always what is wanted, even "
    "when it looks wrong. "
    "Output ONLY JSON matching this schema (no prose, no markdown fences): "
    f"{_SCHEMA_JSON} "
    "Each row's `cells` dict MUST use EXACTLY these keys, one per printed "
    "column, in this order left-to-right on the page - do not invent, "
    "translate, abbreviate, or rename them: "
    f"{json.dumps(_CELL_KEYS)}. Set `columns` to this same list. "
    "If the page has a column this list has no room for (rare), still use "
    "the closest key above rather than a new name. "
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
    # This key is header-auth only (?key= query param 403s) - see ENDPOINTS
    # note above.
    return httpx.post(endpoint, json=body,
                       headers={"User-Agent": USER_AGENT, "X-goog-api-key": api_key},
                       timeout=REQUEST_TIMEOUT_SECONDS)


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
    return httpx.post(endpoint, json=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)


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
    return httpx.post(endpoint, json=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)


_REQUESTERS = {
    "gemini-flash": _request_gemini,
    "gemini-flash-full": _request_gemini,
    "claude-haiku": _request_claude,
    "qwen-vl": _request_qwen,
}


def _extract_text_from_response(provider: str, data: dict) -> str:
    """Pull the model's text reply out of a provider's 200 envelope.

    A malformed/unexpected envelope shape (missing key, wrong type, empty
    list) is a parse failure like any other malformed VLM output, so it is
    raised as ExtractionParseError rather than an uncaught KeyError/
    IndexError/TypeError - callers only need to catch one exception type
    for "this response could not be turned into a Sheet".
    """
    try:
        if provider in _GEMINI_PROVIDERS:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        if provider == "claude-haiku":
            return data["content"][0]["text"]
        if provider == "qwen-vl":
            return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ExtractionParseError(
            f"{provider}: malformed 200 response envelope, could not locate reply text: {e}"
        ) from e
    raise ValueError(f"unknown provider {provider!r}")


# Matches a leading ```(json) fence and its matching closing fence, allowing
# trailing prose AFTER the closing fence (some models append a sentence like
# "Let me know if you need anything else!" after the JSON block) - captures
# just the fenced body. re.DOTALL so `.` spans newlines; non-greedy so the
# FIRST closing ``` ends the match rather than a later one.
_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_JSON_DECODER = json.JSONDecoder()


def _iter_json_values(text: str):
    """Yield every top-level JSON value found in text, left to right,
    skipping whitespace between them and stopping at the first position
    that isn't valid JSON (trailing prose after the last value, etc.)."""
    pos = 0
    n = len(text)
    while pos < n:
        while pos < n and text[pos] in " \t\r\n":
            pos += 1
        if pos >= n:
            break
        try:
            obj, end = _JSON_DECODER.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        yield obj
        pos = end


def _load_json_candidates(stripped: str) -> list:
    """Return every plausible JSON value recoverable from `stripped`, in
    priority order:

    1. Whole-string `json.loads` - the fast path, covers the overwhelming
       majority of well-formed single-JSON replies.
    2. Same, after stripping trailing commas before a closing `}`/`]` (a
       common small-model mistake).
    3. Every top-level JSON value found by scanning left-to-right
       (_iter_json_values) - covers a VLM echoing EXTRA JSON content
       alongside the real payload in the same reply, on EITHER side of
       it. Observed live, Task 11: sheet 14_142's first attempt had the
       real Sheet data followed by an unrelated trailing block ("Extra
       data" at the point after a complete first value); a later attempt
       instead echoed the prompt's own embedded JSON Schema BEFORE the
       real Sheet data (so the *first* parseable object was the schema,
       not the answer). Grabbing only the first candidate handles the
       first shape but silently fails the second (a schema dict has none
       of Sheet's required fields) - so every candidate found this way is
       tried against the Sheet schema by the caller, in order, and
       whichever one actually validates wins regardless of which side of
       the reply it landed on.

    Returns [] if nothing at all parses.
    """
    try:
        return [json.loads(stripped)]
    except json.JSONDecodeError:
        pass

    cleaned = _TRAILING_COMMA_RE.sub(r"\1", stripped)
    try:
        return [json.loads(cleaned)]
    except json.JSONDecodeError:
        pass

    return list(_iter_json_values(stripped))


def _normalize_non_numeric_cells(obj: dict) -> dict:
    """A model sometimes writes a non-numeric printed annotation straight
    into a numeric `cells` slot instead of using the `flags` mechanism the
    prompt already documents for wind_dir (observed live, Task 11: sheet
    14_179 wrote `"precip": "Gottas"` - Portuguese for "drops", i.e. trace
    rainfall too small to meter; the gold set's own convention for exactly
    this case is `precip: null` + `flags["precip"] = "gottas"`, so the
    model read the page correctly but put the reading in the wrong slot).

    Move any non-numeric, non-null cell value into that row's `flags`
    dict (preserving the original string instead of discarding it) and
    null the cell, so a real transcription rather than a schema slip
    doesn't fail Sheet's `cells: dict[str, float | None]` validation. Does
    NOT touch the Sheet schema itself - this only reshapes the dict before
    Sheet(**obj) is called.
    """
    for row in obj.get("rows", []) or []:
        cells = row.get("cells") or {}
        flags = row.setdefault("flags", {}) or {}
        for col, val in list(cells.items()):
            if val is not None and not isinstance(val, (int, float)):
                flags[col] = str(val)
                cells[col] = None
        row["flags"] = flags
    return obj


def _parse_response(text: str) -> Sheet:
    """Parse a VLM's raw text reply into a Sheet: strip markdown code
    fences if present, recover every plausible JSON candidate
    (_load_json_candidates), normalize non-numeric cell values into flags
    on each dict candidate (_normalize_non_numeric_cells), and return the
    first candidate that validates as a Sheet - trying every candidate
    (not just the first) is what makes this robust to extra JSON content
    landing on either side of the real payload (see
    _load_json_candidates). Raises ExtractionParseError if nothing parses
    at all, or if no candidate validates as a Sheet."""
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()

    candidates = _load_json_candidates(stripped)
    if not candidates:
        raise ExtractionParseError("could not parse VLM response as JSON: no valid JSON value found")

    last_error: Exception | None = None
    for obj in candidates:
        if isinstance(obj, dict):
            obj = _normalize_non_numeric_cells(obj)
        try:
            return Sheet(**obj)
        except (ValidationError, TypeError) as e:
            last_error = e
            continue

    raise ExtractionParseError(
        f"VLM response JSON does not match Sheet schema (tried {len(candidates)} "
        f"candidate JSON value(s)): {last_error}"
    ) from last_error


# Safety net against rate-limit blips even on a paid-tier project: retry a
# 429 (rate limited) or 503 (transiently overloaded) up to this many times
# total, with exponential backoff + jitter (capped at 60s/wait so a
# sustained outage doesn't turn into an unbounded wait). Any other status
# is NOT retried - it's raised immediately via raise_for_status() so a
# real error (bad auth, bad request body, etc.) fails fast instead of
# burning the wall-clock retry budget before reporting.
#
# Bumped from 5/32s-max to 8/60s-max (Task 11 review round) specifically to
# give gemini-flash-latest's persistent 503s a genuinely generous real
# effort before falling back to a different model id - see ENDPOINTS.
RETRYABLE_STATUS_CODES = {429, 503}
MAX_ATTEMPTS = 8
_BACKOFF_BASE_SECONDS = [2, 4, 8, 16, 32, 60, 60, 60]


def _sleep_for_retry(attempt: int) -> None:
    """attempt is 0-indexed (0 = first retry, after the first failed try)."""
    base = _BACKOFF_BASE_SECONDS[min(attempt, len(_BACKOFF_BASE_SECONDS) - 1)]
    time.sleep(base + random.uniform(0, base * 0.25))


def _request_with_retry(provider: str, endpoint: str, api_key: str, image_bytes: bytes) -> httpx.Response:
    """Issue the request, retrying on a retryable status code (429/503) or
    a bare read timeout (observed live, Task 11: sheet 14_57 hit
    httpx.ReadTimeout at the old 60s timeout on a slow/loaded endpoint - a
    transient network stall, not a real error, so it gets the same
    backoff-and-retry treatment). Deliberately narrow to ReadTimeout only
    (not the broader httpx.TimeoutException or e.g. ConnectError) - those
    other transport failures are typically not self-resolving on retry and
    stay fail-fast.

    CAP CAVEAT: CostMeter.charge() in extract() charges once per extract()
    call, before any of these retries happen - so a single extract() call
    that times out and retries N times is still only ONE ledger entry
    against the US$ cap, regardless of N. A ReadTimeout means the request
    reached the provider and it may have already spent real compute
    (prompt processing, partial generation) generating tokens we never
    receive and never see billed to us in this ledger - so on the timeout
    path specifically, actual provider-side spend could exceed our
    conservative per-call estimate by more than the 429/503 path (which
    fails before real generation starts). The US$10 cap is enforced
    against OUR ledger, not the provider's own billing, so this is a
    (still small, since 1.5k-input/2k-output-token estimates are already
    conservative) gap between "our cap fired" and "real spend stayed under
    it" that is specific to timeouts, not retries in general."""
    last_response: httpx.Response | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = _REQUESTERS[provider](endpoint, api_key, image_bytes)
        except httpx.ReadTimeout:
            if attempt < MAX_ATTEMPTS - 1:
                _sleep_for_retry(attempt)
                continue
            raise
        if response.status_code not in RETRYABLE_STATUS_CODES:
            return response
        last_response = response
        if attempt < MAX_ATTEMPTS - 1:
            _sleep_for_retry(attempt)
    assert last_response is not None
    return last_response


def extract(image_bytes: bytes, provider: str, meter: CostMeter) -> Sheet:
    """Extract a Sheet from a table image using the named provider.

    Charges `meter` with a conservative pre-call cost estimate BEFORE the
    network request is issued (so a call that would bust the R$ cap never
    goes out at all - see CostMeter.charge / CapExceeded). Every endpoint
    URL and env-var name/value is passed through assert_personal() at
    client-construction time so a Desert Ant identifier can never leak into
    a personal-billing call.

    A 429 or 503 is retried with exponential backoff (see
    _request_with_retry) as a safety net; any other error status is raised
    immediately via raise_for_status().
    """
    endpoint, api_key = _build_client_and_charge(provider, meter)

    response = _request_with_retry(provider, endpoint, api_key, image_bytes)
    response.raise_for_status()

    data = response.json()
    text = _extract_text_from_response(provider, data)
    return _parse_response(text)
