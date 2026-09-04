"""G4 synthetic rows by CELL MIXING (real glyphs, new combinations).

The scarce resource is volume-14 rows (61 real ones; gold is all volume
14). Rendering fake tables with fonts risks teaching the wrong typography.
Instead: on a real page, find the vertical rules that separate the table's
columns, cut every located day row into its cells, and build NEW rows by
taking each column's cell from a random real row of the same page. Every
cell is a genuine printed cell with a genuine label (the transcription of
the row it came from), so the label of the mixed row is exact by
construction, and the model sees the real ink, real column widths, real
rules - just numbers it has not seen in that arrangement.

Gold pages are never sources (the leakage guard applies to the synthetic
manifest too). Photometric jitter (contrast, blur, noise, +-1 px shift) on
top adds robustness to scan variation.

Column detection: vertical rules = x positions continuously inked across
most of the table body (the same cell trick as `wrb.rows.horizontal_rules`,
transposed). A page is used only if the number of detected cell boundaries
is consistent with the 16 printed columns (day + 14 numeric + wind text);
otherwise it is skipped, never guessed.
"""

from __future__ import annotations

import hashlib
import io
import random
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter

from wrb.dataset import COLUMNS, RowExample, png_bytes
from wrb.rows import RowLocation

# printed cell order on a Revista page: day | 14 numeric cells with the wind
# DIRECTION text column inserted after humidity | ...
PRINTED_ORDER = ["day", "pressure", "pressure_max", "pressure_min", "tmean", "tmax", "tmin", "vapor",
                 "humidity", "wind_dir", "wind_force", "cloudiness", "precip", "evap_sol", "evap_sombra", "ozone"]


@dataclass
class ColumnLayout:
    bounds: list[int]           # x boundaries in page coords, len = len(PRINTED_ORDER) + 1
    body: tuple[int, int]       # y range of the day rows


def column_gaps(gray: Image.Image, x0: int, x1: int, y0: int, y1: int, thr: int, *,
                min_gap: int = 5, rule_frac: float = 0.55, dilate: int = 2) -> list[tuple[int, int]]:
    """Vertical whitespace bands across the whole body [y0, y1): x ranges
    where no row has ink at the text threshold, AFTER masking the vertical
    rules (columns inked over > rule_frac of the body height, dilated). A
    separator is then "rule inside whitespace", which reads as one clean
    gap whether the rule printed dark or faint."""
    strip = gray.crop((x0, y0, x1, y1)).point(lambda v: 255 if v < thr else 0, mode="L")
    w = x1 - x0
    col = strip.resize((w, 1), Image.BOX).load()
    frac = [col[x, 0] / 255 for x in range(w)]
    rule = [f > rule_frac for f in frac]
    masked = [any(rule[max(0, x - dilate):x + dilate + 1]) for x in range(w)]
    ink = [frac[x] > 0.01 and not masked[x] for x in range(w)]
    gaps: list[tuple[int, int]] = []
    start = None
    for x, has in enumerate(ink + [True]):
        if not has and start is None:
            start = x
        elif has and start is not None:
            if x - start >= min_gap:
                gaps.append((start + x0, x + x0))
            start = None
    return gaps


