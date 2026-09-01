import json
from pathlib import Path

class CapExceeded(RuntimeError):
    pass

class CostMeter:
    def __init__(self, cap_usd: float = 10.0, ledger: Path = Path("data/ledger.json")):
        self.cap, self.ledger = cap_usd, Path(ledger)
        self.items = json.loads(self.ledger.read_text()) if self.ledger.exists() else []

    def total(self) -> float:
        return sum(i["usd"] for i in self.items)

    def charge(self, desc: str, usd: float) -> None:
        if self.total() + usd > self.cap:
            raise CapExceeded(f"cap US${self.cap:.2f} would be exceeded by '{desc}' (US${usd:.4f}); spent US${self.total():.4f}")
        self.items.append({"desc": desc, "usd": usd})
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.ledger.write_text(json.dumps(self.items, indent=1))
