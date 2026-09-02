"""Multi-resolution zoom cross-check (G3 Task 1b).

G3 Task 1 (self-consistency consensus, see wrb.vlm.consensus_extract +
wrb.qc.flag_violations) got the frozen-gold aggregate to 99.06% cell_acc
(36/3822 wrong cells, bench/g3/consensus-gold.json) but flagged NONE of
those 36 - they are CONSISTENT last-digit misreads: in physical range,
inside the Mez-checksum tolerance, and identical across all 3 consensus
reads, so neither consensus-disagreement nor wrb.qc's validators ever see
them. This module adds a SECOND, independent read at much higher
resolution - crop each day-row out of the full page and upscale it
3-4x - on the theory that a misread glyph that survives three full-page
reads at normal resolution might still resolve correctly when the model
sees just that row at 3-4x linear zoom. Comparing the two independent
reads (full-page consensus vs. zoomed row re-read) turns any residual
disagreement into an external SUSPECT signal, with the zoom read itself as
the proposed correction.

This module has three pieces, kept deliberately separate and each
independently testable:

  1. Row-band CROP GEOMETRY (`detect_table_borders`, `row_band_geometry`,
     `crop_row_bands`) - pure PIL, no network calls. There is no OCR/layout
     ground truth for where each day's row sits on the page, so this is an
     APPROXIMATION, not an exact per-glyph crop (see `crop_row_bands`'s
     docstring for exactly how it's derived and calibrated).
  2. The ZOOM RE-READ itself (`zoom_read_row`, `zoom_reread_sheet`) - one
     small Gemini structured-output call per row-band crop, reusing
     wrb.vlm's request/retry/parsing machinery and exact `_CELL_KEYS`/
     barometer-reconstruction conventions so the two reads are directly
     comparable cell-for-cell.
  3. RECONCILIATION (`reconcile`) - a pure diff between the full-page
     consensus cells and the zoom-reread cells, per (day, column): any
     pair disagreeing by more than `wrb.metrics.TOL` is a SUSPECT, and the
     zoom value is the proposed correction.
"""

import base64
import io
import json
from functools import partial

import httpx
from PIL import Image
from pydantic import BaseModel, ValidationError

from wrb.costs import CostMeter
from wrb.metrics import TOL as CELL_TOL
from wrb.reconstruct import restore_thousands
from wrb.vlm import (
    _BAROMETER_COLS,
    _CELL_KEYS,
    _FENCE_RE,
    _GEMINI_PROVIDERS,
    _build_client_and_charge,
    _cell_properties_schema,
    _load_json_candidates,
    _request_with_retry,
    _extract_text_from_response,
    ExtractionParseError,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)

# --- 1. Row-band crop geometry ------------------------------------------------
#
# The table's DAY column (leftmost, "DATA") prints a stacked, perfectly
# regular sequence 1, 2, 3, ... with a uniform line pitch - a much cleaner
# signal than trying to detect per-row RULED lines, since this source only
# ever rules a horizontal line above the first day row (below the column
# headers + a units subheader like "mm mm mm ... o o o mm") and a second
# one below the last day row (above the "Mez" month-summary row). There is
# no ruled line between individual day rows.
#
# Calibration (this task's own probe sheets, pages 22 and 75 - see the
# Task 1b report): using dark-pixel-density peaks in the first numeric
# column ("Medias diurnas" under BAROMETRO) to find the true row centers,
# the ruled interval [border_top, border_bottom) behaves like
# (day_count + 2) equal-height slots, not day_count - one extra slot above
# day 1 for the units-subheader line, and roughly one slot of margin below
# the last day row before its own border. This was verified against both
# probe sheets' actual row-peak positions (page 22: predicted vs. measured
# row-center error <=5px against a ~28px row pitch; page 75: a similar
# small constant offset <=8px) - close enough, combined with the generous
# per-band padding below, to keep the target row's text safely inside its
# band even though this is an approximation, not an exact per-row ground
# truth.
_ROW_COL_X_FRAC = (0.1552, 0.2090)  # "Medias diurnas" column, as a fraction of page width
# These windows are deliberately narrow, not just "somewhere in the upper/
# lower half of the page": the multi-row nested column header (DATA /
# BAROMETRO A 0 / Medias diurnas-Maximas-Minimas / "mm") draws SEVERAL
# other full-width-of-column ruled lines above the true top border, at
# comparable or even higher darkness (live-measured on both probe sheets:
# page 22 has candidate lines at y-fractions 0.173/0.210/0.264, page 75 at
# 0.151/0.184/0.222/0.275 - the true border is always the LAST of these,
# not the darkest). Likewise below the table, the Mez row and the
# footnote-separator rule sit close enough below the true bottom border to
# tie or beat it on raw darkness (page 22: 0.634 true vs. a 0.656
# distractor; page 75: 0.642 true vs. a 0.673 distractor). Narrowing each
# window to bracket only the true border (calibrated against pages 22 and
# 75 - this task's own probe sheets) turns "pick the darkest row in the
# window" from ambiguous into reliable. A sheet whose header block is
# taller/shorter than these two would need re-calibration - this is an
# approximation tuned to this corpus, not a general layout detector.
_TOP_BORDER_Y_FRAC = (0.24, 0.32)     # search window for the rule above day 1
_BOTTOM_BORDER_Y_FRAC = (0.58, 0.65)  # search window for the rule below the last day row
_TABLE_X_FRAC = (0.09, 0.94)  # approximate full table width (all columns), as a fraction of page width
_DARK_THRESHOLD = 210  # 8-bit grayscale; page background is a light cream, ink is well below this


