"""Deterministic barometer thousands/hundreds-digit reconstruction.

See gold/SELECTION.md "Decimal / elision conventions" #2: the source's
barometer columns print the full value only on a table's first row; every
later row elides the leading hundreds(+thousands) digit(s), printing only
the low-order two digits before the decimal (e.g. `51.69` for a `751.69`
reading). This module recovers that elided prefix MECHANICALLY - by finding
the unique multiple-of-100 prefix that lands the value inside `phys_range`
- and nothing else.

It must never re-derive a *different* prefix from neighbouring-row
smoothness or a min<=mean<=max ordering constraint; that judgment call
belongs to the human gold reviewer (see gold/SELECTION.md's binding
"faithful to print" convention), not this function. Concretely:
`restore_thousands(742.03)` must return `742.03` unchanged even though that
literal value might be an impossible outlier against its neighbours - it is
already the correct answer to "what value in phys_range has these
low-order digits", which is all this function is allowed to decide.
"""


def restore_thousands(low: float, phys_range: tuple[float, float] = (700.0, 780.0)) -> float:
    """Return the unique value in `phys_range` obtained by prefixing `low`'s
    low-order two digits (`low % 100`) with a whole-hundreds leading digit.

    This is idempotent on an already-full value that happens to be the
    unique in-range candidate for its own low-order digits (e.g. the
    table's un-elided first row, or a gold cell already carrying its
    reconstructed prefix) - see the faithful-impossible case above.

    Raises ValueError if zero or more than one candidate value falls
    inside phys_range (an out-of-range or ambiguous printed low-order
    value) - this function never guesses in that case.
    """
    lo, hi = phys_range
    frac = round(low % 100, 2)
    candidates = []
    hundreds = 0
    while hundreds <= 900:
        candidate = round(hundreds + frac, 2)
        if lo <= candidate <= hi:
            candidates.append(candidate)
        hundreds += 100
    if len(candidates) != 1:
        raise ValueError(
            f"restore_thousands({low!r}, phys_range={phys_range!r}): found "
            f"{len(candidates)} candidate value(s) in range, expected exactly 1 "
            f"(candidates: {candidates})"
        )
    return candidates[0]
