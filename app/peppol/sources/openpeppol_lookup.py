import httpx

from app.peppol.models import ParticipantIdentifier
from app.peppol.sources.base import request_with_rate_limit_retry, timeout_from_ms


class OpenPeppolLookupClient:
    def __init__(self, base_url: str, timeout_ms: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_from_ms(timeout_ms)

    async def lookup(self, participant: ParticipantIdentifier) -> dict[str, object]:
        url = f"{self.base_url}/lookup"
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await request_with_rate_limit_retry(
                client,
                "POST",
                url,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={"identifier": participant.compact},
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "json" not in content_type:
                raise ValueError("OpenPeppol Lookup Service did not return JSON")
            payload: object = response.json()
        if not isinstance(payload, dict):
            raise ValueError("OpenPeppol Lookup Service returned invalid JSON")
        if payload.get("exists") is False:
            raise httpx.HTTPStatusError(
                str(payload.get("message") or "OpenPeppol Lookup participant not found"),
                request=httpx.Request("POST", url),
                response=httpx.Response(404, request=httpx.Request("POST", url)),
            )
        return {
            "source": "openpeppol-lookup",
            "baseUrl": self.base_url,
            "status": "success",
            "payload": payload,
        }
