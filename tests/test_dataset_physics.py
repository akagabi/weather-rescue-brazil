"""Physical checks over the whole published dataset, not over a fixture.

These are cheap, they need no model and no images, and they answer a question
nothing else in the suite asks: are the numbers in the file *possible*?

The one here is pressure against altitude. It came out of the `Resumo mensal`
form, where the printed station altitudes span 64 m to 1145 m and made a plain
barometer range almost meaningless - 598 mmHg is inside a range that has to
admit both Bahia and Ouro Preto, and impossible at either. Turned on the
published dataset it is a regression guard: a row whose pressure cannot belong
to its station is either a misread digit or a station wrongly assigned, and
both have happened in this project.

The altitudes it uses are the approximate ones in data/stations.json, which is
weaker than the printed ones - but a city altitude is good to a few tens of
metres and the 25 mmHg window is worth about 280 m, so the check is
comfortably inside what the approximation supports.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb import profile as prof  # noqa: E402
from wrb.qc import pressure_implausible  # noqa: E402

DATASET = ROOT / "data" / "dataset" / "weather-rescue-brazil.jsonl"
STATIONS = ROOT / "data" / "stations.json"
TOL_MM = 25.0


def _rows():
    return [json.loads(l) for l in DATASET.read_text().splitlines() if l.strip()]


def _altitudes():
    st = json.loads(STATIONS.read_text())
    return {v["dataset_name"]: v["alt"] for v in st.values()
            if isinstance(v, dict) and v.get("dataset_name") and v.get("alt") is not None}


def _barometer_keys(profile_id, _cache={}):
    """Which of a profile's columns are barometers - asked of the PROFILE.

    Not of the key name: the barometer is `pressure` on the Revista, `h04m` on
    the Annales, `moyenne`, `baro_fortin`, `baro_media`. What they share is a
    declared unit of mm and a range that starts high, which is also what
    separates them from the other mm columns - vapour tension (4-30), rainfall
    (0-400), evaporation (0-25).
    """
    if profile_id not in _cache:
        try:
            p = prof.load(profile_id)
        except Exception:
            _cache[profile_id] = set()
        else:
            _cache[profile_id] = {c.key for c in p.columns
                                  if c.unit == "mm" and c.range and c.range[0] >= 600}
    return _cache[profile_id]


def _checkable(rows, alt):
    for r in rows:
        if r.get("verdict") not in ("checks_pass", "qc_clean"):
            continue
        a = alt.get(r.get("station"))
        if a is None:
            continue
        keys = _barometer_keys(r.get("profile"))
        for key, v in (r.get("values") or {}).items():
            if key in keys and isinstance(v, (int, float)):
                yield r, key, v, a


def test_no_usable_row_has_a_pressure_its_station_cannot_produce():
    rows = _rows()
    alt = _altitudes()
    bad = []
    for r, key, v, a in _checkable(rows, alt):
        why = pressure_implausible(v, a, tol=TOL_MM)
        if why:
            bad.append(f"{r['item']}/{r['page']} row {r['row']} {r.get('station')}: {why}")
    assert not bad, "\n".join(bad[:20])


def test_the_check_actually_reaches_the_data():
    """A guard that silently checks nothing is worse than no guard."""
    rows = _rows()
    n = sum(1 for _ in _checkable(rows, _altitudes()))
    assert n > 3000, f"only {n} barometer values were checked"


# --- a direction cell holds a direction --------------------------------------

def _direction_keys(profile_id, _cache={}):
    from wrb import profile as prof
    from wrb.qc import direction_keys
    if profile_id not in _cache:
        try:
            _cache[profile_id] = direction_keys(prof.load(profile_id))
        except Exception:
            _cache[profile_id] = []
    return _cache[profile_id]


def test_no_usable_row_holds_a_direction_that_is_not_one():
    """The wind layouts print no summary column, so this is the only check they
    have beyond the force range. It also catches a page assigned the wrong
    layout outright - doc 5 page 351 is a thermometer table that was produced
    as wind, and its 31 rows carry temperatures where rhumbs belong."""
    from wrb.qc import invalid_compass

    bad = []
    for r in _rows():
        if r.get("verdict") not in ("checks_pass", "qc_clean"):
            continue
        keys = _direction_keys(r.get("profile"))
        if not keys:
            continue
        for why in invalid_compass(r.get("values") or {}, keys):
            bad.append(f"{r['item']}/{r['page']} row {r['row']}: {why}")
    assert not bad, "\n".join(bad[:15])


def test_the_direction_check_reaches_the_data():
    """It was written twice: the first version rejected `Variavel` and
    `NW, SSE`, which are readings, and would have flagged 1,063 good rows."""
    n = sum(1 for r in _rows()
            if _direction_keys(r.get("profile"))
            and (r.get("values") or {}).get(_direction_keys(r["profile"])[0]) is not None)
    assert n > 1000, f"only {n} direction cells were checked"
