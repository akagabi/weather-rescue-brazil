#!/usr/bin/env bash
# Fetch every remaining page of the Observatório Nacional archive, one document
# at a time, sequentially. Politeness is the point: a single request every two
# seconds against one server, resumable, skipping what is already on disk.
set -uo pipefail
cd "$(dirname "$0")/.."
# doc:last_page, largest first so the big unknowns land early
for pair in 6:713 5:472 4:301 11:294 10:163 7:129 9:96 12:88 2:73; do
  doc="${pair%%:*}"; last="${pair##*:}"
  echo "=== doc $doc ($last páginas) ==="
  .venv/bin/python scripts/g4_fetch_docvirt.py "$doc" "$last"
done
echo "=== TODOS OS DOCUMENTOS BAIXADOS ==="
