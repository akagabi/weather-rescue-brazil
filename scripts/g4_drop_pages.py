"""Drop pages from a produced file, with the reason recorded.

    python scripts/g4_drop_pages.py data/dataset/annales_doc8b.jsonl \
        --pages data/g4/cloud_form_pages.json --write

A page read under a layout that is not its own does not belong in a dataset.
Its rows would be flagged anyway - cloud-form letters do not parse as a wind
force - but two hundred rows of cirrus under wind-direction names is noise, and
a consumer filtering on `verdict` should not have to know that.

The pages are not forgotten. The list they come from says what they actually
are, so they can be produced properly once a profile exists for them.
"""
from __future__ import annotations

import argparse, collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--pages", required=True, help="JSON with a `pages` list of {doc, page}")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    spec = json.loads(Path(args.pages).read_text())
    drop = {(str(p.get("doc", p.get("item"))), int(p["page"]))
            for p in (spec.get("pages") if isinstance(spec, dict) else spec)}

    path = Path(args.dataset)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    keep = [r for r in rows if (str(r.get("item")), int(r.get("page", -1))) not in drop]
    gone = collections.Counter((str(r.get("item")), int(r.get("page", -1)))
                               for r in rows if r not in keep)

    print(f"{len(rows)} rows, dropping {len(rows) - len(keep)} from "
          f"{len(gone)} pages named in {Path(args.pages).name}")
    for (doc, page), n in sorted(gone.items()):
        print(f"   {doc}/{page:<6} {n} rows")
    print(f"{len(keep)} rows kept")
    if args.write:
        tmp = path.with_suffix(path.suffix + ".partial")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
        tmp.replace(path)
        print(f"rewrote {path}")
    else:
        print("report only - re-run with --write")


if __name__ == "__main__":
    main()