def column_bounds_from_gaps(gaps: list[tuple[int, int]], n_cells: int) -> list[int] | None:
    """Turn separator gaps into n_cells+1 boundaries. Interior gaps become
    one boundary at their centre; a gap much wider than the median (an
    entirely blank printed column, e.g. evap_sol in vols 15/16) is split
    into two boundaries so the blank cell keeps its own slot. Returns None
    when the count does not come out."""
    if len(gaps) < 3:
        return None
    inner = gaps[1:-1]
    widths = sorted(b - a for a, b in inner)
    med = widths[len(widths) // 2] if widths else 0
    bounds = [gaps[0][1]]  # right edge of the left margin gap
    for a, b in inner:
        if med and (b - a) > 2.6 * med:
            third = (b - a) // 3
            bounds += [a + third, b - third]
        else:
            bounds.append((a + b) // 2)
    bounds.append(gaps[-1][0])  # left edge of the right margin gap
    return bounds if len(bounds) == n_cells + 1 else None


def column_layout(image: Image.Image, loc: RowLocation, thr: int) -> ColumnLayout | None:
    """Cell boundaries from the whitespace between printed columns across
    the located day rows. None unless exactly len(PRINTED_ORDER)+1 come out."""
    gray = image.convert("L")
    if loc.skew_deg:
        gray = gray.rotate(loc.skew_deg, resample=Image.BICUBIC, fillcolor=255)
    x0, y_top, x1, _ = loc.day_boxes[0]
    _, _, _, y_bot = loc.day_boxes[-1]
    gaps = column_gaps(gray, x0, x1, y_top, y_bot, thr)
    bounds = column_bounds_from_gaps(gaps, len(PRINTED_ORDER))
    if bounds is None:
        return None
    return ColumnLayout(bounds=bounds, body=(y_top, y_bot))


def cut_cells(row_img: Image.Image, layout: ColumnLayout, box: tuple[int, int, int, int]) -> list[Image.Image]:
    """Split a row crop (taken from `box` on the deskewed page, NOT yet
    scaled) into one image per printed column, using page-coordinate
    bounds shifted into the crop."""
    bx0 = box[0]
    cells = []
    for a, b in zip(layout.bounds, layout.bounds[1:]):
        cells.append(row_img.crop((max(0, a - bx0), 0, max(1, b - bx0), row_img.height)))
    return cells


def jitter(im: Image.Image, rng: random.Random) -> Image.Image:
    im = ImageEnhance.Contrast(im).enhance(rng.uniform(0.8, 1.25))
    im = ImageEnhance.Brightness(im).enhance(rng.uniform(0.9, 1.1))
    if rng.random() < 0.4:
        im = im.filter(ImageFilter.GaussianBlur(rng.uniform(0.2, 0.9)))
    if rng.random() < 0.3:
        im = im.rotate(rng.uniform(-0.4, 0.4), resample=Image.BICUBIC, fillcolor=(245, 240, 225))
    return im


def mix_rows(
    *, doc: str, page: int, period: str, rows: list[dict], row_images: list[Image.Image],
    boxes: list[tuple[int, int, int, int]], layout: ColumnLayout, n: int, rng: random.Random,
    out_dir, manifest_dir, scale: float = 2.0,
) -> list[RowExample]:
    """`rows[i]` is the transcription of `row_images[i]` (unscaled crops).
    Builds `n` mixed rows: the day cell is kept from a base row (so the day
    number stays a real, single printed number), every other column is
    drawn from a random row of the page; labels follow the cells."""
    cells_per_row = [cut_cells(im, layout, b) for im, b in zip(row_images, boxes)]
    out: list[RowExample] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for k in range(n):
        base = rng.randrange(len(rows))
        pick = [base] + [rng.randrange(len(rows)) for _ in PRINTED_ORDER[1:]]
        parts = [cells_per_row[src][ci] for ci, src in enumerate(pick)]
        h = max(p.height for p in parts)
        w = sum(p.width for p in parts)
        canvas = Image.new("RGB", (w, h), (245, 240, 225))
        x = 0
        for p in parts:
            canvas.paste(p, (x, 0))
            x += p.width
        canvas = jitter(canvas, rng)
        if scale != 1.0:
            canvas = canvas.resize((round(canvas.width * scale), round(canvas.height * scale)), Image.LANCZOS)
        cells: dict[str, float | None] = {}
        flags: dict[str, str] = {}
        for ci, col in enumerate(PRINTED_ORDER):
            src = rows[pick[ci]]
            if col == "day":
                continue
            if col == "wind_dir":
                d = (src.get("flags") or {}).get("wind_dir")
                if d:
                    flags["wind_dir"] = d
                continue
            cells[col] = src["cells"].get(col)
            f = (src.get("flags") or {}).get(col)
            if f:
                flags[col] = f
        data = png_bytes(canvas)
        name = f"syn_{doc}_{page:06d}_{k:04d}.png"
        (out_dir / name).write_bytes(data)
        out.append(RowExample(
            doc=doc, page=page, period=period, day=rows[base]["day"], date=rows[base]["date"],
            image=str((out_dir / name).relative_to(manifest_dir)), sha256=hashlib.sha256(data).hexdigest(),
            cells={c: cells.get(c) for c in COLUMNS}, flags=flags, box=tuple(boxes[base]),
            pitch=0.0, skew_deg=0.0, is_gold=False,
        ))
    return out
