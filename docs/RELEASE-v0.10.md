Nineteenth-century weather observations from six stations, 1851-1890,
transcribed from printed tables by a 2B model running offline on a laptop.

**7,418 rows, 3,999 usable, 48,355 values, 258 pages.** Portuguese, French and
English; eighteen printed layouts, fifteen of which needed no labelled rows at
all. Total API spend across the project: US$1.56.

## The part that is hardest to obtain

Almost every quality claim about a transcribed dataset is self-graded — the
gold set is the author's own labels, and a checksum test asks whether the
model's numbers close the model's own parse. The Radcliffe Observatory
(Oxford) tables in here are not. Oxford has published the same observations,
digitised independently more than a century later, so those rows have an
outside answer key.

| | cells | agree with Oxford |
|---|---|---|
| Dry bulb, rows this file calls **usable** | 252 | **100.0%** |
| Rainfall, rows it calls **usable** | 300 | **96.7%** |
| Rainfall, rows it **flags** | 36 | **44.4%** |

The last line is the result. The rows the quality check flags are more than
ten times as likely to disagree with an independent source. The verdict column
predicts correctness rather than merely asserting it.

## Method

Each printed layout is described by a JSON profile declaring its columns,
units, physical ranges and the arithmetic the page asserts about itself. That
one file is what a new publication costs: of eighteen layouts, two ever needed
hand-labelled rows. `docs/ADDING-A-PUBLICATION.md` is the path and the
evidence.

Row localisation does not use the ink profile, which cannot find rows in a
grid of words and was silently publishing pages at a third of their length —
one shipped 3 of its 31 days. Instead the transcription model reads the
printed day numbers, a line is fitted robustly through the ones it is sure of,
every row is placed on that line, and then **the rows are read back** to check
the days return 1, 2, 3 in order. 40 pages were re-read this way and now give
1,667 rows where they gave 626.

## Read before using

`DATASET_CARD.md`, in particular the section on what `checks_pass` actually
verifies — it differs by publication and is **not** a uniform quality tier.
For the Annales and Radcliffe it is the printed arithmetic on the page; for
the Revista it is the day sequence only.

No row has been verified line-by-line by a human. The 3,822-cell evaluation
gold set has been, and is separate from this dataset.

## Licence

CC0 on the transcriptions, Apache-2.0 on the pipeline and the model weights.
The observations themselves are public domain and are not ours to licence.
