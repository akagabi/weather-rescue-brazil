"""HTTP layer for the transcription workbench (see wrb.workbench).

    python -m wrb.serve          ->  http://127.0.0.1:8765

Binds to localhost only: this is a personal tool over local images, not a
service.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

from wrb import profile as prof
from wrb import workbench as wb

ROOT = Path(__file__).resolve().parents[2]
UI = Path(__file__).resolve().parent / "workbench.html"

app = FastAPI(title="Weather Rescue Brazil — workbench")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return UI.read_text()


@app.get("/api/profiles")
def profiles() -> JSONResponse:
    out = []
    for pid in prof.available():
        p = prof.load(pid)
        out.append({"id": p.id, "name": p.name, "source": p.source, "notes": p.notes,
                    "rows_per_page": p.rows_per_page, "n_cells": p.n_cells,
                    "columns": [{"key": c.key, "label": c.label, "kind": c.kind,
                                 "unit": c.unit, "range": list(c.range) if c.range else None}
                                for c in p.columns],
                    "labelled": wb.label_stats(p.id)})
    return JSONResponse(out)


@app.get("/api/docs")
def docs() -> JSONResponse:
    out = []
    for d in sorted((wb.RAW).glob("*")):
        if d.is_dir():
            pages = wb.discover_pages(d.name)
            if pages:
                out.append({"doc": d.name, "n_pages": len(pages), "pages": pages})
    return JSONResponse({"docs": out, "periods": wb.known_periods()})


@app.get("/api/page")
def page(profile: str, doc: str, page: int, period: str) -> JSONResponse:
    try:
        p = prof.load(profile)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    st = wb.page_state(profile, doc, page, period)
    labels = wb.load_labels(profile, doc, page)
    return JSONResponse({
        "doc": doc, "page": page, "period": period, "profile": profile,
        "expected_rows": p.expected_rows(period), "found_rows": len(st.boxes),
        "located": st.ok, "reason": st.reason, "skew": st.skew,
        "rows": [{"index": i, "crop": f"/api/crop?profile={profile}&doc={doc}&page={page}&period={period}&row={i}"}
                 for i in range(len(st.boxes))],
        "labels": labels.get("rows", {}),
    })


@app.get("/api/crop")
def crop(profile: str, doc: str, page: int, period: str, row: int) -> Response:
    st = wb.page_state(profile, doc, page, period)
    if row >= len(st.boxes):
        raise HTTPException(404, "row out of range")
    return Response(wb.row_crop_png(doc, page, st.boxes[row], st.skew),
                    media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.post("/api/labels")
async def put_labels(payload: dict) -> JSONResponse:
    for k in ("profile", "doc", "page", "rows"):
        if k not in payload:
            raise HTTPException(400, f"missing {k}")
    p = prof.load(payload["profile"])
    data = wb.load_labels(payload["profile"], payload["doc"], int(payload["page"]))
    data.setdefault("rows", {}).update({str(k): v for k, v in payload["rows"].items()})
    data["profile"] = p.id
    data["period"] = payload.get("period", data.get("period"))
    wb.save_labels(payload["profile"], payload["doc"], int(payload["page"]), data)
    return JSONResponse({"saved": True, "stats": wb.label_stats(p.id)})


@app.post("/api/validate")
async def validate(payload: dict) -> JSONResponse:
    """Physical-range QC from the profile, for the row being typed."""
    p = prof.load(payload["profile"])
    values = {}
    for k, v in (payload.get("values") or {}).items():
        if v in (None, ""):
            values[k] = None
            continue
        col = p.column(k)
        try:
            values[k] = v if col.kind == "text" else float(str(v).replace(",", "."))
        except ValueError:
            values[k] = None
    return JSONResponse({"violations": p.violations(values)})


@app.post("/api/train")
async def train(payload: dict) -> JSONResponse:
    return JSONResponse(wb.start_training(payload["profile"], payload.get("run", "workbench"),
                                          int(payload.get("epochs", 2))))


@app.get("/api/train")
def train_status() -> JSONResponse:
    return JSONResponse(wb.training_status())


def main() -> None:
    import uvicorn
    print("workbench: http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
