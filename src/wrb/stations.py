"""Station coordinates as the Revista prints them.

`data/stations.json` currently holds coordinates looked up from the modern
city - approximations standing in for the observatory's own record, and the
reason every SEF file goes out with `NA` for latitude and longitude.

The Revista prints better ones. Its `RESUMO MENSAL DAS OBSERVAÇÕES
SIMULTANEAS` form heads each station block with the station's own line:

    Estação, S. Paulo; Observador, Alberto Loefgren; Latitude, 23°36' S;
    Longitude, 3°28' W; Hora local, 8h29m27s; Alt. do Bar. 735m42

Two things about that longitude. It is **measured from Rio de Janeiro, not
Greenwich** - São Paulo is 3°28' west of the Imperial Observatory, not of
Greenwich - and it is printed either in degrees or in TIME (Maceió's reads
`0h,30m E`, meaning half an hour of longitude, 7°30'). Both forms appear on
the same page. Reading either as a Greenwich degree puts the station in the
wrong hemisphere of the wrong continent.

Two independent checks that the Rio reference is right, using the printed
values and nothing else:

    Bahia      4°37'40" E of Rio -> 43.1725 - 4.628 = 38.54 W   (Salvador: 38.51 W)
    Maceió     0h30m     E of Rio -> 43.1725 - 7.5   = 35.67 W  (Maceió:   35.73 W)
    S. Paulo   3°28'     W of Rio -> 43.1725 + 3.467 = 46.64 W  (São Paulo: 46.63 W)

A ship's block prints `Latitude, var ; Longitude, var.` - the Cruzador
Almirante Barroso observing between Recife and São Luís do Maranhão. That is
kept as printed and parses to None, because a station that moves has no
coordinate and inventing one would be the same error in the other direction.
"""

from __future__ import annotations

import re

# The Imperial Observatory's own longitude west of Greenwich, the origin every
# `Longitude` on this form is measured from. 43°10'21"W is the value the
# observatory adopted and published for itself.
RIO_LONGITUDE = -(43 + 10 / 60 + 21 / 3600)

# Degrees, minutes, seconds. The separators are whatever the compositor used:
# "23°36' S", "9°,38'", "12°58'27''". A comma after the degree mark is a
# separator, not a decimal point - reading 9°,38' as 9.0 lost Maceió 38
# arcminutes of latitude.
_DMS = re.compile(
    r"(?P<d>\d+(?:\.\d+)?)\s*(?:°|º|o\b)?\s*[,;]?\s*"
    r"(?:(?P<m>\d+(?:[.,]\d+)?)\s*['\u2032m]\s*)?"
    r"(?:(?P<s>\d+(?:[.,]\d+)?)\s*(?:''|\"|\u2033|s)?\s*)?", re.I)
# The hemisphere letter is printed before the number as often as after it
# ("Latit., S 12°58'27''" against "Latitude, 23°36' S").
_HEMI = re.compile(r"(?:^|[\s,;])(?P<hemi>[NSEWO])(?:$|[\s,;.])", re.I)
_HMS = re.compile(
    r"(?P<h>\d+)\s*h[,.]?\s*(?:(?P<m>\d+(?:[.,]\d+)?)\s*m?)?\s*"
    r"(?:(?P<s>\d+(?:[.,]\d+)?)\s*s?)?\s*(?P<hemi>[EWO])?", re.I)


def _num(x: str | None) -> float:
    return float(x.replace(",", ".")) if x else 0.0


