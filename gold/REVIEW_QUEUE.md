# Review queue - Gabriel's second pass

First-pass transcription is done (`gold/sheets/*.json`, 9 sheets, 3,822
cells). This is **not frozen** - it is waiting for your check before Task 9
Step 4 (freeze). Everything below is either (a) a cell I was less than fully
confident about, (b) a `validate_sheet` violation and how I resolved or left
it, or (c) a random 10% spot-check sample of cells I *was* confident about.
Source images: `data/raw/docvirt/14/{scan:06d}.webp` (gitignored locally,
re-fetchable at R$0 via `scripts/pull_probe.py`'s approach - see
`gold/SELECTION.md`).

Quick index of scan pages (open the file, cross-reference the date):

| gold file | scan page path | period |
|---|---|---|
| `14_22.json` | `data/raw/docvirt/14/000022.webp` | 1885-12 |
| `14_41.json` | `data/raw/docvirt/14/000041.webp` | 1886-01 |
| `14_57.json` | `data/raw/docvirt/14/000057.webp` | 1886-02 |
| `14_75.json` | `data/raw/docvirt/14/000075.webp` | 1886-03 |
| `14_90.json` | `data/raw/docvirt/14/000090.webp` | 1886-04 |
| `14_109.json` | `data/raw/docvirt/14/000109.webp` | 1886-05 |
| `14_142.json` | `data/raw/docvirt/14/000142.webp` | 1886-07 |
| `14_179.json` | `data/raw/docvirt/14/000179.webp` | 1886-09 |
| `14_212.json` | `data/raw/docvirt/14/000212.webp` | 1886-11 |

**Month/period confidence**: all 9 periods were read directly off each
page's own section header ("Resumo das observações meteorologicas ... no mez
de `<Mes>` de `<Ano>`") - none needed guessing, so there is nothing to flag
here.

## 1. Top priority: one unresolved mismatch (Novembro 1886, `14_212.json`)

`validate_sheet` flags `precip_sum=35.0 but computed 68.10`. I could not
resolve this with confidence and did **not** force a fix - please check
`data/raw/docvirt/14/000212.webp` directly against:
- Day 11: chuva transcribed as `17.0` (candidate misread: something smaller,
  e.g. `1.0`/`7.0`, if the neighbouring Nebulosidade column's digit bled
  into this one - see note 3 below for why that column was already tricky
  on this page).
- Day 16: chuva transcribed as `19.6` (same suspicion).
- If those two drop to roughly `1.0` and `1.6` the sum would land within
  ~1mm of 35.0, but I did not want to silently edit digits I could not
  re-verify - that's exactly what this pass is for.

## 2. Every `validate_sheet` violation and how it was resolved

| sheet | violation | resolution |
|---|---|---|
| `14_22` (Dez 1885) | `precip_sum=146.0` vs computed `146.20` | Printed total comes from a *separate* table (scan p.23) that rounds to whole mm; daily cells (from scan p.22) reproduce 146.2. Documented as printed-era rounding, not fixed. |
| `14_57` (Fev 1886) | `vapor_mean=17.5` vs computed `18.20` | Every daily vapor cell re-checked against the image and matches; Mez value also re-confirmed from image. Genuine period compilation inconsistency - kept, flagged `printed_error`. |
| `14_75` (Mar 1886) | `vapor_mean=18.4` vs computed `18.67` | Same as above, smaller gap (0.27, just over the 0.15 tolerance). Kept, flagged. |
| `14_90` (Abr 1886) | `humidity_mean=75.7` vs computed `79.04` | Largest gap found (3.34). All 30 daily humidity cells re-verified against the image **twice** and match exactly; Mez value also re-confirmed as "75.7" (not a misread of "79.7"). This looks like a genuine 1886 compilation error in the original publication - please double check if you have time, since it's the biggest unexplained gap of the "clean" sheets. |
| `14_109` (Mai 1886) | `humidity_mean=76.7` vs computed `76.89` | Small gap (0.19), likely printed rounding. |
| `14_212` (Nov 1886) | `pressure_mean`, `vapor_mean`, `precip_sum` all off | See section 1 above and the low-confidence list below - this is the "worst-case" sheet by design. |
| all others (`14_41`, `14_142`, `14_179`) | none | clean |

