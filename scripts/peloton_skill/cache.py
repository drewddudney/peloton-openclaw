from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CACHE_TTL_SECONDS = 15 * 60


class FileCache:
    def __init__(self, namespace: str):
        self.path = Path.home() / ".openclaw" / "cache" / "peloton"
        self.path.mkdir(parents=True, exist_ok=True)
        self.namespace = namespace

    def _file_path(self, key: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in key)
        return self.path / f"{self.namespace}-{safe}.json"

    def get(self, key: str, ttl_seconds: int = CACHE_TTL_SECONDS) -> Any | None:
        path = self._file_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None

        cached_at = payload.get("cached_at")
        if not cached_at:
            return None
        age = datetime.now(timezone.utc).timestamp() - float(cached_at)
        if age > ttl_seconds:
            return None
        return payload.get("data")

    def set(self, key: str, data: Any) -> None:
        path = self._file_path(key)
        payload = {
            "cached_at": datetime.now(timezone.utc).timestamp(),
            "data": data,
        }
        path.write_text(json.dumps(payload))

    def invalidate_contains(self, text: str) -> None:
        needle = text.lower()
        for path in self.path.glob(f"{self.namespace}-*.json"):
            if needle in path.name.lower():
                path.unlink(missing_ok=True)
