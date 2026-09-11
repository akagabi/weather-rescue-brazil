"""The human verification queue.

Nothing in this dataset has ever been checked against the page it came from -
the frozen gold set is a separate evaluation corpus, not part of the published
rows. This module builds the queue a person reads: a stratified sample of the
usable tier, one entry per row, carrying what the UI needs to show the row's
crop beside the values it claims.

The sampling rules are the point. A sample drawn only from one profile would
answer a question nobody asked; a sample that included `flagged` rows would
misstate the tier being verified (those are already known to need review).
"""

from wrb.verify import build_queue, summarise_verdicts


def row(profile="revista-rio-1886", item="14", page=1, n=0, verdict="checks_pass",
        is_day=True, day=1, **kw):
    return {"profile": profile, "item": item, "page": page, "row": n, "period": "1886-01",
            "verdict": verdict, "is_day_row": is_day, "values": {"day": day}, **kw}


def test_queue_takes_only_usable_day_rows():
    rows = [row(n=0), row(n=1, verdict="flagged"), row(n=2, verdict="qc_clean"),
            row(n=3, is_day=False), row(n=4)]
    q = build_queue(rows, per_profile=10, seed=0)
    got = {e["row"] for e in q}
    assert got == {0, 2, 4}


def test_queue_covers_every_profile_that_has_usable_rows():
    rows = ([row(profile="A", n=i) for i in range(50)]
            + [row(profile="B", n=i) for i in range(3)]
            + [row(profile="C", n=i, verdict="flagged") for i in range(50)])
    q = build_queue(rows, per_profile=5, seed=0)
    assert {e["profile"] for e in q} == {"A", "B"}      # C has nothing usable


def test_queue_is_deterministic_for_a_seed():
    rows = [row(profile="A", n=i) for i in range(100)]
    assert build_queue(rows, per_profile=7, seed=3) == build_queue(rows, per_profile=7, seed=3)
    assert build_queue(rows, per_profile=7, seed=3) != build_queue(rows, per_profile=7, seed=4)


def test_queue_never_repeats_a_row():
    rows = [row(profile="A", page=p, n=n) for p in range(3) for n in range(4)]
    q = build_queue(rows, per_profile=99, seed=0)
    assert len({e["id"] for e in q}) == len(q)


def test_queue_entry_carries_what_the_ui_needs():
    q = build_queue([row(profile="A", item="8", page=39, n=4, day=7)], per_profile=1, seed=0)
    e = q[0]
    assert e["item"] == "8" and e["page"] == 39 and e["row"] == 4
    assert e["profile"] == "A" and e["day"] == 7 and e["verdict"] == "checks_pass"
    assert e["id"] == "A/8/39/4"


def test_summary_separates_correct_from_wrong():
    v = [{"profile": "A", "verdict": "ok"}, {"profile": "A", "verdict": "wrong"},
         {"profile": "B", "verdict": "ok"}]
    s = summarise_verdicts(v)
    assert s["total"] == 3 and s["ok"] == 2 and s["wrong"] == 1
    assert s["by_profile"]["A"] == {"ok": 1, "wrong": 1, "total": 2}
    assert s["by_profile"]["B"]["wrong"] == 0


def test_summary_error_rate_is_about_rows_not_profiles():
    v = [{"profile": "A", "verdict": "wrong"} for _ in range(3)]
    assert summarise_verdicts(v)["error_rate"] == 1.0
    assert summarise_verdicts([])["error_rate"] == 0.0
