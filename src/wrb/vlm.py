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
from functools import partial

import httpx
from pydantic import BaseModel, ValidationError

from wrb.costs import CostMeter
from wrb.gold import Row, Sheet
from wrb.guard import assert_personal
from wrb.reconstruct import restore_thousands

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


# --- G2-B strategy: schema-enforced output + day anchor ---------------------
#
# The G1 gate (docs/gates/g1-report.md, 88.1% cell / 11.5% structural) found
# that the overwhelming majority of wrong cells are STRUCTURAL: whole rows
# landing on the wrong date (day/date drift), a wrong page-level date, and
# the barometer elision rule getting silently dropped somewhere in a long
# free-form generation - not individual glyph misreads. The zero-shot path
# above (SYSTEM_PROMPT / extract(strategy="zero_shot")) is kept exactly as
# it was for A/B comparison; g2b is an ADDITIVE strategy, not a replacement.
# MeteoSaver's core lesson (cited in the G2-B plan) is to decouple *layout*
# from *content*: let the schema pin the shape (row count, field order,
# exact keys) so the model only ever has to fill in numbers, and let
# deterministic code - not another free-form model guess - own anything
# mechanically derivable (the barometer's elided prefix, the calendar date).

# Barometer columns get the low-order-digit treatment (fix #4): the prompt
# asks for the printed low-order digits, restore_thousands() reconstructs
# the elided leading digit deterministically (see wrb/reconstruct.py).
_BAROMETER_COLS = ("pressure", "pressure_max", "pressure_min")

G2B_SYSTEM_PROMPT = (
    "You are transcribing the DAILY DATA ROWS of a printed 19th-century "
    "Brazilian meteorological table from a scanned page. Do NOT read the "
    "page header, month name, or year here - that is handled by a separate "
    "call; this call is table rows only. "
    "Transcribe faithfully to what is PRINTED - never guess, infer, round, "
    "or \"correct\" a value that looks physically impossible; the literal "
    "printed glyph is always what is wanted, even when it looks wrong. "
    "Output ONLY JSON matching the provided response schema (no prose, no "
    "markdown fences). "
    "Each row object's FIRST field is `day`: the integer day-of-month "
    "printed at the start of that row (1, 2, 3, ...) - this is the row's "
    "anchor and must be read directly off that row's own printed line "
    "number, never inferred from position or from the previous row. "
    "Each row's `cells` dict MUST use EXACTLY these keys, one per printed "
    "column, in this order left-to-right on the page - do not invent, "
    "translate, abbreviate, or rename them: "
    f"{json.dumps(_CELL_KEYS)}. "
    "Rules: "
    "1) If a cell is illegible, set it to null and add that column's key to "
    "the row's `flags` dict with the value \"uncertain\". "
    "2) Do NOT guess or silently correct an impossible value - transcribe "
    "it as printed and flag it instead. "
    "3) Decimal points, not commas: `70,9` in the source means `70.9`. "
    "4) BAROMETER COLUMNS "
    f"({', '.join(_BAROMETER_COLS)}): this source elides the leading "
    "hundreds(+thousands) digit after the table's first row. Do NOT try to "
    "reconstruct the elided digit yourself - report EXACTLY the low-order "
    "digits printed on the page for every row (including the first row, "
    "report its digits as printed even if that row happens to be printed "
    "in full) as a plain number, e.g. `51.69` stays `51.69`. Reconstruction "
    "is done mechanically downstream from these digits. "
    "5) Wind DIRECTION text (e.g. \"SSE\", \"Variavel\") is not a numeric "
    "cell - put it verbatim in that row's flags[\"wind_dir\"], never in "
    "`cells`. "
    "6) `printed_totals`: if the table has a bottom \"Mez\" (month) summary "
    "row with printed means/sums, record those literally under keys like "
    "\"pressure_mean\" or \"precip_sum\"; omit any total not printed."
)


