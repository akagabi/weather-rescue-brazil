"""What a page's printed caption says the page is.

Stage A of a bulk run reads the caption off each table page and this module
decides what to do with it. It exists because the cheap signals lie in a
specific, dangerous direction: an astronomical ephemeris has a day column, a
ruled grid, daily rows and a Portuguese month-and-year heading naming Rio de
Janeiro, so BOTH the geometric sweep and a station-name match accept it.

Concretely, `data/raw/docvirt/11` is an *Ephemerides* volume - pages headed
SOL and LUA, columns `TEMPO SIDERAL | ASCENSÃO RECTA | DECLINAÇÃO`. Its page
15 carries the caption

    MARÇO DE 1855. AO MEIO DIA MEDIO NO RIO DE JANEIRO.

which matched `rio de janeiro` and was recorded as profile
`revista-rio-1886`, period 1855-03. Nothing downstream would have caught it:
sidereal time in hours-minutes-seconds parses as numbers, and a barometer
range check on a column of right ascensions is not a check anyone declared.
The volume was never produced, so no published row came from it - this guard
is what keeps that true.

`is_astronomy` runs BEFORE any station match and vetoes it. It looks for terms
that a meteorological table never prints. Note what is deliberately NOT in the
list: `declinação` alone, because magnetic declination is a real geophysical
observation the Revista does print - it only reads as astronomy alongside
right ascension or sidereal time.
"""

from __future__ import annotations

import re

# Terms a table of daily weather observations does not print. Kept narrow on
# purpose: a false veto silently drops real data, which is worse than the
# unidentified-page pile this project already treats as a finding.
ASTRONOMY = (
    "ascensao recta", "ascensão recta", "ascensao reta", "ascension droite",
    "tempo sideral", "temps sideral", "temps sidéral", "sidereal",
    "passagem meridiana", "passagem meri", "lunette meridienne",
    "lunette méridienne", "ephemerid", "ephemerides", "efemerid",
    "occultacao", "occultação", "occultation",
    "culminacao", "culminação", "culmination",
    "posicoes das estrellas", "posições das estrellas", "star position",
    "satellites de jupiter", "satellites", "planeta", "planete", "planète",
    "eclipse", "azimuth do sol", "nascimento do sol", "meio dia medio",
    "meio dia médio", "midi moyen",
    # docId 15 page 87 came through the sweep as a weather table: the Revista
    # prints the Moon's apogee, perigee and semi-diameter in a ruled grid with
    # a day column, and none of the terms above appear on it.
    # The Annales label their astronomical plates in the running head itself:
    # "Observat. astron. f. 10", "Observ. astr. t. 12". Two of doc 5's pages
    # say so and were still matched to a weather profile.
    "observat. astron", "observ. astr", "observations astronomiques",
    "observacoes astronomicas", "observações astronômicas", "astronomic",
    "apogeo", "apogeu", "perigeo", "perigeu", "semi-diametro", "semi diametro",
    "semi-diâmetro", "diametro da lua", "diâmetro da lua", "fases da lua",
    "phases de la lune", "distancias lunares", "distâncias lunares",
)

# Headings that are the whole caption on an ephemeris page.
ASTRONOMY_HEADINGS = ("sol", "lua", "soleil", "lune")

MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}

# station name fragments -> profile id. Order matters: first hit wins.
STATIONS = [
    ("santa-cruz", "revista-santacruz-1889"), ("santa cruz", "revista-santacruz-1889"),
    ("sta. cruz", "revista-santacruz-1889"), ("sta cruz", "revista-santacruz-1889"),
    ("corumba", "corumba-1889"), ("corumbá", "corumba-1889"),
    ("maranhao", "porto-maranhao-1886"), ("maranhão", "porto-maranhao-1886"),
    ("rio de janeiro", "revista-rio-1886"), ("imperial observatorio", "revista-rio-1886"),
    ("imperial observatório", "revista-rio-1886"),
]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def is_astronomy(caption: str) -> bool:
    """True when the caption names something only an astronomical table prints."""
    if any(t in norm(caption) for t in ASTRONOMY):
        return True
    # A bare "SOL." / "LUA." heading, with or without the month line under it.
    # Split the RAW caption: norm() collapses newlines into spaces, so a line
    # test has to happen before it runs.
    first = re.sub(r"\s+", " ", caption.split("\n")[0]).strip(" .:-").lower()
    return first in ASTRONOMY_HEADINGS


# The Annales print one month across several sheets, one instrument to a sheet,
# and every one of them is headed "Observations meteorologiques du mois de
# <Month> <Year>" with the station named only as RIO DE JANEIRO. That caption
# is not enough to say WHICH sheet it is - barometre, thermo, vapeur,
# nebulosite, vento and actinometrie are six different profiles - and matching
# on the station alone hands them `revista-rio-1886`, a Portuguese daily layout
# from a different publication with different columns. Parsing an Annales row
# against it would produce numbers in the wrong fields, all of them plausible.
#
# g4_annales_assign.py tells these apart by CELL COUNT, which is the only thing
# that can. So a French Annales caption deliberately matches no profile here.
_ANNALES = re.compile(
    r"(?:observations?|r[ée]sum[ée]s?)\s+m[ée]t[ée]orologiques?\s+"
    r"d[eou]\s+(?:l['\u2019]\s*)?(?:mois|ann[ée]e)"
    r"|r[ée]sum[ée]\s+m[ée]t[ée]orologique\s+d[eou]\s+(?:l['\u2019]\s*)?(?:mois|ann[ée]e)"
    r"|annales de l['\u2019 ]\s*observatoire", re.I)


