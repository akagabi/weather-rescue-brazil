"""Publication profiles: the table's schema as DATA, not code.

Everything before this module hard-coded one publication's 14 columns - in the
training target, the parser, the metrics, the QC ranges. Adding a publication
meant editing Python, and the model inherited the same flaw: it memorised "15
cells" from training and could not read a 16-column table (see
docs/g4-generalisation.md).

A `Profile` declares a layout once, in JSON:

    columns      the printed columns, LEFT TO RIGHT, exactly as they appear
    kind         day | number | text        (day/text are not scored numerically)
    range        physical plausibility, used by QC
    elided       thousands digit omitted in print (the barometer convention)
    rows_per_page how many day-rows a page holds, given its period

From that, the row target text, its parser, the QC ranges and the review UI
columns are all derived. Adding a publication is writing one JSON file.

Profiles live in `profiles/*.json`; `wrb.profile.load(id)` reads them.
"""

from __future__ import annotations

import calendar
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

SEP = " | "
NULL = "null"
# 19th-century tables repeat a value with a ditto mark rather than reprinting
# it - Corumba writes the day once and dittos the second reading of that day.
# Treated as a first-class value, resolved against the previous row.
DITTO = "\u00bb"
DITTO_TOKENS = {"\u00bb", "\u00ab", '"', "\u201d", "\u2033", "''", ",,", "idem", "id.", "ditto", "\u3003"}