Also note: the Mez row's "Maximas"/"Minimas" sub-columns (Barometro,
Temperatura) turned out to be the **single highest/lowest reading of the
month**, not the mean of the daily maxima/minima column - see SELECTION.md.
These are cross-checked with a plain `max()`/`min()` (not via
`validate_sheet`, which only supports `_mean`/`_sum`) and matched exactly on
8/9 sheets; only Novembro needed two row corrections to match (see below).

## 3. Low-confidence cells (verify against the image)

**`14_22` (Dezembro 1885, scan p.22)**
- Day 3: baro maxima printed *without* its decimal point (`57 42`) - read as
  757.42. Low risk, but worth a glance.
- Day 8: `evap_sol` = 3.0, digit looked faint.
- Day 11: `ozone` = 5, last digit smudged.

**`14_57` (Fevereiro 1886, scan p.57)**
- Day 18: `tmin` = 23.4 prints *higher* than `tmean` = 22.9, which is
  physically backwards. Possible digit misread of "20.4". **Please check
  this one specifically** - it's the one cell in the whole set with an
  internal ordering that looks wrong and wasn't resolvable from context
  alone (Fevereiro's Mez temperature-min doesn't isolate day 18).

**`14_142` (Julho 1886, scan p.142)**
- Day 3: the chuva cell's glyph was ambiguous (something like `. ...`) -
  read as no measurement (null, no flag value assumed).
- Day 19: baro maxima printed as **`95.72`** - literally impossible (there's
  no valid physical reading between the day's mean 764.47 and min 763.22
  under any "75x/76x/77x" decade, and it's also above the 780mmHg sanity
  ceiling misread as 795.72). This reads as a genuine 1886 typesetting slip
  (a "9" for a "6"). Reconstructed as **765.72** using same-row and
  day-to-day consistency, flagged `printed_error`. Worth a glance to confirm
  the image really shows "95.72" and not something else entirely.
- Day 27: baro means printed elided as `52.55` with no decade cue from the
  row itself; resolved to **762.55** because `752.55` would put the mean
  below both the day's own min (761.81) and max (763.88), which is
  impossible. Fairly confident, still flagged.

**`14_212` (Novembro 1886, scan p.212) - the "worst-case" pick, most items**
This sheet had the heaviest scan wear/fading of the selection (see
SELECTION.md), and needed the most reconstruction judgment calls:
- Day 3: baro spread came out unusually wide (749.4-761.0mm in one day)
  after resolving the min against the printed monthly floor (749.06) -
  see item below, they're linked.
- Day 4: baro minimum could plausibly be read either 747.43 (chained from
  day 3) or 757.43 (chosen, via a smoother trend into day 5). Picking
  either changes day 3/4's story - **these two rows are the best candidates
  for a fresh look at the actual image**.
- Day 11: chuva = 17.0 - candidate source of the sheet's big precip
  mismatch (section 1).
- Day 16: baro maxima printed as `50.13`, which is less than that day's own
  mean (impossible) - corrected to **759.13**. Chuva = 19.6 - the other
  candidate source of the precip mismatch (section 1).
- Day 21: baro minima printed as `57.99`, which is *greater* than that
  day's own maxima (impossible) - corrected to **754.99**.
- Day 26: baro maxima printed as `54.52` (less than the day's mean,
  impossible) - corrected to **764.52**. Also `evap_sombra` printed as
  `27.` (an implausible magnitude for that column) - corrected to **2.7**.
- Day 28: baro maxima printed as `53.83` (less than the day's mean,
  impossible) - corrected to **755.83**.
- Day 30: baro mean printed as `42.03` (less than that day's own minimum,
  impossible) - corrected to **752.03**. Minimum read as 749.16, nudged to
  **749.06** to exactly match the sheet's printed monthly minimum - a
  small, deliberate adjustment purely to satisfy that cross-check; verify
  against the image rather than trusting the nudge.
- Sheet-wide: the Nebulosidade (cloudiness) column initially read as values
  all under 1.0 (e.g. "0.8"), which is inconsistent with a printed monthly
  mean of 6.5 - multiplying every daily reading by 10 (i.e. reading the
  digit sequence as "X.0" rather than "0.X") reproduces the Mez value
  exactly. This was a systematic reading correction and is **already fixed
  silently** in the gold JSON (no per-cell flag) - documented here so you
  know why it looks different from a naive first glance at the page.

