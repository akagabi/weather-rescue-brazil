#!/bin/sh
# Everything that happens to a Resumo mensal production run after it lands.
# Each step is model-free and re-derivable from what the rows already store.
set -e
cd "$(dirname "$0")/.."
OUT=${1:-data/dataset/simultaneas.jsonl}

echo "== rescore: elided hundreds, pressure against altitude, duplicates, station ids"
.venv/bin/python scripts/g4_simultaneas_rescore.py "$OUT" --write

echo
echo "== against the independent second reading"
.venv/bin/python scripts/g4_simultaneas_check.py "$OUT"

echo
echo "== month-row tolerances the pages themselves support"
.venv/bin/python scripts/g4_simultaneas_calibrate.py "$OUT"
