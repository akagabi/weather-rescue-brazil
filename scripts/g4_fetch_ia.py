"""Fetch page images from an Internet Archive item and flag the tables.

    python scripts/g4_fetch_ia.py sim_monthly-weather-review_1883-04_11_4 4,8,12,16,20

A third corpus, from a different archive and a different country, is what the
framework claim needs beyond the Brazilian collection. Public-domain items
only; polite by construction (sequential, >=2 s apart, project User-Agent).
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from PIL import Image  # noqa: E402
from g4_probe_other_works import n_vertical_rules, table_score  # noqa: E402
from wrb.rows import PROBE_X_FRAC, ink_threshold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "ia"
UA = "WeatherRescueBrazil/0.1 (open climate data rescue; contact: gabesuit@gmail.com)"
DELAY = 2.0


def item_meta(ident: str) -> dict:
    r = httpx.get(f"https://archive.org/metadata/{ident}", timeout=60, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.json()


def fetch_page(ident: str, meta: dict, n: int, width: int = 1600) -> Path | None:
    out = RAW / ident / f"{n:06d}.jpg"
    if out.exists():
        return out
    server, d = meta["server"], meta["dir"]
    url = (f"https://{server}/BookReader/BookReaderImages.php?id={ident}"
           f"&itemPath={d}&server={server}&page=n{n}_w{width}.jpg")
    r = httpx.get(url, timeout=90, headers={"User-Agent": UA}, follow_redirects=True)
    time.sleep(DELAY)
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    out.with_suffix(".json").write_text(json.dumps(
        {"source": "Internet Archive", "identifier": ident, "page_index": n, "url": url,
         "title": meta.get("metadata", {}).get("title"),
         "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False))
    return out


def looks_tabular(path: Path) -> tuple[int, int]:
    im = Image.open(path).convert("L")
    x0, x1 = round(PROBE_X_FRAC[0] * im.width), round(PROBE_X_FRAC[1] * im.width)
    thr = ink_threshold(im, (x0, 0, x1, im.height))
    h = im.height
    rules = max(n_vertical_rules(im, thr, int(a * h), int(b * h))
                for a, b in ((0.15, 0.50), (0.30, 0.65), (0.45, 0.80), (0.55, 0.92)))
    run, _ = table_score(path)
    return run, rules


def main() -> None:
    ident = sys.argv[1]
    pages = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else list(range(2, 30, 2))
    meta = item_meta(ident)
    m = meta.get("metadata", {})
    print(f"{m.get('title')}  |  {m.get('imagecount')} pages  |  restricted={m.get('access-restricted-item')}")
    hits = []
    for n in pages:
        p = fetch_page(ident, meta, n)
        if p is None:
            print(f"  n{n}: unavailable")
            continue
        run, rules = looks_tabular(p)
        is_table = run >= 18 and rules >= 4
        print(f"  n{n}: {run} regular rows, {rules} vertical rules"
              + ("   <-- TABLE" if is_table else ""), flush=True)
        if is_table:
            hits.append({"page": n, "rows": run, "rules": rules})
    out = ROOT / "bench" / "g4" / f"ia-{ident}.json"
    out.write_text(json.dumps({"identifier": ident, "title": m.get("title"), "candidates": hits}, indent=1))
    print(f"{len(hits)} candidate tables -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
