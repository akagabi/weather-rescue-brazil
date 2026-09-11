"""Read every row TWICE, at two crop scales, and report where the model
disagrees with itself.

    python scripts/g4_disagree.py --profile revista-santacruz-1889 \
        --model runs/g4/mlx-smoke4-q8 --out data/verify/disagreements.jsonl

Why this exists. Human reading of the pages found two misread digits in
Santa-Cruz (tmin 21.16 for a printed 21.3; cloudiness 0.01 for 0.00) - errors
that no rule catches, because both produce a legal-looking number inside its
physical range. The project's own answer to this class, built at G3 and then
shelved, is that a single read carries no signal about itself: you need the
model to disagree with itself to find where it is unsure.

It was shelved because single-read data has nothing to disagree WITH. Re-reading
the same crop at a different scale supplies that, and the result is what a
person should look at: not 660 rows, but the handful where the two reads differ.

Two kinds of disagreement are reported, and they mean different things:

  * `scale` - the two reads of the SAME box differ. The model is unsure about a
    cell. This is the suspect list.
  * `stored` - today's read differs from what the dataset already holds. When
    ALL cells of a row differ, the row's crops are not reproducible any more
    (the locator's answer has changed since production) and the row says so;
    when only a few differ, it is the same reading-level signal.

Reads use the PRINTED-order instruction, the one that produced the dataset -
not g4_run_pages.py's 14-column schema instruction, which is the older path.
"""

from __future__ import annotations

import argparse, json, sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from wrb import profile as prof                      # noqa: E402
from wrb.dataset import boxes_for_centres, crop_boxes  # noqa: E402
from wrb.rows import locate_day_rows                   # noqa: E402
from g4_train import INSTRUCTION_PRINTED               # noqa: E402

SCALE_A, SCALE_B = 2.0, 3.5      # production used 2.0
DAY_KEYS = {"day", "date", "dates", "year"}



class PrintedRowReader:
    """Batched row reads with the PRINTED-order instruction - the exact prompt
    that produced this dataset (g4_produce.py), and with no layout hint.

    NOT g4_run_pages.MlxRowReader: that one hardcodes g4_train.INSTRUCTION, the
    14-column schema prompt from the older path. Reading with it maps a
    14-cell schema answer onto a 15-column profile and every cell "differs" -
    which is exactly what a first version of this script reported, for every
    row on the page.
    """

    def __init__(self, model_path: str, max_tokens: int = 140, batch: int = 8) -> None:
        from mlx_vlm import load
        self.model, self.proc = load(model_path)
        self.max_tokens = max_tokens
        self.batch = batch

    def read_rows(self, crops, hint: str = "") -> list[str]:
        import tempfile
        from mlx_vlm import batch_generate
        from mlx_vlm.prompt_utils import apply_chat_template
        from g4_run_pages import _with_fallback
        if not crops:
            return []
        prompt = apply_chat_template(self.proc, self.model.config, INSTRUCTION_PRINTED, num_images=1)
        paths = []
        try:
            for c in crops:
                f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                c.save(f, format="PNG")
                f.close()
                paths.append(f.name)

            def _run(chunk):
                out = batch_generate(self.model, self.proc, images=chunk,
                                     prompts=[prompt] * len(chunk),
                                     max_tokens=self.max_tokens, verbose=False)
                return out.texts if hasattr(out, "texts") else [o.text for o in out]
            return _with_fallback(_run, paths, self.batch, "printed-reader")
        finally:
            for p_ in paths:
                Path(p_).unlink(missing_ok=True)


def page_rows(dataset: Path, profile: str) -> dict:
    """{(item, page): (period, rows)} for the pages this profile has."""
    out: dict = defaultdict(lambda: [None, []])
    for line in dataset.open():
        r = json.loads(line)
        if r.get("profile") != profile:
            continue
        key = (str(r.get("item")), int(r["page"]))
        out[key][0] = r["period"]
        out[key][1].append(r)
    for v in out.values():
        v[1].sort(key=lambda r: r["row"])
    return dict(out)


def cells(p: prof.Profile, raw: str) -> dict:
    values, _ = p.parse(raw or "")
    return p.from_printed(values)


