from fastapi import APIRouter

from app.api.v1.lookup_routes import router as lookup_router
from app.shared.responses import MessageResponse

router = APIRouter()
router.include_router(lookup_router)


@router.get("", response_model=MessageResponse)
def api_v1_root() -> MessageResponse:
    return MessageResponse(message="API v1 is ready")

