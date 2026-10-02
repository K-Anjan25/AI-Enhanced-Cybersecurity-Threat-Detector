"""Application factory and process entry point for the AEGIS backend.

Run with ``uvicorn app.main:app`` in development. Configuration errors are
reported as a single actionable line rather than a traceback (rule R-06).
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.endpoints import health
from app.core.config import ConfigurationError, Settings, get_settings
from app.core.logging import bind_request_id, clear_request_id, configure_logging, get_logger
from app.services.health_service import ReadinessRegistry

__version__ = "0.1.0"

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation id to every request and every log line it produces.

    Reuses an inbound ``X-Request-ID`` when present so a trace can be followed
    across services (NFR-07), and always echoes the id back on the response.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        """Bind a request id, call the next handler, and echo the id back."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        clear_request_id()
        bind_request_id(request_id)
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging and declare startup/shutdown in one place."""
    settings: Settings = app.state.settings
    configure_logging(settings)
    logger = get_logger("aegis.backend")
    logger.info(
        "startup",
        service=settings.service_name,
        environment=settings.env.value,
        version=__version__,
    )
    try:
        yield
    finally:
        logger.info("shutdown", service=settings.service_name)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: configuration to use. When omitted, settings are loaded from
            the environment via :func:`app.core.config.get_settings`.

    Returns:
        A configured application with probes mounted at the root path.
    """
    resolved = settings if settings is not None else get_settings()

    app = FastAPI(
        title="AEGIS Backend",
        description=(
            "AI-Enhanced Cybersecurity Threat Detector — ingest and query API. "
            "See prd.md for requirements and architecture.md for design."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    app.state.settings = resolved
    app.state.service_name = resolved.service_name
    app.state.version = __version__
    app.state.environment = resolved.env.value
    # Dependencies register probes here as they are introduced (T-301, T-307).
    app.state.readiness = ReadinessRegistry()

    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    return app


def main() -> int:
    """Console entry point. Returns a process exit code."""
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.env.value == "development",
    )
    return 0


def __getattr__(name: str) -> object:
    """Build the ASGI app lazily so importing this module has no side effects.

    ``uvicorn app.main:app`` resolves the attribute and triggers configuration
    loading; merely importing the module (tests, linters, docs builds) does not.
    """
    if name == "app":
        try:
            return create_app()
        except ConfigurationError as exc:
            # Fail with an actionable message naming the bad variable.
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    raise SystemExit(main())
