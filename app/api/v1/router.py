from fastapi import APIRouter

from app.shared.responses import MessageResponse

router = APIRouter()


@router.get("", response_model=MessageResponse)
def api_v1_root() -> MessageResponse:
    return MessageResponse(message="API v1 is ready")

