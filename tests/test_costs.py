import pytest
from pathlib import Path
from wrb.costs import CostMeter, CapExceeded

def test_cap_enforced(tmp_path: Path):
    m = CostMeter(cap_usd=1.00, ledger=tmp_path / "ledger.json")
    m.charge("call a", 0.60)
    with pytest.raises(CapExceeded):
        m.charge("call b", 0.60)
    m2 = CostMeter(cap_usd=1.00, ledger=tmp_path / "ledger.json")  # persists across runs
    assert m2.total() == pytest.approx(0.60)
