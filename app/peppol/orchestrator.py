from collections.abc import Awaitable, Callable, Iterable
from time import perf_counter
from typing import Any
from urllib.parse import quote

import httpx

from app.peppol.codelists.cache import CodeListCache
from app.peppol.codelists.client import CodeListClient
from app.peppol.codelists.evaluator import CodeListEvaluator
from app.peppol.models import (
    BusinessEntity,
    CodeListStatus,
    DetailLookupResponse,
    DocumentCapability,
    EnvironmentName,
    EnvironmentResult,
    IdentifierWithStatus,
    LightLookupResponse,
    LookupMode,
    ParticipantIdentifier,
    SourceResult,
    SourceStatus,
)
from app.peppol.parsers.business_card import business_entities_from_directory
from app.peppol.sources.base import measured_source
from app.peppol.sources.directory import DirectoryClient
from app.peppol.sources.openpeppol_lookup import OpenPeppolLookupClient
from app.peppol.sources.sml_dns import SmlDnsClient
from app.peppol.sources.smp import SmpClient
from app.shared.config import Settings


class LookupOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.codelists = CodeListEvaluator(settings.peppol_codelist_cache_dir)

    async def lookup(
        self,
        participant: ParticipantIdentifier,
        mode: LookupMode,
        environments: Iterable[str],
        sources: set[str],
        include_raw: bool,
        timeout_ms: int | None,
        refresh: bool = False,
    ) -> LightLookupResponse | DetailLookupResponse:
        effective_timeout = timeout_ms or self.settings.peppol_source_timeout_ms
        environment_results: list[EnvironmentResult] = []
        source_results: list[SourceResult] = []

        for environment in environments:
            env_result, env_sources = await self._lookup_environment(
                participant,
                EnvironmentName(environment),
                sources,
                include_raw and mode == LookupMode.detail,
                effective_timeout,
                refresh,
            )
            environment_results.append(env_result)
            source_results.extend(env_sources)

        if mode == LookupMode.light:
            return self._to_light(participant, environment_results)
        return self._to_detail(participant, environment_results, source_results)

    async def _lookup_environment(
        self,
        participant: ParticipantIdentifier,
        environment: EnvironmentName,
        sources: set[str],
        include_raw: bool,
        timeout_ms: int,
        refresh: bool,
    ) -> tuple[EnvironmentResult, list[SourceResult]]:
        source_results: list[SourceResult] = []
        directory = None
        sml = None
        smp = None
        lookup_service = None

        if "directory" in sources and not self.settings.peppol_directory_enabled:
            source_results.append(_disabled_source_result(f"{environment}:directory"))
        elif "directory" in sources:
            directory_url = (
                self.settings.peppol_directory_prod_url
                if environment == EnvironmentName.prod
                else self.settings.peppol_directory_test_url
            )
            source_name = f"{environment}:directory"
            directory, result = await self._cached_source(
                f"{source_name}:{participant.compact}:{directory_url}",
                lambda: measured_source(
                    source_name,
                    lambda: DirectoryClient(directory_url, timeout_ms).lookup(participant),
                ),
                refresh,
            )
            source_results.append(result)

        sml_source = "sml" if environment == EnvironmentName.prod else "smk"
        sml_requested = sml_source in sources or "sml" in sources or "smk" in sources
        if sml_requested and not self.settings.peppol_sml_enabled:
            source_results.append(_disabled_source_result(f"{environment}:{sml_source}"))
        elif sml_requested:
            dns_zone = (
                self.settings.peppol_sml_prod_dns_zone
                if environment == EnvironmentName.prod
                else self.settings.peppol_sml_test_dns_zone
            )
            source_name = f"{environment}:{sml_source}"
            sml, result = await self._cached_source(
                f"{source_name}:{participant.compact}:{dns_zone}",
                lambda: measured_source(
                    source_name,
                    lambda: SmlDnsClient(dns_zone, timeout_ms, sml_source).resolve(participant),
                ),
                refresh,
            )
            source_results.append(result)

        if "smp" in sources and not self.settings.peppol_smp_enabled:
            source_results.append(_disabled_source_result(f"{environment}:smp"))
        elif "smp" in sources and sml and sml.smpBaseUrl:
            source_name = f"{environment}:smp"
            smp, result = await self._cached_source(
                f"{source_name}:{participant.compact}:{sml.smpBaseUrl}:raw={include_raw}",
                lambda: measured_source(
                    source_name,
                    lambda: SmpClient(sml.smpBaseUrl or "", timeout_ms, self.codelists).lookup(
                        participant,
                        include_raw,
                        self.settings.peppol_include_raw_max_bytes,
                    ),
                ),
                refresh,
            )
            source_results.append(result)

        if (
            "lookup" in sources
            and environment == EnvironmentName.prod
            and not self.settings.peppol_lookup_service_enabled
        ):
            source_results.append(_disabled_source_result(f"{environment}:lookup"))
        elif "lookup" in sources and environment == EnvironmentName.prod:
            source_name = f"{environment}:lookup"
            lookup_service, result = await self._cached_source(
                f"{source_name}:{participant.compact}:{self.settings.peppol_lookup_service_url}",
                lambda: measured_source(
                    source_name,
                    lambda: OpenPeppolLookupClient(
                        self.settings.peppol_lookup_service_url, timeout_ms
                    ).lookup(participant),
                ),
                refresh,
            )
            source_results.append(result)

        found = any(
            result.status == SourceStatus.success
            for result in source_results
            if result.source.startswith(f"{environment}:")
        )
        return (
            EnvironmentResult(
                name=environment,
                status="found" if found else "not_found",
                sml=sml,
                smp=smp,
                directory=directory,
                lookupService=lookup_service,
                codeListEvaluation=self._code_list_evaluation(smp),
            ),
            source_results,
        )

    def _to_light(
        self, participant: ParticipantIdentifier, environments: list[EnvironmentResult]
    ) -> LightLookupResponse:
        entities: list[BusinessEntity] = []
        capabilities: list[DocumentCapability] = []
        seen_capabilities: set[tuple[str, str | None, str | None]] = set()

        for environment in environments:
            if environment.directory:
                entities.extend(business_entities_from_directory(environment.directory))
            if environment.smp:
                for service in environment.smp.services:
                    for process in service.processes:
                        for endpoint in process.endpoints or [None]:
                            key = (
                                service.documentTypeIdentifier.value,
                                process.processIdentifier.value,
                                endpoint.transportProfile if endpoint else None,
                            )
                            if key in seen_capabilities:
                                continue
                            seen_capabilities.add(key)
                            capabilities.append(
                                DocumentCapability(
                                    documentTypeIdentifier=service.documentTypeIdentifier,
                                    processIdentifier=process.processIdentifier,
                                    transportProfile=IdentifierWithStatus(
                                        value=endpoint.transportProfile,
                                        status=endpoint.transportProfileStatus,
                                    )
                                    if endpoint
                                    else None,
                                    serviceDescription=(
                                        endpoint.serviceDescription if endpoint else None
                                    ),
                                    technicalContactUrl=(
                                        endpoint.technicalContactUrl if endpoint else None
                                    ),
                                    technicalInformationUrl=endpoint.technicalInformationUrl
                                    if endpoint
                                    else None,
                                )
                            )

        return LightLookupResponse(
            participantIdentifier=participant,
            businessEntities=entities,
            documentCapabilities=capabilities,
        )

    def _to_detail(
        self,
        participant: ParticipantIdentifier,
        environments: list[EnvironmentResult],
        source_results: list[SourceResult],
    ) -> DetailLookupResponse:
        found_in = [
            source.source
            for source in source_results
            if source.status == SourceStatus.success and not source.source.endswith(":lookup")
        ]
        not_found_in = [
            source.source for source in source_results if source.status == SourceStatus.not_found
        ]
        return DetailLookupResponse(
            input={
                "raw": participant.compact,
                "normalized": {
                    "scheme": participant.scheme,
                    "value": participant.value,
                    "icd": participant.icd,
                    "identifier": participant.local_identifier,
                },
            },
            summary={
                "exists": bool(found_in),
                "routable": any(source.endswith(":smp") for source in found_in),
                "foundIn": found_in,
                "notFoundIn": not_found_in,
                "warnings": _warnings(source_results),
            },
            environments=environments,
            sourceResults=source_results,
        )

    def sources(self) -> dict[str, Any]:
        source_cache = getattr(self, "source_cache", None)
        return {
            "environments": self.settings.peppol_lookup_environments,
            "sources": {
                "directory": {
                    "enabled": self.settings.peppol_directory_enabled,
                    "prod": self.settings.peppol_directory_prod_url,
                    "test": self.settings.peppol_directory_test_url,
                },
                "sml": {
                    "enabled": self.settings.peppol_sml_enabled,
                    "prod": self.settings.peppol_sml_prod_dns_zone,
                },
                "smk": {
                    "enabled": self.settings.peppol_sml_enabled,
                    "test": self.settings.peppol_sml_test_dns_zone,
                },
                "smp": {
                    "enabled": self.settings.peppol_smp_enabled,
                    "resolvedFrom": "sml/smk",
                },
                "lookup": {
                    "enabled": self.settings.peppol_lookup_service_enabled,
                    "prod": self.settings.peppol_lookup_service_url,
                },
            },
            "cache": {
                "ttlSeconds": self.settings.peppol_cache_ttl_seconds,
                "sourceResults": source_cache.stats() if source_cache else None,
                "codeLists": self.codelists.metadata(),
            },
        }

    def _code_list_evaluation(self, smp: Any | None) -> dict[str, Any]:
        statuses = [status.value for status in CodeListStatus]
        result: dict[str, Any] = {
            "version": self.codelists._version(),
            "fetchedAt": self._latest_codelist_fetch_time(),
            "documentTypes": {status: 0 for status in statuses},
            "processes": {status: 0 for status in statuses},
            "transportProfiles": {status: 0 for status in statuses},
        }
        if not smp:
            return result

        for service in smp.services:
            result["documentTypes"][service.documentTypeIdentifier.status.value] += 1
            for process in service.processes:
                result["processes"][process.processIdentifier.status.value] += 1
                for endpoint in process.endpoints:
                    result["transportProfiles"][endpoint.transportProfileStatus.value] += 1
        return result

    def _latest_codelist_fetch_time(self) -> str | None:
        fetched_times = [
            cached.fetched_at for cached in self.codelists.loaded_from_cache.values()
        ]
        return max(fetched_times) if fetched_times else None

    async def check_source_health(self) -> dict[str, Any]:
        checks = [
            (
                "prod:directory",
                self.settings.peppol_directory_prod_url,
                self.settings.peppol_directory_enabled,
            ),
            (
                "test:directory",
                self.settings.peppol_directory_test_url,
                self.settings.peppol_directory_enabled,
            ),
            (
                "prod:lookup",
                self.settings.peppol_lookup_service_url,
                self.settings.peppol_lookup_service_enabled,
            ),
            (
                "prod:sml",
                _dns_health_url(self.settings.peppol_sml_prod_dns_zone),
                self.settings.peppol_sml_enabled,
            ),
            (
                "test:smk",
                _dns_health_url(self.settings.peppol_sml_test_dns_zone),
                self.settings.peppol_sml_enabled,
            ),
        ]
        results = []
        timeout = self.settings.peppol_source_timeout_ms / 1000
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            for name, url, enabled in checks:
                if not enabled:
                    results.append(
                        {
                            "source": name,
                            "status": SourceStatus.disabled,
                            "durationMs": 0,
                            "url": url,
                        }
                    )
                    continue
                started = perf_counter()
                try:
                    response = await client.get(url)
                    status = (
                        SourceStatus.success
                        if response.status_code < 500
                        else SourceStatus.error
                    )
                    results.append(
                        {
                            "source": name,
                            "status": status,
                            "httpStatus": response.status_code,
                            "durationMs": int((perf_counter() - started) * 1000),
                            "url": url,
                        }
                    )
                except httpx.TimeoutException:
                    results.append(
                        {
                            "source": name,
                            "status": SourceStatus.timeout,
                            "durationMs": int((perf_counter() - started) * 1000),
                            "url": url,
                        }
                    )
                except httpx.HTTPError as exc:
                    results.append(
                        {
                            "source": name,
                            "status": SourceStatus.error,
                            "durationMs": int((perf_counter() - started) * 1000),
                            "url": url,
                            "error": str(exc),
                        }
                    )
        return {"status": "checked", "results": results, **self.sources()}

    async def refresh_codelists(self) -> dict[str, Any]:
        cache = CodeListCache(self.settings.peppol_codelist_cache_dir)
        client = CodeListClient(
            self.settings.peppol_codelist_source_url,
            cache,
            self.settings.peppol_source_timeout_ms,
        )
        refreshed = await client.refresh()
        self.codelists = CodeListEvaluator(self.settings.peppol_codelist_cache_dir)
        return {
            "status": "refreshed",
            "artifacts": [
                {
                    "name": item.name,
                    "path": str(item.path),
                    "checksum": item.checksum,
                    "fetchedAt": item.fetched_at,
                    "entryCount": item.payload.get("entry-count"),
                }
                for item in refreshed
            ],
            "codeLists": self.codelists.metadata(),
        }

    async def _cached_source[T](
        self,
        key: str,
        factory: Callable[[], Awaitable[tuple[T | None, SourceResult]]],
        refresh: bool,
    ) -> tuple[T | None, SourceResult]:
        source_cache = getattr(self, "source_cache", None)
        if source_cache is None:
            return await factory()
        return await source_cache.get_or_set(key, factory, refresh)

def _warnings(source_results: list[SourceResult]) -> list[str]:
    warnings: list[str] = []
    failed_sources = [
        source.source
        for source in source_results
        if source.status
        not in {SourceStatus.success, SourceStatus.not_found, SourceStatus.disabled}
    ]
    if failed_sources:
        warnings.append(f"Some sources failed: {', '.join(failed_sources)}")
    return warnings


def _disabled_source_result(source: str) -> SourceResult:
    return SourceResult(source=source, status=SourceStatus.disabled, durationMs=0)


def _dns_health_url(zone: str) -> str:
    return f"https://dns.google/resolve?name={quote(zone.rstrip('.'))}&type=NS"
