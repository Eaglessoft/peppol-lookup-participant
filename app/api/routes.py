from fastapi import APIRouter

from app.api.v1.router import router as v1_router
from app.shared.config import get_settings
from app.shared.responses import ApiInfoResponse, HealthResponse

router = APIRouter()
router.include_router(v1_router, prefix="/api/v1")


@router.get("/api", response_model=ApiInfoResponse)
def api_info() -> ApiInfoResponse:
    settings = get_settings()
    return ApiInfoResponse(
        service=settings.app_name,
        version=settings.app_version,
        status="running",
        endpoints=["/api", "/health", "/api/v1"],
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")