def g2b_response_schema(day_count: int | None = None) -> dict:
    """The Gemini `responseSchema` for the g2b table call (fix #1:
    schema-enforced structured output).

    Uses Gemini's OpenAPI-subset schema dialect (uppercase `type` names,
    plus the Gemini-specific `propertyOrdering` hint) - `propertyOrdering`
    is what encodes fix #2's "day is the first field" requirement directly
    into the request, not just into the prompt text.

    `day_count` (the month's day count, e.g. 28/30/31) is accepted for
    signature compatibility and used by `_parse_g2b_response` to reject an
    off-length response, but it is deliberately NOT sent into the schema as
    `minItems`/`maxItems` on the `rows` array.

    CORRECTED (2026-09-01, controller-confirmed): an earlier version of
    this docstring claimed minItems/maxItems were live-verified as not the
    cause of the g2b table call's 400 - that was wrong. A controller curl
    probe showed a tiny 2-item schema WITH minItems/maxItems=2 returns 200,
    but this same schema (14-required-field row objects) pinned to the
    real day_count (31) 400s ("invalid argument") on the gate model. The
    length bound is the cause on the full-size schema; it is removed here
    and the exact row count is enforced CLIENT-SIDE instead, in
    `_parse_g2b_response` below (a wrong count still raises
    ExtractionParseError - it is never padded or truncated to fit)."""
    cell_properties = {key: {"type": "NUMBER", "nullable": True} for key in _CELL_KEYS}
    row_schema = {
        "type": "OBJECT",
        "properties": {
            "day": {"type": "INTEGER"},
            "cells": {
                "type": "OBJECT",
                "properties": cell_properties,
                "required": _CELL_KEYS,
                "propertyOrdering": _CELL_KEYS,
            },
            "flags": {
                "type": "OBJECT",
                "properties": {"wind_dir": {"type": "STRING"}},
            },
        },
        "required": ["day", "cells"],
        "propertyOrdering": ["day", "cells", "flags"],
    }
    # `day_count` is intentionally NOT applied as minItems/maxItems here -
    # see the docstring above. It is unused in this function's body; kept
    # as a parameter only so callers don't need a signature change and so
    # its intent (row-count enforcement) is documented at the call site.
    rows_schema: dict = {"type": "ARRAY", "items": row_schema}
    # `printed_totals` is intentionally NOT in the response schema: Gemini's
    # structured-output rejects an OBJECT with no declared `properties`
    # ("invalid argument" 400), and the Mez summary is not needed from the
    # model here (it is a gold-side checksum; g2b scores daily cells). The
    # model simply doesn't return it; G2BTable.printed_totals stays None.
    return {
        "type": "OBJECT",
        "properties": {
            "rows": rows_schema,
        },
        "required": ["rows"],
        "propertyOrdering": ["rows"],
    }


class G2BRow(BaseModel):
    """One day-row from the g2b table call: `day` (the anchor, fix #2)
    instead of a model-computed calendar `date` - the calendar date is
    assembled later from extract_period()+reconcile_period() (fix #3), not
    read off the table itself."""
    day: int
    cells: dict[str, float | None] = {}
    flags: dict[str, str] = {}


class G2BTable(BaseModel):
    rows: list[G2BRow]
    printed_totals: dict[str, float] | None = None
    # Fix #5: a free confidence read, captured but never gated on. NOT
    # requested via responseLogprobs/logprobs (see _request_gemini_g2b's
    # docstring - the gate model 400s the whole call if those are sent), so
    # this stays None whenever the provider doesn't otherwise report a
    # candidate-level avgLogprobs; extract() never crashes on its absence.
    avg_logprobs: float | None = None


def _apply_barometer_reconstruction(table: G2BTable) -> G2BTable:
    """Fix #4, wired in: replace each barometer cell's printed low-order
    value with restore_thousands()'s mechanical reconstruction. If a
    printed value has no unique in-range reconstruction (e.g. a genuine
    period typesetting error - see gold/SELECTION.md's Julho 1886
    `printed_error` example), leave the raw low-order value in place and
    flag the column instead of raising - one unreconstructable cell must
    not fail the whole sheet."""
    for row in table.rows:
        for col in _BAROMETER_COLS:
            val = row.cells.get(col)
            if val is None:
                continue
            try:
                row.cells[col] = restore_thousands(val)
            except ValueError as e:
                row.flags[col] = f"barometer reconstruction ambiguous: {e}"
    return table


