"""Merging per-document productions into the published dataset.

There is no script that builds data/dataset/weather-rescue-brazil.jsonl - it
was assembled by hand, and `station`/`station_source` reach a dataset row from
no other code path at all. These tests pin the three properties that a hand
merge silently got wrong or could not express:

  * identity is the FULL provenance tuple, because the Annales print several
    different tables on one page under different profiles, so (item, page)
    alone is not unique;
  * page blocks stay contiguous and in order, because g4_rescore.py groups rows
    by page to decide which are days - interleave two files and it flags every
    row of a half page;
  * the station join is applied and its provenance string is honest.
"""

from wrb.merge import apply_station, merge, row_key, summarise


def row(profile="p", item="14", page=1, n=0, **kw):
    return {"profile": profile, "item": item, "page": page, "row": n,
            "period": "1886-01", "verdict": "checks_pass", "values": {}, **kw}


def test_row_identity_includes_the_profile():
    """Two different tables on one page are two different rows."""
    a = row(profile="revista-rio-1886", page=22, n=3)
    b = row(profile="revista-santacruz-1889", page=22, n=3)
    assert row_key(a) != row_key(b)


def test_merge_drops_an_exact_duplicate_across_files():
    a = [row(n=0), row(n=1)]
    b = [row(n=1), row(n=2)]
    out = merge([a, b])
    assert [r["row"] for r in out] == [0, 1, 2]


def test_merge_keeps_both_tables_printed_on_the_same_page():
    a = [row(profile="A", page=22, n=0), row(profile="A", page=22, n=1)]
    b = [row(profile="B", page=22, n=0)]
    out = merge([a, b])
    assert len(out) == 3


def test_merge_keeps_each_page_contiguous_and_ordered():
    """Rescore reads the day sequence off a whole page; a split page reads as
    a page with days missing."""
    a = [row(item="14", page=2, n=0), row(item="14", page=1, n=1)]
    b = [row(item="14", page=1, n=0), row(item="14", page=2, n=1)]
    out = merge([a, b])
    assert [(r["item"], r["page"], r["row"]) for r in out] == [
        ("14", 1, 0), ("14", 1, 1), ("14", 2, 0), ("14", 2, 1)]


def test_merge_keeps_a_page_contiguous_when_profiles_differ():
    """Ordering is by PAGE first, not by profile. Grouping the file by profile
    would scatter a page's rows across the output, and rescore reads the day
    sequence off a contiguous page."""
    a = [row(profile="A", page=22, n=0), row(profile="A", page=22, n=1)]
    b = [row(profile="B", page=9, n=0), row(profile="B", page=22, n=0)]
    out = merge([a, b])
    assert [(r["item"], r["page"]) for r in out] == [
        ("14", 9), ("14", 22), ("14", 22), ("14", 22)]


def test_merge_orders_documents_numerically_not_as_strings():
    out = merge([[row(item="8", page=1, n=0), row(item="14", page=1, n=0),
                  row(item="16", page=1, n=0)]])
    assert [r["item"] for r in out] == ["8", "14", "16"]


def test_merge_does_not_mutate_its_inputs():
    a = [row(n=0)]
    merge([a])
    assert a == [row(n=0)]


def test_apply_station_reads_the_worklist_and_records_its_provenance():
    rows = [row(item="14", page=41, n=0)]
    pages = [{"doc": "14", "page": 41, "station": "Imperial Observatório, Rio de Janeiro",
              "station_source": "legenda impressa"}]
    touched = apply_station(rows, pages)
    assert touched == 1
    assert rows[0]["station"] == "Imperial Observatório, Rio de Janeiro"
    assert rows[0]["station_source"] == "legenda impressa"


def test_apply_station_leaves_a_page_it_does_not_know_about_alone():
    """Never invent a station: a page absent from the worklist keeps whatever
    it had, which for a fresh production is nothing."""
    rows = [row(item="14", page=99, n=0)]
    pages = [{"doc": "14", "page": 41, "station": "X", "station_source": "legenda impressa"}]
    assert apply_station(rows, pages) == 0
    assert "station" not in rows[0]


def test_apply_station_keeps_an_honest_source_string():
    rows = [row(item="8", page=7, n=0)]
    pages = [{"doc": "8", "page": 7, "station": "Rio",
              "station_source": "assumed from worklist, caption unreadable"}]
    apply_station(rows, pages)
    assert rows[0]["station_source"] == "assumed from worklist, caption unreadable"


def test_summarise_counts_from_the_rows_not_from_a_stale_sidecar():
    rows = [row(n=0), row(n=1), row(n=2, verdict="flagged"), row(n=3, verdict="qc_clean")]
    s = summarise(rows)
    assert s["rows"] == 4
    assert s["checks_pass"] == 2
    assert s["qc_clean"] == 1
    assert s["flagged"] == 1
    assert s["usable"] == 3


# --- four tables on one sheet, and rows labelled the way the page labels them

from wrb.merge import row_key, row_ordinal  # noqa: E402


def test_a_labelled_row_does_not_crash_the_key():
    """`Resumo mensal` rows are 1a, 2a, 3a, Mez - not integers."""
    assert row_ordinal({"block": 0, "row": "1"}) == (0, 1)
    assert row_ordinal({"block": 0, "row": "Mez"}) == (0, 99)
    assert row_ordinal({"row": 7}) == (0, 7)


def test_the_month_row_sorts_after_its_dekads():
    b = [{"block": 0, "row": r} for r in ["Mez", "3", "1", "2"]]
    assert [r["row"] for r in sorted(b, key=row_ordinal)] == ["1", "2", "3", "Mez"]


def test_four_stations_on_one_page_keep_four_identities():
    """Without `block` they all claim row 1 and three are dropped as dupes."""
    rows = [{"profile": "p", "item": "16", "page": 41, "block": b, "row": "1"}
            for b in range(4)]
    assert len({row_key(r) for r in rows}) == 4


def test_blocks_stay_in_page_order():
    rows = [{"block": 1, "row": "1"}, {"block": 0, "row": "Mez"}]
    assert [r["block"] for r in sorted(rows, key=row_ordinal)] == [0, 1]


def test_a_block_station_survives_the_worklist():
    """Four stations on one sheet; a page-level station would overwrite three."""
    from wrb.merge import apply_station
    rows = [{"item": "16", "page": 41, "block": b, "row": "1",
             "station": s, "station_source": "linha impressa do bloco"}
            for b, s in enumerate(["S. Paulo", "Bahia", "Ouro Preto", "Santa Cruz"])]
    apply_station(rows, [{"doc": "16", "page": 41, "station": "Rio de Janeiro",
                          "station_source": "legenda impressa"}])
    assert [r["station"] for r in rows] == ["S. Paulo", "Bahia", "Ouro Preto", "Santa Cruz"]


def test_an_inherited_block_station_also_survives():
    from wrb.merge import apply_station
    rows = [{"item": "15", "page": 142, "block": 1, "row": "1",
             "station": "Maceió", "station_source": "herdada do bloco acima"}]
    apply_station(rows, [{"doc": "15", "page": 142, "station": "Rio de Janeiro",
                          "station_source": "legenda impressa"}])
    assert rows[0]["station"] == "Maceió"


def test_a_page_level_station_still_reaches_the_daily_layouts():
    from wrb.merge import apply_station
    rows = [{"item": "14", "page": 41, "row": 3}]
    n = apply_station(rows, [{"doc": "14", "page": 41, "station": "Imperial Observatório",
                              "station_source": "legenda impressa"}])
    assert n == 1 and rows[0]["station"] == "Imperial Observatório"
