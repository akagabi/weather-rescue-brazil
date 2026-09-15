# Weather Rescue Brazil

**Resgate Meteorológico Brasil**

Recovering nineteenth-century Brazilian weather observations from printed
tables into an open dataset, using a small open model that runs offline.

Global reanalysis (20CR, ERA — the datasets behind every climate model) is
nearly blind for South America before about 1950. Brazilian observations from
the 1800s exist, but as scanned paper. This project turns a slice of them into
data, and publishes the method so the rest can follow.

> Independent project. Not affiliated with Zooniverse or with the Weather
> Rescue / Rainfall Rescue projects, whose naming family it gratefully follows.

## The dataset

**5,925 rows, 3,385 usable, 39,899 values, 226 pages, 1882–1890.** Five
stations, two publications, in Portuguese and French.

Read **[DATASET_CARD.md](DATASET_CARD.md)** before using it — in particular the
section on what `checks_pass` actually verifies, which differs by publication
and is *not* a uniform quality tier.

### Also in this repository, and not published

`data/dataset/simultaneas.jsonl` — **92 rows, 46 usable, 9 stations**, from the
Revista's `Resumo mensal das observações simultaneas` form
(`docs/g4-simultaneas.md`). It reaches **São Paulo, Bahia, Ouro Preto, Santa
Cruz, Maceió, Recife, Cidade do Rio Grande, S. João d'El-Rei** and the cruiser
**Almirante Barroso**, against a published dataset that is otherwise almost
entirely Rio de Janeiro.

It is deliberately a separate file: every row is a **dekad or a month**, not a
day. Mixing summaries into a dataset described as daily observations would
misstate what that file is, and a consumer averaging it would double-count.

## How it works

```
fetch pages ─▶ find ruled tables ─▶ profile (layout as data) ─▶ read rows ─▶ QC ─▶ dataset
```

The design decisions that took the work, each with the evidence in `docs/`:

- **A publication's layout is data, not code.** One JSON file per printed
  layout declares its columns, units and physical ranges, and the parser, the
  QC ranges, the review UI and the training target all derive from it. Adding a
  publication is writing a JSON file.
- **Read the row as printed; undo conventions downstream.** Teaching the model
  the reconstructed form taught it to invent a leading digit and apply it to an
  unrelated table (`docs/g4-print-fidelity.md`).
- **Balance distinct examples of each convention, not row counts.** Repetition
  is not diversity, and this is what made one model read layouts it never
  trained on (`docs/g4-generality-result.md`).
- **The page's own arithmetic is the ground truth you get for free.**
  `Oscillation = Max − Min`, `θ = T − t`, the printed monthly mean — a validator
  needs no human and localises the suspect cell.
- **A model cannot flag its own uncertainty.** Measured: `flagged_recall` was
  **0.000**. Review has to be triggered by external validators, never by the
  model's confidence (`docs/gates/g1-report.md`).

## Results

On a frozen, triple-transcribed gold set of nine pages (3,822 cells), excluded
from the dataset and never trained on:

| | |
|---|---|
| Qwen3.5-2B + LoRA, offline, one laptop | **99.08%** cell accuracy |
| Three-vote API consensus (the ceiling it was distilled against) | 99.06% |
| Zero-shot base model | 31.8% |
| Tesseract | 1.8% |

Blind tests on layouts the model never saw: a 12-column table from a different
station (100% of 264 numeric cells, and its rainfall column sums to the printed
monthly total it never saw), a French 9-column table at 98.4%, Oxford
Observatory's year-rows-by-month-columns tables from another archive and
country. A new publication costs about **40 hand-read rows** to reach 95%+.

Total API spend across the whole project: **US$1.56**.

## Running it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e .
```

⚠️ `pyproject.toml` declares only four dependencies. The extraction and training
path additionally needs `torch`, `transformers`, `peft` and (for the packaged
model) `mlx` + `mlx-vlm`; the review UI needs `fastapi` and `uvicorn`. There is
no lockfile yet — this is the largest reproduction gap in the repository and it
is tracked.

```bash
.venv/bin/python scripts/g4_merge.py --out data/dataset/weather-rescue-brazil.jsonl <per-doc.jsonl ...>
.venv/bin/python scripts/g4_rescore.py data/dataset/weather-rescue-brazil.jsonl   # re-judge, no model
.venv/bin/python scripts/g4_sef.py --out data/sef                                  # C3S export
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m wrb.serve            # review UI on :8765
.venv/bin/python -m wrb.verify_serve     # verify rows against the page on :8766
```

## Layout

| Path | |
|---|---|
| `src/wrb/` | the pipeline: geometry, profiles, parsing, QC, the offline model |
| `scripts/` | entry points — fetch, produce, merge, rescore, evaluate, export |
| `profiles/` | one JSON per printed table layout |
| `data/dataset/` | the dataset, its notes and its frozen fingerprint |
| `data/verify/` | human judgements and corrections against the page images |
| `docs/` | gate reports, blind tests, method findings, the full specification |
| `gold/` | the frozen evaluation set, sha256-pinned |

## Licence

Transcriptions: **CC BY-NC 4.0**. Code: **PolyForm Noncommercial 1.0.0**.
The underlying observations are in the public domain (Lei 9.610) and are not
ours to licence. See [LICENSE](LICENSE) and
[DATASET_CARD.md](DATASET_CARD.md#provenance-and-rights) — the collection asks
for an attribution string, and it is worth carrying.
