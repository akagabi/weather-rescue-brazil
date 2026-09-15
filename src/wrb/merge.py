"""Assemble per-document productions into the published dataset.

Until now this step had no code: `data/dataset/weather-rescue-brazil.jsonl` was
concatenated by hand in a session, which is why its sidecar summary and its
README drifted two revisions behind it, and why `station` - a field that
reaches a dataset row from no other code path - was joined by hand and had to
be normalised after the fact ("one station counted as two").

Merging is not a `cat`. Three things have to hold, each learned from the
artefact:

  * identity is (profile, item, page, block, row). Not (item, page): the
    Annales print several unrelated tables on one sheet under different
    profiles, so a page number alone would silently delete one of them - and
    the Revista's `Resumo mensal das observacoes simultaneas` form prints four
    tables of the SAME profile on one sheet, one per station, so profile and
    page together are not enough either. Without `block`, the four stations on
    docId 16 page 41 all claim row "1" and three are dropped as duplicates.
  * page blocks stay contiguous and in order. `g4_rescore.py` reads the day
    sequence off a whole page to decide which rows are days; interleave rows
    from two files and a page reads as one with its days missing, and every row
    on it gets flagged.
  * `station` comes from the page's worklist entry, with an honest
    `station_source`. A page the worklist does not know about is left alone -
    never guessed.

`scripts/g4_merge.py` wraps this; run it and then `g4_rescore.py` on the result.
"""

from __future__ import annotations


# A row's position on its page. `row` is an integer on every daily layout, but
# the `Resumo mensal das observacoes simultaneas` form labels its rows with
# what the page prints - 1a, 2a, 3a, Mez - and puts FOUR tables on one sheet,
# so the page number alone no longer identifies a table. Both facts have to
# reach the key: without `block`, the four stations on docId 16 page 41 all
# claim row "1" and three of them are dropped as duplicates.
_LABEL_ORDER = {"1": 1, "2": 2, "3": 3, "mez": 99}


def row_ordinal(row: dict) -> tuple[int, int]:
    """(block, position within it). Sorts a labelled row after its dekads."""
    block = row.get("block")
    b = int(block) if isinstance(block, (int, float)) or str(block).isdigit() else 0
    r = row.get("row", -1)
    if isinstance(r, (int, float)) or str(r).lstrip("-").isdigit():
        return b, int(r)
    return b, _LABEL_ORDER.get(str(r).strip().rstrip(".").lower(), 98)


def row_key(row: dict) -> tuple:
    """Identity of a produced row: which table, on which page, which row of it."""
    return (row.get("profile"), str(row.get("item")), int(row.get("page", -1)),
            *row_ordinal(row))


def _doc_order(item) -> tuple:
    """Documents sort 8, 14, 15, 16 - not '14', '15', '16', '8'."""
    s = str(item)
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


def page_sort_key(row: dict) -> tuple:
    """Ordering is PAGE-first, profile only as a tie-break.

    Sorting by profile first would group the file by publication and scatter
    each page's rows through the output. `g4_rescore.py` assembles a page's day
    sequence from rows that are adjacent in the file, so a scattered page reads
    as one whose days are missing.
    """
    return (_doc_order(row.get("item")), int(row.get("page", -1)),
            *row_ordinal(row), str(row.get("profile")))


def merge(sources: list[list[dict]]) -> list[dict]:
    """Concatenate produced rows into one dataset, in page order.

    Duplicates are dropped on the full provenance key, first occurrence wins -
    the source files overlap in intent (a backlog run and a sweep both covered
    doc 15), and re-running a document re-produces its pages.
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for src in sources:
        for r in src:
            k = row_key(r)
            if k in seen:
                continue
            seen.add(k)
            out.append(dict(r))
    out.sort(key=page_sort_key)
    return out


def apply_station(rows: list[dict], pages: list[dict]) -> int:
    """Fill `station`/`station_source` on rows from their page's worklist entry.

    Keyed on (doc, page). Returns how many rows were touched. The station is
    read from the caption at identification time and carried in the worklist;
    the dataset row has no other way to learn it, which is why a naive re-run
    produces rows with no station at all.
    """
    by_page: dict[tuple[str, int], dict] = {}
    for p in pages:
        doc = p.get("doc", p.get("item"))
        if doc is None or p.get("page") is None:
            continue
        by_page[(str(doc), int(p["page"]))] = p
    touched = 0
    for r in rows:
        # A row that already knows its station from the PAGE ITSELF keeps it.
        # The `Resumo mensal das observacoes simultaneas` form prints four
        # stations on one sheet and each block carries its own; a worklist
        # station is per page, so applying it here would overwrite three
        # correct stations in four with one wrong one.
        if r.get("station") and r.get("station_source", "").startswith(
                ("linha impressa do bloco", "herdada do bloco")):
            continue
        entry = by_page.get((str(r.get("item")), int(r.get("page", -1))))
        if entry is None:
            continue
        if entry.get("station"):
            r["station"] = entry["station"]
        if entry.get("station_source"):
            r["station_source"] = entry["station_source"]
        touched += 1
    return touched


def summarise(rows: list[dict]) -> dict:
    """Recount the dataset's headline numbers from the rows themselves.

    `g4_produce.py` writes a summary for its own run only and knows nothing
    about a merge, so a merged file's sidecar has to be recomputed - the last
    one still claimed 1,194 rows beside a 3,655-row file.
    """
    verdicts: dict[str, int] = {}
    pages: set[tuple] = set()
    values = 0
    for r in rows:
        v = r.get("verdict", "?")
        verdicts[v] = verdicts.get(v, 0) + 1
        pages.add((str(r.get("item")), int(r.get("page", -1))))
        # A row that carries a measurement, whatever the layout calls it: a
        # day on the daily tables, a dekad on the `Resumo mensal` form. A month
        # total is a restatement of rows already counted and is not counted
        # again - which is also why `is_day_row` alone undercounted the
        # dekadal rows to zero, since nothing sets it on them.
        if v in ("checks_pass", "qc_clean") and (r.get("is_day_row") or r.get("is_dekad")):
            values += sum(1 for x in (r.get("values") or {}).values() if x is not None)
    usable = verdicts.get("checks_pass", 0) + verdicts.get("qc_clean", 0)
    return {
        "pages": len(pages),
        "rows": len(rows),
        "checks_pass": verdicts.get("checks_pass", 0),
        "qc_clean": verdicts.get("qc_clean", 0),
        "flagged": verdicts.get("flagged", 0),
        "usable": usable,
        "values_usable": values,
    }
