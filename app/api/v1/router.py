from fastapi import APIRouter

from app.api.v1.lookup_routes import router as lookup_router

router = APIRouter()
router.include_router(lookup_router)
