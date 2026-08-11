import asyncio
from urllib.parse import quote

import httpx

from app.peppol.codelists.evaluator import CodeListEvaluator
from app.peppol.models import ParticipantIdentifier, SmpResult
from app.peppol.parsers.service_group import parse_service_group
from app.peppol.parsers.service_metadata import parse_service_metadata
from app.peppol.sources.base import request_with_rate_limit_retry, timeout_from_ms

SMP_METADATA_CONCURRENCY = 4


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
            group_response = await request_with_rate_limit_retry(
                client, "GET", service_group_url, headers={"Accept": "application/xml"}
            )
            group_response.raise_for_status()
            service_group, document_refs = parse_service_group(group_response.text)
            document_ref_urls = service_group.get("documentReferenceUrls", {})
            semaphore = asyncio.Semaphore(SMP_METADATA_CONCURRENCY)

            async def fetch_service_metadata(document_ref: str):
                encoded_document = quote(document_ref, safe="")
                service_url = (
                    document_ref_urls.get(document_ref)
                    if isinstance(document_ref_urls, dict)
                    else None
                )
                if not service_url:
                    service_url = f"{service_group_url}/services/{encoded_document}"
                try:
                    async with semaphore:
                        response = await request_with_rate_limit_retry(
                            client, "GET", service_url, headers={"Accept": "application/xml"}
                        )
                    response.raise_for_status()
                    service = parse_service_metadata(
                        response.text,
                        document_ref,
                        self.codelists.evaluate_document_type(document_ref),
                        self.codelists.document_type_name(document_ref),
                        self.codelists.evaluate_process,
                        self.codelists.evaluate_transport_profile,
                        include_raw,
                        raw_max_bytes,
                    )
                    return service, None
                except Exception as exc:
                    http_status = (
                        exc.response.status_code
                        if isinstance(exc, httpx.HTTPStatusError)
                        else None
                    )
                    return None, {
                        "documentTypeIdentifier": document_ref,
                        "url": service_url,
                        "httpStatus": http_status,
                        "error": str(exc) or type(exc).__name__,
                    }

            metadata_results = await asyncio.gather(
                *(fetch_service_metadata(document_ref) for document_ref in document_refs)
            )
            services = [service for service, failure in metadata_results if service is not None]
            failures = [failure for service, failure in metadata_results if failure is not None]

        return SmpResult(
            baseUrl=self.base_url,
            serviceGroup=service_group,
            services=services,
            metadataStatus="partial" if failures else "complete",
            metadataTotal=len(document_refs),
            metadataSuccessful=len(services),
            metadataFailed=len(failures),
            metadataFailures=failures,
        )
