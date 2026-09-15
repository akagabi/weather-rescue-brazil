"""How much of the archive has been looked at, and what is left.

    python scripts/g4_coverage.py

Three numbers per document, each from a different artefact, because they answer
different questions and were repeatedly confused for one another:

  candidates  pages whose geometry says "ruled table with day-like rows"
              (data/g4/sweep_archive.json) - a cheap filter that astronomy and
              two-column prose both pass
  identified  pages whose caption has been read (data/g4/identified*.json)
  produced    pages that reached a dataset (data/dataset/*.jsonl)

The gap between the first two is work not yet done. The gap between the second
and third is mostly work that SHOULD not be done - pages read and found to be
prose, ephemerides or a layout with no profile - and that is the distinction
the triage exists to make.
"""
from __future__ import annotations

import collections, glob, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.caption import load_volume_spans  # noqa: E402


def main() -> None:
    sweep = json.loads((ROOT / "data" / "g4" / "sweep_archive.json").read_text())
    cand = collections.Counter(str(x.get("doc")) for x in sweep)

    seen: set[tuple] = set()
    for f in glob.glob(str(ROOT / "data" / "g4" / "identified*.json")):
        for r in json.loads(Path(f).read_text()):
            if isinstance(r, dict) and r.get("caption"):
                seen.add((str(r.get("doc", r.get("item"))), int(r["page"])))

    produced: set[tuple] = set()
    for f in (ROOT / "data" / "dataset").glob("*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                produced.add((str(r.get("item")), int(r.get("page", -1))))

    spans = (load_volume_spans() or {}).get("spans", {})
    docs = sorted(set(cand) | {k[0] for k in seen},
                  key=lambda d: (len(d), d))
    # An Internet Archive identifier is forty characters and would set the
    # column width for the thirteen DocVirt volumes that are two digits.
    def label(d: str) -> str:
        return d if len(d) <= 12 else d[:11] + "\u2026"

    w = max(5, max((len(label(d)) for d in docs), default=5) + 1)
    print(f"{'doc':<{w}}{'cand':>6}{'ident':>7}{'prod':>6}{'unread':>8}  publication")
    tot = [0, 0, 0, 0]
    for d in docs:
        n = cand.get(d, 0)
        ident = sum(1 for k in seen if k[0] == d)
        prod = sum(1 for k in produced if k[0] == d)
        # a document may be identified beyond its sweep candidates (samples,
        # hand-picked pages), so unread is clamped at zero rather than going
        # negative and looking like an error
        unread = max(0, n - ident)
        pub = (spans.get(d) or {}).get("publication", "")
        print(f"{label(d):<{w}}{n:>6}{ident:>7}{prod:>6}{unread:>8}  {pub}")
        tot = [a + b for a, b in zip(tot, (n, ident, prod, unread))]
    print(f"{'all':<{w}}{tot[0]:>6}{tot[1]:>7}{tot[2]:>6}{tot[3]:>8}")


if __name__ == "__main__":
    main()