def _dark_row_counts(gray: Image.Image, x0: int, x1: int) -> list[int]:
    """Per-row count of pixels darker than `_DARK_THRESHOLD` within
    `gray`'s `[x0, x1)` column band. Pure PIL (`.load()` pixel access) -
    deliberately no numpy dependency, since this project's only declared
    image dependency is Pillow (see pyproject.toml)."""
    px = gray.load()
    height = gray.height
    counts = [0] * height
    for y in range(height):
        c = 0
        for x in range(x0, x1):
            if px[x, y] < _DARK_THRESHOLD:
                c += 1
        counts[y] = c
    return counts


def detect_table_borders(image: Image.Image) -> tuple[int, int]:
    """Auto-detect the two ruled horizontal lines bracketing the table's
    day rows (the line above day 1, and the line below the last day row -
    see the module docstring), by finding the darkest row within each
    search window (`_TOP_BORDER_Y_FRAC`/`_BOTTOM_BORDER_Y_FRAC`) restricted
    to the `_ROW_COL_X_FRAC` column band. A solid ruled line reliably reads
    as the single darkest row in its window (it spans the whole column
    band unbroken, unlike sparse digit strokes) - validated live against
    both probe sheets (pages 22 and 75), see the module docstring.

    Returns (border_top_y, border_bottom_y) in pixel coordinates."""
    gray = image.convert("L")
    width, height = gray.size
    x0 = round(_ROW_COL_X_FRAC[0] * width)
    x1 = round(_ROW_COL_X_FRAC[1] * width)
    counts = _dark_row_counts(gray, x0, x1)

    top_lo, top_hi = (round(f * height) for f in _TOP_BORDER_Y_FRAC)
    bottom_lo, bottom_hi = (round(f * height) for f in _BOTTOM_BORDER_Y_FRAC)
    border_top = max(range(top_lo, top_hi), key=lambda y: counts[y])
    border_bottom = max(range(bottom_lo, bottom_hi), key=lambda y: counts[y])
    return border_top, border_bottom


def row_band_geometry(
    image_size: tuple[int, int],
    day_count: int,
    border_top: int,
    border_bottom: int,
    *,
    band_height_factor: float = 1.8,
    table_x_frac: tuple[float, float] = _TABLE_X_FRAC,
) -> list[tuple[int, int, int, int]]:
    """Pure geometry: given the ruled-border y-positions bracketing the
    table's day rows (see `detect_table_borders`) and the month's
    `day_count`, return one `(x0, y0, x1, y1)` pixel box per day
    (1-indexed, in day order) wide enough to cover every printed column
    (`table_x_frac` of the page width) and tall enough
    (`band_height_factor` times the estimated row pitch, centered on the
    estimated row center) to comfortably contain that day's row even
    though the center estimate is only approximate (see the module
    docstring's calibration note) - `band_height_factor=1.8` means each
    band deliberately overlaps its neighbours by about 0.4 row-heights on
    each side, trading a bit of neighbouring-row bleed (the zoom-read
    prompt handles this - see `ZOOM_ROW_SYSTEM_PROMPT_TEMPLATE`) for
    near-zero risk of clipping the target row itself.

    Always returns exactly `day_count` boxes, in day order (index 0 is
    day 1). Boxes are clipped to `image_size`'s bounds."""
    if day_count < 1:
        raise ValueError(f"day_count must be >= 1, got {day_count}")
    width, height = image_size
    pitch = (border_bottom - border_top) / (day_count + 2)
    half = band_height_factor * pitch / 2
    x0 = max(0, round(table_x_frac[0] * width))
    x1 = min(width, round(table_x_frac[1] * width))

    boxes: list[tuple[int, int, int, int]] = []
    for day in range(1, day_count + 1):
        center = border_top + (day + 1) * pitch
        y0 = max(0, round(center - half))
        y1 = min(height, round(center + half))
        boxes.append((x0, y0, x1, y1))
    return boxes


