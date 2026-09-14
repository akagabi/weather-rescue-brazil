"""Pre-fill the review UI's labels with the model's own read.

READ THIS BEFORE TRUSTING IT ON A NEW LAYOUT. It is only safe when the model
gets the CELL COUNT right. Measured on the Revista's dekadal summary (17 and 34
columns), it does not: fed the correct crop it read

    page : 760.71 | 1.24 | 764.50 | 7 | 752.25 | 1 | 12.25 | 19.04 | 1.175 | 22.00 | ...
    model: 760.71 | 1.24 | 764.5  | 7 | 752.25 |     | 12.25 | 10.04 | 1.175 | 22    | ...

- it DROPPED the `1` and the `19.04`, so everything after them is shifted, and
then padded 28 trailing nulls to a length it believed it knew. A person
correcting a shifted row may well not notice, which makes a misaligned pre-fill
WORSE than blank fields. So: run it, then CHECK the cell counts it reports, and
delete the output if they are wrong.

    python scripts/g4_prefill_labels.py --profile revista-mensal-baroterm \
        --pages data/g4/worklist_doc5.json --dry-run
    python scripts/g4_prefill_labels.py --profile revista-mensal-baroterm \
        --pages data/g4/worklist_doc5.json --yes

Writing the first pass by hand is what makes a new layout expensive: this one is
34 columns wide, and 4 rows x 34 columns typed from a scan is an hour of work
per page. The model already reads most of it - on the upper block it got 14 of
15 cells right - so the human job should be CORRECTING, not transcribing.

That is also the loop the project is built around: the model proposes, a person
verifies, and the verified rows become the training set for the next variant
(wrb.variants is how those get compared).

Writes `data/labels/<profile>/<doc>_<page:06d>.json` in the format
`wrb.workbench` reads, so the page opens with the values already in place. It
does NOT mark them verified - a pre-filled label is a model reading and stays
indistinguishable from one in the provenance until a person touches it.
"""

from __future__ import annotations

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from wrb import profile as prof                      # noqa: E402
from wrb.dataset import boxes_for_centres, crop_boxes  # noqa: E402
from wrb.rows import locate_day_rows                   # noqa: E402
from wrb.workbench import LABELS, label_path, save_labels  # noqa: E402
from g4_train import INSTRUCTION_PRINTED               # noqa: E402


def read_page(reader, p: prof.Profile, item: str, page: int, period: str) -> list[str] | None:
    img = ROOT / "data" / "raw" / "docvirt" / str(item) / f"{page:06d}.webp"
    if not img.exists():
        return None
    from PIL import Image
    image = Image.open(img).convert("RGB")
    loc = locate_day_rows(image, p.expected_rows(period), **p.geometry())
    if not loc.chain:
        return None
    crops = crop_boxes(image, boxes_for_centres(loc.chain, loc, *image.size), loc.skew_deg, scale=2.0)
    return reader.read_rows(crops)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--pages", required=True, help="JSON: {\"pages\": [{doc, page, period}, ...]}")
    ap.add_argument("--model", default="runs/g4/mlx-smoke4-q8")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--only-missing", action="store_true", default=True,
                    help="skip pages that already have labels (default)")
    args = ap.parse_args()

    from g4_disagree import PrintedRowReader
    p = prof.load(args.profile)
    pages = json.loads(Path(args.pages).read_text())["pages"]
    print(f"{args.profile}: {len(pages)} pages, {p.n_cells} columns, "
          f"{p.expected_rows(pages[0]['period']) if pages else '?'} rows/page")

    if args.dry_run or not args.yes:
        for w in pages:
            exists = label_path(args.profile, str(w.get("doc", w.get("item"))), w["page"]).exists()
            print(f"   {w.get('doc', w.get('item'))}/{w['page']:<5} {w.get('period')}  "
                  f"{'already labelled' if exists else 'to pre-fill'}")
        print("\nDRY RUN - nothing written. Re-run with --yes.")
        return

    reader = PrintedRowReader(str(ROOT / args.model))
    written = 0
    for w in pages:
        item = str(w.get("doc", w.get("item")))
        page, period = int(w["page"]), w["period"]
        if args.only_missing and label_path(args.profile, item, page).exists():
            print(f"   {item}/{page}: labels exist, skipped")
            continue
        raws = read_page(reader, p, item, page, period)
        if raws is None:
            print(f"   {item}/{page}: no rows located, skipped")
            continue
        rows = {}
        for i, raw in enumerate(raws):
            values, problems = p.parse(raw)
            rows[str(i)] = {c.key: values.get(c.key) for c in p.columns}
            if problems:
                print(f"   {item}/{page} row {i}: {problems[:2]}")
        save_labels(args.profile, item, page, {"rows": rows, "prefilled_by": "model",
                                               "model": args.model})
        written += 1
        print(f"   {item}/{page}: {len(rows)} rows pre-filled", flush=True)

    print(f"\n{written} pages pre-filled into {LABELS.relative_to(ROOT)}/{args.profile}")
    print("Open the workbench and correct them:")
    print("   .venv/bin/python -m wrb.serve   ->   http://127.0.0.1:8765")
    print("Pre-filled values are a MODEL READING until a person has checked them.")


if __name__ == "__main__":
    main()
