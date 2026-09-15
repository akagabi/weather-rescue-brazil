"""What a caption sweep found, sorted into what to do about it.

    python scripts/g4_triage.py data/g4/identified_rest.json

A sweep's output is a list of captions. This turns it into the three piles that
actually decide the next run:

  * pages matching a profile this project already reads - the cheapest data
    there is, and the doc 5 lesson: more of a layout you already have beats a
    new layout every time;
  * pages of a form we now read but had not swept for (the Revista's
    `Resumo mensal das observacoes simultaneas`);
  * genuine weather tables that match nothing, grouped by the station their
    caption names - each group is a profile someone could write.

Astronomy is vetoed by wrb.caption and counted separately, because an ephemeris
passes both the geometric sweep and a station-name match (docId 11 is a whole
volume of them).
"""
from __future__ import annotations

import argparse, collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.caption import is_astronomy, match_period, match_profile  # noqa: E402

SIMULTANEAS = re.compile(r"simultan", re.I)

# The Annales print one month's observations across several sheets, one
# instrument each, and those sheets do NOT name the station - the caption reads
# "Nebulosite en dixiemes du ciel couvert" and nothing else. A station matcher
# therefore calls them unidentified, when in fact a profile exists for every
# one of them; they are told apart by CELL COUNT, which is what
# g4_annales_assign.py does. Surfacing them as "no profile yet" sent me looking
# for a layout that was already written.
ANNALES_SUBTABLE = re.compile(
    r"n[ée]bulosit|nebulosit|actinom[ée]tr|tension de la vapeur|"
    r"barom[èe]tre|temp[ée]rature centigrade|an[ée]mom", re.I)


def station_of(caption: str) -> str:
    """A rough grouping key: the proper nouns a caption leads with."""
    c = re.sub(r"\s+", " ", caption or "").strip()
    c = re.sub(r"(?i)revista do observat[oó]rio\s*\d*", "", c)
    c = re.sub(r"(?i)resumo das observa[çc][õo]es meteorol[oó]gicas( feitas)?( em| no| na)?",
               "", c)
    c = re.sub(r"(?i)observations m[ée]t[ée]orologiques du mois d[e']?\s*\w+\s*\d*", "", c)
    return re.sub(r"[^A-Za-zÀ-ÿ .'-]", " ", c).strip()[:48] or "(no station named)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--exclude-produced", action="store_true", default=True,
                    help="drop pages already in a produced dataset (default)")
    args = ap.parse_args()

    done: set[tuple] = set()
    if args.exclude_produced:
        for f in (ROOT / "data" / "dataset").glob("*.jsonl"):
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                done.add((str(r.get("item")), int(r.get("page", -1))))

    seen: dict[tuple, dict] = {}
    for f in args.files:
        for r in json.loads(Path(f).read_text()):
            if not isinstance(r, dict) or not r.get("caption"):
                continue
            key = (str(r.get("doc", r.get("item"))), int(r["page"]))
            if key in done:
                continue
            seen[key] = r

    known, simult, unmatched, astro, annales = [], [], [], [], []
    not_weather = 0
    for (doc, page), r in sorted(seen.items()):
        cap = r["caption"]
        if not r.get("is_weather_table"):
            if is_astronomy(cap):
                astro.append((doc, page, cap))
            else:
                not_weather += 1
            continue
        if is_astronomy(cap):
            astro.append((doc, page, cap))
        elif SIMULTANEAS.search(cap):
            simult.append((doc, page, cap))
        elif ANNALES_SUBTABLE.search(cap):
            annales.append((doc, page, cap))
        elif match_profile(cap):
            known.append((doc, page, match_profile(cap), match_period(cap), cap))
        else:
            unmatched.append((doc, page, cap))

    print(f"{len(seen)} pages with a caption on file and not already produced "
          f"({len(done)} produced pages skipped)\n")
    print(f"  {len(known):>4}  match a profile already written")
    print(f"  {len(simult):>4}  Resumo mensal das observacoes simultaneas")
    print(f"  {len(annales):>4}  Annales sub-tables (assign by cell count, not caption)")
    print(f"  {len(unmatched):>4}  weather tables matching no profile")
    print(f"  {len(astro):>4}  astronomy (vetoed)")
    print(f"  {not_weather:>4}  not a table of weather\n")

    if known:
        by = collections.Counter(k[2] for k in known)
        print("READY TO PRODUCE - a profile exists for these:")
        for pid, n in by.most_common():
            pages = [f"{d}/{p}" for d, p, q, _, _ in known if q == pid]
            print(f"  {pid:<28} {n:>3}  {' '.join(pages[:10])}"
                  f"{' ...' if len(pages) > 10 else ''}")
        print()
    if simult:
        print("RESUMO MENSAL SIMULTANEAS - the form read in docs/g4-simultaneas.md:")
        for d, p, _ in simult:
            print(f"  {d}/{p}")
        print()
    if annales:
        print("ANNALES SUB-TABLES - a profile exists; assign by cell count:")
        print("  " + " ".join(f"{d}/{p}" for d, p, _ in annales))
        print()
    if unmatched:
        print("NO PROFILE YET - grouped by the station the caption names:")
        for name, n in collections.Counter(station_of(c) for _, _, c in unmatched).most_common(args.top):
            pages = [f"{d}/{p}" for d, p, c in unmatched if station_of(c) == name]
            print(f"  {n:>3}  {name:<50} {' '.join(pages[:6])}"
                  f"{' ...' if len(pages) > 6 else ''}")


if __name__ == "__main__":
    main()
