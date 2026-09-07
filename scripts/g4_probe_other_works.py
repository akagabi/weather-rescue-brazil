"""Look for ruled tables in OTHER publications on DocVirt (docIds 1-13).

Every layout tested so far lives in one publication, the Revista do
Observatorio. A table from a different work would close the last gap in the
generality claim. This probes a spread of pages per document and runs the free
row-periodicity detector on each; nothing paid, nothing CAPTCHA-gated.

Polite by construction: sequential, >=2 s apart, project User-Agent, and it
stops on a document as soon as the API says the page does not exist (422).
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PIL import Image  # noqa: E402
from wrb.rows import PROBE_X_FRAC, find_peaks, ink_threshold, pitch_candidates, row_profile  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "docvirt"
URL = "https://api.docvirt.com/v1/documents/obnacional/{doc}/{page}"
UA = "WeatherRescueBrazil/0.1 (open climate data rescue; contact: gabesuit@gmail.com)"
DELAY = 2.0


def fetch(doc: str, page: int) -> Path | None:
    out = RAW / doc / f"{page:06d}.webp"
    if out.exists():
        return out
    r = httpx.get(URL.format(doc=doc, page=page), timeout=60, headers={"User-Agent": UA})
    time.sleep(DELAY)
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    out.with_suffix(".json").write_text(json.dumps(
        {"url": URL.format(doc=doc, page=page), "doc": doc, "page": page,
         "attribution": "Biblioteca Digital de Obras Raras do Observatório Nacional",
         "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False))
    return out


def table_score(path: Path) -> tuple[int, float]:
    """Longest run of evenly spaced text rows - a cheap free table detector."""
    im = Image.open(path).convert("L")
    w, h = im.size
    x0, x1 = round(PROBE_X_FRAC[0] * w), round(PROBE_X_FRAC[1] * w)
    thr = ink_threshold(im, (x0, 0, x1, h))
    prof, _ = row_profile(im, x0, x1, thr)
    best = (0, 0.0)
    for pitch in pitch_candidates(prof)[:3]:
        ys = [y for y, _ in find_peaks(prof, pitch)]
        run = cur = 1
        for i in range(1, len(ys)):
            cur = cur + 1 if 0.8 * pitch <= ys[i] - ys[i - 1] <= 1.2 * pitch else 1
            run = max(run, cur)
        if run > best[0]:
            best = (run, pitch)
    return best


def main() -> None:
    docs = sys.argv[1].split(",") if len(sys.argv) > 1 else [str(i) for i in range(1, 14)]
    pages = [int(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else
                              ["15", "35", "55", "75", "95", "115", "135"])]
    hits = []
    for doc in docs:
        found = 0
        for pg in pages:
            p = fetch(doc, pg)
            if p is None:
                print(f"doc {doc} p{pg}: not available")
                continue
            run, pitch = table_score(p)
            found += 1
            flag = "  <-- TABLE?" if run >= 20 else ""
            print(f"doc {doc} p{pg}: {run} regular rows, pitch {pitch}{flag}", flush=True)
            if run >= 20:
                hits.append({"doc": doc, "page": pg, "rows": run, "pitch": pitch})
        if not found:
            print(f"doc {doc}: no pages fetched, skipping")
    out = ROOT / "bench" / "g4" / "other-works-probe.json"
    out.write_text(json.dumps({"probed_docs": docs, "pages": pages, "candidates": hits}, indent=1))
    print(f"\n{len(hits)} candidate table pages in other works -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