def crop_row_bands(
    image_bytes: bytes,
    day_count: int,
    *,
    band_height_factor: float = 1.8,
    scale: float = 3.5,
    border_top: int | None = None,
    border_bottom: int | None = None,
) -> list[bytes]:
    """Produce `day_count` PNG-encoded crops, one per day row (index 0 =
    day 1), each upscaled `scale`x with PIL LANCZOS resampling - the
    "high-zoom re-read" input.

    `border_top`/`border_bottom` are auto-detected via
    `detect_table_borders` when not given; passing them explicitly lets a
    caller override the auto-detection (or a test supply exact,
    known-good values) without re-deriving them from the image."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if border_top is None or border_bottom is None:
        auto_top, auto_bottom = detect_table_borders(image)
        border_top = auto_top if border_top is None else border_top
        border_bottom = auto_bottom if border_bottom is None else border_bottom

    boxes = row_band_geometry(
        image.size, day_count, border_top, border_bottom,
        band_height_factor=band_height_factor,
    )

    crops: list[bytes] = []
    for box in boxes:
        crop = image.crop(box)
        if scale != 1.0:
            new_size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
            crop = crop.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        crops.append(buf.getvalue())
    return crops


# --- 2. Zoom re-read: one small structured-output call per row-band ----------
#
# Reuses wrb.vlm's request/retry/parsing machinery (charge-before-call,
# 429/503 backoff, fence-stripping + multi-candidate JSON recovery) and its
# exact `_CELL_KEYS`/barometer-reconstruction conventions, so this read is
# directly comparable cell-for-cell against the g2b/consensus read - see
# wrb.vlm's module docstring for why those conventions exist.

# Each row-band crop is small (one table row, upscaled) - far less image
# content and a far smaller JSON reply than the full-page g2b table call,
# hence its own (smaller) conservative cost estimate.
ESTIMATED_ZOOM_INPUT_TOKENS = 500
ESTIMATED_ZOOM_OUTPUT_TOKENS = 400


def estimate_zoom_cost_usd(provider: str) -> float:
    from wrb.vlm import PRICES
    prices = PRICES[provider]
    return (
        ESTIMATED_ZOOM_INPUT_TOKENS / 1_000_000 * prices["input"]
        + ESTIMATED_ZOOM_OUTPUT_TOKENS / 1_000_000 * prices["output"]
    )


ZOOM_ROW_SYSTEM_PROMPT_TEMPLATE = (
    "You are re-reading, at HIGH ZOOM, one row-band cropped and enlarged from "
    "a printed 19th-century Brazilian meteorological table. Because row "
    "boundaries are estimated, not exact, this crop may also show part of "
    "the row above or below the target row. Report ONLY the row whose "
    "printed day-of-month number (the leftmost \"DATA\" column) is EXACTLY "
    "{day} - ignore any other row partially visible in the crop. "
    "Transcribe faithfully to what is PRINTED - never guess, infer, round, "
    "or \"correct\" a value that looks physically impossible; the literal "
    "printed glyph is always what is wanted, even when it looks wrong. "
    "Output ONLY JSON matching the provided response schema (no prose, no "
    "markdown fences). "
    "The `cells` dict MUST use EXACTLY these keys, one per printed column, "
    "in this order left-to-right on the page - do not invent, translate, "
    "abbreviate, or rename them: "
    f"{json.dumps(_CELL_KEYS)}. "
    "Rules: "
    "1) If a cell is illegible, set it to null. "
    "2) Decimal points, not commas: `70,9` in the source means `70.9`. "
    "3) BAROMETER COLUMNS "
    f"({', '.join(_BAROMETER_COLS)}): this source elides the leading "
    "hundreds(+thousands) digit after the table's first row. Do NOT try to "
    "reconstruct the elided digit yourself - report EXACTLY the low-order "
    "digits printed on the page for this row as a plain number, e.g. "
    "`51.69` stays `51.69`. Reconstruction is done mechanically downstream."
)


def _zoom_row_response_schema() -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "day": {"type": "INTEGER"},
            "cells": {
                "type": "OBJECT",
                "properties": _cell_properties_schema(),
                "required": _CELL_KEYS,
                "propertyOrdering": _CELL_KEYS,
            },
        },
        "required": ["day", "cells"],
        "propertyOrdering": ["day", "cells"],
    }


class ZoomRowReading(BaseModel):
    day: int
    cells: dict[str, float | None] = {}


def _request_gemini_zoom_row(endpoint: str, api_key: str, image_bytes: bytes, day: int) -> httpx.Response:
    body = {
        "system_instruction": {"parts": [{"text": ZOOM_ROW_SYSTEM_PROMPT_TEMPLATE.format(day=day)}]},
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/png",
                                  "data": base64.b64encode(image_bytes).decode("ascii")}},
            ],
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _zoom_row_response_schema(),
        },
    }
    return httpx.post(endpoint, json=body,
                       headers={"User-Agent": USER_AGENT, "X-goog-api-key": api_key},
                       timeout=REQUEST_TIMEOUT_SECONDS)


def _apply_barometer_reconstruction_to_cells(cells: dict[str, float | None]) -> dict[str, float | None]:
    """Cell-dict equivalent of wrb.vlm._apply_barometer_reconstruction (that
    one operates on a G2BTable's rows; the zoom re-read works one bare
    cells-dict at a time). An unreconstructable printed value (no unique
    in-range candidate) is left as the raw low-order value rather than
    raising - one ambiguous cell must not fail the whole row's re-read."""
    out = dict(cells)
    for col in _BAROMETER_COLS:
        val = out.get(col)
        if val is None:
            continue
        try:
            out[col] = restore_thousands(val)
        except ValueError:
            pass
    return out


