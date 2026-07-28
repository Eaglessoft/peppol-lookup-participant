import re
from urllib.parse import quote

import httpx

from app.peppol.models import DirectoryResult, ParticipantIdentifier
from app.peppol.sources.base import request_with_rate_limit_retry, timeout_from_ms

PARTICIPANT_VALUE_PATTERN = re.compile(r"^(?:iso6523-actorid-upis::)?[A-Za-z0-9]{4}:.+")


class DirectoryClient:
    def __init__(self, base_url: str, timeout_ms: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_from_ms(timeout_ms)

    async def lookup(self, participant: ParticipantIdentifier) -> DirectoryResult:
        encoded_participant = quote(participant.compact, safe="")
        urls = [
            (f"{self.base_url}/businesscard/{encoded_participant}", False),
            (f"{self.base_url}/api/businesscard/{encoded_participant}", False),
            (f"{self.base_url}/search/1.0/json?q={encoded_participant}", True),
        ]
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            last_response: httpx.Response | None = None
            for url, exact_required in urls:
                response = await request_with_rate_limit_retry(
                    client, "GET", url, headers={"Accept": "application/json"}
                )
                last_response = response
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                payload = response.json()
                if not _payload_has_match(payload):
                    continue
                if exact_required and not _payload_has_exact_participant(payload, participant):
                    continue
                if exact_required:
                    payload = _filter_payload_to_participant(payload, participant)
                return DirectoryResult(baseUrl=self.base_url, found=True, businessCard=payload)
            if last_response is not None:
                raise httpx.HTTPStatusError(
                    "Directory participant not found",
                    request=last_response.request,
                    response=httpx.Response(404, request=last_response.request),
                )
        return DirectoryResult(baseUrl=self.base_url, found=False, businessCard=None)

    async def search(self, query: str) -> DirectoryResult:
        encoded_query = quote(query.strip(), safe="")
        url = f"{self.base_url}/search/1.0/json?q={encoded_query}"
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await request_with_rate_limit_retry(
                client, "GET", url, headers={"Accept": "application/json"}
            )
            if response.status_code == 404:
                raise httpx.HTTPStatusError(
                    "Directory search not found",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            payload = response.json()
            if not _payload_has_match(payload):
                raise httpx.HTTPStatusError(
                    "Directory search not found",
                    request=response.request,
                    response=httpx.Response(404, request=response.request),
                )
            return DirectoryResult(baseUrl=self.base_url, found=True, businessCard=payload)


def _payload_has_match(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    total_result_count = payload.get("total-result-count")
    if isinstance(total_result_count, int):
        return total_result_count > 0
    matches = payload.get("matches")
    if isinstance(matches, list):
        return len(matches) > 0
    return True


def _payload_has_exact_participant(payload: object, participant: ParticipantIdentifier) -> bool:
    expected = {participant.value.lower(), participant.compact.lower()}
    return any(value.lower() in expected for value in _participant_values(payload))


def participant_values_from_directory(payload: object) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for value in _participant_values(payload, participant_fields_only=True):
        normalized = value.replace("iso6523-actorid-upis::", "")
        if not _looks_like_participant_value(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return values


def _filter_payload_to_participant(payload: object, participant: ParticipantIdentifier) -> object:
    if not isinstance(payload, dict):
        return payload
    matches = payload.get("matches")
    if not isinstance(matches, list):
        return payload

    expected = {participant.value.lower(), participant.compact.lower()}
    filtered = [
        item
        for item in matches
        if any(value.lower() in expected for value in _participant_values(item))
    ]
    if not filtered:
        return payload
    return {
        **payload,
        "total-result-count": len(filtered),
        "used-result-count": len(filtered),
        "matches": filtered,
    }


def _participant_values(value: object, participant_fields_only: bool = False) -> list[str]:
    if isinstance(value, str):
        return [value.strip()]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_participant_values(item, participant_fields_only))
        return values
    if not isinstance(value, dict):
        return []

    values = []
    if (
        not participant_fields_only
        and isinstance(value.get("scheme"), str)
        and isinstance(value.get("value"), str)
    ):
        values.append(f"{value['scheme']}::{value['value']}")
        values.append(value["value"])
    for key in ("participantID", "participantId", "participantIdentifier", "id"):
        if key in value:
            values.extend(_participant_values(value[key], False))
    for child in value.values():
        if isinstance(child, (list, dict)):
            values.extend(_participant_values(child, participant_fields_only))
    return values


def _looks_like_participant_value(value: str) -> bool:
    return bool(PARTICIPANT_VALUE_PATTERN.match(value.strip()))
