import time
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.logging import (
    configure_logging,
    correlation_scope,
    get_logger,
)
from opportunity_radar.presentation.http.auth import (
    AuthConfig,
    JwksClient,
    JwtVerifier,
    RequireAuthenticated,
    RequireOperationalOwner,
)
from opportunity_radar.presentation.http.routes import private_router, public_router

CORRELATION_HEADER = "X-Correlation-ID"

logger = get_logger("opportunity_radar.http")

#: SQLSTATE of a statement Postgres cancelled (`statement_timeout`, card F50-10).
_QUERY_CANCELED = "57014"


async def database_error_handler(request: Request, error: DBAPIError) -> Response:
    """A query past the API's statement timeout is a 503; other errors propagate untouched."""
    if getattr(error.orig, "sqlstate", None) == _QUERY_CANCELED:
        logger.warning("database statement timed out", extra={"path": request.url.path})
        return JSONResponse(
            status_code=503,
            content={"detail": "The database took too long to answer. Try again."},
            headers={"Retry-After": "5"},
        )
    # Re-raise non-timeout errors so they propagate through the logging middleware.
    raise error


def _base_app(settings: Settings | None = None, *, docs: bool = False) -> FastAPI:
    """Build the HTTP application without initializing external dependencies."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Opportunity Radar API",
        version="0.1.0",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
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
        supplied_correlation_id = request.headers.get(CORRELATION_HEADER)
        correlation_id = (
            supplied_correlation_id
            if supplied_correlation_id
            and supplied_correlation_id.replace("-", "").replace("_", "").isalnum()
            and len(supplied_correlation_id) <= 64
            else None
        )
        with correlation_scope(correlation_id) as correlation_id:
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
    return app


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the protected production API; missing Clerk configuration aborts startup."""
    settings = settings or get_settings()
    issuer, jwks_url, owner_sub = (
        settings.clerk_issuer,
        settings.clerk_jwks_url,
        settings.clerk_owner_sub,
    )
    parties = frozenset(
        item.strip() for item in settings.clerk_authorized_parties.split(",") if item.strip()
    )
    if not issuer or not jwks_url or not parties or not owner_sub:
        raise RuntimeError(
            "production API requires Clerk issuer, JWKS URL, authorized parties, and owner subject"
        )
    config = AuthConfig(
        issuer=issuer.strip(),
        jwks_url=jwks_url.strip(),
        authorized_parties=parties,
        owner_sub=owner_sub.strip(),
    )
    app = _base_app(settings)
    app.include_router(public_router)
    authenticated = RequireAuthenticated(JwtVerifier(config, JwksClient(config.jwks_url)))
    app.include_router(
        private_router,
        dependencies=[Depends(authenticated), Depends(RequireOperationalOwner())],
    )
    return app


def create_development_app(settings: Settings | None = None) -> FastAPI:
    """Explicit local-only factory for development; production entrypoints use create_app."""
    app = _base_app(settings, docs=True)
    app.include_router(public_router)
    app.include_router(private_router)
    return app
