from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.presentation.http.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the HTTP application without initializing external dependencies."""
    settings = settings or get_settings()
    app = FastAPI(title="Opportunity Radar API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(router)
    return app
