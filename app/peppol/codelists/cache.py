import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CachedCodeList:
    name: str
    payload: dict[str, Any]
    path: Path
    checksum: str
    fetched_at: str | None


class CodeListCache:
    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = Path(cache_dir)

    def path_for(self, name: str) -> Path:
        return self.cache_dir / f"{name}.json"

    def read(self, name: str) -> CachedCodeList | None:
        path = self.path_for(name)
        if not path.exists():
            return None
        content = path.read_bytes()
        payload = json.loads(content.decode("utf-8"))
        return CachedCodeList(
            name=name,
            payload=payload,
            path=path,
            checksum=hashlib.sha256(content).hexdigest(),
            fetched_at=payload.get("_cache", {}).get("fetchedAt"),
        )

    def write(self, name: str, payload: dict[str, Any], source_url: str) -> CachedCodeList:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached_payload = {
            **payload,
            "_cache": {
                "fetchedAt": datetime.now(UTC).isoformat(),
                "sourceUrl": source_url,
            },
        }
        content = json.dumps(cached_payload, indent=2, sort_keys=True).encode("utf-8")
        path = self.path_for(name)
        path.write_bytes(content)
        return CachedCodeList(
            name=name,
            payload=cached_payload,
            path=path,
            checksum=hashlib.sha256(content).hexdigest(),
            fetched_at=cached_payload["_cache"]["fetchedAt"],
        )
