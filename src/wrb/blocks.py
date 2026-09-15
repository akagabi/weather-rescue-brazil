"""Pages that carry several tables, each belonging to a different station.

Until this layout, a page meant a station: the caption named it, and the
producer stamped it on every row of the page. The Revista's `RESUMO MENSAL DAS
OBSERVAÇÕES SIMULTANEAS` form breaks that. One landscape sheet carries four
station blocks - docId 16 page 41 holds São Paulo, Bahia (Capital), Ouro Preto
and Santa Cruz - each headed by its own line:

    Estação, S. Paulo; Observador, Alberto Loefgren; Latitude, 23°36' S; ...

and each with its own month. Blocks that continue the station above them print
only the month line and no station header at all (docId 15 page 142's second
block is Maceió's July, under Maceió's June).

Two rules follow, and both are about not inventing provenance:

  * A block with no printed header INHERITS the station above it, and the row
    records that it was inherited. A block at the top of a page with no header
    has nothing to inherit from and gets no station.
  * The station comes from the block's own line, not from the page caption and
    not from the worklist. A worklist station on this form would be wrong for
    three of every four blocks.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Block:
    """One station's table on a multi-table sheet."""
    index: int
    header_box: tuple[int, int, int, int] | None
    row_boxes: list[tuple[int, int, int, int]]
    inherits_station: bool


def _band(x_frac, width: int) -> tuple[int, int]:
    x0, x1 = x_frac
    return max(0, round(x0 * width)), min(width, round(x1 * width))


def blocks_for_page(declared: list[dict], width: int, height: int,
                    x_frac: tuple[float, float]) -> list[Block]:
    """Pixel boxes for each declared block's header line and data rows.

    `declared` is the profile's `blocks` list: fractions of page height, which
    is what a printed form allows - the form does not move between issues, so
    the bands are measured once and declared, the same argument `row_bands`
    already makes for the dekadal summaries.
    """
    x0, x1 = _band(x_frac, width)
    out: list[Block] = []
    for i, b in enumerate(declared):
        head = b.get("header")
        hbox = None
        if head:
            hbox = (x0, max(0, round(head[0] * height)), x1,
                    min(height, round(head[1] * height)))
        rows = [(x0, max(0, round(lo * height)), x1, min(height, round(hi * height)))
                for lo, hi in b.get("rows", [])]
        out.append(Block(index=i, header_box=hbox, row_boxes=rows,
                         inherits_station=head is None))
    return out


# What the caller found in a block's header strip. The three cases have to stay
# apart, because two of them look identical from the read alone and inheriting
# on the wrong one attributes a station's observations to another station.
#
# Measured on docId 15 page 158: the page prints Cruzador Almirante Barroso,
# then Ponte B. de Macedo with its own header, then Ponte's next month with no
# header, then Bahia. The read of Ponte's header came back without the word
# `Estação`, the block was treated as headerless, and it inherited CRUZADOR -
# a warship's observations attributed to a bridge works in Recife. The station
# was wrong, and nothing in the row said so.
import re as _re  # noqa: E402

NO_HEADER = None        # the page prints only a month line: inherit, and say so
UNREADABLE = ""         # a header IS printed and could not be read: no station

# What a strip's text turns out to be. Line count cannot answer this - the form
# sets a station line alone when the month is shared, so a header can be one
# line and a continuation is also one line - so the words decide.
def header_kind(text: str) -> str:
    """`station`, `month_only`, or `unclear` for a strip's transcription.

    `month_only` is the only one that inherits. `unclear` yields no station:
    a missing station is a gap a consumer can see, a wrong one is data, and
    docId 15 page 158 produced the wrong one - a failed read of Ponte B. de
    Macedo's header let the block inherit CRUZADOR ALMIRANTE BARROSO, putting
    a warship's observations at a bridge works in Recife.
    """
    t = _re.sub(r"\s+", " ", (text or "")).strip().lower()
    if not t:
        return "unclear"
    if _re.search(r"esta[çc][ãa]o|observador|observ\.|latitude|latit\.|alt\. do bar", t):
        return "station"
    # "Mez de Junho de 1889", "Mezes de Julho de 1889" and nothing else
    if _re.fullmatch(r"(?:mez|mês|mes|mezes|meses)\s+d[eo]\s+[a-zà-ÿ]+\s+de\s+\d{4}\.?", t):
        return "month_only"
    return "unclear"