def is_annales(caption: str) -> bool:
    """True for the Annales' own caption form, whose sheet a caption cannot name."""
    return bool(_ANNALES.search(norm(caption)))


# A place name on its own is a RUNNING HEAD, not a table. Doc 5 sets "DE RIO
# DE JANEIRO" across the top of every left-hand page with a roman folio beside
# it, and eleven of those were matched to revista-rio-1886 - two of them say
# "Observat. astron." in the same breath. Requiring something besides the place
# name and the furniture is what separates a caption from a page header.
_FURNITURE = re.compile(
    r"\b(?:de|do|da|dos|das|no|na|em|of|the|annales|annaes|observ|obs|imp|"
    r"imperial|t|f|p|n|pag|pl)\b|[ivxlcdmj]{2,}|\d+|[^\w\s]", re.I)


def _has_content_beyond(caption: str, station_fragment: str) -> bool:
    rest = norm(caption).replace(station_fragment, " ")
    rest = _FURNITURE.sub(" ", rest)
    return any(len(w) >= 4 for w in rest.split())


def match_profile(caption: str) -> str | None:
    """The profile this caption names, or None.

    Astronomy never matches, the Annales caption form never matches (the
    station alone cannot say which of its six sheets a page is), and neither
    does a caption that is only a place name - that is a running head.
    """
    if is_astronomy(caption) or is_annales(caption):
        return None
    c = norm(caption)
    for frag, pid in STATIONS:
        if frag in c:
            return pid if _has_content_beyond(caption, frag) else None
    return None


# "Rio de Janeiro" contains the month name "janeiro". The first version of
# this matched month names by substring, in dict order, with "janeiro" first -
# so EVERY Annales caption ("Observations météorologiques du mois de Mars 1883
# ... DE RIO DE JANEIRO") resolved to month 01. That shipped: 16 pages and ~520
# rows of dataset v0.2 carry a January date printed as March, May, July, August,
# October, November or December. Place names are therefore removed before any
# month is looked for, months are matched on word boundaries, and a caption
# naming two different months resolves by its "mois de"/"mez de" phrase or not
# at all - guessing a date is worse than declaring the page unidentified.
PLACES = ("rio de janeiro", "rio-de-janeiro", "riu de janeiro")
_OF_MONTH = re.compile(r"\b(?:mez|mes|mois|month)\s+d[eo']?\s*'?\s*([a-zà-ÿ]+)")


def _months_in(text: str) -> list[int]:
    found = []
    for name, n in MONTHS.items():
        if re.search(rf"(?<![a-zà-ÿ]){re.escape(name)}(?![a-zà-ÿ])", text) and n not in found:
            found.append(n)
    return found


def match_period(caption: str) -> str | None:
    c = norm(caption)
    for place in PLACES:
        c = c.replace(place, " ")
    ym = re.search(r"\b(18[5-9]\d)\b", c)
    year = int(ym.group(1)) if ym else None

    months = _months_in(c)
    if len(months) > 1:
        # several months named: trust only the one the caption says the table
        # is OF, and give up rather than pick one by position
        phrase = [MONTHS[m.group(1)] for m in _OF_MONTH.finditer(c) if m.group(1) in MONTHS]
        months = sorted(set(phrase)) if len(set(phrase)) == 1 else []
    if len(months) != 1:
        return None
    return f"{year:04d}-{months[0]:02d}" if year else None


# --- a period that cannot belong to its volume -------------------------------
#
# A period is a DATE, and nothing downstream looks at dates: no range test, no
# printed arithmetic, no verdict. The only witness is the caption, and the
# caption is the thing being misread. Two cases already seen:
#
#   doc 8 page 83  captioned "Septembre 1893" in a volume that ends in 1885
#   doc 15 page 109 captioned "Março de 1859" in the 1889 Revista
#
# Neither is corrected here. The month may be right and only the year misread,
# and guessing which is exactly how 509 rows came to be dated January.
def period_outside_volume(period: str | None, doc: str, spans: dict | None = None
                          ) -> str | None:
    """A reason string when a period cannot belong to that volume, else None."""
    if not period or not spans:
        return None
    span = (spans.get("spans") or spans).get(str(doc))
    if not span:
        return None
    lo, hi = span.get("from"), span.get("to")
    if lo and hi and not (lo <= period <= hi):
        return (f"period {period} is outside doc {doc}'s span {lo}..{hi} "
                f"({span.get('publication', '')})".strip())
    return None


def load_volume_spans(path=None) -> dict:
    import json as _json
    from pathlib import Path as _Path
    p = _Path(path) if path else _Path(__file__).resolve().parents[2] / "data" / "volume_spans.json"
    return _json.loads(p.read_text()) if p.exists() else {}
