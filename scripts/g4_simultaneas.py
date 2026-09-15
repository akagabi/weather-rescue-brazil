"""Read the Revista's `RESUMO MENSAL DAS OBSERVAÇÕES SIMULTANEAS` form.

    python scripts/g4_simultaneas.py --pages data/g4/worklist_simultaneas.json \
        --out data/dataset/simultaneas.jsonl

Three things make this form different from every layout the pipeline had
before, and each is handled here rather than in the generic producer:

1. IT IS TOO WIDE TO READ. 26 printed columns against a reader that is
   reliable to about 16. Only the band that carries the measurements is
   cropped (`band_x_frac` in the profile). Measured on docId 16 page 41, the
   gen3 adapter read all 24 cells of the first block's four rows correctly
   with no training at all - the width, not the hand, was the problem.

2. THE ROWS ARE DECIDED BY THEIR PRINTED LABEL. Geometry proposes bands of
   ink; the label read out of the first cell - 1ª, 2ª, 3ª or Mez - says which
   of them are data and where each block starts. Grouping by pitch alone was
   tried and gets 3 of the 10 known pages right; the labels get all of them,
   for the same reason the printed day numbers beat the row detector at
   Cuyabá.

3. THE STATION BELONGS TO THE BLOCK, NOT THE PAGE. Four stations to a sheet,
   each with its own printed header line, and a block that continues the
   station above it prints only a month. The header strip above each 1ª row is
   read as text and parsed by wrb.stations; wrb.blocks.resolve_stations
   applies the inheritance rule and records which rows inherited.

Nothing is invented. A block whose header cannot be read gets no station and
says so, a run whose label is not a dekad is dropped, and a page that yields
no complete block is refused with its reason.
"""
from __future__ import annotations

import argparse, json, re, statistics, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from wrb import profile as prof                       # noqa: E402
from wrb.blocks import band_from_rules, blocks_from_labels, resolve_stations, row_label  # noqa: E402
from wrb.qc import degenerate_row                      # noqa: E402
from wrb.rows import ink_threshold                     # noqa: E402

PROFILE = "revista-resumo-simultaneas"


# The probe column: where to ask "is there a row here". It is a fraction of the
# PAGE, unlike the band, and deliberately so - it only has to land inside the
# numeric columns, which it does on every page measured, and deriving it from
# the detected rules made it worse rather than better (the outer rule the
# detector returns is the printed frame on some scans and the table edge on
# others, and a span computed from that lands on the frame line itself).
PROBE_X = (0.150, 0.205)


