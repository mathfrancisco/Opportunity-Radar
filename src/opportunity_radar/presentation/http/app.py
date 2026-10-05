import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.logging import (
    configure_logging,
    correlation_scope,
    get_logger,
)
from opportunity_radar.presentation.http.routes import router

CORRELATION_HEADER = "X-Correlation-ID"

logger = get_logger("opportunity_radar.http")

#: SQLSTATE of a statement Postgres cancelled (`statement_timeout`, card F50-10).
_QUERY_CANCELED = "57014"


async def database_error_handler(request: Request, error: DBAPIError) -> Response:
    """A query past the API's statement timeout is a 503, any other database error a 500."""
    if getattr(error.orig, "sqlstate", None) == _QUERY_CANCELED:
        logger.warning("database statement timed out", extra={"path": request.url.path})
        return JSONResponse(
            status_code=503,
            content={"detail": "The database took too long to answer. Try again."},
            headers={"Retry-After": "5"},
        )
    logger.error("database error", exc_info=error, extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the HTTP application without initializing external dependencies."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Opportunity Radar API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """One line per request, carrying the id a client sent or the one we minted."""
        with correlation_scope(request.headers.get(CORRELATION_HEADER)) as correlation_id:
            started = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "request failed",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    },
                )
                raise
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            response.headers[CORRELATION_HEADER] = correlation_id
            return response

    app.add_exception_handler(DBAPIError, database_error_handler)  # type: ignore[arg-type]
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(router)
    return app
