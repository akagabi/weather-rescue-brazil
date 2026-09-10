"""Sweep every downloaded page of the archive for daily-table geometry.

    python scripts/g4_sweep_archive.py

Answers one question definitively rather than by sample: which pages of the
Observatorio Nacional archive carry a ruled table with day-like row spacing.
Geometry only, no model, no network. Astronomy tables pass this too - the
caption pass is what separates them - but a page that fails it is not a daily
meteorological table.
"""
from __future__ import annotations
import collections, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PIL import Image  # noqa: E402
from wrb.rows import (PROBE_X_FRAC, find_peaks, ink_threshold,  # noqa: E402
                      pitch_candidates, row_profile, vertical_rules)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "docvirt"


def main() -> None:
    out, per_doc = [], collections.Counter()
    paths = sorted(RAW.rglob("*.webp"))
    print(f"{len(paths)} páginas no acervo", flush=True)
    for i, p in enumerate(paths):
        doc = p.parent.name
        try:
            im = Image.open(p).convert("L")
        except Exception:
            continue
        thr = ink_threshold(im)
        if len(vertical_rules(im, thr)) < 4:
            continue
        x0, x1 = int(im.width * PROBE_X_FRAC[0]), int(im.width * PROBE_X_FRAC[1])
        prof, _ = row_profile(im, x0, x1, thr)
        c = pitch_candidates(prof)
        if c and len(find_peaks(prof, c[0])) >= 15:
            out.append({"doc": doc, "page": int(p.stem)})
            per_doc[doc] += 1
        if i % 250 == 0:
            print(f"  {i}/{len(paths)}", flush=True)
    (ROOT / "data" / "g4" / "sweep_archive.json").write_text(json.dumps(out, indent=1))
    print(f"\n{len(out)} candidatas a tabela, por documento:")
    for d, n in sorted(per_doc.items(), key=lambda x: -x[1]):
        print(f"  doc {d}: {n}")


if __name__ == "__main__":
    main()
