"""Freezing the published dataset.

Everything downstream - the SEF export, the Hugging Face package, a number
quoted in a paper - refers to a specific state of this file. Nothing recorded
which state that was: the dataset has already changed three times in one day
under re-scoring alone (3070 -> 3059 -> 2895 usable), and the sidecar summary
had drifted two revisions behind it before anyone noticed.

`g4_rescore.py` can regenerate the file from the stored raw at any time, which
is a feature - and exactly why the published bytes need a recorded fingerprint.
"""

import json

from wrb.freeze import check_version, fingerprint, write_version


def row(v="checks_pass", day=True, vals=None):
    return {"verdict": v, "is_day_row": day, "values": vals if vals is not None else {"day": 1, "t": 20.0}}


def test_fingerprint_counts_and_hashes(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in [row(), row("flagged", False), row("qc_clean")]) + "\n")
    fp = fingerprint(p)
    assert fp["rows"] == 3
    assert fp["usable"] == 2
    assert fp["values_usable"] == 4          # 2 usable day rows x 2 non-null values
    assert len(fp["sha256"]) == 64


def test_a_frozen_version_verifies_against_its_own_file(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text(json.dumps(row()) + "\n")
    v = tmp_path / "version.json"
    write_version(p, "0.1", v)
    assert check_version(p, v) == []


def test_a_changed_row_is_caught(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text(json.dumps(row()) + "\n")
    v = tmp_path / "version.json"
    write_version(p, "0.1", v)
    # one value re-scored - exactly the kind of silent drift this exists for
    p.write_text(json.dumps(row(vals={"day": 1, "t": 99.0})) + "\n")
    problems = check_version(p, v)
    assert problems and "changed" in problems[0].lower()


def test_a_missing_version_file_says_so(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text(json.dumps(row()) + "\n")
    assert check_version(p, tmp_path / "nope.json") != []
