from fastapi import APIRouter, Depends, Response, status

from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.health import ollama_health, ready_health
from opportunity_radar.presentation.http.acquisition import router as acquisition_router
from opportunity_radar.presentation.http.companies import router as companies_router
from opportunity_radar.presentation.http.matching import router as matching_router
from opportunity_radar.presentation.http.opportunities import router as opportunities_router
from opportunity_radar.presentation.http.profile import router as profile_router

router = APIRouter()
router.include_router(acquisition_router)
router.include_router(companies_router)
router.include_router(matching_router)
router.include_router(opportunities_router)
router.include_router(profile_router)


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(response: Response, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    database = ready_health(settings)
    if database.status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if database.status == "healthy" else "not_ready"}


@router.get("/health")
def health(response: Response, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    database = ready_health(settings)
    ollama = ollama_health(settings)
    if database.status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if database.status == "healthy" else "unhealthy",
        "database": database.as_dict(),
        "ollama": ollama.as_dict(),
    }