def ink_runs(image, x_frac, min_h=6, floor=2):
    import numpy as np
    W, H = image.size
    g = image.convert("L")
    a = np.asarray(g, dtype=float)
    thr = ink_threshold(g)
    prof_ = (a[:, int(x_frac[0] * W):int(x_frac[1] * W)] < thr).sum(axis=1)
    out, s = [], None
    for y, v in enumerate(prof_ > floor):
        if v and s is None:
            s = y
        elif not v and s is not None:
            if y - s >= min_h:
                out.append((s, y))
            s = None
    if s is not None:
        out.append((s, len(prof_)))
    if not out:
        return [], H
    hs = [b - a_ for a_, b in out]
    mode = statistics.median([h for h in hs if h <= max(hs) * 0.5] or hs)
    kept = []
    for a_, b in out:
        h = b - a_
        # Two rows whose ink touches come back as one run twice the height.
        # Dropping it loses both; splitting it evenly recovers both, and a bad
        # split costs only a crop that comes back without a label.
        n = max(1, round(h / mode)) if mode else 1
        if n > 1 and h > mode * 1.6:
            step = h / n
            kept += [(round(a_ + i * step), round(a_ + (i + 1) * step)) for i in range(n)]
        elif abs(h - mode) <= mode * 0.5:
            kept.append((a_, b))
    return kept, H


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--adapter", default="runs/g4/gen3/epoch2")
    ap.add_argument("--base", default="Qwen/Qwen3.5-2B")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    p = prof.load(PROFILE)
    work = json.loads(Path(args.pages).read_text())["pages"]
    if args.limit:
        work = work[:args.limit]

    from PIL import Image
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor
    from g4_train import INSTRUCTION_PRINTED

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    procr = AutoProcessor.from_pretrained(args.base)
    model = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16).to(dev)
    model = PeftModel.from_pretrained(model, str(ROOT / args.adapter)).to(dev)
    model.eval()

    def run(crop, instruction=INSTRUCTION_PRINTED, max_new=140):
        msgs = [{"role": "user", "content": [{"type": "image", "image": crop},
                                             {"type": "text", "text": instruction}]}]
        inp = procr.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                        return_dict=True, return_tensors="pt").to(dev)
        n = inp["input_ids"].shape[1]
        with torch.no_grad():
            o = model.generate(**inp, max_new_tokens=max_new, do_sample=False)
        txt = procr.decode(o[0][n:], skip_special_tokens=True).split("<|im_end|>")[0].strip()
        if dev == "mps":
            torch.mps.empty_cache()
        return txt

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fh = out_path.with_suffix(out_path.suffix + ".partial").open("w")
    stats = {"pages": 0, "refused": 0, "blocks": 0, "rows": 0,
             "stations": set(), "inherited": 0, "no_station": 0}
    t0 = time.time()

    for w in work:
        doc, page = str(w.get("doc", w.get("item"))), int(w["page"])
        img = ROOT / "data" / "raw" / "docvirt" / doc / f"{page:06d}.webp"
        if not img.exists():
            print(f"  {doc}/{page}: image missing", flush=True)
            stats["refused"] += 1
            continue
        image = Image.open(img).convert("RGB")
        W, H = image.size
        span = tuple(p.extra["band_table_span"])
        band = band_from_rules(image, span)
        if band is None:
            print(f"  {doc}/{page}: table rules not found, page refused", flush=True)
            stats["refused"] += 1
            continue
        runs, _ = ink_runs(image, PROBE_X)
        bx0, bx1 = int(band[0] * W), int(band[1] * W)

        # 1. read every proposed run, let the printed label decide what it is
        read = []
        for y0, y1 in runs:
            pad = max(2, (y1 - y0) // 4)
            c = image.crop((bx0, max(0, y0 - pad), bx1, min(H, y1 + pad)))
            c = c.resize((c.width * 3, c.height * 3), Image.LANCZOS)
            raw = run(c)
            read.append({"box": (y0, y1), "raw": raw, "label": row_label(raw)})
        labelled = [r for r in read if r["label"]]
        if not labelled:
            print(f"  {doc}/{page}: no row carried a dekad label, page refused", flush=True)
            stats["refused"] += 1
            continue

        # 2. a block is a complete 1, 2, 3, Mez and nothing less
        idx = blocks_from_labels([r["label"] for r in labelled])
        blocks = [[labelled[j] for j in group] for group in idx]
        if not blocks:
            seq = [r["label"] for r in labelled]
            print(f"  {doc}/{page}: no complete 1/2/3/Mez block (labels {seq}), refused",
                  flush=True)
            stats["refused"] += 1
            continue

        # 3. the header strip above each block's first row, read full-width
        headers = []
        prev_bottom = 0
        for b in blocks:
            top = b[0]["box"][0]
            strip = image.crop((int(0.06 * W), max(0, prev_bottom + 2), int(0.95 * W),
                                max(prev_bottom + 6, top - 2)))
            txt = None
            if strip.height > 12:
                strip = strip.resize((min(1600, strip.width * 2), strip.height * 2),
                                     Image.LANCZOS)
                got = run(strip, "Transcribe the printed text on this strip exactly.", 120)
                txt = got if re.search(r"esta[çc][ãa]o", got, re.I) else None
            headers.append(txt)
            prev_bottom = b[-1]["box"][1]
        stations = resolve_stations(headers)

        for bi, (b, st) in enumerate(zip(blocks, stations)):
            parsed = []
            for r in b:
                values, problems = p.parse(r["raw"])
                parsed.append((r, values, problems))
            dek = [v for (_, v, _) in parsed[:3]]
            mez = parsed[3][1]
            month_fail = p.verify_month(dek, mez)
            for (r, values, problems), label in zip(parsed, ["1", "2", "3", "Mez"]):
                viol = p.violations(values)
                if degenerate_row(values, index_keys={"decada"}):
                    problems = problems + ["degenerate_row: measurements collapsed to a repeated value"]
                hard = [x for x in problems if x != prof.PADDED_TRAILING]
                verdict = ("checks_pass" if not month_fail and not viol and not hard
                           else "qc_clean" if not viol and not hard
                           else "flagged")
                fh.write(json.dumps({
                    "profile": p.id, "publication": p.name, "source": p.source,
                    "archive": "docvirt", "item": doc, "page": page,
                    "period": w.get("period"), "block": bi, "row": label,
                    "is_dekad": label != "Mez",
                    "values": values, "values_as_printed": values, "raw": r["raw"],
                    "station": st.get("station"), "station_source": st.get("station_source"),
                    "station_printed": st.get("printed"),
                    "station_lat": st.get("lat_deg"), "station_lon": st.get("lon_deg"),
                    "station_bar_alt_m": st.get("bar_alt_m"),
                    "verdict": verdict, "problems": problems,
                    "range_violations": viol, "month_check": month_fail,
                    "localisation": "printed row label",
                }, ensure_ascii=False) + "\n")
                stats["rows"] += 1
            stats["blocks"] += 1
            if st.get("station"):
                stats["stations"].add(st["station"])
            if st.get("station_source", "").startswith("herdada"):
                stats["inherited"] += 1
            if not st.get("station"):
                stats["no_station"] += 1
        stats["pages"] += 1
        print(f"  {doc}/{page}: {len(blocks)} blocks, "
              f"{[s.get('station') for s in stations]}", flush=True)

    fh.close()
    out_path.with_suffix(out_path.suffix + ".partial").replace(out_path)
    stats["stations"] = sorted(stats["stations"])
    stats["minutes"] = round((time.time() - t0) / 60, 1)
    (out_path.with_suffix(".summary.json")).write_text(json.dumps(stats, indent=1, ensure_ascii=False))
    print(f"\n{json.dumps(stats, ensure_ascii=False)}\nwrote {out_path}")


if __name__ == "__main__":
    main()
