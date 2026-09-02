#!/usr/bin/env python3
"""G3 Task 2a corpus-scope discovery (R$0, no paid VLM).

Two jobs, both against the CAPTCHA-free DocVirt page-image API
(GET https://api.docvirt.com/v1/documents/obnacional/{docId}/{page}):

  1. TABLE DISCOVERY in docId 14 (Revista do Observatório, Tomo I). The
     9 frozen gold sheets already anchor the daily-table SCAN page for
     Dec 1885 + Jan/Feb/Mar/Apr/May/Jul/Sep/Nov 1886. This fetches the
     candidate windows where the three un-anchored months (Jun/Aug/Oct
     1886) and any Dec-1886 table should fall, plus the volume tail, so a
     human (Read-tool vision, free) can pin each remaining table page.

  2. NEIGHBOUR PROBE: fetch page 1 of docIds 1..30 to map what else lives
     in the "obnacional" acervo and whether any is a second/third Revista
     tomo. Page-not-found comes back as HTTP 422 {"documentnotfound"}.

Rate-limited (>=2s), sequential, cache-aware (no re-fetch), identifying UA.
Prints a JSON report to stdout. Fetched images land in data/raw/docvirt/.
"""

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from wrb.cache import PageCache  # noqa: E402
from wrb.fetch_static import StaticFetcher  # noqa: E402

DATA_ROOT = ROOT / "data" / "raw"
COLLECTION = "obnacional"
ATTRIBUTION = "Biblioteca Digital de Obras Raras do Observatório Nacional"


def url_for(doc_id: str, page: int) -> str:
    return f"https://api.docvirt.com/v1/documents/{COLLECTION}/{doc_id}/{page}"


def fetch_one(fetcher: StaticFetcher, doc_id: str, page: int) -> dict:
    """Fetch one page; classify outcome. Returns a small result dict."""
    url = url_for(doc_id, page)
    cached = fetcher.cache.get("docvirt", doc_id, page, ext="webp")
    if cached is not None:
        return {"doc": doc_id, "page": page, "status": "cached", "bytes": len(cached)}
    try:
        p = fetcher.fetch("docvirt", doc_id, page, url, ext="webp", attribution=ATTRIBUTION)
        return {"doc": doc_id, "page": page, "status": "ok", "bytes": p.stat().st_size}
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = e.response.json().get("mensagem", "")
        except Exception:
            body = e.response.text[:80]
        return {"doc": doc_id, "page": page, "status": f"http_{e.response.status_code}", "msg": body}
    except Exception as e:  # noqa: BLE001
        return {"doc": doc_id, "page": page, "status": "error", "msg": str(e)[:120]}


def discover_tables(fetcher: StaticFetcher) -> list[dict]:
    # Candidate SCAN-page windows for the tables not anchored by gold.
    # Interpolated from the gold anchors (see docstring). Wide enough to
    # bracket the real page but small enough to stay polite.
    windows = {
        "jun_1886": range(127, 137),   # between May(109) and Jul(142)
        "aug_1886": range(155, 167),   # between Jul(142) and Sep(179)
        "oct_1886": range(192, 202),   # between Sep(179) and Nov(212)
        "tail":     range(213, 218),   # end of volume + first 422
    }
    out = []
    for label, rng in windows.items():
        for page in rng:
            r = fetch_one(fetcher, "14", page)
            r["window"] = label
            out.append(r)
            print(f"  [tables/{label}] 14/{page}: {r['status']} {r.get('bytes', r.get('msg',''))}")
    return out


def probe_neighbours(fetcher: StaticFetcher) -> list[dict]:
    out = []
    for doc_id in range(1, 31):
        r = fetch_one(fetcher, str(doc_id), 1)
        out.append(r)
        print(f"  [neighbour] doc {doc_id}/1: {r['status']} {r.get('bytes', r.get('msg',''))}")
    return out


if __name__ == "__main__":
    cache = PageCache(DATA_ROOT)
    fetcher = StaticFetcher(cache, delay_s=2.0)
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    report: dict = {}
    if mode in ("tables", "all"):
        print("=== docId 14 table-window discovery ===")
        report["tables"] = discover_tables(fetcher)
    if mode in ("neighbours", "all"):
        print("=== neighbour docId probe (1..30, page 1) ===")
        report["neighbours"] = probe_neighbours(fetcher)
    print("\n=== JSON ===")
    print(json.dumps(report, ensure_ascii=False, indent=1))
