# Draft — to the EMERLAC authors (NOT SENT)

**To:** Fernando Domínguez-Castro, Senior Researcher, Instituto Pirenaico de
Ecología (IPE-CSIC) — corresponding author, *Early meteorological records from
Latin-America and the Caribbean during the 18th and 19th centuries*,
Scientific Data 4, 170169 (2017).

**Address:** `f.dominguez.castro@gmail.com` — published as the corresponding
author's contact in the PANGAEA dataset metadata for this collection
(doi:10.1594/PANGAEA.871490), not guessed.

**Subject:** Brazilian daily records, 1885–1890 — a gap in EMERLAC we may be
able to fill

---

Dear Dr Domínguez-Castro,

I am writing about a gap I believe your EMERLAC compilation identifies, and
which I may be in a position to help close.

Working from the *Revista do Observatório* (Imperial Observatório, Rio de
Janeiro, 1886–1891), digitised and public-domain, I have transcribed 1,194
daily station-rows covering December 1885 to November 1890 — barometer,
dry/wet bulb, maximum and minimum temperature, vapour tension, humidity, wind
direction and force, cloudiness, rainfall and evaporation, at up to three
readings a day.

Before going further I checked whether this duplicates existing work:

- The EMERLAC collection on PANGAEA lists 14 Brazilian series. The latest ends
  in **December 1856**.
- GHCN-Daily's station inventory contains **no Brazilian daily record before
  1901**.

If I have read both correctly, Brazilian daily data between 1857 and 1900 is
largely absent from the international archives, and this material sits inside
that gap. The period is not an accident: the Rio observatory established
Brazil's first meteorological network in 1886, and the *Revista* is that
network's publication. The record was printed and shelved, never keyed in.

Since writing the above I have swept 269 further pages of the same collection.
95 are monthly meteorological tables, and they are not from one observatory but
from at least fourteen reporting sites:

| site | pages found | already transcribed |
|---|---|---|
| Rio de Janeiro (Imperial Observatório) | 27 | yes |
| Cuiabá, Mato Grosso | 12 | no |
| Santa Cruz, Rio de Janeiro | 5 | yes |
| São Paulo (Comissão Geográfica e Geológica) | 5 | no |
| Maceió, Alagoas | 4 | no |
| Cidade do Rio Grande, RS | 2 | no |
| Comissão da Barra do Rio Grande do Sul | 2 | no |
| Corumbá, Mato Grosso | 2 | yes |
| Ouro Preto, Minas Gerais | 2 | no |
| Porto do Maranhão | 1 | yes |
| S. João d'El-Rei, Minas Gerais | 1 | no |
| Tatuí, São Paulo | 1 | no |
| Observatório Graça Filho | 1 | no |
| **Cruzador Almirante Barroso** (naval vessel) | 1 | no |

Most arrive on one standardised printed form — *Resumo mensal das observações
simultaneas*, with fields for station, observer and latitude — which suggests a
single parser reads all of them. The observers are named on the page: Alberto
Löfgren at São Paulo, Pedro Rodrigues Soares at Maceió, Major Américo
Rodrigues at Cuiabá.

One of these is different in kind: the *Almirante Barroso* is a naval vessel,
so those are marine observations and presumably belong with ICOADS rather than
the land archives.

I should say plainly that I looked for an overlap with your existing Brazilian
series and could not find one. Your BRARIO7 covers Rio 1851–1856, but as
monthly temperature means in Réaumur taken from Dove (1859), and the material I
have starts in 1885. I briefly thought I had found Rio tables from 1853 and
1855 in the same archive; on inspection they are a lunar almanac — moon phases
and meridian passages — not meteorology. So I cannot offer you a blind
validation against data you have already published, which is the test I would
most want to see before trusting someone else's transcription.

What I can offer instead is the check the pages carry themselves: each monthly
table is accompanied by a printed *Revista climatologica do mez* summarising
the same month, so the arithmetic can be closed against the page rather than
against my own judgement. Roughly a fifth of rows fail some check and are
flagged rather than asserted. If you would rather assess the method on a
sample of your own choosing, I will transcribe whatever pages you name and
send the raw output.

**Three questions, in order of usefulness to me:**

1. Have I misread the coverage? If Brazilian 1857–1900 daily data exists
   somewhere I have not looked, I would rather know now than publish a
   redundant dataset.
2. If the gap is real, what format would make this usable to you and to the
   ACRE/C3S community? I assume SEF, but I would rather be told than guess,
   and it is much cheaper to produce it correctly than to convert later.
3. Is there interest in the remaining stations? The transcription is
   automated and the marginal cost per additional month is small.

On method, so you can judge the data's reliability: the transcription is done
by a small open-weights vision model I fine-tuned for this, running locally.
It scores 99.1% per-cell against a frozen, human-verified gold set, matching a
commercial API on the same test. Values are stored exactly as printed, with
the publication's conventions (elided barometer thousands, ditto marks,
printed words such as "Gottas") recorded separately rather than silently
normalised, so a consumer can restore them deterministically or reject them.
Every row carries its page-level provenance and a QC verdict; roughly 20% are
flagged for review rather than asserted. Nothing is corrected without a record
of the correction.

I am not affiliated with an institution and I am not seeking authorship. The
data will be released openly whatever you advise; I would simply rather it
land somewhere it gets used.

With thanks for the EMERLAC compilation, which is what let me check my own
claim in the first place,

Gabriel Bueno
gabesuit@gmail.com
