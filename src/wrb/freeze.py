"""Record which state of the dataset was published.

The dataset can be regenerated at any time from the stored model output -
`g4_rescore.py` re-derives every verdict and every value, in under a second,
with no model and no images. That is the project's central design bet, and it
is also why the published bytes need a fingerprint: nothing in the repo records
which state a downstream artefact referred to.

It matters in practice. In a single day of review the file went 3,070 -> 3,059
-> 2,895 usable rows under re-scoring alone, and its sidecar summary had drifted
two revisions behind it before anyone noticed.

The convention: `data/dataset/version.json` is written once, when a state is
declared published, and never regenerated silently. `check_version` is what a
release step - or a test - runs to prove the file on disk is still the one that
was published.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def fingerprint(dataset: Path) -> dict:
    """Counts plus a content hash, from the rows themselves.

    The hash is over the file bytes, not over a re-serialisation, so it also
    catches a change in field order or whitespace - anything that would make a
    downstream copy differ from the published one.
    """
    data = Path(dataset).read_bytes()
    rows = [json.loads(l) for l in data.decode().splitlines() if l.strip()]
    usable_rows = [r for r in rows if r.get("verdict") in ("checks_pass", "qc_clean")]
    values = sum(1 for r in usable_rows if r.get("is_day_row")
                 for v in (r.get("values") or {}).values() if v is not None)
    return {
        "rows": len(rows),
        "usable": len(usable_rows),
        "values_usable": values,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def write_version(dataset: Path, version: str, out: Path) -> dict:
    """Freeze the current state as `version`. Overwrites deliberately - this is
    the explicit act of declaring a new state published, not a side effect."""
    import datetime
    fp = fingerprint(dataset)
    rec = {"version": version, "frozen_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
           "dataset": Path(dataset).name, **fp}
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    return rec


def check_version(dataset: Path, version_file: Path) -> list[str]:
    """Empty when the file on disk is still the published one."""
    vp = Path(version_file)
    if not vp.exists():
        return [f"no version file at {vp} - nothing records what was published"]
    rec = json.loads(vp.read_text())
    now = fingerprint(dataset)
    if now["sha256"] != rec.get("sha256"):
        return [f"dataset changed since {rec.get('version')} was frozen "
                f"({rec.get('rows')} rows then, {now['rows']} now; "
                f"sha256 {rec.get('sha256', '')[:12]} -> {now['sha256'][:12]})"]
    return []
