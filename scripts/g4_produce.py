"""Production run: read every page in a worklist and emit the dataset.

    python scripts/g4_produce.py --adapter runs/g4/gen3/epoch2 --worklist data/g4/worklist.json

Each output row carries its value, its provenance (archive, item, page, row)
and a QC verdict, so a consumer can filter to the guaranteed subset:

    checks_pass   the page's own arithmetic closes for this row (strongest)
    qc_clean      every value inside the profile's physical range
    flagged       something to review; the reason is recorded

Nothing is silently corrected: values are stored AS PRINTED, with the
publication's conventions (elided digits) recorded in the profile so a
consumer can restore them deterministically.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from g4_train import INSTRUCTION_PRINTED  # noqa: E402
from wrb import profile as prof  # noqa: E402
from wrb.dataset import boxes_for_centres, crop_boxes  # noqa: E402
from g4_build_dataset import resolve_by_oracle  # noqa: E402
from wrb.rows import locate_day_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# The chat template ends the assistant turn with <|im_end|> (248046), but
# Qwen3.5-2B ships no generation_config.json and its config.json declares no
# eos_token_id, so generate() falls back to <|endoftext|> (248044) alone. The
# model therefore emits <|im_end|>, is not stopped by it, and keeps going: 110
# published rows carry a newline and the START OF THE NEXT DAY'S ROW inside
# them, which reached Profile.parse as extra cells. The `.split("<|im_end|>")`
# guard below cannot help - skip_special_tokens=True has already removed the
# marker by then.
STOP_IDS = [248046, 248044]          # <|im_end|>, <|endoftext|>



def page_path(item: dict) -> Path:
    if item.get("archive") == "ia":
        return ROOT / "data" / "raw" / "ia" / item["item"] / f"{item['page']:06d}.jpg"
    return ROOT / "data" / "raw" / "docvirt" / item["doc"] / f"{int(item['page']):06d}.webp"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base", default="Qwen/Qwen3.5-2B")
    ap.add_argument("--worklist", required=True)
    # REQUIRED, and deliberately not defaulted to the published dataset: this
    # script truncates its output at start and has no resumability, so a
    # default pointing at data/dataset/weather-rescue-brazil.jsonl meant one
    # absent-minded run replaced the whole published artefact with a single
    # worklist's rows. Callers pass an explicit per-doc path (g4_pipeline.sh).
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    # Geometry alone cannot localise every layout. On the Cuyaba "Resumo" form
    # the row pitch is 22px - below MIN_PITCH_PX, so the cheap path is built to
    # reject it - the centroids jitter by +/-50% around a pitch that tight, the
    # header is three levels deep, and Doc./Mez rows break the chain. Measured:
    # the geometric chain returns 31 rows of which the first FOUR are the
    # header, so days 28-31 are never read. Letting the printed day numbers
    # decide recovers all 31 (see docs/g4-cuyaba-locator.md).
    ap.add_argument("--oracle", choices=("none", "torch", "mlx"), default="none",
                    help="localise rows by reading the printed day numbers, not by geometry")
    args = ap.parse_args()

    work = json.loads(Path(args.worklist).read_text())["pages"]
    if args.limit:
        work = work[:args.limit]
    from PIL import Image
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(args.base)
    model = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16).to(dev)
    model = PeftModel.from_pretrained(model, args.adapter).to(dev)
    model.eval()

    # Write beside the target and rename at the end, so a run that dies (there
    # is no --resume) cannot leave a half-written file where a good one was.
    oracle = None
    if args.oracle != "none":
        if args.oracle == "mlx":
            from g4_run_pages import MlxDayOracle
            oracle = MlxDayOracle()
        else:
            from g4_build_dataset import DayOracle
            oracle = DayOracle()
        print(f"oracle localisation: {args.oracle}", flush=True)

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fh = out_path.with_suffix(out_path.suffix + ".partial").open("w")
    stats = {"pages": 0, "refused": 0, "rows": 0, "checks_pass": 0, "qc_clean": 0, "flagged": 0}
    t0 = time.time()
    for w in work:
        p = prof.load(w["profile"])
        img_path = page_path(w)
        if not img_path.exists():
            print(f"  {w.get('label', img_path.name)}: image missing, skipped", flush=True)
            stats["refused"] += 1
            continue
        image = Image.open(img_path).convert("RGB")
        want = p.expected_rows(w["period"])
        loc = locate_day_rows(image, want, **p.geometry())
        if not loc.chain:
            print(f"  {w.get('label')}: no rows located, skipped", flush=True)
            stats["refused"] += 1
            continue
        located_ok = loc.ok
        localisation = "geometry"
        centres = loc.chain
        if oracle is not None:
            centres, info = resolve_by_oracle(oracle, image, loc, want,
                                              min_direct=p.oracle_min_direct)
            if centres is None:
                # print WHY. Three pages refused at 0.74, 0.67 and 0.67 of
                # their days read directly - comfortably over the bar - and the
                # message said only how many were read, so the bar looked
                # broken when the overlap check was doing the refusing.
                print(f"  {w.get('label')}: oracle could not resolve the day rows "
                      f"({info['direct']} of {want} read directly"
                      + (f"; {info['reason']}" if info.get("reason") else "")
                      + ") - page skipped", flush=True)
                stats["refused"] += 1
                continue
            localisation = "oracle"
            located_ok = True
            print(f"  {w.get('label')}: oracle localised {info['direct']}/{want} days directly, "
                  f"{info['candidates']} candidates", flush=True)
        crops = crop_boxes(image, boxes_for_centres(centres, loc, *image.size), loc.skew_deg, scale=2.0)

        # Preflight. A caption read off the whole page is NOT evidence that the
        # page is a daily table: doc 14 p140 is prose whose caption belongs to a
        # table on a neighbouring leaf, and it produced 28 junk rows before the
        # QC caught it. Read three rows first and require two of them to start
        # with a plausible day number. One generation per row instead of thirty.
        day_key = next((c.key for c in p.columns if c.kind == "day"), None)
        # What counts as a plausible index value is the PROFILE's business.
        # `1 <= d <= 31` was a day of the month, and the Radcliffe tables
        # index their rows by year, so all four of their pages failed a
        # preflight written for a different publication.
        idx_lo, idx_hi = p.index_range
        if day_key and len(crops) >= 3:
            probes = []
            for probe in crops[:3]:
                msgs = [{"role": "user", "content": [{"type": "image", "image": probe},
                                                     {"type": "text", "text": INSTRUCTION_PRINTED}]}]
                inp = procr.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                                return_dict=True, return_tensors="pt").to(dev)
                n = inp["input_ids"].shape[1]
                with torch.no_grad():
                    o = model.generate(**inp, max_new_tokens=140, do_sample=False,
                                       eos_token_id=STOP_IDS)
                txt = procr.decode(o[0][n:], skip_special_tokens=True).split("<|im_end|>")[0].strip()
                if dev == "mps":
                    torch.mps.empty_cache()
                probes.append(p.parse(txt))
            # The elided integer part carries DOWN the column, so a row cannot
            # be judged alone - three rows is enough to establish the carry
            # from the first of them, which is what the page does too.
            restored = [p.from_printed(v) for v, _ in probes]
            if any(c.elided_carry for c in p.columns):
                restored = p.resolve_column_carry(restored)
            from wrb.qc import degenerate_row as _degen
            seen = 0
            for (vals, probs), rest in zip(probes, restored):
                d = vals.get(day_key)
                if isinstance(d, (int, float)) and idx_lo <= d <= idx_hi:
                    seen += 1
                    continue
                # A legible index is the usual evidence that this is a data
                # row, but it is not the only evidence, and on the Radcliffe
                # barometer it is the one thing that does NOT read: the years
                # are old-style figures and come back as `18`, while every
                # measurement on the row is perfect. So accept a row that
                # instead produces exactly the right number of cells, all of
                # them inside the profile's declared physical ranges and not
                # collapsed to a repeated constant. That is a HARDER test than
                # the index, and the page this preflight was built to reject -
                # doc 14 p140, prose read as fifteen 1s - still fails it on
                # both counts.
                hard_probs = [x for x in probs if not prof.is_soft_problem(x)]
                # not the index column: that is the cell this branch exists
                # to forgive, and it has already been tested above.
                measured = {k: v for k, v in rest.items() if k != day_key}
                if (not hard_probs and not p.violations(measured)
                        and not _degen(rest, index_keys={day_key, "year"})
                        and any(isinstance(v, (int, float))
                                for k, v in rest.items() if k != day_key)):
                    seen += 1
            if seen < 2:
                print(f"  {w.get('label')}: preflight falhou ({seen}/3 linhas plausíveis, "
                      f"índice em {idx_lo:g}..{idx_hi:g}), página ignorada", flush=True)
                stats["refused"] += 1
                continue

        n_pass = n_clean = n_flag = 0
        for idx, crop in enumerate(crops):
            msgs = [{"role": "user", "content": [{"type": "image", "image": crop},
                                                 {"type": "text", "text": INSTRUCTION_PRINTED}]}]
            inp = procr.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                            return_dict=True, return_tensors="pt").to(dev)
            n = inp["input_ids"].shape[1]
            with torch.no_grad():
                o = model.generate(**inp, max_new_tokens=140, do_sample=False,
                                   eos_token_id=STOP_IDS)
            text = procr.decode(o[0][n:], skip_special_tokens=True).split("<|im_end|>")[0].strip()
            if dev == "mps":
                torch.mps.empty_cache()
            values, problems = p.parse(text)
            # A period the worklist already doubts travels with every row it
            # dates. The caption is the only witness to a date and it is the
            # thing being misread - doc 8 page 83 is captioned "Septembre 1893"
            # in a volume that ends in 1885. Nothing is corrected: the month
            # may be right and only the year wrong, and guessing which is how
            # 509 rows came to be dated January.
            if w.get("period_suspect"):
                problems = problems + [f"period_suspect: {w['period_suspect']}"]
            # words the page prints instead of a number, kept verbatim
            markers = dict(getattr(p, 'last_markers', {}) or {})
            # read AS PRINTED, then restore the publication's elided digits in
            # code before any QC - checking a printed 54.44 against a barometer
            # range of 650-800 flags every cell (docs/g4-print-fidelity.md)
            restored = p.from_printed(values)
            viol = p.violations(restored)
            check_fail = p.verify(restored) if p.checks else []
            scoreable = bool(p.checks) and any(
                isinstance(restored.get(c["result"]), (int, float)) for c in p.checks)
            from wrb.profile import PADDED_TRAILING
            from wrb.qc import degenerate_row
            # a row whose measurements collapsed to one repeated value is
            # fabricated: it sits inside every declared range, so only its own
            # shape can catch it (see wrb.qc.degenerate_row)
            if degenerate_row(restored, index_keys={p.day_key or "day", "year"}):
                problems = problems + ["degenerate_row: measurements collapsed to a repeated value"]
            hard = [x for x in problems if not prof.is_soft_problem(x)]
            padded = PADDED_TRAILING in problems
            verdict = ("checks_pass" if scoreable and not check_fail and not viol and not hard
                       else "qc_clean" if not viol and not hard and not check_fail
                       else "flagged")
            n_pass += verdict == "checks_pass"
            n_clean += verdict == "qc_clean"
            n_flag += verdict == "flagged"
            fh.write(json.dumps({
                "profile": p.id, "publication": p.name, "source": p.source,
                "archive": w.get("archive", "docvirt"), "item": w.get("item", w.get("doc")),
                "page": w["page"], "period": w["period"], "row": idx,
                # A page whose rows are YEARS covers a span, not a month. The
                # row's own period is its `year` value; `period` here is the
                # first month the PAGE covers and this the last. Absent on the
                # daily layouts, where page and period are the same thing.
                **({"period_end": w["period_end"]} if w.get("period_end") else {}),
                "values_as_printed": values, "values": restored, "markers": markers, "raw": text,
                "verdict": verdict, "padded_trailing": padded, "problems": problems, "localisation": localisation,
                "range_violations": viol,
                "check_failures": check_fail, "page_rows_located_ok": located_ok,
            }, ensure_ascii=False) + "\n")
        stats["pages"] += 1
        stats["rows"] += len(crops)
        stats["checks_pass"] += n_pass
        stats["qc_clean"] += n_clean
        stats["flagged"] += n_flag
        print(f"  {w.get('label')}: {len(crops)} rows  "
              f"checks_pass={n_pass} qc_clean={n_clean} flagged={n_flag}"
              + ("" if located_ok else "  [rows did not close]"), flush=True)
    fh.close()
    # only now does the target path change; an aborted run leaves whatever was
    # already there untouched (its `.partial` sibling is for the next run)
    out_path.with_suffix(out_path.suffix + ".partial").replace(out_path)
    stats["minutes"] = round((time.time() - t0) / 60, 1)
    (out_path.with_suffix(".summary.json")).write_text(json.dumps(stats, indent=1))
    try:
        shown = out_path.relative_to(ROOT)
    except ValueError:
        shown = out_path          # an --out outside the repo is legal
    print(f"\n{json.dumps(stats)}\nwrote {shown}")


if __name__ == "__main__":
    main()
