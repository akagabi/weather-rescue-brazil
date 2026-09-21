"""Which candidate a contested day belongs to.

The oracle asks the reader for the day number at every candidate row. A
candidate that is not a row at all - a header strip above the table - still
gets an answer, and the answer is "1", because that is what the reader says
when there is nothing to read. Doc 8 page 43 has six such strips, so day 1 had
seven claimants and the uniqueness rule deleted it.

Days increase down the page at a near-constant pitch, so the settled days draw
a line and the right claimant is the one on it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def resolve(by_day, pitch=24.0):
    """The assignment step, lifted out of the model loop."""
    assigned = {d: ys[0] for d, ys in by_day.items() if len(ys) == 1}
    contested = {d: ys for d, ys in by_day.items() if len(ys) > 1}
    if contested and len(assigned) >= 3:
        xs = sorted(assigned)
        n = len(xs)
        mean_d = sum(xs) / n
        mean_y = sum(assigned[d] for d in xs) / n
        var = sum((d - mean_d) ** 2 for d in xs)
        if var > 0:
            slope = sum((d - mean_d) * (assigned[d] - mean_y) for d in xs) / var
            for d, ys in contested.items():
                want = mean_y + slope * (d - mean_d)
                best = min(ys, key=lambda y: abs(y - want))
                if abs(best - want) <= 1.5 * pitch:
                    assigned[d] = best
    return assigned


def test_the_page_43_shape_recovers_day_one():
    """Six header strips read as 1, plus the real day 1 at the top of the table."""
    by_day = {1: [120, 150, 180, 210, 240, 270, 600],   # last one is the real row
              2: [624], 3: [648], 4: [672], 5: [696]}
    got = resolve(by_day)
    assert got[1] == 600


def test_an_unsettled_page_leaves_the_contested_day_alone():
    """Fewer than three settled days is not a line."""
    assert 1 not in resolve({1: [120, 600], 2: [624]})


def test_claimants_nowhere_near_the_line_are_all_refused():
    """A day with a SINGLE candidate is settled by definition and never reaches
    this check - the monotonicity pass downstream is what catches a lone bad
    one. This is about a contested day none of whose claimants fit."""
    by_day = {1: [5000, 5200], 2: [624], 3: [648], 4: [672], 5: [696]}
    assert 1 not in resolve(by_day)


def test_settled_days_are_untouched():
    by_day = {d: [600 + 24 * (d - 1)] for d in range(1, 6)}
    got = resolve(by_day)
    assert got == {d: 600 + 24 * (d - 1) for d in range(1, 6)}


def test_a_contested_day_in_the_middle_picks_its_own_row():
    by_day = {1: [600], 2: [624], 3: [100, 648, 2000], 4: [672], 5: [696]}
    assert resolve(by_day)[3] == 648


# --- what to do when neither end of the month was confirmed -----------------

def bracket(keep: dict, day_count: int):
    """The day range the confirmed days can carry, as resolve_by_oracle picks it."""
    known = sorted(keep)
    if not known:
        return None
    return (1, day_count) if (1 in keep and day_count in keep) else (known[0], known[-1])


def test_a_page_with_both_ends_confirmed_covers_the_month():
    keep = {d: 100 + 24 * d for d in [1, 5, 12, 20, 30]}
    assert bracket(keep, 30) == (1, 30)


def test_a_page_missing_both_ends_covers_what_it_brackets():
    """Doc 5 page 342 read twenty of its thirty days and was thrown away whole
    because neither end was among them."""
    keep = {d: 100 + 24 * d for d in range(4, 27)}
    assert bracket(keep, 30) == (4, 26)


def test_one_end_confirmed_is_still_only_the_bracket():
    """Day 1 alone does not license extrapolating past the last known day."""
    keep = {d: 100 + 24 * d for d in [1, 5, 12, 22]}
    assert bracket(keep, 30) == (1, 22)


def test_nothing_confirmed_brackets_nothing():
    assert bracket({}, 30) is None


# --- placing unread days on the line the read ones fit -------------------
# `min_direct` is a count, and a count is a proxy. These pages read 20-24 of
# 31 days because the Annales set their dates in old-style figures; what
# decides whether the rest can be placed is whether the confirmed days
# reproduce the page's own measured pitch.

sys.path.insert(0, str(ROOT / "scripts"))
from g4_build_dataset import _line_through_days  # noqa: E402


def test_days_on_the_page_pitch_are_accepted():
    pitch = 28.0
    keep = {d: 100 + round(pitch * d) for d in (1, 3, 4, 7, 9, 12, 15, 18, 22, 29)}
    fit = _line_through_days(keep, pitch)
    assert fit["accept"]
    assert abs(fit["slope"] - pitch) < 0.5
    assert fit["max_resid"] < 1.0


def test_a_slope_that_contradicts_the_measured_pitch_is_refused():
    """The ink profile measured the pitch without ever seeing a day number.
    If the assignment implies a different spacing, one of them is wrong."""
    pitch = 28.0
    keep = {d: 100 + round(14.0 * d) for d in range(1, 15)}   # every OTHER row
    fit = _line_through_days(keep, pitch)
    assert not fit["slope_ok"]
    assert not fit["accept"]


def test_one_badly_placed_day_refuses_the_whole_fit():
    pitch = 28.0
    keep = {d: 100 + round(pitch * d) for d in range(1, 13)}
    keep[6] += 40                       # a misassignment, well over 0.35 pitch
    fit = _line_through_days(keep, pitch)
    assert not fit["resid_ok"]
    assert not fit["accept"]


def test_too_few_days_is_not_a_line():
    pitch = 28.0
    assert _line_through_days({1: 128, 2: 156, 3: 184}, pitch) is None


def test_no_pitch_no_fit():
    assert _line_through_days({d: d * 10 for d in range(1, 20)}, 0.0) is None


def test_a_two_rows_per_day_layout_is_refused_with_a_reason_not_silently():
    """Corumba prints two readings a day, so `day_count` is 62 while only 31
    distinct day numbers exist. The oracle keys its assignment BY DAY, so at
    most 31 can ever be confirmed and a bar of 0.55*62 is unreachable however
    well the page reads - doc 16 page 72 read 30 of its 31 days and was
    refused. The fix is not built; being told why is."""
    from g4_build_dataset import resolve_by_oracle

    class NeverCalled:
        def read_days(self, crops):                    # pragma: no cover
            raise AssertionError("the guard must fire before any model call")

    centres, info = resolve_by_oracle(NeverCalled(), None, None, 62,
                                      min_direct=0.55, distinct_days=31)
    assert centres is None
    assert "rows per day" in info["reason"]
    assert "not a reading failure" in info["reason"]


def test_a_one_row_per_day_layout_is_not_caught_by_that_guard():
    """31 days, 31 rows, bar 17 - reachable, so the guard must stay out of
    the way and let the normal path run."""
    from g4_build_dataset import resolve_by_oracle
    calls = []

    class Recorder:
        def read_days(self, crops):
            calls.append(len(crops))
            return [None] * len(crops)

    class Loc:
        pitch = 24.0
        chain = [100, 124, 148]
        peaks = [100, 124, 148]
        skew_deg = 0.0
        day_boxes = [(0, 88, 500, 112)]

    from PIL import Image
    img = Image.new("RGB", (600, 900), "white")
    centres, info = resolve_by_oracle(Recorder(), img, Loc(), 31,
                                      min_direct=0.55, distinct_days=31)
    assert calls, "the guard fired on a layout it should not have"
    assert centres is None            # nothing read, so it still refuses
    assert "rows per day" not in (info.get("reason") or "")
