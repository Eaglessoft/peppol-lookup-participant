import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.peppol.runtime import build_orchestrator, build_rate_limiter, codelist_refresh_loop
from app.shared.config import Settings, get_settings
from app.shared.logging import configure_logging

ROOT_DIR = Path(__file__).resolve().parent.parent




class _NoCacheStaticFiles(StaticFiles):
    """StaticFiles that always revalidates.

    Asset URLs carry a hand-maintained ?v=, which is one forgotten bump away
    from serving last release's stylesheet against this release's markup -
    exactly the failure the HTML response had. StaticFiles sends no
    Cache-Control at all, leaving browsers to guess a freshness lifetime, so
    say it explicitly instead.
    """

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


BASE_PLACEHOLDER = "__APP_BASE_HREF__"


def _base_href(context_path: str) -> str:
    """Normalise a context path into a <base href> value.

    Always leading and trailing slash, or plain "/" when the app is mounted at
    the root. Mirrors IndexController in saxon-xslt-service and IndexServlet in
    phive-doc-validator so the three tools resolve assets identically.
    """
    trimmed = (context_path or "").strip()
    if not trimmed or trimmed == "/":
        return "/"
    if not trimmed.startswith("/"):
        trimmed = "/" + trimmed
    return trimmed.rstrip("/") + "/"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    context_path = settings.normalized_context_path

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
            await app.state.lookup_orchestrator.aclose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=f"{context_path}/docs" if context_path else "/docs",
        openapi_url=f"{context_path}/openapi.json" if context_path else "/openapi.json",
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

    app.include_router(api_router, prefix=context_path)

    @app.get(f"{context_path}/" if context_path else "/", include_in_schema=False)
    def root_ui() -> HTMLResponse:
        """Serve the page shell with a base href for the running context path.

        Every asset URL in the template is relative and has no leading slash, so
        it resolves against that value - which is what lets one image run at the
        root during local development and behind the /peppol-lookup prefix in
        production without the markup changing. Links that address *other*
        services on the same origin (the portal, a sibling tool) stay
        path-absolute on purpose: <base> does not touch those, so they resolve
        against the origin alone.

        This replaces a pair of substring rewrites on embed/sample.html, which
        only worked because the widget doubled as the page.
        """
        html = (ROOT_DIR / "app" / "ui" / "index.html").read_text(encoding="utf-8")
        # The ?v= query strings keep the browser honest about CSS and JS, but
        # nothing was protecting the document that references them: with no
        # Cache-Control the browser caches this page heuristically, so after a
        # deploy a returning visitor gets the new stylesheet against the old
        # markup.
        return HTMLResponse(
            html.replace(BASE_PLACEHOLDER, _base_href(context_path)),
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    app.mount(
        f"{context_path}/static" if context_path else "/static",
        _NoCacheStaticFiles(directory=ROOT_DIR / "app" / "static"),
        name="static",
    )
    # Kept mounted for jsDelivr and for anyone already embedding the widget.
    app.mount(
        f"{context_path}/embed" if context_path else "/embed",
        StaticFiles(directory=ROOT_DIR / "embed", html=True),
        name="embed",
    )
    return app


app = create_app()
