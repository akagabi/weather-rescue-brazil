"""Fetch missing pages of a DocVirt volume, politely and resumably.

    python scripts/g4_fetch_docvirt.py 14 216

Sequential, >=2 s apart, project User-Agent, skips what is already on disk.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "docvirt"
URL = "https://api.docvirt.com/v1/documents/obnacional/{doc}/{page}"
UA = "WeatherRescueBrazil/0.1 (open climate data rescue; contact: gabesuit@gmail.com)"


def main() -> None:
    doc, last = sys.argv[1], int(sys.argv[2])
    out_dir = RAW / doc
    out_dir.mkdir(parents=True, exist_ok=True)
    missing = [p for p in range(1, last + 1) if not (out_dir / f"{p:06d}.webp").exists()]
    print(f"doc {doc}: {last} páginas no total, {len(missing)} a baixar", flush=True)
    got = 0
    for i, p in enumerate(missing):
        out = out_dir / f"{p:06d}.webp"
        try:
            r = httpx.get(URL.format(doc=doc, page=p), timeout=60, headers={"User-Agent": UA})
        except Exception as e:
            print(f"  p{p}: erro {e}", flush=True)
            time.sleep(2.0)
            continue
        time.sleep(2.0)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
            print(f"  p{p}: HTTP {r.status_code}", flush=True)
            continue
        out.write_bytes(r.content)
        out.with_suffix(".json").write_text(json.dumps(
            {"url": URL.format(doc=doc, page=p), "doc": doc, "page": p,
             "attribution": "Biblioteca Digital de Obras Raras do Observatório Nacional",
             "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False))
        got += 1
        if got % 20 == 0:
            print(f"  {got}/{len(missing)} baixadas", flush=True)
    print(f"pronto: {got} páginas novas em {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
