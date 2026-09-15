"""Build the printed-coordinate registry from the Revista's own station lines.

    python scripts/g4_stations_printed.py            # report
    python scripts/g4_stations_printed.py --write    # write data/stations_printed.json

`data/stations.json` holds coordinates looked up from the modern city. They
are approximations, they are all `verified: false`, and that is why every SEF
file this project exports carries `NA` where a latitude should be.

The Revista prints the observatory's own coordinates at the head of each
station block of the `RESUMO MENSAL DAS OBSERVAÇÕES SIMULTANEAS` form. This
records them, with the page each came from, and converts the longitudes from
the Rio meridian they are measured against (see wrb.stations).

It does NOT assume a hemisphere. Several lines print none: Maceió's latitude
is set as `9°,38'` and Cidade do Rio Grande's longitude as `0h,36m,30s`, with
no letter on either. The convention here is that a coordinate whose direction
the page does not state is written with its magnitude and
`hemisphere_missing: true`, and no signed value at all. Guessing south-and-west
would be right for every station in this volume and is still the wrong habit:
it is the same move that dated 509 rows to January.
"""
from __future__ import annotations

import argparse, json, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wrb.stations import parse_header  # noqa: E402

# Read from the scans named beside each line. Kept verbatim, accents and all,
# including the compositor's inconsistencies between one printing and the next.
PRINTED = [
    ("16", 41, "Estação, S. Paulo; Observador, Alberto Loefgren; Latitude, 23°36' S; "
                "Longitude, 3°28' W; Hora local, 8h29m27s; Alt. do Bar. 735m42"),
    ("15", 126, "Estação, Maceió; Observador, Pedro Rodrigues Soares; Latitude, 9°,38'; "
                "Longitude, 0h,30m E; Hora local, 9h,36m; Altura do Barometro, 10m"),
    ("15", 126, "Estação, Ponte B. de Macedo; Observador, Manoel Villarouco; "
                "Latit., 8°3'54'' S; Long., 0h33m11s4 E; Hora local, 9h40m; Alt. do Bar., 2m,87"),
    ("16", 41, "Estação, Bahia (Capital); Observador, Dr. R. A. Pereira Guimarães; "
               "Latitude, S 12°58'27''; Long., E 4°37'40''; Hora local, 9h25m30s; Alt. do Bar. 64m"),
    ("16", 41, "Estação, Santa Cruz; Observador, J. N. C. Lousada; Latitude, 22°,56'; "
               "Longitude, 2m W; Hora local, 9h,9m; Alt. do Bar. 26m"),
    ("16", 90, "Estação, Cidade do Rio Grande; Observador, Commissão da Barra; "
               "Latitude, 31°,59'53''; Longitude, 0h,36m,30s; Hora local, 8h,31m; "
               "Alt. do Bar. 16m,50"),
    ("15", 158, "Estação, Cruzador Almirante Barroso; Observador, 2º tenente A. Silvado; "
                "Latitude, var ; Longitude, var.; Hora local, var.; Alt. do Bar., 2m,5"),
]


def slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "_".join("".join(c if c.isalnum() else " " for c in n).lower().split())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    out = {"_note": "Coordinates as PRINTED by the Revista do Observatório, with the page "
                    "each came from. Longitudes are printed relative to the Rio meridian and "
                    "converted here (wrb.stations.RIO_LONGITUDE). A coordinate whose "
                    "hemisphere the page does not print is left unsigned and flagged; it is "
                    "not guessed. `verified` stays false until a person checks the line "
                    "against the scan.",
           "_source_form": "RESUMO MENSAL DAS OBSERVAÇÕES SIMULTANEAS",
           "stations": {}}
    for doc, page, line in PRINTED:
        h = parse_header(line)
        name = h["fields"]["station"]
        rec = {
            "name": name,
            "observer": h["fields"]["observer"],
            "printed": line,
            "source": {"archive": "docvirt", "doc": doc, "page": page},
            "verified": False,
            "moves": h["moves"],
            "bar_alt_m": h["bar_alt_m"],
            "lat_printed": h["fields"]["lat"],
            "lon_printed": h["fields"]["lon"],
            "lon_reference": "Rio de Janeiro (Imperial Observatório)",
        }
        if h["moves"]:
            rec["note"] = "ship under way; the page prints `var` for both coordinates"
        else:
            if h["lat_hemisphere"]:
                rec["lat"] = round(h["lat_deg"], 4)
            else:
                rec["lat_magnitude"] = round(abs(h["lat_deg"]), 4) if h["lat_deg"] else None
                rec["hemisphere_missing"] = True
            if h["lon_hemisphere"]:
                rec["lon"] = h["lon_deg"]
                rec["lon_from_rio"] = round(h["lon_from_rio_deg"], 4)
            else:
                rec["lon_from_rio_magnitude"] = (round(abs(h["lon_from_rio_deg"]), 4)
                                                 if h["lon_from_rio_deg"] else None)
                rec["hemisphere_missing"] = True
        out["stations"][slug(name)] = rec

    for k, r in out["stations"].items():
        flag = "  <- hemisphere not printed" if r.get("hemisphere_missing") else ""
        pos = ("moves" if r.get("moves")
               else f"{r.get('lat', r.get('lat_magnitude'))}, {r.get('lon', '?')}")
        print(f"  {k:<28} {str(pos):<22} alt={r['bar_alt_m']}m  doc {r['source']['doc']}/"
              f"{r['source']['page']}{flag}")
    print(f"\n{len(out['stations'])} stations read off the printed form")
    if args.write:
        p = ROOT / "data" / "stations_printed.json"
        p.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        print("wrote", p.relative_to(ROOT))
    else:
        print("report only - re-run with --write")


if __name__ == "__main__":
    main()
