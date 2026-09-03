"""G4.2 - local (offline) extraction engine with the SAME downstream
interface as the API path, so it drops into assemble_sheet / barometer
reconstruction / qc / metrics unchanged.

    extractor = LocalExtractor(reader)          # reader: any RowReader
    table = extractor.extract_table(image_bytes, day_count)   # G2BTable
    sheet = extractor.extract(image_bytes, day_count, year=..., month=..., ...)  # Sheet

Structure is deterministic (wrb.rows finds the day rows; the day anchor is
the row index, never a model guess - row shifts are impossible by
construction); the model only READS one row crop at a time. A `RowReader`
returns the row as text; `parse_row_target` turns it into the 14 cells.

Row TEXT FORMAT (also the training target): the 14 columns in COLUMNS
order, separated by " | ", blanks written as "null", plus an optional
trailing " | dir=<wind direction text>" carried into flags. Example:
    "754.44 | 756.18 | 752.60 | 24.1 | 27.3 | 22.2 | 18.7 | 83.9 | 2.4 | 8.0 | 0.5 | 2.7 | 1.7 | 3 | dir=O. variavel"
Barometer cells are written as printed (elided thousands) and restored by
_apply_barometer_reconstruction, exactly as the API path does.

No torch import at module level: readers wrap the model; this module is pure.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Protocol

from PIL import Image

from wrb.dataset import COLUMNS, crop_boxes
from wrb.gold import Sheet
from wrb.rows import RowLocation, locate_day_rows
from wrb.vlm import G2BRow, G2BTable, _apply_barometer_reconstruction, assemble_sheet

SEP = " | "
NULL = "null"


class RowReader(Protocol):
    def read_row(self, crop: Image.Image) -> str: ...


def _fmt(v: float | None) -> str:
    if v is None:
        return NULL
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s else "0"


def row_target(cells: dict[str, float | None], flags: dict[str, str] | None = None) -> str:
    """Training target text for one row (see module docstring)."""
    parts = [_fmt(cells.get(c)) for c in COLUMNS]
    d = (flags or {}).get("wind_dir")
    if d:
        parts.append(f"dir={d}")
    return SEP.join(parts)


def parse_row_target(text: str) -> tuple[dict[str, float | None], dict[str, str], list[str]]:
    """Inverse of row_target. Returns (cells, flags, problems). Tolerant:
    fewer tokens -> missing columns None + a problem note; extra tokens
    ignored + a note; unparsable token -> None + note."""
    problems: list[str] = []
    flags: dict[str, str] = {}
    toks = [t.strip() for t in text.strip().strip("`").split("|")]
    if toks and toks[-1].startswith("dir="):
        flags["wind_dir"] = toks[-1][4:].strip()
        toks = toks[:-1]
    if len(toks) < len(COLUMNS):
        problems.append(f"{len(toks)} tokens, expected {len(COLUMNS)}")
    elif len(toks) > len(COLUMNS):
        problems.append(f"{len(toks)} tokens, expected {len(COLUMNS)} (extra ignored)")
    cells: dict[str, float | None] = {}
    for i, col in enumerate(COLUMNS):
        tok = toks[i] if i < len(toks) else NULL
        if tok.lower() in (NULL, "", "-", "—", "...", "…"):
            cells[col] = None
            continue
        try:
            cells[col] = float(tok.replace(",", "."))
        except ValueError:
            cells[col] = None
            problems.append(f"{col}: unparsable {tok!r}")
    return cells, flags, problems


@dataclass
class LocalExtractor:
    reader: RowReader
    scale: float = 2.0
    last_location: RowLocation | None = None
    last_problems: dict[int, list[str]] = field(default_factory=dict)

    def extract_table(self, image_bytes: bytes, day_count: int) -> G2BTable:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        loc = locate_day_rows(image, day_count)
        self.last_location = loc
        if not loc.ok:
            raise RowLocationError(loc.reason)
        crops = crop_boxes(image, loc.day_boxes, loc.skew_deg, scale=self.scale)
        rows: list[G2BRow] = []
        self.last_problems = {}
        for day, crop in enumerate(crops, start=1):
            text = self.reader.read_row(crop)
            cells, flags, problems = parse_row_target(text)
            if problems:
                self.last_problems[day] = problems
                flags["parse"] = "; ".join(problems)
            rows.append(G2BRow(day=day, cells=cells, flags=flags))
        return _apply_barometer_reconstruction(G2BTable(rows=rows))

    def extract(self, image_bytes: bytes, day_count: int, *, year: int, month: int, source: str,
                bib: str, page: int, station: str, columns: list[str] | None = None) -> Sheet:
        table = self.extract_table(image_bytes, day_count)
        return assemble_sheet(table, year=year, month=month, source=source, bib=bib, page=page,
                              station=station, columns=columns or list(COLUMNS))


class RowLocationError(RuntimeError):
    pass
