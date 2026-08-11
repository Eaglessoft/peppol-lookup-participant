import asyncio
from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.peppol.company_lookup import CompanyLookupService
from app.peppol.models import (
    CompanyLookupRequest,
    CompanyLookupResponse,
    DetailLookupResponse,
    EnvironmentName,
    LightLookupResponse,
    LookupMode,
    LookupRequest,
)
from app.peppol.normalizer import (
    normalize_environment_list,
    normalize_participant_id,
    normalize_source_list,
)
from app.peppol.orchestrator import LookupOrchestrator
from app.peppol.runtime import enforce_rate_limit, get_orchestrator_from_request
from app.shared.config import Settings, get_settings

router = APIRouter(tags=["Peppol lookup"])

async def _with_request_timeout[ResponseT](
    awaitable: Awaitable[ResponseT], settings: Settings
) -> ResponseT:
    try:
        async with asyncio.timeout(settings.peppol_request_timeout_ms / 1000):
            return await awaitable
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="lookup request timed out") from exc


def get_orchestrator(request: Request) -> LookupOrchestrator:
    return get_orchestrator_from_request(request)


def require_lookup_rate_limit(request: Request) -> None:
    enforce_rate_limit(request)


@router.get(
    "/participants/{participant_id:path}",
    response_model=LightLookupResponse | DetailLookupResponse,
    summary="Lookup participant by Peppol ID",
)
async def lookup_participant(
    participant_id: str,
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    settings: Annotated[Settings, Depends(get_settings)],
    mode: LookupMode = LookupMode.light,
    environments: str | None = Query(default=None),
    sources: str | None = Query(default="all"),
    include_raw: bool = False,
    timeout_ms: int | None = Query(default=None, ge=100, le=30000),
    refresh: bool = False,
    _: Annotated[None, Depends(require_lookup_rate_limit)] = None,
) -> LightLookupResponse | DetailLookupResponse:
    participant = normalize_participant_id(participant_id)
    return await _with_request_timeout(
        orchestrator.lookup(
            participant=participant,
            mode=mode,
            environments=normalize_environment_list(
                environments, settings.peppol_lookup_environments
            ),
            sources=normalize_source_list(sources),
            include_raw=include_raw,
            timeout_ms=timeout_ms,
            refresh=refresh,
            raise_on_all_timeout=True,
        ),
        settings,
    )


@router.post(
    "/participants/search",
    response_model=LightLookupResponse | DetailLookupResponse,
    summary="Search participant",
)
async def post_lookup(
    request: LookupRequest,
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    _: Annotated[None, Depends(require_lookup_rate_limit)] = None,
) -> LightLookupResponse | DetailLookupResponse:
    participant = normalize_participant_id(
        f"{request.participant_id.scheme}::{request.participant_id.value}"
    )
    return await _with_request_timeout(
        orchestrator.lookup(
            participant=participant,
            mode=request.mode,
            environments=[environment.value for environment in request.environments],
            sources=normalize_source_list("all"),
            include_raw=request.include_raw,
            timeout_ms=request.timeout_ms,
            refresh=request.refresh,
            raise_on_all_timeout=True,
        ),
        orchestrator.settings,
    )


@router.get(
    "/companies",
    response_model=CompanyLookupResponse,
    summary="Discover company participants",
)
async def lookup_company(
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    country: str = Query(min_length=2, max_length=2),
    identifier: str = Query(min_length=1),
    identifier_type: str | None = None,
    mode: LookupMode = LookupMode.light,
    environments: str | None = Query(default=None),
    max_candidates: int = Query(default=20, ge=1, le=100),
    refresh: bool = False,
    _: Annotated[None, Depends(require_lookup_rate_limit)] = None,
) -> CompanyLookupResponse:
    service = CompanyLookupService(orchestrator, orchestrator.codelists)
    environment_values = normalize_environment_list(
        environments, orchestrator.settings.peppol_lookup_environments
    )
    envs = [EnvironmentName(value) for value in environment_values]
    return await _with_request_timeout(
        service.lookup(
            country, identifier, identifier_type, mode, envs, max_candidates, refresh
        ),
        orchestrator.settings,
    )


@router.post(
    "/companies/search",
    response_model=CompanyLookupResponse,
    summary="Search companies",
)
async def post_lookup_company(
    request: CompanyLookupRequest,
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    _: Annotated[None, Depends(require_lookup_rate_limit)] = None,
) -> CompanyLookupResponse:
    service = CompanyLookupService(orchestrator, orchestrator.codelists)
    return await _with_request_timeout(
        service.lookup(
            request.country,
            request.identifier,
            request.identifier_type,
            request.mode,
            request.environments,
            request.max_candidates,
            request.refresh,
        ),
        orchestrator.settings,
    )


@router.get("/sources", summary="List lookup sources")
def sources(
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
) -> dict[str, object]:
    return orchestrator.sources()


@router.get(
    "/codelists/participant-countries",
    summary="List supported participant countries",
)
def participant_countries(
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
) -> dict[str, object]:
    return {"countries": orchestrator.codelists.participant_countries()}


@router.get("/sources/health", summary="Check lookup source health")
async def source_health(
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    request: Request,
    check: bool = False,
    refresh: bool = False,
) -> dict[str, object]:
    if check:
        health = await orchestrator.check_source_health(force=refresh)
    else:
        health = orchestrator.health_snapshot()
    limiter = getattr(request.app.state, "rate_limiter", None)
    return {
        **health,
        "rateLimit": limiter.stats() if limiter else None,
    }


@router.post("/codelists/refresh", summary="Refresh Peppol codelists")
async def refresh_codelists(
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
) -> dict[str, object]:
    return await orchestrator.refresh_codelists()