def resolve_stations(headers: list[str | None]) -> list[dict]:
    """One station record per block, in page order, carrying how it was got.

    `headers[i]` is the text read from block i's header strip, `NO_HEADER` when
    the page prints no header there, or `UNREADABLE` when one is printed and
    the read failed. Only `NO_HEADER` inherits; `UNREADABLE` yields no station,
    which is a gap to report rather than a neighbour's name to borrow.

    It takes the headers rather than the blocks because that is all it needs:
    inheritance runs down the page in order, and a caller that has only read
    the header strips should not have to manufacture block geometry to ask.
    """
    from wrb.stations import parse_header

    out: list[dict] = []
    last: dict | None = None
    for text in headers:
        if text:
            h = parse_header(text)
            rec = {"station": h["fields"]["station"], "observer": h["fields"]["observer"],
                   "printed": text, "station_source": "linha impressa do bloco",
                   "lat_deg": h["lat_deg"], "lon_deg": h["lon_deg"],
                   "lat_hemisphere": h["lat_hemisphere"],
                   "lon_hemisphere": h["lon_hemisphere"],
                   "bar_alt_m": h["bar_alt_m"], "moves": h["moves"]}
            last = rec
            out.append(rec)
        elif text == UNREADABLE:
            out.append({"station": None,
                        "station_source": "cabecalho impresso mas ilegivel"})
        elif last is not None:
            out.append({**last, "station_source": "herdada do bloco acima"})
        else:
            out.append({"station": None, "station_source": "sem cabecalho e sem bloco acima"})
    return out


# The printed row label is what decides a row on the `Resumo mensal das
# observações simultaneas` form. Grouping the ink bands by pitch alone was
# tried first and reads 3 of the 10 known pages correctly; the labels read all
# of them. Same principle as the printed day numbers at Cuyabá: geometry
# proposes, the print disposes.
def text_lines(image, floor: int = 3, min_h: int = 4) -> int:
    """How many printed lines of text a strip holds.

    Deliberately NOT the row detector, which filters candidates against a modal
    ROW height and splits anything much taller - right for a table, wrong for a
    caption. Here the only question is how many bands of ink there are, so
    nothing is filtered and nothing is split.

    Note what this does NOT settle: whether a header is printed. Counting lines
    was tried for that and is wrong, because the form sets a station line on
    its own when the month is shared - on docId 15 page 126 the Ponte B. de
    Macedo and Bahia blocks each carry a single line, exactly like a month-only
    continuation. `header_kind` reads the text instead.
    """
    import numpy as np

    from wrb.rows import ink_threshold

    g = image.convert("L")
    a = np.asarray(g, dtype=float)
    on = (a < ink_threshold(g)).sum(axis=1) > floor
    lines, start = 0, None
    for y, v in enumerate(on):
        if v and start is None:
            start = y
        elif not v and start is not None:
            if y - start >= min_h:
                lines += 1
            start = None
    if start is not None and len(on) - start >= min_h:
        lines += 1
    return lines


def band_from_rules(image, span: tuple[float, float], bleed: float = 0.010
                    ) -> tuple[float, float] | None:
    """The x-band to crop, anchored on THIS page's own table rules.

    The first version of this declared the band as fixed fractions of page
    width, measured on docId 16 page 41. It read that page perfectly and
    returned nothing at all on docId 15 page 126, because the two scans do not
    share a margin: the table's left rule sits at 0.133 of the width on one and
    0.102 on the other. The band landed three hundredths to the right, clipped
    the `Decadas` column, and every row came back without the printed label
    that decides what it is.

    So the band is expressed as a fraction of the TABLE, not of the page, and
    the table's own outermost rules locate it. `span` is that fraction - for
    the measurement block of the `Resumo mensal` form, (0.0, 0.253).

    Returns None when the rules do not give a plausible table, which is a page
    to refuse rather than to read at a guessed offset.
    """
    from wrb.rows import ink_threshold, vertical_rules

    g = image.convert("L")
    width = g.width
    rules = [x / width for x in vertical_rules(g, ink_threshold(g))]
    inner = [x for x in rules if 0.05 < x < 0.95]
    if len(inner) < 2:
        return None
    left, right = min(inner), max(inner)
    if not 0.3 < right - left < 0.95:
        return None
    w = right - left
    return (max(0.0, left + span[0] * w - bleed), min(1.0, left + span[1] * w))


