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


def test_restore_thousands_raises_when_no_unique_candidate_in_range():
    with pytest.raises(ValueError):
        restore_thousands(999.99)


def test_restore_thousands_custom_phys_range():
    assert restore_thousands(10.5, phys_range=(300.0, 400.0)) == pytest.approx(310.5)
