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

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22876699.svg)](https://doi.org/10.5281/zenodo.22876699)

## The dataset

**7,418 rows, 3,998 usable, 48,341 values, 258 pages, 1851–1890.** Six
stations, three publications, in Portuguese, French and English.

The last of those is new and it is the only part of this dataset that can be
checked against somebody else's answer key: four summary tables from the
**Radcliffe Observatory, Oxford**, whose observations Oxford has itself
published, digitised independently a century later. Of the cells this file
calls usable, **100% of the dry-bulb and 96.7% of the rainfall** agree with
Oxford's series; of the cells it *flags*, rainfall agrees only 44.4%. The
verdict column is doing real work, and that is the first time it has been
shown against an outside source rather than against our own transcription.

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
monthly total it never saw), a French 9-column table at 98.4%. A new
publication costs about **40 hand-read rows** to reach 95%+ — and fifteen of
the eighteen layouts here needed none at all, only a JSON file describing the
columns.

### Graded by someone else

Every figure above is self-graded, against our own labels or the model's own
parse. The Radcliffe Observatory tables are not: Oxford has published the same
observations, digitised independently a century later, so those rows have an
outside answer key (`docs/g4-radcliffe.md`).

| | cells | agree with Oxford |
|---|---|---|
| Dry bulb, rows this pipeline calls **usable** | 252 | **100.0%** |
| Rainfall, rows it calls **usable** | 300 | **96.7%** |
| Rainfall, rows it **flags** | 36 | **44.4%** |

The last line is the one that matters. The rows the QC flags are more than ten
times as likely to disagree with an independent source — the verdict column
predicts correctness, and that had never been shown against anything but our
own transcription.

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

Transcriptions: **CC0 1.0** (public domain dedication). Code and model
weights: **Apache-2.0**. Everything here is free for any use, commercial
included.
The underlying observations are in the public domain (Lei 9.610) and are not
ours to licence. See [LICENSE](LICENSE) and
[DATASET_CARD.md](DATASET_CARD.md#provenance-and-rights) — the collection asks
for an attribution string, and it is worth carrying.
