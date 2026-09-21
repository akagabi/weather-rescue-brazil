Nineteenth-century weather observations from six stations, 1851-1890,
transcribed from printed tables by a 2B model running offline on a laptop.

**7,197 rows, 3,936 usable, 47,544 values, 259 pages.** Portuguese, French and
English; eighteen printed layouts, fifteen of which needed no labelled rows at
all. Total API spend across the project: US$1.56.

## What is new since the first public version

**External validation.** The Radcliffe Observatory (Oxford) tables can be
graded against Oxford's own published series, digitised independently more
than a century later. Of the cells this dataset calls usable, **100% of the
dry bulb and 96.7% of the rainfall** agree with it — and of the rainfall cells
it *flags*, only 44.4% do. The quality verdict predicts agreement with an
outside source, not merely internal consistency.

**Row localisation by the reader rather than the ink profile.** A page whose
columns are words defeats an ink-profile row detector, and 27 pages were being
published at a third of their length — one shipped 3 of its 31 days. Letting
the transcription model read the printed day numbers, fitting a line through
the ones it is sure of, placing every row on that line and then **reading them
back to check** recovers them. Those 27 pages now give 867 rows where they gave
477.

**Everything is open.** CC0 on the transcriptions, Apache-2.0 on the code and
the model weights.

## Read before using

`DATASET_CARD.md`, in particular the section on what `checks_pass` actually
verifies — it differs by publication and is not a uniform quality tier. No row
has been verified line-by-line by a human; the 3,822-cell gold set has been,
and is separate from the dataset.
