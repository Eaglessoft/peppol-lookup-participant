import asyncio

from fastapi import HTTPException

from app.peppol.codelists.evaluator import CodeListEvaluator
from app.peppol.models import (
    CandidateResult,
    CompanyLookupResponse,
    DetailLookupResponse,
    DirectoryResult,
    EnvironmentName,
    LightLookupResponse,
    LookupMode,
    ParticipantIdentifier,
    SourceStatus,
)
from app.peppol.orchestrator import LookupOrchestrator
from app.peppol.sources.base import measured_source
from app.peppol.sources.directory import DirectoryClient, participant_values_from_directory


class CompanyLookupService:
    def __init__(self, orchestrator: LookupOrchestrator, codelists: CodeListEvaluator) -> None:
        self.orchestrator = orchestrator
        self.codelists = codelists

    async def lookup(
        self,
        country: str,
        identifier: str,
        identifier_type: str | None,
        mode: LookupMode,
        environments: list[EnvironmentName],
        max_candidates: int,
        refresh: bool = False,
    ) -> CompanyLookupResponse:
        country = country.strip().upper()
        candidates = self.codelists.participant_candidate_evaluations(
            country, identifier, identifier_type, max_candidates
        )
        candidate_results: list[CandidateResult] = []
        matches: list[LightLookupResponse | DetailLookupResponse] = []
        explicit_scheme_code = _explicit_scheme_code(identifier_type, self.codelists)
        directory_matches = (
            []
            if explicit_scheme_code
            else await self._directory_identifier_search(
                country, identifier, environments, refresh
            )
        )
        directory_participant_values = _directory_participant_values(
            directory_matches, explicit_scheme_code
        )
        lookup_values = _unique_participant_values(
            (
                participant_value
                for _, participant_value, validation in candidates
                if validation.valid
            ),
            directory_participant_values,
        )
        candidate_by_value = {
            participant_value: (scheme, validation)
            for scheme, participant_value, validation in candidates
        }

        for scheme, participant_value, validation in candidates:
            if validation.valid or mode != LookupMode.detail:
                continue
            participant = ParticipantIdentifier(value=participant_value)
            candidate_results.append(
                CandidateResult(
                    participantIdentifier=participant,
                    country=country,
                    schemeCode=scheme.code,
                    schemeName=scheme.name,
                    schemeStatus=scheme.status,
                    validationStatus=validation.status,
                    rejectionReason=validation.reason,
                    warnings=_scheme_country_warnings(scheme.countries, country),
                )
            )

        concurrency = max(1, self.orchestrator.settings.peppol_company_lookup_concurrency)
        semaphore = asyncio.Semaphore(concurrency)

        async def lookup_participant_value(
            participant_value: str,
        ) -> tuple[CandidateResult, LightLookupResponse | DetailLookupResponse | None]:
            async with semaphore:
                return await lookup_participant_value_unlocked(participant_value)

        async def lookup_participant_value_unlocked(
            participant_value: str,
        ) -> tuple[CandidateResult, LightLookupResponse | DetailLookupResponse | None]:
            participant = ParticipantIdentifier(value=participant_value)
            candidate_metadata = candidate_by_value.get(participant_value)
            scheme = candidate_metadata[0] if candidate_metadata else None
            validation = candidate_metadata[1] if candidate_metadata else None

            environment_values = [environment.value for environment in environments]
            detail, directory_detail = await asyncio.gather(
                self.orchestrator.lookup(
                    participant=participant,
                    mode=LookupMode.detail,
                    environments=environment_values,
                    sources={"sml", "smk", "smp"},
                    include_raw=False,
                    timeout_ms=None,
                    refresh=refresh,
                ),
                self.orchestrator.lookup(
                    participant=participant,
                    mode=LookupMode.detail,
                    environments=environment_values,
                    sources={"directory"},
                    include_raw=False,
                    timeout_ms=None,
                    refresh=refresh,
                ),
            )
            detail = _merge_detail_responses(
                self.orchestrator, participant, detail, directory_detail
            )
            found_in = detail.summary.get("foundIn", [])
            confidence_score = _confidence_score(found_in)
            candidate_result = CandidateResult(
                participantIdentifier=participant,
                country=country,
                schemeCode=scheme.code if scheme else participant.icd or "unknown",
                schemeName=scheme.name if scheme else "Directory result",
                schemeStatus=scheme.status
                if scheme
                else self.codelists.evaluate_participant_scheme(participant.icd),
                validationStatus=validation.status if validation else "directory_candidate",
                found=bool(found_in),
                foundIn=found_in,
                confidenceScore=confidence_score,
                warnings=(
                    _scheme_country_warnings(scheme.countries, country)
                    + ([validation.reason] if validation and validation.reason else [])
                    if scheme
                    else []
                ),
                sourceResults=detail.sourceResults,
            )
            if not found_in:
                return candidate_result, None
            if mode == LookupMode.detail:
                return candidate_result, detail
            return candidate_result, self.orchestrator._to_light(participant, detail.environments)

        lookup_results = await asyncio.gather(
            *(lookup_participant_value(value) for value in sorted(lookup_values.values()))
        )
        for candidate_result, match in lookup_results:
            candidate_results.append(candidate_result)
            if match:
                matches.append(match)

        active_source_results = [
            source
            for candidate in candidate_results
            for source in candidate.sourceResults
            if source.status != SourceStatus.disabled
        ]
        if active_source_results and all(
            source.status == SourceStatus.timeout for source in active_source_results
        ):
            raise HTTPException(status_code=504, detail="all company lookup sources timed out")

        candidate_results.sort(key=lambda candidate: candidate.confidenceScore, reverse=True)
        matches.sort(key=_match_confidence_score, reverse=True)
        return CompanyLookupResponse(
            input={
                "country": country,
                "identifier": identifier,
                "identifierType": identifier_type,
            },
            candidates=candidate_results,
            matches=matches,
            directoryMatches=directory_matches if mode == LookupMode.detail else [],
        )

    async def _directory_identifier_search(
        self,
        country: str,
        identifier: str,
        environments: list[EnvironmentName],
        refresh: bool,
    ) -> list[DirectoryResult]:
        if not self.orchestrator.settings.peppol_directory_enabled:
            return []

        timeout_ms = self.orchestrator.settings.peppol_source_timeout_ms

        async def search_environment(environment: EnvironmentName) -> DirectoryResult | None:
            base_url = (
                self.orchestrator.settings.peppol_directory_prod_url
                if environment == EnvironmentName.prod
                else self.orchestrator.settings.peppol_directory_test_url
            )
            query = f"{country} {identifier}".strip()
            source_name = f"{environment}:directory-search"
            result, source_result = await self.orchestrator._cached_source(
                f"{source_name}:{query}:{base_url}",
                lambda: measured_source(
                    source_name,
                    lambda: self.orchestrator._with_source_limit(
                        "directory",
                        lambda: DirectoryClient(
                            base_url, timeout_ms, self.orchestrator.http_client
                        ).search(query),
                    ),
                ),
                refresh,
            )
            return result if result and source_result.status == "success" else None

        results = await asyncio.gather(*(search_environment(env) for env in environments))
        matches: list[DirectoryResult] = []
        seen_payloads: set[str] = set()
        for result in results:
            if not result:
                continue
            payload_key = str(result.businessCard)
            if payload_key in seen_payloads:
                continue
            seen_payloads.add(payload_key)
            matches.append(result)
        return matches


