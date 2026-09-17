---
language:
  - pt
  - fr
license: apache-2.0
base_model: Qwen/Qwen3.5-2B
library_name: peft
tags:
  - table-recognition
  - historical-documents
  - climate
  - lora
  - offline
---

# Weather Rescue Brazil — row reader

A small open model that reads **one printed table row** out of a scanned
nineteenth-century meteorological table and returns its cells as text.

It is not a chatbot, not a general OCR model, and not a climate model. It reads
a strip of paper and writes back numbers.

```
input : a crop of one row from a printed table
output: 57.23 | 58.08 | 55.67 | 22.37 | 23.2 | 21.3 | 16.75 | 83.4 | C, SSE | 3.3 | 7.4 | 2 | 9
```

Trained and evaluated entirely on Brazilian historical records, but the
interesting result is that it reads **layouts it has never seen** — and usually
with no labelled rows at all. Of the 17 layouts this project describes, **two
ever needed hand-labelling**; the other fifteen were added by writing a JSON
description of the columns and running the pipeline. `docs/ADDING-A-PUBLICATION.md`
is the path and the evidence.

## Base and adapters

Base: **Qwen/Qwen3.5-2B**, with LoRA (r=16) on the language layers only.
Training ran on a Mac (MPS), offline, ~45 minutes per epoch.

Three adapters are published, and it matters which you take:

| Adapter | Trained on | Gold accuracy | Use it for |
|---|---|---|---|
| **`gen3`** | 390 rows, balanced across **two layouts** | blind tests below | **reproducing the published dataset** |
| `smoke4` | 889 rows | **99.08%** | best measured accuracy on the home layout |
| `smoke2` | 762 rows | 98.90% | provenance of the recipe |

`gen3` is the one that produced the dataset in the companion repository, and it
is deliberately *not* the highest-scoring adapter here: it was trained to keep
reading when the layout changes, which costs a little on the layouts it knows.
Report the adapter you actually measured.

## Measured accuracy

On a frozen, triple-transcribed gold set of nine pages (273 rows, 3,822 cells),
never trained on:

| | |
|---|---|
| `smoke4`, offline, one laptop | **99.08%** cells |
| Three-vote API consensus (the ceiling it was distilled against) | 99.06% |
| Zero-shot base model | 31.8% |
| Tesseract | 1.8% |

Blind tests on layouts it had never seen, with `gen3`:

| Test | Result |
|---|---|
| Porto do Maranhão, 12 printed columns (trained on 15 and 16) | 264/264 numeric cells; the model's rainfall column sums to the printed monthly total it never saw |
| Rio 1883 vapour, French, 9 columns | 98.4% |
| Radcliffe Observatory, Oxford — another archive, another country, rows are years and columns are months | 99.3% temperature, 96.7% rain (on rows whose months close to the printed annual total) |

Added 2026-09-15, on layouts absent from the corpus when the adapter was
trained and given **no labelled rows at all**:

| Test | Result |
|---|---|
| *Resumo mensal das observações simultaneas* — 26 printed columns, four stations to a sheet, dekadal rather than daily | **24 of 24 cells**, first contact, reading one column band at a time |
| Revista dekadal summary — 18 columns, rows labelled `1ª 2ª 3ª Mez` | full row correct in one pass, no band and no training |
| Annales nébulosité — 16 columns, half of them cloud-form text | 38 rows `checks_pass` on 8 pages, where the same pages under the wrong profile gave zero |

The useful correction in those three: a claim that the model **could not read
rows wider than 16 columns** had shelved a whole layout as needing a trained
variant. It reads 18 columns in one pass and 26 in two bands. What had failed
was the crop.

## Training-data provenance — please read

**The training labels were produced by the Gemini API**, not by hand. The
photographs were read by a frontier model and its output, after human review of
disagreements, was used as the training target for this adapter. This is
declared because it matters: the adapter inherits the label generator's
conventions, and anyone redistributing or building on these weights should know
where the targets came from.

The evaluation gold set, by contrast, *is* human — triple-transcribed, with
every disagreement adjudicated against the image.

## Known limits

- **It counts cells from training, not from the image.** A layout whose printed
  column count it has not been balanced on will come back with the wrong number
  of cells. Balancing distinct examples per convention is the fix, and it is
  documented; stating the count in the prompt does not work.
- **Two values in one printed cell defeat it.** The 1883 nébulosité and wind
  tables print a number and a cloud-form code stacked in the same column, and
  the model's cell count is unreliable there.
- **A ~1% residual of consistent, in-range misreads.** These are the same wrong
  digit on every read, so neither voting nor re-reading at another scale finds
  them. Only a human comparing against the page does. Three automatic detection
  strategies were tried and all failed.
- **It does not read a whole page.** Row localisation is done by geometry in
  the companion repository; this model reads one prepared crop at a time.

## Using it

```python
from transformers import AutoModelForImageTextToText, AutoProcessor
from peft import PeftModel

base = "Qwen/Qwen3.5-2B"
model = AutoModelForImageTextToText.from_pretrained(base, dtype="bfloat16")
model = PeftModel.from_pretrained(model, "<this repo>/gen3").eval()
```

The prompt is fixed and lives in the companion repository:

> Transcreva esta linha de tabela impressa exatamente como está, célula por
> célula, da esquerda para a direita, separando as células com ' | '. Inclua
> todas as colunas, inclusive número do dia e texto. Use 'null' para célula
> vazia. Só a lista.

Read the row **as printed**. The publication's conventions — an elided leading
digit on a barometer, a ditto mark meaning "the same as the row above" — are
undone in code afterwards, not by the model. Teaching the model the
reconstructed form taught it to invent digits.

## Licence

**Apache-2.0** — the same terms as the base model it adapts (Qwen3.5-2B), which
this does not alter. Commercial use is permitted.

Until 2026-09-17 these weights were CC BY-NC 4.0. That was changed so the method
could be adopted by the people most likely to want it — national meteorological
institutes with their own shelves of scanned tables — and so the work could go
to venues that require an OSI-conforming licence. Read the provenance section
above before building on it: the training labels came from the Gemini API.
Google claims no ownership of generated content, and its use restriction on
developing competing services binds the API customer rather than travelling with
these weights, but anyone redistributing them should know where the targets came
from.

## Companion

Pipeline, profiles, the dataset and every measurement above:
**github.com/akagabi/weather-rescue-brazil**.