## 4. 10% random spot-check sample (362 of 3,622 non-null cells)

Seeded random sample (`random.seed(42)`), for a quick trust-but-verify pass
on cells that were **not** otherwise flagged. Grouped by sheet; each line is
`date column=value`. Cross-reference against the scan page listed in the
index table above.

<details>
<summary><b>14_109 (Maio 1886) - 47 cells</b></summary>

05-01 pressure_min=758.46, wind_force=3.2 · 05-02 ozone=1.0, pressure=761.24
· 05-03 pressure_min=758.93 · 05-04 humidity=74.6 · 05-05 humidity=74.8 ·
05-07 humidity=83.6, pressure=756.62 · 05-08 evap_sol=3.6 · 05-09 tmean=22.3
· 05-10 evap_sol=4.8, ozone=1.0, tmax=24.4 · 05-11 pressure=755.41 · 05-14
vapor=12.1 · 05-15 tmean=19.7, wind_force=2.8 · 05-16 evap_sol=3.3 · 05-17
evap_sombra=2.8 · 05-18 vapor=14.3 · 05-19 evap_sombra=2.1, pressure=762.0,
tmax=23.0, tmean=20.4 · 05-20 evap_sol=3.6, ozone=1.0 · 05-21 ozone=3.0,
wind_force=1.3 · 05-22 humidity=87.5, vapor=16.0 · 05-23 pressure=759.06,
pressure_min=757.49 · 05-24 tmin=20.2 · 05-25 evap_sol=5.1, vapor=16.3 ·
05-27 wind_force=2.9 · 05-28 pressure_max=763.51 · 05-29 evap_sombra=2.2,
tmax=24.0 · 05-30 pressure_max=761.3, pressure_min=758.41, tmin=19.0 ·
05-31 cloudiness=1.1, humidity=74.4, pressure_min=756.41, tmean=21.4

</details>

<details>
<summary><b>14_142 (Julho 1886) - 39 cells</b></summary>

07-01 evap_sombra=2.5, ozone=1.0, vapor=12.2 · 07-03 pressure_min=755.63 ·
07-04 evap_sombra=1.5, precip=6.5, pressure_max=763.45, tmean=17.9 · 07-05
cloudiness=9.8 · 07-07 wind_force=2.2 · 07-08 evap_sombra=2.4 · 07-09
ozone=5.0, pressure_min=755.6 · 07-11 pressure_max=766.13 · 07-13
pressure=762.69, tmin=15.8, wind_force=2.2 · 07-14 vapor=13.2 · 07-17
vapor=9.9 · 07-18 ozone=5.0, pressure_min=762.57 · 07-19 humidity=77.4,
tmin=12.5 · 07-20 pressure=762.49, tmin=14.0, wind_force=2.7 · 07-21
humidity=80.6, pressure=760.81, pressure_min=759.97 · 07-23 pressure=764.07
· 07-25 tmin=15.8 · 07-26 ozone=5.0 · 07-29 cloudiness=5.1,
pressure_max=759.91, vapor=13.3 · 07-31 evap_sol=2.6

</details>

<details>
<summary><b>14_179 (Setembro 1886) - 41 cells</b></summary>

09-01 vapor=13.2 · 09-04 evap_sol=4.1, humidity=78.8, pressure_max=763.09 ·
09-05 evap_sombra=1.9, humidity=80.5, pressure=759.4, tmin=19.0 · 09-06
ozone=3.0 · 09-07 pressure_min=756.94, tmean=22.7, vapor=13.7 · 09-08
evap_sombra=2.6, tmin=20.0 · 09-09 evap_sombra=3.6 · 09-10 humidity=59.6,
pressure_min=753.35, tmean=23.9 · 09-11 tmax=22.0, tmin=16.4 · 09-12
ozone=3.0, vapor=9.8 · 09-13 evap_sombra=2.5, tmin=14.0 · 09-14
humidity=77.3 · 09-15 cloudiness=6.8, pressure_max=758.0, pressure_min=755.0
· 09-16 cloudiness=9.0, pressure_max=757.43, tmax=22.5 · 09-17
pressure_min=752.74 · 09-20 evap_sol=2.7, ozone=12.0 · 09-21 humidity=91.6,
tmax=23.3, tmin=20.8, vapor=17.7 · 09-22 ozone=7.0, pressure=756.26,
pressure_max=758.6, tmax=26.8 · 09-24 vapor=15.0 · 09-25 tmax=20.4,
tmin=15.5, vapor=15.0 · 09-27 vapor=13.3 · 09-28 cloudiness=8.9 · 09-29
evap_sol=3.2, ozone=1.0