def _merge_detail_responses(
    orchestrator: LookupOrchestrator,
    participant: ParticipantIdentifier,
    primary: DetailLookupResponse,
    enrichment: DetailLookupResponse,
) -> DetailLookupResponse:
    enrichment_by_environment = {
        environment.name: environment for environment in enrichment.environments
    }
    for environment in primary.environments:
        enriched = enrichment_by_environment.get(environment.name)
        if not enriched:
            continue
        if enriched.directory:
            environment.directory = enriched.directory
        if enriched.lookupService:
            environment.lookupService = enriched.lookupService
    return orchestrator._to_detail(
        participant,
        primary.environments,
        [*primary.sourceResults, *enrichment.sourceResults],
    )


def _unique_participant_values(*groups: object) -> dict[str, str]:
    values: dict[str, str] = {}
    for group in groups:
        for value in group:
            values.setdefault(value.casefold(), value)
    return values


def _scheme_country_warnings(scheme_countries: tuple[str, ...], country: str) -> list[str]:
    if not scheme_countries or country in scheme_countries:
        return []
    return [
        f"Scheme country {', '.join(scheme_countries)} does not match requested country {country}"
    ]


def _confidence_score(found_in: list[str]) -> int:
    score = 0
    for source in found_in:
        if source.endswith(":smp"):
            score += 100
        elif source.endswith(":sml") or source.endswith(":smk"):
            score += 80
        elif source.endswith(":directory"):
            score += 50
        elif source.endswith(":lookup"):
            score += 30
    return score


def _explicit_scheme_code(
    identifier_type: str | None, codelists: CodeListEvaluator
) -> str | None:
    if not identifier_type:
        return None
    value = identifier_type.strip()
    return value if value in codelists.participant_schemes else None


def _directory_participant_values(
    directory_matches: list[DirectoryResult], scheme_code: str | None = None
) -> set[str]:
    values: set[str] = set()
    for directory in directory_matches:
        for value in participant_values_from_directory(directory.businessCard or {}):
            if scheme_code and not value.startswith(f"{scheme_code}:"):
                continue
            values.add(value)
    return values


def _filter_directory_matches_by_icd(
    directory_matches: list[DirectoryResult], scheme_code: str
) -> list[DirectoryResult]:
    filtered_results: list[DirectoryResult] = []
    for directory in directory_matches:
        payload = directory.businessCard
        if not isinstance(payload, dict):
            continue
        matches = payload.get("matches")
        if not isinstance(matches, list):
            if _directory_payload_matches_icd(payload, scheme_code):
                filtered_results.append(directory)
            continue
        filtered_matches = [
            item
            for item in matches
            if any(
                value.startswith(f"{scheme_code}:")
                for value in participant_values_from_directory(item)
            )
        ]
        if not filtered_matches:
            continue
        filtered_results.append(
            directory.model_copy(
                update={
                    "businessCard": {
                        **payload,
                        "total-result-count": len(filtered_matches),
                        "used-result-count": len(filtered_matches),
                        "matches": filtered_matches,
                    }
                }
            )
        )
    return filtered_results


def _directory_payload_matches_icd(payload: dict[str, object], scheme_code: str) -> bool:
    return any(
        value.startswith(f"{scheme_code}:")
        for value in participant_values_from_directory(payload)
    )


def _match_confidence_score(match: LightLookupResponse | DetailLookupResponse) -> int:
    if isinstance(match, DetailLookupResponse):
        return _confidence_score(match.summary.get("foundIn", []))
    score = 0
    if match.documentCapabilities:
        score += 100
    if match.businessEntities:
        score += 50
    return score
