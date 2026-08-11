import base64
import hashlib
import re
from urllib.parse import quote

import httpx

from app.peppol.models import ParticipantIdentifier, SmlResult
from app.peppol.sources.base import request_with_rate_limit_retry, timeout_from_ms

NAPTR_REPLACEMENT_PATTERN = re.compile(r"!.*?!([^!]+)!")


def build_sml_query_name(participant: ParticipantIdentifier, dns_zone: str) -> str:
    normalized = participant.value.lower().encode("utf-8")
    digest = hashlib.sha256(normalized).digest()
    encoded_digest = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return f"{encoded_digest}.{participant.scheme}.{dns_zone}".lower()


def extract_smp_base_url(answers: list[dict[str, object]]) -> tuple[str | None, list[str]]:
    records: list[str] = []
    for answer in answers:
        data = str(answer.get("data", "")).strip('"')
        if not data:
            continue
        records.append(data)
        match = NAPTR_REPLACEMENT_PATTERN.search(data)
        if match:
            return match.group(1), records
        for token in data.split():
            if token.startswith("http://") or token.startswith("https://"):
                return token.strip('"'), records
    return None, records


class SmlDnsClient:
    def __init__(
        self,
        dns_zone: str,
        timeout_ms: int,
        source: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.dns_zone = dns_zone
        self.timeout = timeout_from_ms(timeout_ms)
        self.source = source
        self.client = client

    async def resolve(self, participant: ParticipantIdentifier) -> SmlResult:
        query_name = build_sml_query_name(participant, self.dns_zone)
        url = f"https://dns.google/resolve?name={quote(query_name)}&type=NAPTR"
        client = self.client or httpx.AsyncClient(timeout=self.timeout, trust_env=False)
        try:
            response = await request_with_rate_limit_retry(
                client,
                "GET",
                url,
                headers={"Accept": "application/dns-json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if self.client is None:
                await client.aclose()
        answers = payload.get("Answer") or []
        smp_base_url, records = extract_smp_base_url(answers)
        if not smp_base_url:
            raise httpx.HTTPStatusError(
                "NAPTR record not found",
                request=httpx.Request("GET", url),
                response=httpx.Response(404, request=httpx.Request("GET", url)),
            )
        return SmlResult(
            source=self.source,
            dnsZone=self.dns_zone,
            queryName=query_name,
            naptrRecords=records,
            smpBaseUrl=smp_base_url,
        )