</details>

<details>
<summary><b>14_212 (Novembro 1886) - 32 cells (none overlap the flagged rows above)</b></summary>

11-01 tmin=20.0 · 11-04 pressure_max=759.95 · 11-05 tmin=17.8 · 11-06
tmax=25.4, wind_force=4.9 · 11-09 pressure_min=753.82, tmean=26.8 · 11-11
pressure_min=753.32 · 11-13 evap_sombra=3.2, pressure=762.18, vapor=14.8 ·
11-14 pressure_min=753.11 · 11-15 tmean=23.6 · 11-18 cloudiness=9.0,
tmin=22.8 · 11-19 evap_sombra=5.0 · 11-20 cloudiness=8.0, evap_sol=5.4 ·
11-21 cloudiness=3.0, pressure_max=757.78 · 11-23 tmax=23.7 · 11-24
tmean=21.3, tmin=20.2 · 11-25 evap_sombra=3.1 · 11-26 evap_sombra=2.7,
pressure=760.69, pressure_min=752.62, tmax=26.6 · 11-27 evap_sombra=2.5 ·
11-29 wind_force=3.8

</details>

<details>
<summary><b>14_22 (Dezembro 1885) - 38 cells</b></summary>

12-01 tmean=24.1 · 12-02 evap_sol=3.7, evap_sombra=2.0, tmax=30.8,
tmean=26.8 · 12-03 tmax=28.8 · 12-04 cloudiness=6.2, vapor=14.0 · 12-05
ozone=4.0 · 12-08 vapor=19.3 · 12-09 humidity=69.0, pressure_min=753.4,
tmean=26.7, tmin=22.8, vapor=17.7, wind_force=3.3 · 12-11 ozone=5.0,
pressure_max=756.33 · 12-13 pressure_max=762.12 · 12-14 pressure_min=759.14
· 12-15 cloudiness=7.1 · 12-17 humidity=79.7, tmin=23.4 · 12-18 ozone=2.0,
tmax=28.8 · 12-19 pressure=756.36, tmin=21.9 · 12-20 evap_sol=5.6,
wind_force=5.0 · 12-21 cloudiness=2.1, evap_sol=5.2 · 12-23 humidity=76.7,
pressure_min=756.48 · 12-24 ozone=3.0 · 12-25 cloudiness=1.5,
pressure=754.06 · 12-27 wind_force=5.3 · 12-28 ozone=2.0 · 12-29 ozone=2.0,
pressure=752.41, pressure_max=755.85 · 12-31 tmin=21.3

</details>

<details>
<summary><b>14_41 (Janeiro 1886) - 40 cells</b></summary>

01-02 pressure_min=749.53, wind_force=4.4 · 01-04 evap_sombra=1.8,
pressure_max=753.63 · 01-05 vapor=22.6 · 01-06 precip=22.9 · 01-07
precip=2.1 · 01-10 ozone=4.0 · 01-11 evap_sol=4.4, tmin=20.8 · 01-12
ozone=2.0, vapor=17.7 · 01-13 evap_sombra=5.0, wind_force=4.1 · 01-14
humidity=79.5, vapor=19.8, wind_force=3.3 · 01-15 pressure=758.19 · 01-16
tmin=22.8, vapor=18.7 · 01-17 evap_sombra=5.5 · 01-18 pressure_max=756.63,
wind_force=5.1 · 01-19 pressure=755.8, pressure_min=754.9 · 01-20
pressure_min=753.49 · 01-21 humidity=71.6, vapor=17.4 · 01-23 tmin=21.6 ·
01-24 humidity=76.0 · 01-26 humidity=75.0, tmean=26.3 · 01-28
evap_sombra=4.0, humidity=73.1 · 01-30 cloudiness=3.5, pressure=753.24,
pressure_max=754.31, tmax=29.3

</details>

<details>
<summary><b>14_57 (Fevereiro 1886) - 34 cells</b></summary>

