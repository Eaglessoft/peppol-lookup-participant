import asyncio
from urllib.parse import quote

import httpx

from app.peppol.codelists.evaluator import CodeListEvaluator
from app.peppol.models import ParticipantIdentifier, SmpResult
from app.peppol.parsers.service_group import parse_service_group
from app.peppol.parsers.service_metadata import parse_service_metadata
from app.peppol.sources.base import timeout_from_ms


class SmpClient:
    def __init__(self, base_url: str, timeout_ms: int, codelists: CodeListEvaluator) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_from_ms(timeout_ms)
        self.codelists = codelists

    async def lookup(
        self, participant: ParticipantIdentifier, include_raw: bool, raw_max_bytes: int
    ) -> SmpResult:
        participant_path = quote(participant.compact, safe="")
        service_group_url = f"{self.base_url}/{participant_path}"

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            group_response = await client.get(
                service_group_url, headers={"Accept": "application/xml"}
            )
            group_response.raise_for_status()
            service_group, document_refs = parse_service_group(group_response.text)
            document_ref_urls = service_group.get("documentReferenceUrls", {})

            async def fetch_service_metadata(document_ref: str):
                encoded_document = quote(document_ref, safe="")
                service_url = (
                    document_ref_urls.get(document_ref)
                    if isinstance(document_ref_urls, dict)
                    else None
                )
                if not service_url:
                    service_url = f"{service_group_url}/services/{encoded_document}"
                response = await client.get(service_url, headers={"Accept": "application/xml"})
                response.raise_for_status()
                return parse_service_metadata(
                    response.text,
                    document_ref,
                    self.codelists.evaluate_document_type(document_ref),
                    self.codelists.document_type_name(document_ref),
                    self.codelists.evaluate_process,
                    self.codelists.evaluate_transport_profile,
                    include_raw,
                    raw_max_bytes,
                )

            services = await asyncio.gather(
                *(fetch_service_metadata(document_ref) for document_ref in document_refs)
            )

        return SmpResult(baseUrl=self.base_url, serviceGroup=service_group, services=services)