def validate_day_sequence(table: G2BTable) -> list[str]:
    """Fix #2's validator: surface a row/date shift STRUCTURALLY instead of
    silently renumbering. Returns one violation string per row whose `day`
    does not equal its 1-indexed position, plus one per duplicated `day`
    value. An empty list means the day sequence is clean (1, 2, 3, ...
    with no gaps or repeats)."""
    violations: list[str] = []
    seen: dict[int, int] = {}
    for i, row in enumerate(table.rows):
        expected = i + 1
        if row.day != expected:
            violations.append(
                f"row index {i}: expected day {expected}, got day {row.day} "
                "(row/date shift - see gold/SELECTION.md faithful-to-print convention)"
            )
        if row.day in seen:
            violations.append(f"day {row.day} is duplicated (rows {seen[row.day]} and {i})")
        else:
            seen[row.day] = i
    return violations


def _normalize_g2b_obj(obj: dict) -> dict:
    """Reuse the zero-shot path's non-numeric-cell recovery (a model
    writing a printed annotation like "Gottas" straight into a numeric
    cells slot) - the shape (`rows` list of dicts each with `cells`/
    `flags`) is identical for the g2b table, so the same repair applies."""
    return _normalize_non_numeric_cells(obj)


def _parse_g2b_response(text: str, day_count: int | None) -> G2BTable:
    """Parse a g2b table-call reply into a G2BTable, reusing the zero-shot
    path's JSON recovery (fence-stripping, trailing-comma cleanup, and
    trying every top-level JSON candidate - see _load_json_candidates).

    A row-count mismatch against the known `day_count` (when given) is an
    unrecoverable off-shape response per fix #1 - rather than silently
    guessing which row to drop or duplicate (exactly the structural-shift
    failure mode this strategy exists to eliminate), it is rejected as
    ExtractionParseError."""
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()

    candidates = _load_json_candidates(stripped)
    if not candidates:
        raise ExtractionParseError("could not parse g2b response as JSON: no valid JSON value found")

    last_error: Exception | None = None
    table: G2BTable | None = None
    for obj in candidates:
        if isinstance(obj, dict):
            obj = _normalize_g2b_obj(obj)
        try:
            table = G2BTable(**obj)
            break
        except (ValidationError, TypeError) as e:
            last_error = e
            continue

    if table is None:
        raise ExtractionParseError(
            f"g2b response JSON does not match G2BTable schema (tried {len(candidates)} "
            f"candidate JSON value(s)): {last_error}"
        ) from last_error

    if day_count is not None and len(table.rows) != day_count:
        raise ExtractionParseError(
            f"g2b response has {len(table.rows)} row(s), expected exactly {day_count} "
            "for this month - rejecting rather than guessing which row(s) to drop/add"
        )

    return table


def _request_gemini_g2b(
    endpoint: str, api_key: str, image_bytes: bytes, day_count: int | None = None,
) -> httpx.Response:
    """Build the g2b table-call request.

    Fix #5 (`responseLogprobs`/`logprobs` in generationConfig) is NOT sent:
    live-verified (Task 2 probe, 2026-09-01) via direct curl, the gate
    model (gemini-3.5-flash) 400s the ENTIRE request with `{"error":
    {"code": 400, "message": "Logprobs is not enabled for this model",
    "status": "INVALID_ARGUMENT"}}` whenever either field is present - this
    is not a per-field soft-reject, it fails the whole call. The same curl
    probe confirmed `responseSchema` (below, unchanged) is NOT implicated -
    a schema-only request (no logprobs fields) returns 200 with correctly
    structured output. `G2BTable.avg_logprobs` stays in the model (see its
    docstring) and stays None-safe downstream in `extract()` - Gemini may
    still report a candidate-level `avgLogprobs` without `responseLogprobs`
    being set, so it is still opportunistically captured when present."""
    gen_cfg = {
        "responseMimeType": "application/json",
        "responseSchema": g2b_response_schema(day_count),
    }
    body = {
        "system_instruction": {"parts": [{"text": G2B_SYSTEM_PROMPT}]},
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/png",
                                  "data": base64.b64encode(image_bytes).decode("ascii")}},
            ],
        }],
        "generationConfig": gen_cfg,
    }
    return httpx.post(endpoint, json=body,
                       headers={"User-Agent": USER_AGENT, "X-goog-api-key": api_key},
                       timeout=REQUEST_TIMEOUT_SECONDS)


# --- G2-B strategy: separate header/period call ------------------------------
#
# Fix #3: the main table call is no longer the date's source of truth. A
# small, separate call reads ONLY the page header (month name + year);
# reconcile_period then cross-checks it against the known consecutive-1886
# sequence rather than trusting either call blindly.

MONTHS_PT = {
    "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, "Maio": 5, "Junho": 6,
    "Julho": 7, "Agosto": 8, "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12,
}

