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

Default range (700.0, 800.0): this station's era barometer readings are
always in the 700s mmHg - the real gold set (see gold/sheets/*.json, all 9
sheets) spans roughly 742-796, including a genuine printed_error outlier at
795.72 (day 19, 14_142.json - "the compositor printed 95.72", a physically
extreme-but-faithful reading that still belongs in the 700s bracket). A
plain (700.0, 780.0) window (an earlier draft of this module) silently
excluded that legitimate value - see the Task 1 fix report. The range's
upper bound is treated as EXCLUSIVE specifically to avoid a boundary tie: a
full-100-wide inclusive-both-ends window has exactly one degenerate case
(a printed low-order fraction of `.00`) where both `hundreds=700` (giving
`700.00`) and `hundreds=800` (giving `800.00`) would satisfy an
inclusive-on-both-ends test simultaneously. Making the upper bound
exclusive removes that tie entirely (a genuine `800.00`+ reading, which
does not occur in this station's data, would then raise rather than be
silently guessed) while still resolving every real 7xx.xx fraction to the
single correct `700 + fraction` answer.
"""


def restore_thousands(low: float, phys_range: tuple[float, float] = (700.0, 800.0)) -> float:
    """Return the unique value in `[phys_range[0], phys_range[1])` obtained
    by prefixing `low`'s low-order two digits (`low % 100`) with a
    whole-hundreds leading digit. The upper bound is EXCLUSIVE (see the
    module docstring) - this is what keeps a full-100-wide window
    (like the default) from ever producing two candidates.

    This is idempotent on an already-full value that happens to be the
    unique in-range candidate for its own low-order digits (e.g. the
    table's un-elided first row, or a gold cell already carrying its
    reconstructed prefix) - see the faithful-impossible case above.

    Raises ValueError if zero or more than one candidate value falls
    inside the range (an out-of-range or ambiguous printed low-order
    value) - this function never guesses in that case.
    """
    lo, hi = phys_range
    frac = round(low % 100, 2)
    candidates = []
    hundreds = 0
    while hundreds <= 900:
        candidate = round(hundreds + frac, 2)
        if lo <= candidate < hi:
            candidates.append(candidate)
        hundreds += 100
    if len(candidates) != 1:
        raise ValueError(
            f"restore_thousands({low!r}, phys_range={phys_range!r}): found "
            f"{len(candidates)} candidate value(s) in [{lo}, {hi}), expected "
            f"exactly 1 (candidates: {candidates})"
        )
    return candidates[0]
