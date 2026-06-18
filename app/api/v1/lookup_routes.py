from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

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

router = APIRouter()


def get_orchestrator(request: Request) -> LookupOrchestrator:
    return get_orchestrator_from_request(request)


def require_lookup_rate_limit(request: Request) -> None:
    enforce_rate_limit(request)


def require_admin_token(
    request: Request,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    settings: Settings = request.app.state.settings
    if settings.peppol_admin_token and x_admin_token != settings.peppol_admin_token:
        raise HTTPException(status_code=403, detail="admin token required")


def require_refresh_permission(
    request: Request,
    refresh: bool,
    x_admin_token: str | None,
) -> None:
    settings: Settings = request.app.state.settings
    if refresh and settings.peppol_admin_token and x_admin_token != settings.peppol_admin_token:
        raise HTTPException(status_code=403, detail="admin token required for refresh")


@router.get(
    "/participants/{participant_id:path}/lookup",
    response_model=LightLookupResponse | DetailLookupResponse,
)
async def lookup_participant(
    request: Request,
    participant_id: str,
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    mode: LookupMode = LookupMode.light,
    environments: str | None = Query(default=None),
    sources: str | None = Query(default="all"),
    include_raw: bool = False,
    timeout_ms: int | None = Query(default=None, ge=100, le=30000),
    refresh: bool = False,
    _: Annotated[None, Depends(require_lookup_rate_limit)] = None,
) -> LightLookupResponse | DetailLookupResponse:
    require_refresh_permission(request, refresh, x_admin_token)
    participant = normalize_participant_id(participant_id)
    return await orchestrator.lookup(
        participant=participant,
        mode=mode,
        environments=normalize_environment_list(environments, settings.peppol_lookup_environments),
        sources=normalize_source_list(sources),
        include_raw=include_raw,
        timeout_ms=timeout_ms,
        refresh=refresh,
    )


@router.post("/lookup", response_model=LightLookupResponse | DetailLookupResponse)
async def post_lookup(
    request_context: Request,
    request: LookupRequest,
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    _: Annotated[None, Depends(require_lookup_rate_limit)] = None,
) -> LightLookupResponse | DetailLookupResponse:
    require_refresh_permission(request_context, request.refresh, x_admin_token)
    participant = normalize_participant_id(
        f"{request.participant_id.scheme}::{request.participant_id.value}"
    )
    return await orchestrator.lookup(
        participant=participant,
        mode=request.mode,
        environments=[environment.value for environment in request.environments],
        sources=normalize_source_list("all"),
        include_raw=request.include_raw,
        timeout_ms=request.timeout_ms,
        refresh=request.refresh,
    )


@router.get("/companies/lookup", response_model=CompanyLookupResponse)
async def lookup_company(
    request: Request,
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    country: str = Query(min_length=2, max_length=2),
    identifier: str = Query(min_length=1),
    identifier_type: str | None = None,
    mode: LookupMode = LookupMode.light,
    environments: str | None = Query(default=None),
    max_candidates: int = Query(default=20, ge=1, le=100),
    refresh: bool = False,
    _: Annotated[None, Depends(require_lookup_rate_limit)] = None,
) -> CompanyLookupResponse:
    require_refresh_permission(request, refresh, x_admin_token)
    service = CompanyLookupService(orchestrator, orchestrator.codelists)
    environment_values = normalize_environment_list(
        environments, orchestrator.settings.peppol_lookup_environments
    )
    envs = [EnvironmentName(value) for value in environment_values]
    return await service.lookup(
        country, identifier, identifier_type, mode, envs, max_candidates, refresh
    )


@router.post("/companies/lookup", response_model=CompanyLookupResponse)
async def post_lookup_company(
    request_context: Request,
    request: CompanyLookupRequest,
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    _: Annotated[None, Depends(require_lookup_rate_limit)] = None,
) -> CompanyLookupResponse:
    require_refresh_permission(request_context, request.refresh, x_admin_token)
    service = CompanyLookupService(orchestrator, orchestrator.codelists)
    return await service.lookup(
        request.country,
        request.identifier,
        request.identifier_type,
        request.mode,
        request.environments,
        request.max_candidates,
        request.refresh,
    )


@router.get("/sources")
def sources(
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
) -> dict[str, object]:
    return orchestrator.sources()


@router.get("/codelists/participant-countries")
def participant_countries(
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
) -> dict[str, object]:
    return {"countries": orchestrator.codelists.participant_countries()}


@router.get("/sources/health")
async def source_health(
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    request: Request,
    check: bool = False,
) -> dict[str, object]:
    if check:
        health = await orchestrator.check_source_health()
    else:
        health = {"status": "configured", **orchestrator.sources()}
    limiter = getattr(request.app.state, "rate_limiter", None)
    return {
        **health,
        "rateLimit": limiter.stats() if limiter else None,
    }


@router.post("/sources/codelists/refresh")
async def refresh_codelists(
    orchestrator: Annotated[LookupOrchestrator, Depends(get_orchestrator)],
    _: Annotated[None, Depends(require_admin_token)] = None,
) -> dict[str, object]:
    return await orchestrator.refresh_codelists()