# The header call reads a mostly-blank crop with a short line of text - far
# less content than the full table, hence its own (smaller) conservative
# cost estimate rather than reusing ESTIMATED_INPUT_TOKENS/OUTPUT_TOKENS.
# The image itself still costs roughly the same input tokens (we pass the
# whole page - no cropping logic in this task), but the output is a tiny
# fixed-shape JSON object instead of a full month of numbers.
ESTIMATED_PERIOD_INPUT_TOKENS = 1_500
ESTIMATED_PERIOD_OUTPUT_TOKENS = 50


def estimate_period_cost_usd(provider: str) -> float:
    prices = PRICES[provider]
    return (
        ESTIMATED_PERIOD_INPUT_TOKENS / 1_000_000 * prices["input"]
        + ESTIMATED_PERIOD_OUTPUT_TOKENS / 1_000_000 * prices["output"]
    )


PERIOD_SYSTEM_PROMPT = (
    "You are reading ONLY the printed header of a 19th-century Brazilian "
    "meteorological table page - the month name and year printed at the "
    "top (e.g. \"Janeiro de 1886\"). Do NOT read any table cell or row. "
    "Output ONLY JSON matching the provided response schema (no prose, no "
    "markdown fences): the year as a 4-digit integer, and the month as its "
    "Portuguese name exactly as printed (one of Janeiro, Fevereiro, "
    "Março, Abril, Maio, Junho, Julho, Agosto, Setembro, Outubro, "
    "Novembro, Dezembro)."
)


def _period_response_schema() -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "year": {"type": "INTEGER"},
            "month_name": {"type": "STRING", "enum": list(MONTHS_PT.keys())},
        },
        "required": ["year", "month_name"],
        "propertyOrdering": ["year", "month_name"],
    }


class _PeriodReading(BaseModel):
    year: int
    month_name: str


def _request_gemini_period(endpoint: str, api_key: str, image_bytes: bytes) -> httpx.Response:
    body = {
        "system_instruction": {"parts": [{"text": PERIOD_SYSTEM_PROMPT}]},
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/png",
                                  "data": base64.b64encode(image_bytes).decode("ascii")}},
            ],
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _period_response_schema(),
        },
    }
    return httpx.post(endpoint, json=body,
                       headers={"User-Agent": USER_AGENT, "X-goog-api-key": api_key},
                       timeout=REQUEST_TIMEOUT_SECONDS)


def _parse_period_response(text: str) -> tuple[int, int]:
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()

    candidates = _load_json_candidates(stripped)
    if not candidates:
        raise ExtractionParseError("could not parse period response as JSON: no valid JSON value found")

    last_error: Exception | None = None
    for obj in candidates:
        try:
            reading = _PeriodReading(**obj)
        except (ValidationError, TypeError) as e:
            last_error = e
            continue
        month = MONTHS_PT.get(reading.month_name)
        if month is None:
            last_error = ValueError(f"unrecognized Portuguese month name {reading.month_name!r}")
            continue
        return reading.year, month

    raise ExtractionParseError(
        f"period response JSON does not match schema (tried {len(candidates)} "
        f"candidate JSON value(s)): {last_error}"
    ) from last_error


def extract_period(image_bytes: bytes, provider: str, meter: CostMeter) -> tuple[int, int]:
    """Fix #3's small header/period call: reads ONLY the month/year printed
    at the top of the page. Charges `meter` before the network call, same
    charge-before-call contract as extract(). Gemini-only (the schema/
    logprobs machinery is Gemini-specific, same as the g2b table call)."""
    if provider not in _GEMINI_PROVIDERS:
        raise ValueError(
            f"extract_period is only implemented for gemini providers, got {provider!r}"
        )

    endpoint, api_key = _build_client_and_charge(
        provider, meter,
        cost_usd=estimate_period_cost_usd(provider),
        desc=f"{provider} period/header call (image~{ESTIMATED_PERIOD_INPUT_TOKENS}tok, "
             f"out~{ESTIMATED_PERIOD_OUTPUT_TOKENS}tok)",
    )

    response = _request_with_retry(provider, endpoint, api_key, image_bytes,
                                    requester=_request_gemini_period)
    response.raise_for_status()

    data = response.json()
    text = _extract_text_from_response(provider, data)
    return _parse_period_response(text)