def _parse_zoom_row_response(text: str, expected_day: int) -> dict[str, float | None]:
    """Parse a zoom row-band reply into a cells dict, reusing wrb.vlm's
    fence-stripping + multi-candidate JSON recovery. Raises
    ExtractionParseError if nothing parses, or if the model's own reported
    `day` does not match `expected_day` - a mismatch means the model read a
    neighbouring row instead of the target one (see the prompt's overlap
    warning), and this function refuses to silently attribute that
    neighbour's values to `expected_day` rather than guessing."""
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()

    candidates = _load_json_candidates(stripped)
    if not candidates:
        raise ExtractionParseError("could not parse zoom row response as JSON: no valid JSON value found")

    last_error: Exception | None = None
    reading: ZoomRowReading | None = None
    for obj in candidates:
        try:
            reading = ZoomRowReading(**obj)
            break
        except (ValidationError, TypeError) as e:
            last_error = e
            continue

    if reading is None:
        raise ExtractionParseError(
            f"zoom row response JSON does not match schema (tried {len(candidates)} "
            f"candidate JSON value(s)): {last_error}"
        ) from last_error

    if reading.day != expected_day:
        raise ExtractionParseError(
            f"zoom row response reported day={reading.day}, expected day={expected_day} "
            "(the crop's row-band overlap likely landed on a neighbouring row instead - "
            "refusing to attribute its values to the requested day)"
        )

    return _apply_barometer_reconstruction_to_cells(reading.cells)


