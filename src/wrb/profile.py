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
PADDED_TRAILING = "padded 1 trailing cell (assumed the last column is blank)"
# Problems a row RECORDS without being disqualified by them. Each is a repair
# made on evidence rather than a defect in the reading: the assumed-blank last
# cell, and the two index repairs in `_resegment_index`, where the digits were
# read correctly and only cut into the wrong number of cells. Nothing here
# excuses a row from the page's own arithmetic - a wrong repair does not close
# a checksum, which is precisely why these can be soft.
SOFT_PROBLEM_PREFIXES = (
    PADDED_TRAILING,
    "index cell read as two tokens",
    "dropped a spurious leading cell",
    "dropped an empty cell at position",
)


def is_soft_problem(problem: str) -> bool:
    """A recorded repair rather than a reason to distrust the row."""
    return str(problem).startswith(SOFT_PROBLEM_PREFIXES)
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
    # A SECOND elision convention, and a different one. `elided` means a
    # constant prefix is always omitted (the Rio barometer prints 54.44 for
    # 754.44, every row, forever), so a single declared band restores it.
    # The Radcliffe tables omit the integer part only when it is the SAME AS
    # THE CELL ABOVE IT IN THE SAME COLUMN, and reprint it the moment it
    # changes: January reads 29·969 / ·404 / ·589 / 30·108. The carry runs
    # DOWN the column, not along the row - checked against the page's own
    # yearly-mean checksum, which closes to ±0.0004 under this reading and
    # not under any other. It needs the whole page, so it is resolved by
    # `resolve_column_carry` in the page pass, not by `from_printed`.
    elided_carry: bool = False
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
    # words historical tables print instead of a number: trace rain, no reading.
    # They are data, not parse failures - recorded as a marker with a null value.
    markers: list[str] = field(default_factory=list)
    # the page's printed MONTH-TOTAL row, as data: which words the page prints
    # in the day column for it, and which aggregation each column's printed
    # figure is. Declared per publication because the convention differs - the
    # Revista prints means for most columns but the month's max/min for the
    # extremes and a sum for rainfall (measured on doc 14 p41, 1886-01).
    monthly: dict = field(default_factory=dict)
    probe_x_frac: tuple[float, float] | None = None
    table_x_frac: tuple[float, float] | None = None
    # WHERE the table sits vertically, as a fraction of page height - the Y twin
    # of table_x_frac. Needed when a header is as tall as the data is dense and
    # the row search starts counting header rows (wrb.rows.locate_day_rows).
    table_y_frac: tuple[float, float] | None = None
    # For a table that prints a FIXED number of rows per page (a monthly or
    # dekadal summary prints 1a/2a/3a/Mez and nothing else), say where those
    # rows are and skip detection entirely. A printed form does not move, and on
    # this layout the detector cannot be made to work: the row pitch is ~25px
    # under a three-level header, and the ink peaks are too faint for the
    # strong-peak threshold - it returns 2 rows of the 4. Declaring them is both
    # simpler and more honest than tuning a threshold until it happens to pass.
    row_bands: list | None = None
    # A sheet that carries SEVERAL tables, each with its own station.
    #
    # Every layout before this one held a page to a single station named in the
    # caption, and the producer attached that station to the whole page. The
    # Revista's `RESUMO MENSAL DAS OBSERVAÇÕES SIMULTANEAS` form does not: one
    # landscape sheet carries four station blocks - São Paulo, Bahia, Ouro
    # Preto and Santa Cruz on docId 16 page 41 - each with its own printed
    # header line and often its own month. A block that repeats the station
    # above it prints only the month and no header at all.
    #
    # So the station is a property of the BLOCK, not of the page, and the
    # geometry has to say where each block's header line and rows sit:
    #
    #     "blocks": [{"header": [y0, y1] | null, "rows": [[y0, y1], ...]}, ...]
    #
    # all as fractions of page height. A null header means "same station as the
    # block above" - inherited, and recorded as inherited, never re-read.
    blocks: list | None = None
    # The x-extent to crop, as fractions of page width, when the printed table
    # is wider than the model can read in one row. This form is 26 columns; the
    # reader is reliable to about 16. Declaring the band that carries the
    # measurements turns one unreadable row into one readable one, and leaves
    # the rest (17 sparse wind-frequency counts) for a second pass rather than
    # corrupting the first.
    band_x_frac: tuple[float, float] | None = None
    # How much of the day column the oracle must read DIRECTLY before its
    # localisation is accepted; the rest is interpolated between confirmed days
    # at the page pitch and checked for overlap. 0.7 suits a publication whose
    # day numbers are lining figures. The Annales set theirs in OLD-STYLE
    # figures - 1 as a small-capital I, 10 as IO, 11 as II - and the reader
    # loses perhaps a third of them, so a bar tuned elsewhere refuses pages that
    # are perfectly regular and perfectly legible to a person. This is a fact
    # about the printing, so it is declared per publication rather than lowered
    # for everyone.
    oracle_min_direct: float = 0.7
    # What the row-index column COUNTS. Every layout up to here indexed its
    # rows by day of month, and the pipeline said so in constants: the
    # producer's preflight required `1 <= d <= 31` before it would read a
    # page, and the rescorer looked for a run of days inside the same bounds.
    # The Radcliffe tables invert the table - rows are YEARS and columns are
    # MONTHS - so every one of their rows failed a test written for a
    # different publication, and the whole series would have published as
    # `flagged` with `not_a_day_row` against rows that are perfectly good.
    # Declared here rather than inferred, and the legal values come from the
    # index column's own `range`.
    index_kind: str = "day_of_month"      # day_of_month | year
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
    def index_range(self) -> tuple[float, float]:
        """The values the row-index column may legally take.

        Days of the month unless the profile's index column declares its own
        range - the Radcliffe year column declares 1851..1879.
        """
        c = next((c for c in self.columns if c.kind == "day"), None)
        if c is not None and c.range is not None:
            return c.range
        return (1.0, 31.0)

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

    def _resegment_index(self, toks: list[str], problems: list[str]) -> list[str]:
        """Repair a row-index cell the reader emitted as two tokens.

        The Radcliffe year column is set in OLD-STYLE figures, and the reader
        splits `1856` into `18 | 56` - one cell too many, and every value after
        it shifted one column right. That is a SEGMENTATION failure, not a
        reading one: both halves of the number are correct, and joining them
        restores the row exactly. The same rows also pick up a spurious leading
        cell where the page rules a heavy line down the left edge.

        Two repairs, and each requires evidence rather than a guess:

        * join tokens 0 and 1 when the joined digits land inside the index
          column's declared range and token 0 alone does not;
        * drop a leading blank or ditto token when token 1 is already a
          legal index.

        Both are gated on the index column DECLARING a range, so they cannot
        touch a layout that has not asked for them - every Brazilian day column
        leaves `range` null and is unaffected. A row still one cell over after
        this is left alone and reported, because the extra cell is then
        somewhere this cannot see.
        """
        col = next((c for c in self.columns if c.kind == "day"), None)
        if col is None or col.range is None or len(toks) != self.n_cells + 1:
            return toks
        lo, hi = col.range

        def legal(tok: str) -> bool:
            try:
                return lo <= float(tok.replace(",", ".").replace("\u00b7", ".")) <= hi
            except ValueError:
                return False

        if legal(toks[0]):
            return toks                       # the index is fine; the extra cell is elsewhere
        if toks[0].lower() in DITTO_TOKENS or toks[0].lower() in (
                NULL, "", "-", "\u2014", "...", "\u2026"):
            if legal(toks[1]):
                problems.append(f"dropped a spurious leading cell {toks[0]!r}")
                return toks[1:]
            return toks
        joined = toks[0].strip() + toks[1].strip()
        if joined.isdigit() and legal(joined):
            problems.append(
                f"index cell read as two tokens {toks[0]!r} {toks[1]!r}, joined to {joined!r}")
            return [joined] + toks[2:]
        return toks

    def _drop_ruled_blank(self, toks: list[str], problems: list[str]) -> list[str]:
        """Drop an empty cell the reader invented where the page rules a line.

        Radcliffe Table I sets a DOUBLE rule between December and the Yearly
        Mean, and the reader takes the gap for a column: seven of its
        twenty-five rows come back as `... | 688 | null | 29.721 | 785` where
        the page prints Nov ·688, Dec 29·721, Yearly ·785. The row is one cell
        too long and the surplus is a blank in the MIDDLE, which the existing
        trailing-null trim cannot reach.

        Required before removing anything: exactly one cell too many, exactly
        one interior blank, and - the evidence that matters - every numeric
        cell landing inside its column's declared range once the blank is
        gone. A row that only happens to be long does not qualify.

        Gated, like the index repairs, on the index column declaring a range,
        so no layout that has not asked for this can be affected.
        """
        col = next((c for c in self.columns if c.kind == "day"), None)
        if col is None or col.range is None or len(toks) != self.n_cells + 1:
            return toks
        blank = (NULL, "", "-", "\u2014", "...", "\u2026", "....")
        holes = [i for i, t in enumerate(toks[1:-1], start=1) if t.lower() in blank]
        if len(holes) != 1:
            return toks
        trimmed = toks[:holes[0]] + toks[holes[0] + 1:]
        probe: dict = {}
        for c, tok in zip(self.columns, trimmed):
            try:
                probe[c.key] = float(tok.replace(",", ".").replace("\u00b7", "."))
            except ValueError:
                pass
        # judged on the columns that are NOT elided-by-carry: those cannot be
        # range-checked until the page pass restores their integer part.
        checkable = {k: v for k, v in probe.items()
                     if not self.column(k).elided_carry}
        if self.violations(checkable):
            return toks
        problems.append(f"dropped an empty cell at position {holes[0]} "
                        f"(the page rules a line there, it is not a column)")
        return trimmed

    def parse(self, text: str) -> tuple[dict, list[str]]:
        """Inverse of `target`. Never raises; reports problems instead."""
        for stop in ("<|im_end|>", "<|endoftext|>", "</s>"):
            text = text.split(stop)[0]
        toks = [t.strip() for t in text.strip().strip("`").split("|")]
        problems: list[str] = []
        markers: dict[str, str] = {}
        self.last_markers = markers
        # A row whose LAST printed cell is blank comes back one short (the model
        # stops) or one long (a trailing null). Both are the tail, not a
        # misalignment, so trim/pad quietly; any other mismatch is a real problem.
        blank = (NULL, "", "-", "\u2014", "...", "\u2026", "....")
        while len(toks) == self.n_cells + 1 and toks[-1].lower() in blank:
            toks = toks[:-1]
        toks = self._resegment_index(toks, problems)
        toks = self._drop_ruled_blank(toks, problems)
        if len(toks) == self.n_cells - 1:
            # ASSUMPTION, recorded not hidden: the absent cell is the last one.
            # If it is not, every value after it is shifted - the failure this
            # whole pipeline exists to avoid - so the row stays distinguishable.
            toks = toks + [NULL]
            problems.append(PADDED_TRAILING)
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
                # 19th-century tables print a signed value with a space after
                # the sign ("+ 0.35", "— 1.23"), and the em-dash IS a minus
                # sign here, not punctuation. 36 rows of the 1883 barometer
                # were being thrown away over the space alone.
                # The raised decimal point. British scientific printing of the
                # period sets the decimal separator high on the line - the
                # Radcliffe tables print 29·969 and ·404, never 29.969 - and
                # the reader reproduces it faithfully, which is what a reader
                # of printed text should do. Without this every numeric cell
                # of the Oxford barometer and rainfall tables came back
                # `unparsable`, so the pages localised, read correctly and
                # then produced nothing but nulls.
                num = (tok.replace(",", ".").replace("\u00b7", ".").replace("\u2027", ".")
                          .replace("\u2219", ".").replace("\u22c5", ".")
                          .replace("\u2014", "-").replace("\u2013", "-")
                          .replace("+ ", "+").replace("- ", "-"))
                values[col.key] = int(float(num)) if col.kind == "day" else float(num)
            except ValueError:
                values[col.key] = None
                low = tok.lower().rstrip(".").strip()
                if any(low.startswith(m.lower().rstrip(".")[:4]) for m in self.markers if m):
                    markers[col.key] = tok          # a printed word, kept verbatim
                else:
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
        if self.table_y_frac:
            kw["table_y_frac"] = tuple(self.table_y_frac)
        if self.row_bands:
            kw["row_bands"] = [tuple(b) for b in self.row_bands]
        return kw

    def verify(self, values: dict, tol: float = 0.051) -> list[str]:
        """Check the arithmetic the PAGE asserts about its own numbers - a row's
        oscillation equalling max minus min, a mean equalling the mean of its
        readings. Free ground truth: it needs no human and it localises the
        suspect cell. Declared per publication in `checks`:

            {"kind": "diff", "result": k, "a": k, "b": k}
            {"kind": "mean", "result": k, "of": [k, ...]}
            {"kind": "sum",  "result": k, "of": [k, ...]}
            {"kind": "order", "result": k, "of": [low_k, high_k]}

        `order` is the strongest of the four and needs no tolerance to speak of:
        a printed mean that sits outside its own printed min and max is not a
        close call, it is impossible, so the cell is certainly misread. It costs
        nothing to declare and it is the only arithmetic these Brazilian
        day-rows actually carry - their "mean" is the mean of the day's
        readings, which the row does not print (docs/g4-qc-audit.md).
        """
        out: list[str] = []
        for c in self.checks:
            keys = [c.get("result")] + ([c["a"], c["b"]] if c["kind"] == "diff" else list(c.get("of", [])))
            vals = [values.get(k) for k in keys]
            if any(not isinstance(v, (int, float)) for v in vals):
                continue                      # a blank row is not a failure
            got = float(vals[0])
            if c["kind"] == "order":
                lo, hi = float(vals[1]), float(vals[2])
                if not (lo - tol <= got <= hi + tol):
                    out.append(f"{c['result']}={got} outside [{lo}, {hi}]")
                continue
            if c["kind"] == "atleast":
                # "this column can never fall below that one" - a maximum below
                # its own minimum, a mean below its minimum. Impossible for any
                # two readings of one instrument, so it needs no tolerance to
                # speak of. Declared separately from the printed `diff` check
                # because that one SKIPS when its result cell is blank: two
                # rows reached `checks_pass` with sansabri_max 7.5 and
                # sansabri_min 39.2 precisely because the oscillation cell was
                # empty and the check quietly declined to run.
                if got < float(vals[1]) - tol:
                    out.append(f"{c['result']}={got} below {c['of'][0]}={vals[1]}")
                continue
            if c["kind"] == "diff":
                want = float(vals[1]) - float(vals[2])
            elif c["kind"] == "sum":
                want = sum(float(v) for v in vals[1:])
            else:
                want = sum(float(v) for v in vals[1:]) / (len(vals) - 1)
            if abs(got - want) > tol:
                out.append(f"{c['result']}={got} but {c['kind']} gives {want:.4f}")
        return out

    # --- the page's printed month-total row ------------------------------
    def is_monthly_summary(self, raw: str) -> bool:
        """True when a row's day cell holds the word the page prints for its
        month total ("Mez", "Mois", "Déc") instead of a day number. Deliberately
        structural: it reads the printed marker, never the numbers, so it cannot
        be fooled by a total that happens to look plausible."""
        markers = self.monthly.get("markers") or []
        if not markers or not raw:
            return False
        first = raw.split("|")[0].strip().rstrip(".").lower()
        return first in {m.rstrip(".").lower() for m in markers}

    def verify_month(self, day_rows: list[dict], summary: dict, tol: float = 0.06) -> list[str]:
        """Check the page's printed month-total row against the day rows it
        summarises - the one arithmetic available to publications whose rows
        carry no per-row check of their own.

        Declared per column in `monthly.aggregate`, because the convention is
        not uniform: on doc 14 p41 (1886-01) the printed row reproduces the
        MEAN of the 31 day rows for tmean (25.30), vapor (18.50), humidity,
        evaporation, cloudiness, ozone and wind, but the month's MAX for tmax
        and MIN for tmin, and a SUM for rainfall.

        The value is that it names the COLUMN, and it catches the one failure
        physical ranges cannot see: two same-unit columns swapped. Both values
        stay plausible, so no range check fires - but the column's monthly mean
        stops reproducing. Like `verify`, it needs no human and no model.

        A column the page did not print in full is skipped, not failed: a mean
        over a gapped month cannot match, and that is absence of evidence
        rather than evidence of an error.
        """
        agg = self.monthly.get("aggregate") or {}
        # Per-column tolerance, because how exact the printed total IS varies by
        # publication. The Revista's daily pages assert a mean over 31 equal
        # days and it reproduces to the last printed digit. The `Resumo mensal
        # das observacoes simultaneas` form does not: its Mez row and its three
        # dekad rows disagree by a few tenths on every column of every block
        # measured, in both directions, because the Mez is computed from all
        # the daily observations and the dekad figures are rounded means of
        # subsets of 10, 10 and 11 days. A tolerance tight enough for the first
        # form flags every row of the second. Where `monthly.tolerance` names a
        # column, its number is used; otherwise `tol`.
        per_key = self.monthly.get("tolerance") or {}
        out: list[str] = []
        for key, kind in agg.items():
            printed = summary.get(key)
            if not isinstance(printed, (int, float)):
                continue
            col = [r.get(key) for r in day_rows]
            if not col or any(not isinstance(v, (int, float)) for v in col):
                continue
            if kind == "mean":
                want = sum(col) / len(col)
            elif kind == "sum":
                want = sum(col)
            elif kind == "max":
                want = max(col)
            elif kind == "min":
                want = min(col)
            else:
                continue
            limit = float(per_key.get(key, tol))
            if abs(want - printed) > limit:
                out.append(f"{key}: printed {printed} but {kind} of the day rows "
                           f"gives {want:.4f} (tolerance {limit})")
        return out

    def verify_month_unordered(self, day_rows: list[dict], printed: list[float],
                               tol: float | None = None) -> list[str]:
        """The month row's arithmetic when its CELL ORDER cannot be trusted.

        On the `Resumo mensal das observacoes simultaneas` form the month row
        frequently comes back with its cells out of order - Maceio's printed
        `Mez.... | 763.64 | 26.9 | 26.9 | 21 1 | 80.9` read right to left with
        the label last. The numbers are all there and all correct; only their
        order is lost. Matching them to columns by position would invent data,
        so this compares the two SETS instead: every expected column mean has
        to find a printed number near it, and each printed number is spent
        once.

        It cannot name the column that failed, which `verify_month` can, so it
        is the weaker check and says so at the call site. What it still does is
        catch a month row that does not summarise these dekads at all - and, on
        the block measured, the one column that is genuinely out by 1.34.
        """
        agg = self.monthly.get("aggregate") or {}
        per_key = self.monthly.get("tolerance") or {}
        wants: list[tuple[str, float]] = []
        for key, kind in agg.items():
            col = [r.get(key) for r in day_rows]
            if not col or any(not isinstance(v, (int, float)) for v in col):
                continue
            if kind != "mean":
                continue
            wants.append((key, sum(col) / len(col)))
        pool = [v for v in printed if isinstance(v, (int, float))]
        out: list[str] = []
        for key, want in wants:
            limit = float(per_key.get(key, tol if tol is not None else 0.06))
            hit = min(pool, key=lambda v: abs(v - want)) if pool else None
            if hit is None or abs(hit - want) > limit:
                out.append(f"{key}: no printed figure near {want:.4f} "
                           f"(closest {hit}, tolerance {limit})")
            else:
                pool.remove(hit)
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

    def resolve_column_carry(self, rows: list[dict]) -> list[dict]:
        """Restore an integer part the page omitted because it had not changed.

        Only columns declaring `elided_carry`. A cell printed as a bare
        fraction (0 <= v < 1) takes the integer part of the last cell ABOVE it
        in the same column that printed one; a cell that prints its own
        integer part sets the carry for everything below. A column whose first
        rows are bare has nothing to carry from and is left alone, because
        inventing the digit is how a reconstruction becomes a fabrication.

        The page's own arithmetic is the witness: on Radcliffe Table I the
        printed Yearly Mean equals the mean of the twelve restored months to
        four decimal places, and does not under any other reading.
        """
        carry: dict[str, int] = {}
        out: list[dict] = []
        for row in rows:
            fixed = dict(row)
            for col in self.columns:
                if not col.elided_carry:
                    continue
                v = fixed.get(col.key)
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    continue
                v = abs(float(v))
                lo, hi = col.range or (float("-inf"), float("inf"))
                if lo <= v <= hi:
                    carry[col.key] = int(v)            # this cell printed its own
                elif v < 1.0 and col.key in carry:
                    fixed[col.key] = round(carry[col.key] + v, 4)
                elif col.key in carry and v >= 1.0:
                    # The raised point dropped ENTIRELY: `·404` came back as
                    # `404`. The fraction's digits are all there, only its
                    # scale is gone, and the column's declared range says
                    # where the point belongs - 404 can only be ·404 when the
                    # column runs 28..31. Shift until the carried integer part
                    # plus the fraction lands in range, and if no shift does,
                    # leave the cell alone rather than invent a scale.
                    frac = v
                    for _ in range(6):
                        if frac < 1.0:
                            break
                        frac /= 10.0
                    cand = round(carry[col.key] + frac, 4)
                    if frac < 1.0 and lo <= cand <= hi:
                        fixed[col.key] = cand
            out.append(fixed)
        return out

    def resolve_index_sequence(self, rows: list[dict]) -> dict[int, int]:
        """Fill a row index the reader could not read, from the ones it could.

        The Radcliffe year column is set in old-style figures and the reader
        sometimes returns only its first two digits - `1856` comes back as
        `18`, with the row otherwise complete and correct. Nothing in the row
        can recover the lost digits, but the PAGE can: it prints one row per
        year, consecutively, and the locator returns those rows in order, so
        every year that WAS read is a witness to the same mapping from row
        position to year.

        This fills a missing index only when the rows that read cleanly agree
        unanimously on one offset, and only from at least three of them. If
        they disagree - which is what a misread year or a mislocalised row
        looks like - nothing is filled. That is the same rule the day oracle
        uses (printed labels decide, the gaps are interpolated between
        confirmed anchors) applied to a column of years.

        Declared per publication: only a profile whose `index_kind` is not
        `day_of_month` is eligible, so no daily layout's behaviour changes.

        Returns {row position: the index it must be}.
        """
        col = next((c for c in self.columns if c.kind == "day"), None)
        if col is None or col.range is None or self.index_kind == "day_of_month":
            return {}
        lo, hi = col.range
        legal: dict[int, int] = {}
        for i, row in enumerate(rows):
            v = row.get(col.key)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi:
                legal[i] = int(v)
        if len(legal) < 3:
            return {}
        offsets = {idx - i for i, idx in legal.items()}
        if len(offsets) != 1:                 # the witnesses disagree: fill nothing
            return {}
        off = offsets.pop()
        return {i: off + i for i in range(len(rows))
                if i not in legal and lo <= off + i <= hi}

    # --- QC -------------------------------------------------------------
    def violations(self, values: dict) -> list[str]:
        """Physical-range checks from the profile (the QC the model cannot do
        for itself - see the G3 finding that models never self-flag)."""
        out = []
        for col in self.columns:
            v = values.get(col.key)
            # a ditto mark is a legitimate value and not a number: skip, do not crash
            if not isinstance(v, (int, float)) or col.range is None or col.kind == "text":
                continue
            lo, hi = col.range
            if not (lo <= float(v) <= hi):
                out.append(f"{col.key}={v} outside {col.range}")
        return out

    # --- io -------------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("probe_x_frac", "table_x_frac", "table_y_frac"):
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
