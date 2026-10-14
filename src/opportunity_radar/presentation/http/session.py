from fastapi import APIRouter, Request, Response

from opportunity_radar.presentation.http.auth import authenticated_identity

router = APIRouter()


@router.get("/session")
def session(request: Request, response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    return {"is_owner": authenticated_identity(request).is_owner}