def _slug(text: str) -> str:
    """ASCII key from a printed label: 'Barômetro' -> 'barometro'."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", plain.strip().lower()).strip("_")


PROFILE_DIR = Path(__file__).resolve().parents[2] / "profiles"


@dataclass
class Column:
    key: str
    label: str
    kind: str = "number"           # day | number | text
    unit: str | None = None
    range: tuple[float, float] | None = None
    elided: bool = False           # printed without its leading digit(s), e.g. 54.44 for 754.44
    elided_range: tuple[float, float] | None = None  # the narrow band the true value sits in, for reconstruction
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("day", "number", "text"):
            raise ValueError(f"{self.key}: unknown kind {self.kind!r}")
        if self.range is not None:
            self.range = (float(self.range[0]), float(self.range[1]))
        if self.elided_range is not None:
            self.elided_range = (float(self.elided_range[0]), float(self.elided_range[1]))


@dataclass
class Profile:
    id: str
    name: str
    columns: list[Column]
    source: str = ""
    rows_per_page: str = "days_in_month"   # days_in_month | days_in_month_x2 | fixed:<n>
    adapter: str = ""
    checks: list[dict] = field(default_factory=list)   # arithmetic the page itself asserts
    # page geometry, per publication: where the row-index column sits and how
    # wide the table runs, as fractions of page width. Defaults suit the
    # Brazilian layouts; Oxford's year column sits elsewhere (docs/g4-blind-summary.md).
    probe_x_frac: tuple[float, float] | None = None
    table_x_frac: tuple[float, float] | None = None
    notes: str = ""
    extra: dict = field(default_factory=dict)

    # --- shape ---------------------------------------------------------
    @property
    def keys(self) -> list[str]:
        return [c.key for c in self.columns]

    @property
    def numeric_keys(self) -> list[str]:
        return [c.key for c in self.columns if c.kind == "number"]

    @property
    def day_key(self) -> str | None:
        return next((c.key for c in self.columns if c.kind == "day"), None)

    @property
    def n_cells(self) -> int:
        return len(self.columns)

    def column(self, key: str) -> Column:
        for c in self.columns:
            if c.key == key:
                return c
        raise KeyError(key)

    def expected_rows(self, period: str) -> int:
        """Day-rows on a page covering `period` (YYYY-MM)."""
        spec = self.rows_per_page
        if spec.startswith("fixed:"):
            return int(spec.split(":", 1)[1])
        year, month = (int(x) for x in period.split("-"))
        days = calendar.monthrange(year, month)[1]
        return days * 2 if spec == "days_in_month_x2" else days

    # --- the row as printed --------------------------------------------
    @staticmethod
    def _fmt(v) -> str:
        if v is None or v == "":
            return NULL
        if isinstance(v, str):
            return v
        s = f"{float(v):.2f}".rstrip("0").rstrip(".")
        return s or "0"

    def target(self, values: dict) -> str:
        """Training/eval target: every printed cell, left to right."""
        return SEP.join(self._fmt(values.get(c.key)) for c in self.columns)

    def parse(self, text: str) -> tuple[dict, list[str]]:
        """Inverse of `target`. Never raises; reports problems instead."""
        for stop in ("<|im_end|>", "<|endoftext|>", "</s>"):
            text = text.split(stop)[0]
        toks = [t.strip() for t in text.strip().strip("`").split("|")]
        problems: list[str] = []
        if len(toks) != self.n_cells:
            problems.append(f"{len(toks)} cells, expected {self.n_cells}")
        values: dict = {}
        for i, col in enumerate(self.columns):
            tok = toks[i] if i < len(toks) else NULL
            if tok.lower() in DITTO_TOKENS:
                values[col.key] = DITTO
                continue
            blank = tok.lower() in (NULL, "", "-", "—", "...", "…", "....")
            if blank:
                values[col.key] = None
                continue
            if col.kind == "text":
                values[col.key] = tok
                continue
            try:
                values[col.key] = int(float(tok)) if col.kind == "day" else float(tok.replace(",", "."))
            except ValueError:
                values[col.key] = None
                problems.append(f"{col.key}: unparsable {tok!r}")
        return values, problems

    def to_printed(self, values: dict, threshold: float = 100.0) -> dict:
        """Undo a domain convention before writing a TRAINING TARGET: columns
        flagged `elided` are printed without their leading digits, so the page
        shows 58.36 where the value is 758.36. Teaching the reconstructed form
        taught the model to invent a leading 7 and it then applied that to an
        unrelated 1883 vapour table (docs/g4-print-fidelity.md). Targets must
        be faithful to print; `restore_thousands` puts the digits back
        downstream, where it belongs."""
        out = dict(values)
        for col in self.columns:
            v = out.get(col.key)
            if col.elided and isinstance(v, (int, float)) and v >= threshold:
                out[col.key] = round(float(v) % threshold, 4)
        return out

    def from_printed(self, values: dict, threshold: float = 100.0) -> dict:
        """Inverse of `to_printed`: put the elided digits back, using the
        column's physical range to choose them."""
        from wrb.reconstruct import restore_thousands
        out = dict(values)
        for col in self.columns:
            v = out.get(col.key)
            band = col.elided_range or (700.0, 800.0)
            if col.elided and isinstance(v, (int, float)) and v < threshold:
                try:
                    out[col.key] = restore_thousands(float(v), band)
                except ValueError:
                    pass
        return out

    def geometry(self) -> dict:
        """Keyword arguments for `wrb.rows.locate_day_rows`, from the profile."""
        kw = {}
        if self.probe_x_frac:
            kw["probe_x_frac"] = tuple(self.probe_x_frac)
        if self.table_x_frac:
            kw["table_x_frac"] = tuple(self.table_x_frac)
        return kw

    def verify(self, values: dict, tol: float = 0.051) -> list[str]:
        """Check the arithmetic the PAGE asserts about its own numbers - a row's
        oscillation equalling max minus min, a mean equalling the mean of its
        readings. Free ground truth: it needs no human and it localises the
        suspect cell. Declared per publication in `checks`:

            {"kind": "diff", "result": k, "a": k, "b": k}
            {"kind": "mean", "result": k, "of": [k, ...]}
        """
        out: list[str] = []
        for c in self.checks:
            keys = [c.get("result")] + ([c["a"], c["b"]] if c["kind"] == "diff" else list(c.get("of", [])))
            vals = [values.get(k) for k in keys]
            if any(not isinstance(v, (int, float)) for v in vals):
                continue                      # a blank row is not a failure
            got = float(vals[0])
            if c["kind"] == "diff":
                want = float(vals[1]) - float(vals[2])
            else:
                want = sum(float(v) for v in vals[1:]) / (len(vals) - 1)
            if abs(got - want) > tol:
                out.append(f"{c['result']}={got} but {c['kind']} gives {want:.4f}")
        return out

    def resolve_dittos(self, rows: list[dict]) -> list[dict]:
        """Replace ditto marks with the value they repeat from the row above.
        A ditto in the first row has nothing to repeat and becomes None."""
        out: list[dict] = []
        for row in rows:
            fixed = dict(row)
            for key, val in row.items():
                if val == DITTO:
                    fixed[key] = out[-1].get(key) if out else None
            out.append(fixed)
        return out

    # --- QC -------------------------------------------------------------
    def violations(self, values: dict) -> list[str]:
        """Physical-range checks from the profile (the QC the model cannot do
        for itself - see the G3 finding that models never self-flag)."""
        out = []
        for col in self.columns:
            v = values.get(col.key)
            if v is None or col.range is None or col.kind == "text":
                continue
            lo, hi = col.range
            if not (lo <= float(v) <= hi):
                out.append(f"{col.key}={v} outside {col.range}")
        return out

    # --- io -------------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("probe_x_frac", "table_x_frac"):
            if d.get(k) is not None:
                d[k] = list(d[k])
        for c in d["columns"]:
            for k in ("range", "elided_range"):
                if c.get(k) is not None:
                    c[k] = list(c[k])
        return d

    def save(self, path: Path | None = None) -> Path:
        path = path or PROFILE_DIR / f"{self.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1, ensure_ascii=False))
        return path


def from_dict(d: dict) -> Profile:
    cols = [Column(**c) for c in d["columns"]]
    return Profile(**{**d, "columns": cols})


def load(profile_id: str, directory: Path | None = None) -> Profile:
    directory = directory or PROFILE_DIR
    path = directory / f"{profile_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no profile {profile_id!r} in {directory}")
    return from_dict(json.loads(path.read_text()))


def available(directory: Path | None = None) -> list[str]:
    directory = directory or PROFILE_DIR
    return sorted(p.stem for p in directory.glob("*.json")) if directory.exists() else []


def blank(profile_id: str, name: str, labels: list[str]) -> Profile:
    """Skeleton profile from a list of printed column labels - what the review
    UI creates when a user onboards a new publication."""
    cols = []
    for i, lab in enumerate(labels):
        key = _slug(lab) or f"col{i}"
        kind = "day" if i == 0 and re.search(r"dia|day|data", lab, re.I) else "number"
        cols.append(Column(key=key, label=lab.strip(), kind=kind))
    return Profile(id=profile_id, name=name, columns=cols)