def parse_angle(text: str) -> float | None:
    """Degrees from a printed angle, signed by its hemisphere letter.

    Returns None for `var` (a ship) and for anything it cannot read - never a
    zero, which would read as the equator or the prime meridian.
    """
    t = (text or "").strip().rstrip(".;").strip()
    if not t or t.lower().startswith("var"):
        return None
    # A bare "2m W" with no degree mark is minutes of TIME, not arcminutes:
    # the form writes arcminutes with an apostrophe (3°28') and keeps `m` for
    # the time units it uses in `0h,30m E` and `Hora local, 9h,9m`. Santa Cruz
    # is the check - "Longitude, 2m W" is 0°30', half a degree west of Rio, and
    # 43.17 + 0.5 = 43.67 is the longitude the observatory sits at. Read as two
    # arcminutes it lands 0.47° out; read as two degrees, 2.5° out, in the sea.
    if re.fullmatch(r"\d+(?:[.,]\d+)?\s*m\.?\s*[EWO]?", t, re.I):
        deg = _num(re.match(r"\d+(?:[.,]\d+)?", t).group(0)) * 0.25
        h = _HEMI.search(t)
        return -deg if h and h.group("hemi").upper() in ("S", "W", "O") else deg
    if re.search(r"\d\s*h", t, re.I):                       # time: 0h30m E
        m = _HMS.search(t)
        if not m:
            return None
        deg = (_num(m["h"]) + _num(m["m"]) / 60 + _num(m["s"]) / 3600) * 15.0
    else:
        m = _DMS.search(t)
        if not m or m["d"] is None:
            return None
        deg = _num(m["d"]) + _num(m["m"]) / 60 + _num(m["s"]) / 3600
    h = _HEMI.search(t)
    if h and h.group("hemi").upper() in ("S", "W", "O"):
        deg = -deg
    return deg


def hemisphere(text: str) -> str | None:
    """The N/S/E/W letter the line prints, or None when it prints none.

    Maceió's block heads `Latitude, 9°,38';` with no letter at all. Every
    station on this form is in Brazil and so south of the equator, but that is
    an inference about the world, not something the page says, so it is left
    to whoever builds the registry to make and to record.
    """
    m = _HEMI.search((text or "").strip().rstrip(".;"))
    return m.group("hemi").upper() if m else None


def to_greenwich(lon_from_rio: float | None) -> float | None:
    """A longitude printed relative to Rio, expressed west of Greenwich."""
    if lon_from_rio is None:
        return None
    return round(RIO_LONGITUDE + lon_from_rio, 4)


FIELDS = {
    "station": r"esta[cç][aã]o(?:\s+de)?\s*[,:]?\s*(?P<v>[^;]+)",
    "observer": r"observ(?:ador|\.)\s*[,:]?\s*(?P<v>[^;]+)",
    "lat": r"latit(?:ude|\.)\s*[,:]?\s*(?P<v>[^;]+)",
    "lon": r"long(?:itude|\.)?\s*[,:]?\s*(?P<v>[^;]+)",
    "local_hour": r"hora\s+l[eo]cal\s*[,:]?\s*(?P<v>[^;]+)",
    "bar_alt": r"(?:alt(?:ura)?\.?\s*(?:do\s*)?bar(?:ometro|\.)?)\s*[,:]?\s*(?P<v>[^;]+)",
}


def parse_header(line: str) -> dict:
    """One printed station line -> its fields, verbatim and parsed.

    `printed` always carries the text exactly as set; the parsed values sit
    beside it and are None wherever the line does not yield one.
    """
    low = re.sub(r"\s+", " ", line or "")
    out: dict = {"printed": line, "fields": {}}
    for key, pat in FIELDS.items():
        m = re.search(pat, low, re.I)
        out["fields"][key] = m.group("v").strip().rstrip(".,;") if m else None
    f = out["fields"]
    out["lat_deg"] = parse_angle(f["lat"] or "")
    out["lat_hemisphere"] = hemisphere(f["lat"] or "")
    out["lon_from_rio_deg"] = parse_angle(f["lon"] or "")
    out["lon_hemisphere"] = hemisphere(f["lon"] or "")
    out["lon_deg"] = to_greenwich(out["lon_from_rio_deg"])
    alt = re.search(r"(\d+)\s*m", f["bar_alt"] or "")
    out["bar_alt_m"] = int(alt.group(1)) if alt else None
    out["moves"] = bool(f["lat"] and f["lat"].strip().lower().startswith("var"))
    return out
