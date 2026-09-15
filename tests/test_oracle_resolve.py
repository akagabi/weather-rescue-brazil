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
