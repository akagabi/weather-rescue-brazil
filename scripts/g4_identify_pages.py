"""Stage A of a bulk run: read each table page's CAPTION to learn what it is.

A Revista volume interleaves tables from several stations, so a page's profile
cannot be guessed from the document it lives in. This crops the header band and
reads it with the base model, then matches the caption against the known
profiles by station name and parses the month.

    python scripts/g4_identify_pages.py --pages data/g4/table_pages.json

Pages it cannot identify are written out with why, not silently dropped: an
unmatched caption usually means a station we have no profile for yet, which is
a finding rather than an error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wrb.caption import is_astronomy, match_period, match_profile  # noqa: E402


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


def page_path(doc: str, page: int) -> Path:
    p = ROOT / "data" / "raw" / "docvirt" / doc / f"{page:06d}.webp"
    if p.exists():
        return p
    return ROOT / "data" / "raw" / "ia" / doc / f"{page:06d}.jpg"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True, help="json list of {doc,page} to identify")
    ap.add_argument("--base", default="Qwen/Qwen3.5-2B")
    ap.add_argument("--out", default="data/g4/identified.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    cands = json.loads(Path(args.pages).read_text())
    if args.limit:
        cands = cands[:args.limit]

    out_path = ROOT / args.out
    seen: dict[str, dict] = {}
    if args.resume and out_path.exists():
        seen = {f"{r['doc']}/{r['page']}": r for r in json.loads(out_path.read_text())}
        print(f"resuming: {len(seen)} pages already identified")

    from PIL import Image
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(args.base)
    model = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16).to(dev)
    model.eval()

    ask = ("This is a page from a 19th-century scientific journal. If it holds a "
           "table of daily meteorological observations, reply with the table's "
           "heading, naming the observatory or place and the month and year. "
           "If the page is prose, or a table of anything else, reply exactly NOT_WEATHER.")

    results = list(seen.values())
    t0 = time.time()
    for i, c in enumerate(cands):
        key = f"{c['doc']}/{c['page']}"
        if key in seen:
            continue
        path = page_path(str(c["doc"]), int(c["page"]))
        if not path.exists():
            continue
        im = Image.open(path).convert("RGB")
        # the caption sits directly above the table, which is not always near the
        # top of the page, so classify from the whole page downscaled
        head = im
        if head.width > 1000:
            k = 1000 / head.width
            head = head.resize((1000, max(1, int(head.height * k))), Image.LANCZOS)
        msgs = [{"role": "user", "content": [{"type": "image", "image": head},
                                             {"type": "text", "text": ask}]}]
        inp = procr.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                        return_dict=True, return_tensors="pt").to(dev)
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            o = model.generate(**inp, max_new_tokens=90, do_sample=False,
                               eos_token_id=STOP_IDS)
        cap = procr.decode(o[0][n:], skip_special_tokens=True).split("<|im_end|>")[0].strip()
        if dev == "mps":
            torch.mps.empty_cache()
        # No geometry here: locate_day_rows on a full-size scan is far too slow
        # for a 269-page sweep, and its cheap proxies mis-classify in BOTH
        # directions (4 of 39 known-good pages carry fewer than 5 vertical
        # rules). The production run already localises properly and refuses a
        # page whose rows do not close, so let it be the geometry filter and
        # keep this pass to the one question a caption can answer: what is it?
        # An ephemeris passes both the geometric sweep and the station match
        # (docId 11's "AO MEIO DIA MEDIO NO RIO DE JANEIRO" is a SOL table),
        # so the veto has to be explicit and has to be recorded.
        astro = is_astronomy(cap)
        weather = "NOT_WEATHER" not in cap.upper() and not astro
        rec = {"doc": str(c["doc"]), "page": int(c["page"]), "caption": cap,
               "is_weather_table": weather, "astronomy": astro,
               "profile": match_profile(cap) if weather else None,
               "period": match_period(cap) if weather else None}
        results.append(rec)
        if i % 10 == 0:
            out_path.write_text(json.dumps(results, indent=1, ensure_ascii=False))
            el = (time.time() - t0) / 60
            print(f"  {i}/{len(cands)}  {el:.1f}min  {key}: {rec['profile']} {rec['period']} | {cap[:65]}",
                  flush=True)

    out_path.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    ok = [r for r in results if r["profile"] and r["period"]]
    wx = [r for r in results if r["is_weather_table"]]
    astro = [r for r in results if r.get("astronomy")]
    print(f"\n{len(wx)}/{len(results)} pages read as a weather table "
          f"({len(astro)} vetoed as astronomy)")
    print(f"identified {len(ok)}/{len(results)} pages with a profile AND a period")
    import collections
    print(collections.Counter(r["profile"] for r in results))
    print("wrote", out_path)


if __name__ == "__main__":
    main()
