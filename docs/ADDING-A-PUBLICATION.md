# Adding a publication

The project's claim is that a new publication costs **a JSON file**, and a few
dozen hand-labelled rows only when that fails. This is the path, and the
evidence that it holds.

## The evidence first

**17 layouts are described in `profiles/`. Two of them ever needed labelled
rows.** The other fifteen were added by writing the JSON and running the
pipeline — no training, no labelling, no new model.

That includes layouts structurally unlike anything in the training set:

| layout | what it is | training |
|---|---|---|
| `revista-resumo-simultaneas` | 26 printed columns, four stations to a sheet, dekadal | **none** — 24 of 24 cells right on first contact |
| `revista-mensal-baroterm` | 18 columns, dekadal summary, `1ª 2ª 3ª Mez` | **none** — full row read in one pass |
| `rio-1883-*` (six Annales layouts) | French daily tables, 9 to 16 columns | **none** |
| `porto-maranhao-1886` | 12 columns, trained on 15 and 16 | **none** — 264/264 numeric cells |

The two that needed labels were `corumba-1889` (whose ditto marks the model had
never seen) and `revista-mensal-baroterm` (labelled before anyone checked
whether it was necessary — it was not).

`docs/g4-learning-curve.md` measures the fallback: **~40 distinct labelled rows
per layout** reaches 95%+ on an unseen publication. `docs/g4-generality-result.md`
explains why *distinct* matters — a model trained on 91% one column count
learns the number instead of learning to look.

## The path

**1. Find the pages.** `scripts/g4_sweep_archive.py` finds ruled tables by
geometry; `scripts/g4_identify_pages.py` reads their captions;
`scripts/g4_triage.py` sorts the result into what a written profile already
covers, what needs a new one, and what is not weather at all. A caption cannot
always name its layout — see `docs/g4-data.md` on what a caption can and cannot
settle.

**2. Write the profile.** One JSON in `profiles/`. The columns as the page
prints them, their units, their physical ranges, and — the part that pays for
itself — any arithmetic the page asserts about its own numbers:

```json
"checks": [{"kind": "diff", "result": "oscillation", "a": "max", "b": "min"}]
```

That check needs no human and no model, and it localises the suspect cell. A
layout with printed arithmetic can reach `checks_pass`; one without tops out at
`qc_clean` no matter how well it is read.

**3. Run it and look at the output.** Not the summary — the rows.

```
scripts/g4_produce.py --adapter runs/g4/gen3/epoch2 --worklist <pages> --out <file>
scripts/g4_rescore.py <file>
```

**4. Only if it fails, label.** `scripts/g4_prefill_labels.py` fills the review
UI with the model's own reading so the human job is correcting, not typing.
Read its docstring first: a misaligned pre-fill is worse than a blank form.

## What actually goes wrong

Not the reading. In this project's whole history the model has rarely been the
problem — it read a 26-column form cold and an 18-column row in one pass. What
fails is everything around the reading, and each of these cost real data:

- **The wrong columns.** A page assigned the nearest layout by cell count when
  it is a different table entirely. Fifteen cells is the wind table *and* the
  hourly cloud-form table; sixteen is nébulosité *and* actinometry. Separate
  them on content, never on the count alone.
- **The wrong rows.** An ink profile finds row boundaries in a grid of figures
  and loses them in a grid of words, so text-column layouts read short. Oracle
  localisation — the printed row label decides, geometry only proposes — is the
  answer, and it is in `resolve_by_oracle`.
- **The wrong month.** `"Rio de Janeiro"` contains `"janeiro"`.
- **The wrong station.** A header that failed to read is not a header that was
  never printed.

A date, a name and a column heading are not measurements, so none of the
physical checks look at them. Whatever guards them has to be built on purpose.

## What you get

Every row carries its provenance (archive, item, page, row), its reading as
printed, the conventions undone in code, and a verdict with the reason. Every
row also carries its `raw` — the model's literal output — so
`scripts/g4_rescore.py` re-derives every judgement in under a second with no
model and no images. A check written tomorrow reaches data produced today.
