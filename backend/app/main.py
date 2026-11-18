"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.core.config import APP_NAME, APP_VERSION, Settings, get_settings
from app.core.crypto import encryption_key_available
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' "
        "data: https://image.tmdb.org; connect-src 'self'; font-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
    ),
}


class RequestContextMiddleware:
    """Assign a request id, bind it to the log context and log the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = f"req_{uuid.uuid4().hex}"
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "http_request",
                method=scope.get("method"),
                path=scope.get("path"),
                status_code=status_code,
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware:
    """Add the security headers required by the security design."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    if name.lower().encode() not in existing:
                        headers.append((name.encode(), value.encode()))
                if self.settings.cookie_secure and b"strict-transport-security" not in existing:
                    headers.append(
                        (
                            b"Strict-Transport-Security",
                            b"max-age=31536000; includeSubDomains",
                        )
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> object:
    settings = get_settings()
    logger.info(
        "app_startup",
        env=settings.app_env,
        version=APP_VERSION,
        encryption_key=encryption_key_available(settings),
        bootstrap_enabled=settings.bootstrap_enabled,
    )
    if not encryption_key_available(settings):
        logger.warning("app_startup_missing_encryption_key")
    if not settings.bootstrap_enabled:
        logger.warning("app_startup_missing_bootstrap_token")
    yield
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    """Build the FastAPI application (used by uvicorn and the tests)."""
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token", REQUEST_ID_HEADER],
        )
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Serve the compiled SPA; API routes are matched before this catch-all."""
        if full_path == "api" or full_path.startswith("api/"):
            raise StarletteHTTPException(status_code=404, detail="Risorsa non trovata.")
        root = Path(settings.frontend_dist_dir).resolve()
        candidate = (root / full_path).resolve()
        if root.is_dir() and candidate.is_relative_to(root) and candidate.is_file():
            response = FileResponse(candidate)
            if full_path.startswith("assets/"):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
        index = root / "index.html"
        if index.is_file():
            response = FileResponse(index)
            response.headers["Cache-Control"] = "no-store"
            return response
        raise StarletteHTTPException(status_code=404, detail="Frontend non compilato.")

    return app


app = create_app()