# The corpus this gold set is drawn from (Revista do Observatório, Tomo I,
# Ano 1, 1886/1887 - see gold/SELECTION.md) only spans Dezembro 1885
# through Novembro 1886 in the 9 selected sheets, but the printed volume
# itself can run into early 1887 for later issues - so the year sanity
# check below is deliberately not a hardcoded "== 1886".
_KNOWN_CORPUS_YEARS = (1885, 1886, 1887)


def reconcile_period(
    pred: tuple[int, int], expected_prev: tuple[int, int] | None = None,
) -> tuple[tuple[int, int], str | None]:
    """Fix #3's cross-check: given the known consecutive-month sequence
    (each gold sheet is exactly one calendar month after the previous
    one), flag - and where possible OVERRIDE - an out-of-sequence period
    read from extract_period().

    With an `expected_prev` anchor (the previous sheet's already-reconciled
    (year, month)), any predicted period other than exactly prev+1 month is
    overridden to that expected value and flagged (this is what fixes the
    G1 wrong-year sheet, 14_41, once a prior sheet's period is known).
    Without an anchor (e.g. the very first sheet in a run), there is
    nothing to override FROM, so an out-of-corpus year is flagged but left
    unchanged - a human/downstream check, not a silent guess."""
    year, month = pred

    if expected_prev is not None:
        prev_year, prev_month = expected_prev
        if prev_month == 12:
            expected = (prev_year + 1, 1)
        else:
            expected = (prev_year, prev_month + 1)
        if (year, month) != expected:
            flag = (
                f"period read as {year}-{month:02d} but the known consecutive "
                f"sequence (previous sheet {prev_year}-{prev_month:02d}) expects "
                f"{expected[0]}-{expected[1]:02d} - overriding to expected"
            )
            return expected, flag
        return (year, month), None

    if year not in _KNOWN_CORPUS_YEARS:
        flag = (
            f"period read as {year}-{month:02d} but the corpus only spans "
            f"{_KNOWN_CORPUS_YEARS} - no prior-sheet anchor available to override, "
            "flagging only"
        )
        return (year, month), flag

    return (year, month), None


def assemble_sheet(
    table: G2BTable, *, year: int, month: int,
    source: str, bib: str, page: int, station: str, columns: list[str],
) -> Sheet:
    """Stitch a g2b day-only table (fix #2's `day` anchor) together with a
    reconciled (year, month) (fix #3) into a real gold-shaped Sheet, so
    wrb.metrics.score() can compare it against gold like any other Sheet.
    This is the one place a calendar `date` gets constructed for the g2b
    path - the table call itself never determines it (see G2B_SYSTEM_PROMPT
    and extract_period's docstring)."""
    rows = [
        Row(date=f"{year:04d}-{month:02d}-{r.day:02d}", cells=dict(r.cells), flags=dict(r.flags))
        for r in table.rows
    ]
    return Sheet(
        source=source, bib=bib, page=page, station=station,
        period=f"{year:04d}-{month:02d}",
        columns=columns, rows=rows,
        printed_totals=table.printed_totals,
    )


def _build_client_and_charge(
    provider: str,
    meter: CostMeter,
    *,
    cost_usd: float | None = None,
    desc: str | None = None,
) -> tuple[str, str]:
    """Validate provider, assert_personal() on endpoint + env var value, and
    charge the meter's conservative pre-call estimate. Returns (endpoint,
    api_key). Raises CapExceeded (propagated from meter.charge) BEFORE any
    network call is made if this would bust the cap.

    `cost_usd`/`desc` let a caller other than the plain zero-shot table call
    (e.g. the smaller g2b header/period call - see extract_period) charge a
    different conservative estimate under its own ledger description,
    without duplicating the provider/endpoint/env-var validation above."""
    if provider not in PRICES:
        raise ValueError(f"unknown provider {provider!r}; expected one of {sorted(PRICES)}")

    endpoint = ENDPOINTS[provider]
    assert_personal(endpoint)

    env_name = ENV_VARS[provider]
    assert_personal(env_name)
    api_key = os.environ.get(env_name, "")
    assert_personal(api_key)

    charge_usd = cost_usd if cost_usd is not None else estimate_cost_usd(provider)
    charge_desc = desc or (
        f"{provider} extract call (image~{ESTIMATED_INPUT_TOKENS}tok, "
        f"out~{ESTIMATED_OUTPUT_TOKENS}tok)"
    )
    meter.charge(charge_desc, charge_usd)

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


