#!/usr/bin/env bash
# Sweep newly-fetched pages, identify them, build a worklist, transcribe.
#
#   bash scripts/g4_pipeline.sh 14
#
# The order matters and was learned the hard way. Geometry finds table
# candidates but mis-classifies in both directions. The caption gives the month
# and the station but is read by a base model and is not trustworthy on its
# own. So geometry proposes, the caption supplies metadata, and the preflight
# inside g4_produce (three rows must yield a day number) is what actually
# decides whether a page is a daily table.
set -euo pipefail
cd "$(dirname "$0")/.."
DOC="$1"
PY=.venv/bin/python

echo "== 1/4 varrendo doc $DOC =="
$PY - "$DOC" <<'PYEOF'
import json, sys
from pathlib import Path
sys.path.insert(0, "src")
from PIL import Image
from wrb.rows import ink_threshold, vertical_rules, row_profile, pitch_candidates, find_peaks, PROBE_X_FRAC
doc = sys.argv[1]
done = {(str(w.get("item", w.get("doc"))), int(w["page"]))
        for f in ("data/g4/worklist.json", "data/g4/worklist_backlog.json")
        if Path(f).exists() for w in json.load(open(f))["pages"]}
out = []
for p in sorted(Path(f"data/raw/docvirt/{doc}").glob("*.webp")):
    page = int(p.stem)
    if (doc, page) in done:
        continue
    im = Image.open(p).convert("L")
    thr = ink_threshold(im)
    if len(vertical_rules(im, thr)) < 4:
        continue
    x0, x1 = int(im.width * PROBE_X_FRAC[0]), int(im.width * PROBE_X_FRAC[1])
    prof, _ = row_profile(im, x0, x1, thr)
    c = pitch_candidates(prof)
    if c and len(find_peaks(prof, c[0])) >= 15:
        out.append({"doc": doc, "page": page})
json.dump(out, open(f"data/g4/sweep_{doc}.json", "w"), indent=1)
print(f"  {len(out)} candidatas")
PYEOF

echo "== 2/4 lendo legendas =="
$PY scripts/g4_identify_pages.py --pages "data/g4/sweep_${DOC}.json" \
    --out "data/g4/identified_${DOC}.json" --resume 2>&1 | tail -4

echo "== 3/4 montando worklist =="
$PY - "$DOC" <<'PYEOF'
import json, sys
doc = sys.argv[1]
rows = json.load(open(f"data/g4/identified_{doc}.json"))
STATION = {"revista-rio-1886": "Imperial Observatório, Rio de Janeiro",
           "revista-santacruz-1889": "Observatório de Santa-Cruz, Rio de Janeiro",
           "corumba-1889": "Corumbá, Mato Grosso",
           "porto-maranhao-1886": "Porto do Maranhão, Maranhão"}
pages = [{"profile": r["profile"], "archive": "docvirt", "doc": doc, "page": r["page"],
          "period": r["period"], "station": STATION.get(r["profile"], ""),
          "station_source": "legenda impressa",
          "label": f"{r['profile']} {doc}/{r['page']} {r['period']}"}
         for r in rows if r.get("is_weather_table") and r.get("profile") and r.get("period")]
json.dump({"pages": pages}, open(f"data/g4/worklist_{doc}.json", "w"), indent=1, ensure_ascii=False)
print(f"  {len(pages)} páginas com perfil E período")
PYEOF

echo "== 4/4 transcrevendo (preflight rejeita o que não for tabela) =="
$PY scripts/g4_produce.py --adapter runs/g4/gen3/epoch2 \
    --worklist "data/g4/worklist_${DOC}.json" --out "data/dataset/doc${DOC}.jsonl"