def zoom_read_row(
    image_bytes: bytes, provider: str, meter: CostMeter, day: int,
) -> dict[str, float | None]:
    """Zoom-reread ONE row-band crop for the given `day`. Charges `meter`
    BEFORE the network call (same charge-before-call contract as
    wrb.vlm.extract). Gemini-only, same reason as wrb.vlm's schema-enforced
    calls (the schema/logprobs machinery is Gemini-specific)."""
    if provider not in _GEMINI_PROVIDERS:
        raise ValueError(f"zoom_read_row is only implemented for gemini providers, got {provider!r}")

    endpoint, api_key = _build_client_and_charge(
        provider, meter,
        cost_usd=estimate_zoom_cost_usd(provider),
        desc=f"{provider} zoom row-band re-read call (day={day}, "
             f"image~{ESTIMATED_ZOOM_INPUT_TOKENS}tok, out~{ESTIMATED_ZOOM_OUTPUT_TOKENS}tok)",
    )
    requester = partial(_request_gemini_zoom_row, day=day)
    response = _request_with_retry(provider, endpoint, api_key, image_bytes, requester=requester)
    response.raise_for_status()

    data = response.json()
    text = _extract_text_from_response(provider, data)
    return _parse_zoom_row_response(text, expected_day=day)


def zoom_reread_sheet(
    page_image_bytes: bytes, provider: str, meter: CostMeter, day_count: int,
    *, band_height_factor: float = 1.8, scale: float = 3.5,
    border_top: int | None = None, border_bottom: int | None = None,
) -> tuple[dict[int, dict[str, float | None]], list[str]]:
    """Crop every day's row-band out of `page_image_bytes` (`crop_row_bands`)
    and zoom-reread each one (`zoom_read_row`). Robust to a single row's
    read failing outright (a parse error, a day mismatch, an HTTP error) -
    that day is skipped and its error recorded, the rest proceed; this
    mirrors wrb.vlm.consensus_extract's per-run robustness, at per-row
    granularity here instead of per-whole-table-call.

    Returns `(cells_by_day, errors)`: `cells_by_day` maps day (1-indexed)
    to its zoom-reread cells dict for every day that succeeded;  `errors`
    is one human-readable string per day that failed. CapExceeded is never
    swallowed - it must stop the whole re-read, not just one row."""
    from wrb.costs import CapExceeded

    crops = crop_row_bands(
        page_image_bytes, day_count,
        band_height_factor=band_height_factor, scale=scale,
        border_top=border_top, border_bottom=border_bottom,
    )

    cells_by_day: dict[int, dict[str, float | None]] = {}
    errors: list[str] = []
    for day, crop_bytes in enumerate(crops, start=1):
        try:
            cells_by_day[day] = zoom_read_row(crop_bytes, provider, meter, day)
        except CapExceeded:
            raise
        except Exception as e:  # noqa: BLE001 - one bad row must not sink the sheet
            errors.append(f"day {day}: {type(e).__name__}: {e}")
    return cells_by_day, errors


# --- 3. Reconciliation: full-page consensus vs. zoom re-read -----------------

def _disagree(a: float | None, b: float | None, tol: float) -> bool:
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    return abs(a - b) > tol


def reconcile(
    consensus_cells_by_day: dict[int, dict[str, float | None]],
    zoom_cells_by_day: dict[int, dict[str, float | None]],
    *, tol: float = CELL_TOL,
) -> list[dict]:
    """Pure diff between the full-page consensus read and the zoom re-read,
    per (day, column). For every day present in BOTH inputs, any column
    where the two reads disagree by more than `tol` (default:
    wrb.metrics.TOL, the same tolerance `wrb.metrics.score` uses to call a
    cell "correct") is a SUSPECT: a cell the two independent,
    different-resolution reads could not agree on. A day missing from
    `zoom_cells_by_day` (e.g. that row's zoom-reread failed - see
    `zoom_reread_sheet`'s `errors`) is skipped entirely, not treated as a
    disagreement on every column.

    Returns one dict per suspect: `{"day", "col", "consensus_value",
    "zoom_value", "proposed_value"}` - `proposed_value` is always the zoom
    value (the plan's "propose the zoom read as the correction"), in day
    order and then column order for determinism."""
    suspects: list[dict] = []
    for day in sorted(consensus_cells_by_day):
        zoom_cells = zoom_cells_by_day.get(day)
        if zoom_cells is None:
            continue
        cons_cells = consensus_cells_by_day[day]
        for col in cons_cells:
            if col not in zoom_cells:
                continue
            cval, zval = cons_cells[col], zoom_cells[col]
            if _disagree(cval, zval, tol):
                suspects.append({
                    "day": day, "col": col,
                    "consensus_value": cval, "zoom_value": zval,
                    "proposed_value": zval,
                })
    return suspects