def _request_with_retry(
    provider: str, endpoint: str, api_key: str, image_bytes: bytes,
    requester=None,
) -> httpx.Response:
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
    it" that is specific to timeouts, not retries in general.

    `requester` optionally overrides the provider's default zero-shot
    request-builder (_REQUESTERS[provider]) - used by the g2b table call
    and the period/header call, which POST a different request body to
    the same provider/endpoint (see _request_gemini_g2b,
    _request_gemini_period) but want the identical retry/backoff
    contract."""
    requester = requester or _REQUESTERS[provider]
    last_response: httpx.Response | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requester(endpoint, api_key, image_bytes)
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


def extract(
    image_bytes: bytes, provider: str, meter: CostMeter,
    strategy: str = "zero_shot", *, day_count: int | None = None,
) -> Sheet | G2BTable:
    """Extract a table from an image using the named provider.

    `strategy="zero_shot"` (the default, unchanged since Task 10/11) is the
    original single free-form-JSON call - returns a `Sheet` whose own
    generation determines both the date and the barometer reconstruction.

    `strategy="g2b"` (the G2-B structural-error strategy - see the plan's
    Task 1 and the block of code above this function) is Gemini-only and
    applies all four research-backed fixes to the MAIN TABLE call: a
    schema-enforced response shape pinned to `day_count` rows (fix #1), a
    `day`-anchored row shape validated separately by
    `validate_day_sequence` (fix #2 - NOT run automatically here; the
    caller decides what to do with a shifted sheet), deterministic
    barometer-prefix reconstruction applied to the parsed result before it
    is returned (fix #4), and an opportunistic candidate-level `avgLogprobs`
    (when the provider reports one) captured onto `G2BTable.avg_logprobs`
    (fix #5) - `responseLogprobs`/`logprobs` are deliberately NOT requested
    (live-verified, Task 2 probe 2026-09-01: the gate model 400s the whole
    call if either is set - see `_request_gemini_g2b`'s docstring), so this
    field is commonly None and every caller must treat it as optional. It
    returns a `G2BTable`
    (day-indexed, no calendar date) rather than a `Sheet` - fix #3 moves
    the calendar date out of this call entirely; combine the result with
    `extract_period`+`reconcile_period` via `assemble_sheet` to get a
    `Sheet` for `wrb.metrics.score()`.

    Charges `meter` with a conservative pre-call cost estimate BEFORE the
    network request is issued (so a call that would bust the US$ cap never
    goes out at all - see CostMeter.charge / CapExceeded), for BOTH
    strategies. Every endpoint URL and env-var name/value is passed
    through assert_personal() at client-construction time so a Desert Ant
    identifier can never leak into a personal-billing call.

    A 429 or 503 is retried with exponential backoff (see
    _request_with_retry) as a safety net; any other error status is raised
    immediately via raise_for_status() - after the charge has already
    landed, for both strategies.
    """
    if strategy == "zero_shot":
        endpoint, api_key = _build_client_and_charge(provider, meter)
        response = _request_with_retry(provider, endpoint, api_key, image_bytes)
        response.raise_for_status()
        data = response.json()
        text = _extract_text_from_response(provider, data)
        return _parse_response(text)

    if strategy == "g2b":
        if provider not in _GEMINI_PROVIDERS:
            raise ValueError(
                f"strategy='g2b' is only implemented for gemini providers, got {provider!r}"
            )
        endpoint, api_key = _build_client_and_charge(
            provider, meter,
            desc=f"{provider} g2b table call (image~{ESTIMATED_INPUT_TOKENS}tok, "
                 f"out~{ESTIMATED_OUTPUT_TOKENS}tok, schema-enforced)",
        )
        requester = partial(_request_gemini_g2b, day_count=day_count)
        response = _request_with_retry(provider, endpoint, api_key, image_bytes, requester=requester)
        response.raise_for_status()

        data = response.json()
        text = _extract_text_from_response(provider, data)
        table = _parse_g2b_response(text, day_count)
        table = _apply_barometer_reconstruction(table)
        try:
            table.avg_logprobs = data["candidates"][0].get("avgLogprobs")
        except (KeyError, IndexError, TypeError):
            table.avg_logprobs = None
        return table

    raise ValueError(f"unknown strategy {strategy!r}; expected 'zero_shot' or 'g2b'")
