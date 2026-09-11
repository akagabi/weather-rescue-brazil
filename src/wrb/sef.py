"""Export to the C3S Station Exchange Format (SEF) - the Data Rescue submission.

    https://datarescue.climate.copernicus.eu/station-exchange-format-sef

SPEC (read from the C3S page, 2026-09-11):
  * UTF-8 TSV, one VARIABLE per file, one station per file.
  * Lines 1-12: header, `name` and `value` separated by a tab, IN THIS ORDER:
    SEF, ID, Name, Lat, Lon, Alt, Source, Link, Vbl, Stat, Units, Meta.
    Only the version is strictly mandatory; missing values are `NA`.
  * Line 13: the column header.
  * Lines 14+: observations, 8 columns in this order:
    Year, Month, Day, Hour, Minute, Period, Value, Meta.
  * Times are UTC. Daily values calculated midnight-to-midnight should use
    hour 24.
  * There is NO quality-flag column. The C3S convention is a meta entry on the
    observation (the tutorial shows `qc=climatic_outliers`), which is how this
    module carries a row's uncertainty - the spec's "flags de qualidade".

TWO THINGS STILL NEED AN OUTSIDE CHECK BEFORE SUBMISSION, and they are
isolated in data rather than guessed here:

  1. VARIABLE AND STATISTIC CODES. `data/sef_variables.json` holds this
     project's mapping. The C3S lists live behind an image and a PDF that could
     not be read, so the codes are marked `needs_verification` and a wrong code
     is a rejected submission. The format machinery around them is verified
     against the spec above; the codes are not.
  2. STATION COORDINATES. `data/stations.json` carries them with a `verified`
     flag, and an unverified coordinate is written as `NA` rather than an
     approximate number that would look authoritative in a registry.

Run `dataresqc::check_sef` (or the Python equivalent) over the output before
sending anything.
"""

from __future__ import annotations

import json
from pathlib import Path

SEF_VERSION = "1.0.0"
HEADER_KEYS = ("SEF", "ID", "Name", "Lat", "Lon", "Alt", "Source", "Link",
               "Vbl", "Stat", "Units", "Meta")
COLUMN_KEYS = ("Year", "Month", "Day", "Hour", "Minute", "Period", "Value", "Meta")

_STATIONS = Path(__file__).resolve().parents[2] / "data" / "stations.json"
_VARIABLES = Path(__file__).resolve().parents[2] / "data" / "sef_variables.json"


def _cell(v) -> str:
    """SEF spells absence `NA`, never an empty string or a zero."""
    if v is None or v == "":
        return "NA"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def header(station: dict, variable: str, stat: str, units: str, meta: str,
           link: str = "NA", source: str = "wrb") -> str:
    """The 12 header lines, in the order the spec fixes.

    A coordinate that has not been verified is written `NA`: an approximate
    latitude in a registry file is worse than an admitted gap, because it looks
    authoritative and nothing downstream can tell.
    """
    def coord(key):
        return station.get(key) if station.get("verified") else None

    values = {
        "SEF": SEF_VERSION,
        "ID": station.get("id"),
        "Name": station.get("name"),
        "Lat": coord("lat"),
        "Lon": coord("lon"),
        "Alt": coord("alt"),
        "Source": source,
        "Link": link,
        "Vbl": variable,
        "Stat": stat,
        "Units": units,
        "Meta": meta or None,
    }
    return "".join(f"{k}\t{_cell(values[k])}\n" for k in HEADER_KEYS)


def data_line(year: int, month: int, day: int, hour, minute, period: str,
              value, meta: str = "") -> str:
    return "\t".join([
        _cell(year), _cell(month), _cell(day), _cell(hour), _cell(minute),
        _cell(period), _cell(value), meta or "",
    ])


def sef_filename(source: str, station_id: str, start: str, end: str, variable: str,
                 stat: str | None = None) -> str:
    """`dataresqc::write_sef`'s convention, plus the statistic.

    dataresqc's name is `sou_cod_start_end_variable.tsv` and does not carry the
    statistic - but SEF holds one VARIABLE per file, and a mean, a maximum and
    a minimum of the same variable are three different files with three
    different `Stat` headers. Without the statistic in the name they overwrite
    each other: the first version of this exporter silently wrote `ta.tsv`
    three times and kept only the last.
    """
    tail = f"{variable}-{stat}" if stat else variable
    return f"{source}_{station_id}_{start}_{end}_{tail}.tsv"


def write_sef(path: Path, station: dict, *, variable: str, stat: str, units: str,
              rows: list[tuple], meta: str = "", link: str = "NA") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [header(station, variable, stat, units, meta, link=link),
            "\t".join(COLUMN_KEYS) + "\n"]
    body += [data_line(*r) + "\n" for r in rows]
    path.write_text("".join(body), encoding="utf-8")
    return path


def load_stations(path: Path | None = None) -> dict:
    return json.loads(Path(path or _STATIONS).read_text())


def load_variables(path: Path | None = None) -> dict:
    """This project's column -> SEF (variable, stat, units) mapping.

    Isolated in data, and carrying `needs_verification`, because the C3S
    accepted-code lists could not be read at the time of writing - see the
    module docstring.
    """
    return json.loads(Path(path or _VARIABLES).read_text())
