import json
from datetime import datetime, timezone
from pathlib import Path


class PageCache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, source: str, doc: str, page: int) -> Path:
        return self.root / source / doc / f"{page:06d}.jpg"

    def path(self, source: str, doc: str, page: int) -> Path:
        return self._path(source, doc, page)

    def get(self, source: str, doc: str, page: int) -> bytes | None:
        p = self._path(source, doc, page)
        return p.read_bytes() if p.exists() else None

    def put(self, source: str, doc: str, page: int, content: bytes, meta: dict) -> Path:
        p = self._path(source, doc, page)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        meta = {**meta, "fetched_at": datetime.now(timezone.utc).isoformat()}
        p.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        return p
