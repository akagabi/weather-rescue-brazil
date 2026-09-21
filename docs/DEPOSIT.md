# Minting a DOI

The dataset and the code are published (GitHub, Hugging Face) but neither is
*citable* or *findable* by the people most likely to want them. A DOI is what
fixes that, and it is the last thing standing between this work and the places
it should end up: the International Surface Pressure Databank, Copernicus C3S,
a data paper.

Everything below is a decision or a click. None of it is code.

## Done — 2026-09-21

**Concept DOI `10.5281/zenodo.22876699`** (cite this one; it always resolves
to the newest version) and version DOI `10.5281/zenodo.22876700` for v0.10.

One thing to know for next time, recorded because it wasted half an hour of
suspicion: **Zenodo's public search API did not return the record for at
least 25 minutes after it was minted**, while the record itself was complete
and live the whole time. Querying `/api/records?q=...` and getting nothing
back is not evidence that anything failed. The authoritative places are
<https://zenodo.org/account/settings/github/>, which shows the DOI badge
against the repository, and `/api/records/<id>` once the id is known. The
webhook returning **202** on the `published` event is the real signal that
Zenodo accepted the job; the `409`s on the `created` and `released` events
that follow are duplicates being correctly ignored, not errors.

`.zenodo.json` should still be kept to schema fields only — no `_comment`
key, no empty `affiliation` — but for tidiness, not because either broke
this deposit. `version` must match `data/dataset/version.json` and the tag.

## Before you mint anything

**A DOI cannot be edited after it is minted.** The record can get new versions,
but the author line on version 1 is permanent. Two fields matter:

1. **Your name.** `CITATION.cff` and `.zenodo.json` both say `akagabi`. A DOI
   credited to a handle does not connect to you on a CV, in a citation index,
   or to a future employer. Put your real name in both files.
2. **An ORCID.** Free, takes five minutes at <https://orcid.org/register>, and
   it is the thing that makes every future output accumulate under one
   identity. Add it to `CITATION.cff` as `orcid:` and to `.zenodo.json` as
   `"orcid"` inside `creators`.

Do those two first. Everything else here is reversible.

## The route: GitHub release, archived by Zenodo

Chosen because it needs no API token, versions itself with the repository, and
picks up `.zenodo.json` automatically. The tracked repository is 118 MB, well
inside what this handles.

1. Sign in at <https://zenodo.org> with GitHub.
2. Go to <https://zenodo.org/account/settings/github/> and switch
   **`akagabi/weather-rescue-brazil`** on. This must happen BEFORE the release
   — Zenodo only sees releases published after the switch is flipped.
3. Cut the release:

       git tag -a v0.8 -m "v0.8 - 7,197 rows, 3,936 usable, 47,544 values"
       git push origin v0.8
       gh release create v0.8 --title "v0.8" --notes-file docs/RELEASE-v0.8.md

4. Zenodo archives it within a minute or two and mints the DOI. It appears on
   the same settings page, as a badge.
5. Put the DOI back into `README.md`, `DATASET_CARD.md`, `CITATION.cff`
   (`doi:` and `identifiers:`) and the Hugging Face card, then re-publish those
   with `scripts/g4_publish.py --yes`.

A concept DOI is minted alongside the version DOI. **Cite the concept DOI** —
it always resolves to the newest version, which is what you want on a dataset
that is still growing.

## Then, and only then

These all ask for a DOI on the form, which is why they have been waiting:

- **C3S Data Rescue registration**, <https://datarescue.climate.copernicus.eu>.
  The inventory form takes a DOI, a station list, a period and a licence. All
  four now exist.
- **International Surface Pressure Databank.** The pressure series is the part
  of this with the clearest home — ISPD feeds 20CR, and the Annales print
  barometric pressure seven times a day for 1883-85, which is unusually dense
  for the period and the hemisphere.
- **A data paper**, if you want one. *Geoscience Data Journal* and *Earth
  System Science Data* both take dataset descriptions, and both want the data
  deposited under a DOI with an open licence first.

## What NOT to claim

Everything in the cards is measured, and it should stay that way when it is
restated on a form or in an abstract:

- 3,936 rows are usable of 7,197. Do not quote the row count alone.
- `checks_pass` means the row does not contradict itself, and what verifies it
  differs by publication — printed arithmetic for the Annales and Radcliffe,
  the day sequence only for the Revista.
- The external agreement figures (100% dry bulb, 96.7% rainfall) are the
  **usable subset** of the Radcliffe rows, 252 and 300 cells. Over every row
  read they are 99.3% and 91.1%. Both are true; say which one you mean.
- No row has been verified line-by-line by a human.
