# Oxford Radcliffe published series — the external answer key

Downloaded 2026-09-18 from
<https://www.geog.ox.ac.uk/research/climate/rms/monthly-annual.html>.

| file | series | units | span |
|---|---|---|---|
| `oxford-monthly-tmean-celsius.csv` | monthly mean temperature | °C | 1813-12 → 2025-12 |
| `oxford-monthly-pptn-mm.csv` | monthly rainfall total | mm | 1767 → 2025-12 |

These are **not** this project's output and are not covered by its CC0
dedication. They are Oxford's, kept here so that
`scripts/g4_external_test.py` can be re-run by anyone.

They matter because every other measurement in this project is self-graded:
the gold set is our own labels and a checksum test asks whether the model's
numbers close the model's own parse. These files were digitised independently,
from the same observations, more than a century later. The two series are not
numerically identical — Oxford homogenised theirs — so the test is not equality
but whether every cell sits on one fitted relation. A misread digit cannot.