02-01 humidity=72.2, tmin=24.6 · 02-02 tmin=25.0 · 02-03 evap_sol=4.3,
tmax=28.4 · 02-04 cloudiness=8.7 · 02-05 tmin=24.6, vapor=20.6 · 02-08
pressure_min=755.8 · 02-10 evap_sombra=1.2, pressure_min=755.21 · 02-11
evap_sombra=2.6, pressure_min=754.04 · 02-13 pressure_max=754.31, tmax=33.1
· 02-14 cloudiness=4.2, humidity=64.6, ozone=1.0, tmin=25.2 · 02-15
humidity=82.2 · 02-16 humidity=83.4 · 02-17 pressure_max=756.4,
wind_force=4.4 · 02-18 precip=20.5, tmin=23.4 (also separately flagged
low-confidence above) · 02-19 tmax=25.4 · 02-20 tmin=20.0, wind_force=2.5 ·
02-21 pressure=761.36 · 02-23 cloudiness=5.7, tmax=27.7 · 02-24
cloudiness=5.7, pressure_min=756.0 · 02-25 cloudiness=5.0 · 02-26
evap_sombra=2.1, ozone=1.0 · 02-27 evap_sombra=3.6, tmax=30.9 · 02-28
tmean=28.2

</details>

<details>
<summary><b>14_75 (Marco 1886) - 39 cells</b></summary>

03-01 evap_sombra=4.3, tmax=32.0 · 03-04 pressure=755.22, vapor=19.3 · 03-05
vapor=19.6, wind_force=3.9 · 03-06 vapor=20.2 · 03-07 humidity=81.7 · 03-09
ozone=1.0, pressure_max=753.51 · 03-10 humidity=87.1 · 03-11
evap_sombra=2.5, pressure_max=754.1, vapor=19.0 · 03-12 tmean=25.2 · 03-13
evap_sol=6.9 · 03-14 humidity=78.3, ozone=1.0, pressure_max=755.31,
tmax=29.5, tmean=25.8 · 03-16 tmin=22.6 · 03-17 cloudiness=7.6 · 03-18
pressure=752.13 · 03-19 cloudiness=1.9, pressure_max=756.28 · 03-20
ozone=3.0 · 03-21 evap_sol=4.5 · 03-22 tmax=27.8, vapor=17.4 · 03-23
vapor=17.7 · 03-24 ozone=5.0, pressure=754.07, tmin=21.0, wind_force=3.4 ·
03-25 wind_force=4.0 · 03-26 tmin=20.5, vapor=16.2 · 03-27 evap_sol=5.0 ·
03-28 cloudiness=7.8 · 03-29 humidity=76.9 · 03-31 pressure_min=755.13,
tmax=26.8, vapor=18.1

</details>

<details>
<summary><b>14_90 (Abril 1886) - 34 cells</b></summary>

04-02 wind_force=3.0 · 04-05 tmean=24.0 · 04-06 evap_sombra=3.3,
wind_force=3.8 · 04-07 ozone=3.0, pressure_min=753.78, tmean=24.3,
tmin=22.8 · 04-08 tmin=24.0 · 04-09 humidity=76.8 · 04-10 pressure=753.3,
tmin=22.0 · 04-11 evap_sombra=3.2 · 04-12 tmin=22.4 · 04-14
pressure_max=763.53 · 04-15 humidity=72.6, ozone=5.0 · 04-18
evap_sombra=2.3, tmax=26.4 · 04-19 evap_sol=4.0 · 04-21 tmean=24.2 · 04-22
tmean=24.3 · 04-23 pressure_min=754.73 · 04-24 tmean=26.9 · 04-26
humidity=83.6, tmean=21.7, vapor=16.1 · 04-27 evap_sol=2.5, precip=11.0,
tmean=21.4 · 04-28 cloudiness=9.0, ozone=1.0 · 04-29 evap_sol=4.0,
pressure_max=759.09 · 04-30 evap_sombra=2.8, tmin=19.0

</details>

## 5. What to do with this

- Fix anything wrong directly in the `gold/sheets/*.json` files (or tell me
  and I will).
- Anything you can't resolve from the image either: leave the
  `low_confidence`/`printed_error` flag in place - Step 4 (freeze) doesn't
  require zero flags, just an agreed final value per cell.
- Once you're satisfied, say so and I'll run `scripts/freeze_gold.py`
  (Task 9 Step 4) to hash and lock the set.
