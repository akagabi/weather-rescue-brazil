#!/bin/bash
# Learning curve: how many DISTINCT labelled rows per layout does adapting to a
# new publication actually take? Same recipe, same epochs, only the number of
# distinct rows varies. Blind-tested each time on two held-out publications.
set -u
cd "$(dirname "$0")/.."
for n in 10 20; do
  echo "=== training on $n distinct rows per layout ==="
  .venv/bin/python scripts/g4_train.py --model qwen35 --run curve$n --epochs 3 --printed \
    --manifest data/g4/curve_$n.json --dev-pages 15/60 --save-every 20 --grad-accum 8 \
    > runs/g4/curve$n.log 2>&1
  for set in maranhao rio1883; do
    printf "curve%s %s: " "$n" "$set"
    .venv/bin/python scripts/g4_blind_test.py --adapter runs/g4/curve$n/epoch3 --set $set 2>&1 \
      | grep -E "^BLIND CELL" || echo "FAILED"
  done
done
echo "=== done ==="
