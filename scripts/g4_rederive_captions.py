"""Re-derive a sweep's profile and period from the captions it already read.

    python scripts/g4_rederive_captions.py data/g4/identified_rest.json --write

A sweep stores the profile and period it worked out at the time. When the
matcher changes - and it has twice tonight, once for "Rio de Janeiro"
containing "janeiro" and once for Annales sheets being handed a Revista
profile - those stored answers are stale, and a sweep is expensive to repeat
for something the captions can settle in a second.

The caption itself is the reading and is never touched. Only the conclusions
drawn from it are recomputed.
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.caption import is_astronomy, match_period, match_profile  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    for f in args.files:
        path = Path(f)
        recs = json.loads(path.read_text())
        changed = []
        for r in recs:
            cap = r.get("caption")
            if not cap:
                continue
            astro = is_astronomy(cap)
            new = {"astronomy": astro,
                   "is_weather_table": "NOT_WEATHER" not in cap.upper() and not astro}
            new["profile"] = match_profile(cap) if new["is_weather_table"] else None
            new["period"] = match_period(cap) if new["is_weather_table"] else None
            # A field the record never had is not a change worth reporting:
            # adding `astronomy` to an old sweep touched all 269 records and
            # buried the six that actually moved.
            diff = {k: (r.get(k), v) for k, v in new.items()
                    if r.get(k) != v and (k in r or v not in (None, False))}
            if diff:
                changed.append((r.get("doc"), r.get("page"), diff, cap))
                r.update(new)
        print(f"{path.name}: {len(changed)} of {len(recs)} records re-derived")
        for doc, page, diff, cap in changed[:20]:
            bits = ", ".join(f"{k} {a!r}->{b!r}" for k, (a, b) in diff.items())
            print(f"  {doc}/{page}: {bits}")
            print(f"        | {cap[:76]}")
        if args.write and changed:
            path.write_text(json.dumps(recs, indent=1, ensure_ascii=False))
            print(f"  wrote {path}")
    if not args.write:
        print("\nreport only - re-run with --write")


if __name__ == "__main__":
    main()
