"""Localising rows with the production reader instead of a zero-shot model.

The zero-shot day oracle cannot read the Annales' old-style date figures and
refused 43 legible pages over it. The reader can, because the day is cell 0 of
every row target it was trained on. What is unit-testable here is the part
that turns a row transcription back into a day number - the rest is a model
call, measured in docs/g4-wind-locator.md.
"""

import pytest

from wrb.oracle import AdapterDayOracle, first_printed_int


@pytest.mark.parametrize("text,want", [
    ("13 | 29.5 | 7", 13),
    ("1 | null | null", 1),
    ("  07 | x", 7),
    ("31 | 762.1 | 20.4 | SSE | 2", 31),
    # a leading ditto is not a day: Corumba writes the day once and dittos the
    # second reading, and the resolution for that belongs to the page pass
    ("» | 2 | 3", None),
    ("null | 5", None),
    ("", None),
    (None, None),
    # old-style figures the reader failed to resolve stay unread rather than
    # becoming a wrong number
    ("IO | 3", None),
])
def test_first_printed_int(text, want):
    assert first_printed_int(text) == want


def test_it_reads_the_first_cell_not_the_first_digit_anywhere():
    """`13 | 29.5` must be 13. Reaching into the barometer column for a
    number is how a row gets assigned to the wrong day."""
    assert first_printed_int("13 | 29.5 | 7") == 13
    assert first_printed_int("null | 29.5") is None


def test_the_oracle_does_not_load_a_second_model():
    """Two 2B models resident at once is how this last ran a laptop out of
    memory, so the oracle takes the reader that is already loaded."""
    sentinel_model, sentinel_proc = object(), object()
    o = AdapterDayOracle(sentinel_model, sentinel_proc, "cpu", instruction="x")
    assert o.model is sentinel_model and o.proc is sentinel_proc
    # and it stops after the first cell rather than decoding the whole row
    assert o.max_new_tokens == 10


def test_the_producer_offers_the_adapter_oracle():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "scripts" / "g4_produce.py").read_text()
    assert '"none", "torch", "mlx", "adapter"' in src
    assert "AdapterDayOracle(model, procr, dev" in src
