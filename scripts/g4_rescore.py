"""Re-derive dataset verdicts from the stored model output, no model needed.

    python scripts/g4_rescore.py data/dataset/weather-rescue-brazil.jsonl

Every row keeps the model's raw text, so improving the parser or the QC rules
means rescoring, not re-reading 1200 pages. Keeps the pipeline honest too: the
reading and the judgement about it are separate artefacts.
"""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wrb import profile as prof  # noqa: E402
from wrb.profile import PADDED_TRAILING  # noqa: E402

src = Path(sys.argv[1])
rows = [json.loads(l) for l in src.open()]
cache: dict[str, prof.Profile] = {}
stats: Counter = Counter()
out = src.with_name(src.stem + ".rescored.jsonl").open("w")
for r in rows:
    p = cache.setdefault(r["profile"], prof.load(r["profile"]))
    values, problems = p.parse(r["raw"])
    markers = dict(getattr(p, "last_markers", {}) or {})
    restored = p.from_printed(values)
    viol = p.violations(restored)
    fails = p.verify(restored) if p.checks else []
    hard = [x for x in problems if x != PADDED_TRAILING]
    scoreable = bool(p.checks) and any(isinstance(restored.get(c["result"]), (int, float)) for c in p.checks)
    # A page whose located row count does not equal the days in its month has
    # picked up rows that are not days - the Revista prints a decade sub-total
    # ("Dec.") and a month total ("Mez") in the same column, and the locator
    # takes them for days. Those rows ARE plausible numbers in plausible
    # ranges, so no per-row check can catch them; only the page-level count
    # can. Until the page closes, none of its rows may be called usable.
    page_ok = r.get("page_rows_located_ok", True)
    verdict = ("flagged" if not page_ok
               else "checks_pass" if scoreable and not fails and not viol and not hard
               else "qc_clean" if not viol and not hard and not fails
               else "flagged")
    if not page_ok:
        problems = problems + ["page_row_count_did_not_close"]
    r.update(values_as_printed=values, values=restored, markers=markers, verdict=verdict,
             padded_trailing=PADDED_TRAILING in problems, problems=problems,
             range_violations=viol, check_failures=fails)
    stats[verdict] += 1
    stats["padded"] += PADDED_TRAILING in problems
    out.write(json.dumps(r, ensure_ascii=False) + "\n")
out.close()
usable = stats["checks_pass"] + stats["qc_clean"]
print(f"{len(rows)} rows -> {dict(stats)}")
print(f"usable (checks_pass + qc_clean): {usable}/{len(rows)} = {usable / len(rows):.1%}")
print("wrote", src.with_name(src.stem + ".rescored.jsonl").name)
