import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from app.peppol.codelists.cache import CachedCodeList, CodeListCache
from app.peppol.sources.base import timeout_from_ms


@dataclass(frozen=True)
class CodeListArtifact:
    name: str
    url: str


def default_artifacts(source_url: str) -> list[CodeListArtifact]:
    base = source_url.rstrip("/")
    version = _version_from_source_url(base) or "9.6"
    version_path = f"{base}/v{version}"
    return artifacts_for_version(base, version, version_path)


def artifacts_for_version(
    base_url: str, version: str, version_path: str | None = None
) -> list[CodeListArtifact]:
    base = base_url.rstrip("/")
    version_path = version_path or f"{base}/v{version}"
    return [
        CodeListArtifact(
            "participant_identifier_schemes",
            f"{version_path}/Peppol%20Code%20Lists%20-%20Participant%20identifier%20schemes%20v{version}.json",
        ),
        CodeListArtifact(
            "document_types",
            f"{version_path}/Peppol%20Code%20Lists%20-%20Document%20types%20v{version}.json",
        ),
        CodeListArtifact(
            "processes",
            f"{version_path}/Peppol%20Code%20Lists%20-%20Processes%20v{version}.json",
        ),
        CodeListArtifact(
            "transport_profiles",
            f"{version_path}/Peppol%20Code%20Lists%20-%20Transport%20profiles%20v{version}.json",
        ),
    ]


def _version_from_source_url(source_url: str) -> str | None:
    match = re.search(r"/v(\d+\.\d+)(?:/)?$", source_url)
    return match.group(1) if match else None


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


class CodeListClient:
    def __init__(self, source_url: str, cache: CodeListCache, timeout_ms: int) -> None:
        self.source_url = source_url
        self.cache = cache
        self.timeout = timeout_from_ms(timeout_ms)

    async def refresh(self) -> list[CachedCodeList]:
        refreshed: list[CachedCodeList] = []
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            artifacts = await self._current_artifacts(client)
            for artifact in artifacts:
                response = await client.get(artifact.url, headers={"Accept": "application/json"})
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("values"), list):
                    raise ValueError(f"Invalid codelist payload for {artifact.name}")
                refreshed.append(self.cache.write(artifact.name, payload, artifact.url))
        return refreshed

    async def _current_artifacts(self, client: httpx.AsyncClient) -> list[CodeListArtifact]:
        base = self.source_url.rstrip("/")
        pinned_version = _version_from_source_url(base)
        if pinned_version:
            return artifacts_for_version(base.rsplit("/", 1)[0], pinned_version, base)

        try:
            response = await client.get(base, headers={"Accept": "text/html,application/json"})
            response.raise_for_status()
        except httpx.HTTPError:
            return default_artifacts(base)

        versions = sorted(
            set(re.findall(r"v(\d+\.\d+)", response.text)),
            key=_version_key,
            reverse=True,
        )
        if not versions:
            return default_artifacts(base)

        version = versions[0]
        version_path = urljoin(f"{base}/", f"v{version}")
        return artifacts_for_version(base, version, version_path)
