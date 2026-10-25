"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import Settings, get_settings
from app.logging import configure_logging
from app.repository.datasets import DatasetRepository, build_repository
from app.schemas.models import ErrorBody, ErrorDetail, ErrorEnvelope
from app.services.analysis_service import AnalysisService, ApiError
from app.services.content import APP_VERSION

log = logging.getLogger(__name__)


def _error(
    status: int, code: str, message: str, details: list[ErrorDetail] | None = None
) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details or []))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def create_app(
    settings: Settings | None = None, repository: DatasetRepository | None = None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            repo = repository or build_repository(settings)
            app.state.service = AnalysisService(repo.load(), settings)
            log.info("dataset loaded", extra={"extra_fields": {"mode": settings.data_source_mode}})
        except Exception as exc:
            app.state.service = None
            app.state.load_error = f"{type(exc).__name__}: {exc}"
            log.error("dataset failed to load: %s", app.state.load_error)
        yield

    app = FastAPI(
        title="UK Wind Forecast Intelligence API",
        version=APP_VERSION,
        description=(
            "Retrospective evaluation of day-ahead wind forecasts (Elexon BMRS WINDFOR vs FUELHH) for "
            "January 2026 deliveries. error = actual - forecast."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings
    app.state.service = None
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, [ErrorDetail(**d) for d in exc.details])

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            ErrorDetail(
                field=".".join(str(p) for p in e["loc"] if p != "query"), message=str(e["msg"])
            )
            for e in exc.errors()
        ]
        return _error(422, "VALIDATION_ERROR", "Request parameters are invalid.", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "INTERNAL"
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return _error(500, "INTERNAL", "An unexpected error occurred.")

    app.include_router(router)
    _mount_spa(app, settings.frontend_dist_dir)
    return app


# The SPA needs same-origin scripts/XHR and inline styles (Recharts/Radix set style attributes). The Swagger UI
# page at /docs is intentionally excluded from this policy because it loads assets from a CDN.
SPA_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def _mount_spa(app: FastAPI, dist: Path | None) -> None:
    """Serve the built React app (production image). API routes take precedence."""
    if dist is None or not (dist / "index.html").is_file():
        return
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith("api/") or path in ("docs", "openapi.json"):
            return _error(404, "NOT_FOUND", "Not found")
        candidate = (root / path).resolve()
        headers = {"Content-Security-Policy": SPA_CSP}
        if path and candidate.is_file() and root in candidate.parents:
            immutable = path.startswith("assets/")  # content-hashed filenames
            if immutable:
                headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return FileResponse(candidate, headers=headers)
        headers["Cache-Control"] = "no-cache"
        return FileResponse(root / "index.html", headers=headers)


app = create_app()
