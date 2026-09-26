from fastapi.testclient import TestClient

from opportunity_radar.platform.config import Settings
from opportunity_radar.presentation.http.app import create_app


def test_semantic_search_route_is_removed() -> None:
    app = create_app(
        Settings(database_url="postgresql+psycopg://test:test@localhost/test")
    )

    response = TestClient(app).get("/search/semantic")

    assert response.status_code == 404
