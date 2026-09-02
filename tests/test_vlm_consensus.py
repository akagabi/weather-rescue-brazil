"""Self-consistency consensus (G3 Task 1): every test here is respx-mocked -
no real API calls (see wrb/vlm.py's consensus_extract/_vote_cell/
_majority_vote_tables and the module note above them for the design
rationale: the model's own self-flag rate is ~0, so cross-run disagreement
is the external signal this mechanism surfaces)."""

import json

import httpx
import pytest
import respx

from wrb.costs import CapExceeded, CostMeter
from wrb.vlm import ENDPOINTS, G2BTable, consensus_extract

GEMINI_PROVIDER = "gemini-flash-full"


def _body(rows):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps({"rows": rows})}]}}]}


def _row(day, **cells):
    return {"day": day, "cells": cells, "flags": {}}


@respx.mock
def test_consensus_agreed_cell_kept_unflagged_disagreed_cell_flagged_uncertain(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")

    # 3 runs, single day-1 row: "tmax" agrees 2-of-3 (20.0); "precip" is a
    # 3-way split (10.0/20.0/30.0) -> no majority -> median (20.0) + flagged.
    responses = [
        httpx.Response(200, json=_body([_row(1, tmax=20.0, precip=10.0)])),
        httpx.Response(200, json=_body([_row(1, tmax=20.0, precip=20.0)])),
        httpx.Response(200, json=_body([_row(1, tmax=25.0, precip=30.0)])),
    ]
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(side_effect=responses)

    table = consensus_extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, day_count=1, n=3)

    assert isinstance(table, G2BTable)
    row = table.rows[0]
    assert row.cells["tmax"] == pytest.approx(20.0)
    assert "tmax" not in row.flags  # 2-of-3 agreement -> no disagreement flag

    assert row.cells["precip"] == pytest.approx(20.0)  # median of 10/20/30
    assert row.flags.get("precip") == "uncertain"


@respx.mock
def test_consensus_charges_meter_once_per_run(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(
        return_value=httpx.Response(200, json=_body([_row(1, tmax=20.0)])),
    )

    consensus_extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, day_count=1, n=3)

    assert len(meter.items) == 3


@respx.mock
def test_consensus_sends_temperature_on_every_call(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    route = respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(
        return_value=httpx.Response(200, json=_body([_row(1, tmax=20.0)])),
    )

    consensus_extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, day_count=1, n=3, temperature=0.9)

    assert route.call_count == 3
    for call in route.calls:
        sent = json.loads(call.request.content)
        assert sent["generationConfig"]["temperature"] == pytest.approx(0.9)


@respx.mock
def test_consensus_proceeds_when_one_of_three_runs_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    responses = [
        httpx.Response(500, json={"error": "boom"}),  # one run fails outright
        httpx.Response(200, json=_body([_row(1, tmax=20.0)])),
        httpx.Response(200, json=_body([_row(1, tmax=20.0)])),
    ]
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(side_effect=responses)

    table = consensus_extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, day_count=1, n=3)

    assert table.rows[0].cells["tmax"] == pytest.approx(20.0)
    # 2 successful runs still charged the ledger; the failed one did too
    # (charge-before-call happens inside extract() regardless of outcome).
    assert len(meter.items) == 3


@respx.mock
def test_consensus_raises_when_fewer_than_two_runs_succeed(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    meter = CostMeter(cap_usd=10.0, ledger=tmp_path / "ledger.json")
    responses = [
        httpx.Response(500, json={"error": "boom"}),
        httpx.Response(500, json={"error": "boom"}),
        httpx.Response(200, json=_body([_row(1, tmax=20.0)])),
    ]
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(side_effect=responses)

    with pytest.raises(RuntimeError):
        consensus_extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, day_count=1, n=3)


@respx.mock
def test_consensus_propagates_cap_exceeded_instead_of_swallowing_it(tmp_path, monkeypatch):
    monkeypatch.setenv("WRB_GEMINI_KEY", "test-personal-key-123")
    # A cap tiny enough that the 2nd of 3 calls busts it.
    from wrb.vlm import estimate_cost_usd
    per_call = estimate_cost_usd(GEMINI_PROVIDER)
    meter = CostMeter(cap_usd=per_call * 1.5, ledger=tmp_path / "ledger.json")
    respx.post(ENDPOINTS[GEMINI_PROVIDER]).mock(
        return_value=httpx.Response(200, json=_body([_row(1, tmax=20.0)])),
    )

    with pytest.raises(CapExceeded):
        consensus_extract(b"fake-image-bytes", GEMINI_PROVIDER, meter, day_count=1, n=3)


@respx.mock
def test_consensus_aligns_rows_by_day_not_list_position(tmp_path, monkeypatch):
    """If one run's rows list is missing a day (e.g. a dropped row before
    consensus_extract is even reached - here simulated directly since
    _parse_g2b_response would normally reject a short response against a
    fixed day_count, but consensus must still not silently misalign an
    uneven day set across runs), voting must key off `day`, not index."""
    from wrb.vlm import G2BRow, G2BTable, _majority_vote_tables

    t1 = G2BTable(rows=[G2BRow(day=1, cells={"tmax": 20.0}), G2BRow(day=2, cells={"tmax": 21.0})])
    t2 = G2BTable(rows=[G2BRow(day=2, cells={"tmax": 21.0})])  # day 1 missing from this run
    t3 = G2BTable(rows=[G2BRow(day=1, cells={"tmax": 20.0}), G2BRow(day=2, cells={"tmax": 21.0})])

    merged = _majority_vote_tables([t1, t2, t3])

    by_day = {r.day: r for r in merged.rows}
    assert by_day[1].cells["tmax"] == pytest.approx(20.0)
    assert by_day[2].cells["tmax"] == pytest.approx(21.0)
