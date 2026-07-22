import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.peppol.runtime import build_orchestrator, build_rate_limiter, codelist_refresh_loop
from app.shared.config import Settings, get_settings
from app.shared.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.peppol_codelist_auto_refresh:
            app.state.codelist_refresh_task = asyncio.create_task(
                codelist_refresh_loop(
                    app.state.lookup_orchestrator,
                    settings.peppol_codelist_refresh_seconds,
                )
            )
        try:
            yield
        finally:
            task = app.state.codelist_refresh_task
            if task:
                task.cancel()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        root_path=settings.normalized_context_path,
        lifespan=lifespan,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=settings.allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "Origin", "X-Requested-With"],
    )

    app.state.settings = settings
    app.state.lookup_orchestrator = build_orchestrator(settings)
    app.state.rate_limiter = build_rate_limiter(settings)
    app.state.codelist_refresh_task = None

    app.include_router(api_router)
    app.mount("/embed", StaticFiles(directory="embed", html=True), name="embed")
    return app


app = create_app()
