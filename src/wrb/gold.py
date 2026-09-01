from pydantic import BaseModel

RANGES = {"tmax": (-10.0, 50.0), "tmin": (-15.0, 45.0), "precip": (0.0, 400.0),
          "pressure": (650.0, 800.0)}  # mmHg era units; adjust per-series in G2
TOL = 0.15  # tolerance for printed mean/sum reproduction (rounding in period arithmetic)

class Row(BaseModel):
    date: str
    cells: dict[str, float | None]
    flags: dict[str, str] = {}

class Sheet(BaseModel):
    source: str; bib: str; page: int
    station: str; period: str
    columns: list[str]
    rows: list[Row]
    printed_totals: dict[str, float] | None = None

def validate_sheet(s: Sheet) -> list[str]:
    v: list[str] = []
    for r in s.rows:
        tmax, tmin = r.cells.get("tmax"), r.cells.get("tmin")
        if tmax is not None and tmin is not None and tmax < tmin:
            v.append(f"{r.date}: tmax {tmax} < tmin {tmin}")
        for col, val in r.cells.items():
            lo_hi = RANGES.get(col)
            if val is not None and lo_hi and not (lo_hi[0] <= val <= lo_hi[1]):
                v.append(f"{r.date}: {col}={val} outside physical range {lo_hi}")
    if s.printed_totals:
        for key, printed in s.printed_totals.items():
            col, kind = key.rsplit("_", 1)          # e.g. "tmax_mean", "precip_sum"
            vals = [r.cells[col] for r in s.rows if r.cells.get(col) is not None]
            if not vals:
                continue
            calc = (sum(vals) / len(vals)) if kind == "mean" else sum(vals)
            if abs(calc - printed) > TOL:
                v.append(f"printed {key}={printed} but computed {calc:.2f} (possible row/col shift)")
    return v