import re as _re  # noqa: E402

_DEKAD = _re.compile(r"^([123])\s*[ªaº°o]?$", _re.I)


def row_label(raw: str) -> str | None:
    """`1`, `2`, `3` or `Mez` from a row's first printed cell, else None.

    The compositor sets the month row as `Mez`, `Mez.` or `Mez....` and the
    dekads as `1ª`, `2ª`, `3ª`, which the reader returns variously as `1a`,
    `1º` or bare `1`. Anything else - a column header caught by the detector,
    a stray rule, a line of notes - is not a data row and is dropped rather
    than read into the table.
    """
    first = (raw or "").split("|")[0].strip().strip(".").strip().lower()
    if first.startswith(("mez", "mês", "mes", "moi")):
        return "Mez"
    m = _DEKAD.match(first)
    return m.group(1) if m else None


def dedupe_labels(labels: list[str | None], score=None) -> list[int]:
    """Indices to keep when the same row was detected more than once.

    Row candidates are proposed generously - a run of ink taller than one row
    is split rather than dropped - so the same printed row can arrive as two
    crops, and both read back with the same label. Left alone that is fatal,
    not merely wasteful: a block's labels come out `1, 1, 2, 2, 3, 3, Mez`,
    which is not the `1, 2, 3, Mez` a block has to be, and the whole block is
    discarded. It is why docId 15 page 126 yielded one block of its four.

    Consecutive candidates carrying the SAME label are one row, and only one
    survives - by `score` when given (the fuller read wins), else the first.
    Within a block the labels are strictly 1, 2, 3, Mez and between blocks a
    Mez is followed by a 1, so no two genuinely different rows are ever
    adjacent with the same label.
    """
    keep: list[int] = []
    for i, lab in enumerate(labels):
        if lab is None:
            continue
        if keep and labels[keep[-1]] == lab:
            if score is not None and score(i) > score(keep[-1]):
                keep[-1] = i
            continue
        keep.append(i)
    return keep


def blocks_from_labels(labels: list[str]) -> list[list[int]]:
    """Indices of each complete `1, 2, 3, Mez` block, in page order.

    A block opens at a `1` and closes at the `Mez` that follows it. Anything
    that does not form that exact sequence is not returned: a page whose labels
    read 1,2,3,1,2,3,Mez has lost a row somewhere, and half a block is worse
    than none - its Mez would be checked against the wrong three dekads.
    """
    out, cur = [], []
    for i, lab in enumerate(labels):
        if lab == "1" and cur:
            cur = []
        cur.append(i)
        if lab == "Mez":
            if [labels[j] for j in cur] == ["1", "2", "3", "Mez"]:
                out.append(cur)
            cur = []
    return out


def dekad_trios(labels: list[str | None]) -> list[list[int]]:
    """Indices of each `1, 2, 3` run - a block's three dekadal rows.

    The month row is deliberately NOT required here, because on this form it is
    the row that reads worst. Measured on docId 15 page 126, the three dekads
    of all four blocks came back exactly right and three of the four month rows
    came back with their cells out of order - Maceió's printed
    `Mez.... | 763.64 | 26.9 | 26.9 | 21 1 | 80.9` was read as
    `21 | 80.9 | 26.9 | 763.64 | 26.9 | Mez.`, right to left with the label
    last. Requiring a leading `Mez` threw away three complete blocks of good
    dekadal data to protect a row that only restates them.

    So the dekads are found by their labels, which are reliable, and the month
    row is taken by POSITION afterwards (see `month_row_after`). A month row
    that cannot be read is recorded as unreadable and its arithmetic check
    skipped - the dekads are the observations, the month is the summary.
    """
    out: list[list[int]] = []
    i = 0
    while i + 2 < len(labels):
        if [labels[i], labels[i + 1], labels[i + 2]] == ["1", "2", "3"]:
            out.append([i, i + 1, i + 2])
            i += 3
        else:
            i += 1
    return out