def classify(p: prof.Profile, a: dict, b: dict) -> dict:
    """What kind of disagreement two readings of one row have.

    Not every difference is a defect, and the first cut of this script learned
    that the hard way: on 15/22 it reported 22 of 31 rows differing while the
    VALUES were identical between the two reads. The difference was cell
    alignment - across scales the model slides values into neighbouring
    columns - and presence-only changes (a cell null in one read and filled in
    the other) swamped the list without meaning anything.

    Three classes, and only two of them are defects:

      shift   a value sits in column k in one read and in column k+1 or k-1 in
              the other. THIS is the signature of the human-found error: a
              printed "21.3 | 16.75" read as "21.16 | 16.75" is a value that
              moved into its neighbour. Both cells non-null.
      changed same column, both non-null, different values. A real misread.
      (presence-only differences are ignored - the model omits blank cells
      freely and the parser fills them.)
    """
    keys = [k for k in a if k not in DAY_KEYS]
    shifts, changed = [], []
    for i, k in enumerate(keys):
        va, vb = a.get(k), b.get(k)
        if va == vb:
            continue
        if va is None or vb is None:
            continue                      # presence-only: not evidence
        moved = None
        for j in (i + 1, i - 1):
            if 0 <= j < len(keys) and keys[j] in b:
                if vb == a.get(keys[j]) and va == b.get(keys[j]):
                    moved = keys[j]       # the two reads swapped these columns
                    break
                if va == b.get(keys[j]):
                    moved = keys[j]       # a's value for k sits at j in b
                    break
                if vb == a.get(keys[j]):
                    moved = keys[j]
                    break
        if moved:
            shifts.append(f"{k}<->{moved}")
        else:
            changed.append({"col": k, "a": va, "b": vb})
    return {"shifts": shifts, "changed": changed}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--model", default="runs/g4/mlx-smoke4-q8")
    ap.add_argument("--dataset", default="data/dataset/weather-rescue-brazil.jsonl")
    ap.add_argument("--out", default="data/verify/disagreements.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="pages, for a smoke test")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--scales", default="2.0,3.5",
                    help="the two crop scales; 3.5 degrades badly on faint pages")
    args = ap.parse_args()

    reader = PrintedRowReader(str(ROOT / args.model), batch=args.batch)

    p = prof.load(args.profile)
    pages = page_rows(ROOT / args.dataset, args.profile)
    keys = sorted(pages, key=lambda k: (int(k[0]) if k[0].isdigit() else 99, k[1]))
    if args.limit:
        keys = keys[: args.limit]
    print(f"{args.profile}: {len(keys)} pages, {sum(len(pages[k][1]) for k in keys)} rows", flush=True)

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in out_path.open():
            if line.strip():
                rec = json.loads(line)
                if rec.get("page_record"):
                    done.add((str(rec["item"]), int(rec["page"])))
    fh = out_path.open("a")

    stats = Counter()
    for item, page in keys:
        if (item, page) in done:
            continue
        period, stored = pages[(item, page)]
        path = ROOT / "data" / "raw" / "docvirt" / item / f"{page:06d}.webp"
        if not path.exists():
            continue
        im = Image.open(path).convert("RGB")
        loc = locate_day_rows(im, p.expected_rows(period), **p.geometry())
        boxes = boxes_for_centres(loc.chain, loc, *im.size)
        if not boxes:
            fh.write(json.dumps({"page_record": True, "item": item, "page": page,
                                 "notes": "no rows located"}) + "\n")
            fh.flush()
            continue

        sa, sb = args.scales.split(",")
        read_a = reader.read_rows(crop_boxes(im, boxes, loc.skew_deg, scale=float(sa)))
        read_b = reader.read_rows(crop_boxes(im, boxes, loc.skew_deg, scale=float(sb)))

        whole_page_differs = 0
        for i, sr in enumerate(stored):
            if i >= len(read_a):
                break
            a, b = cells(p, read_a[i]), cells(p, read_b[i])
            cls = classify(p, a, b)
            # does today's read reproduce the stored one at all? when every
            # column differs the crops themselves moved (the locator's answer
            # has drifted since production) and per-cell comparison is
            # meaningless for that page - recorded as a page-level fact.
            st = [k for k in a if k not in DAY_KEYS and a.get(k) != (sr.get("values") or {}).get(k)]
            moved = len(st) >= max(3, 0.7 * len([k for k in a if k not in DAY_KEYS]))
            whole_page_differs += moved
            rec = {"id": f"{args.profile}/{item}/{page}/{sr['row']}", "item": item, "page": page,
                   "row": sr["row"], "period": period, "day": sr["values"].get("day"),
                   "shifts": cls["shifts"], "changed": cls["changed"],
                   "crops_moved": moved, "verdict": sr.get("verdict")}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if cls["shifts"]:
                stats["rows_with_shift"] += 1
            if cls["changed"]:
                stats["rows_with_changed"] += 1
            if moved:
                stats["rows_crops_moved"] += 1
            if sr.get("human_verified"):
                stats["rows_human_verified"] += 1
        fh.write(json.dumps({"page_record": True, "item": item, "page": page,
                             "rows": len(read_a), "crops_moved": whole_page_differs,
                             "shift_rows": stats["rows_with_shift"],
                             "changed_rows": stats["rows_with_changed"]}) + "\n")
        fh.flush()
        print(f"  {item}/{page} {period}: {len(read_a)} rows | "
              f"shift={stats['rows_with_shift']} changed={stats['rows_with_changed']} "
              f"crops_moved={stats['rows_crops_moved']}", flush=True)
    fh.close()
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
