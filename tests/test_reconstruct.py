import pytest

from wrb.reconstruct import restore_thousands


def test_restore_thousands_42_03_to_742_03():
    assert restore_thousands(42.03) == pytest.approx(742.03)


def test_restore_thousands_51_44_to_751_44():
    assert restore_thousands(51.44) == pytest.approx(751.44)


def test_restore_thousands_62_39_to_762_39():
    assert restore_thousands(62.39) == pytest.approx(762.39)


def test_restore_thousands_faithful_impossible_742_03_stays_742_03():
    """gold/SELECTION.md's binding convention: reconstruction only ADDS a
    leading digit, it never re-derives a different decade even when the
    result looks physically impossible against neighbouring days. Feeding
    an already-full value back in must return it unchanged."""
    assert restore_thousands(742.03) == pytest.approx(742.03)


def test_restore_thousands_gold_printed_error_outlier_795_72_stays_795_72():
    """Coordinator fix (post Task-1-approval, before the paid probe): the
    real gold set (gold/sheets/14_142.json, day 19 pressure_max) has a
    genuine printed_error value of 795.72 - a physically extreme but
    faithful-to-print reading. The original (700.0, 780.0) default window
    excluded it (ValueError), which would have made that gold cell
    UNRECOVERABLE by g2b and silently understated g2b's true accuracy on
    the upcoming paid probe. The widened default (700.0, 800.0) must
    recover it, and it must stay 795.72 - not get "corrected" toward the
    780s just because 795.72 is itself an outlier."""
    assert restore_thousands(95.72) == pytest.approx(795.72)
    assert restore_thousands(795.72) == pytest.approx(795.72)  # idempotent, same as 742.03 above


def test_restore_thousands_751_44_stays_751_44_when_fed_back_in():
    assert restore_thousands(751.44) == pytest.approx(751.44)


def test_restore_thousands_762_39_stays_762_39_when_fed_back_in():
    assert restore_thousands(762.39) == pytest.approx(762.39)


def test_restore_thousands_raises_when_no_unique_candidate_in_range():
    # The widened default (700.0, 800.0) is a full 100-wide window, so it
    # always finds exactly one candidate for ANY low-order fraction - by
    # design (this station's readings are always in the 700s, so there is
    # never a genuine ambiguity to reject). To exercise the "no candidate"
    # failure path, use an explicitly narrower phys_range instead.
    with pytest.raises(ValueError):
        restore_thousands(50.0, phys_range=(700.0, 720.0))


def test_restore_thousands_custom_phys_range():
    assert restore_thousands(10.5, phys_range=(300.0, 400.0)) == pytest.approx(310.5)


def test_restore_thousands_full_width_range_never_ties_on_boundary_fraction():
    """The exclusive-upper-bound design (see module docstring) exists
    specifically so a `.00`-fraction value can't satisfy both the
    `hundreds=700` and `hundreds=800` candidates simultaneously under a
    full-100-wide inclusive-both-ends window. Lock in that a `.00`
    fraction resolves uniquely rather than raising an ambiguity error."""
    assert restore_thousands(0.0) == pytest.approx(700.0)
