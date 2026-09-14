"""The variant registry.

The project's ultimate goal is not one model - it is being able to train and
compare several, cheaply. That needs the variants to be enumerable: which
adapters exist, what each was trained on, and what it measured. Today that
information is scattered across `runs/**/log.json`, `models/**/train_log.json`
and prose in the docs, so "which variant should I use / retrain / compare
against" is answered by memory.

This reads them into one table. It deliberately does NOT invent numbers: a
variant whose accuracy was never measured reports None, not a guess.
"""

import json

from wrb.variants import Variant, collect, format_table


def write_log(tmp_path, run, name, *, base="Qwen/Qwen3.5-2B", rows=100, epochs=2, gold=None):
    d = tmp_path / run / name
    d.mkdir(parents=True, exist_ok=True)
    rec = {"args": {"model": "qwen35", "run": run, "epochs": epochs, "rank": 16},
           "model": base, "train_rows": rows, "dev_rows": 10,
           "epochs": [{"epoch": i + 1, "train_loss": 0.1, "minutes": 40.0} for i in range(epochs)]}
    if gold is not None:
        rec["gold"] = {"cell_acc": gold}
    (d / "log.json").write_text(json.dumps(rec))
    return d


def test_collect_finds_every_variant(tmp_path):
    write_log(tmp_path, "g4", "gen3", gold=0.9)
    write_log(tmp_path, "g4", "smoke4", rows=889)
    vs = collect(tmp_path)
    assert {v.name for v in vs} == {"gen3", "smoke4"}


def test_a_variant_reports_what_it_was_trained_on(tmp_path):
    write_log(tmp_path, "g4", "gen3", base="Qwen/Qwen3.5-2B", rows=390, epochs=3)
    v = collect(tmp_path)[0]
    assert v.base == "Qwen/Qwen3.5-2B"
    assert v.train_rows == 390
    assert v.epochs == 3
    assert v.rank == 16


def test_an_unmeasured_variant_reports_none_not_a_guess(tmp_path):
    write_log(tmp_path, "g4", "smoke4", gold=None)
    assert collect(tmp_path)[0].gold_cell_acc is None


def test_the_train_logs_own_number_is_not_the_variants_accuracy(tmp_path):
    """The log's `gold` is a check taken during training. It is kept, and it is
    NOT the number the variant is measured at - smoke4 reads 0.9545 there
    against a committed final 0.9908."""
    write_log(tmp_path, "g4", "smoke4", gold=0.9545)
    v = collect(tmp_path)[0]
    assert v.gold_cell_acc is None          # nothing was measured for it
    assert v.in_training_gold == 0.9545     # but the run's own check is kept


def test_collect_is_sorted_and_stable(tmp_path):
    for n in ("zeta", "alpha", "mid"):
        write_log(tmp_path, "g4", n)
    assert [v.name for v in collect(tmp_path)] == ["alpha", "mid", "zeta"]


def test_collect_survives_a_broken_log(tmp_path):
    """Half-written logs exist - a training run killed mid-save."""
    good = write_log(tmp_path, "g4", "good")
    bad = tmp_path / "g4" / "bad"
    bad.mkdir(parents=True)
    (bad / "log.json").write_text("{not json")
    assert [v.name for v in collect(tmp_path)] == ["good"]


def test_the_table_shows_the_unmeasured_as_a_dash(tmp_path):
    write_log(tmp_path, "g4", "gen3", gold=0.9)
    write_log(tmp_path, "g4", "smoke4", gold=None)
    table = format_table(collect(tmp_path))
    assert "gen3" in table and "smoke4" in table
    assert "0.900" in table or "90.0%" in table
    assert "—" in table or "-" in table


# --- final measurement vs the in-training check --------------------------
# The train log's `gold` field is a check taken DURING training. smoke4's reads
# 0.9545 there while its committed final evaluation is 0.9908 - so a table that
# reports the log's number understates every variant, and does it silently.
# The authoritative number lives in bench/*-final-gold.json, which names the
# adapter it measured.

def write_final_gold(tmp_path, stem, adapter, acc):
    b = tmp_path / "bench"
    b.mkdir(parents=True, exist_ok=True)
    (b / f"{stem}-final-gold.json").write_text(json.dumps(
        {"model": "Qwen/Qwen3.5-2B", "adapter": adapter, "gold": {"cell_acc": acc}}))


def test_a_variant_prefers_its_committed_final_evaluation(tmp_path):
    write_log(tmp_path, "runs", "smoke4", gold=0.9545)
    write_final_gold(tmp_path, "smoke4-epoch2", "runs/g4/smoke4/epoch2", 0.9908)
    v = collect(tmp_path)[0]
    assert v.gold_cell_acc == 0.9908       # the measured one
    assert v.in_training_gold == 0.9545    # kept, but labelled as what it is


def test_without_a_final_evaluation_the_variant_is_reported_unmeasured(tmp_path):
    """Not 'about the same as the in-training check'. Unmeasured."""
    write_log(tmp_path, "runs", "gen3", gold=0.7857)
    v = collect(tmp_path)[0]
    assert v.gold_cell_acc is None
    assert v.in_training_gold == 0.7857


def test_the_table_distinguishes_the_two_columns(tmp_path):
    write_log(tmp_path, "runs", "smoke4", gold=0.9545)
    write_final_gold(tmp_path, "smoke4-epoch2", "runs/g4/smoke4/epoch2", 0.9908)
    t = format_table(collect(tmp_path))
    assert "0.9908" in t          # final
    assert "final" in t.lower() and "train" in t.lower()
