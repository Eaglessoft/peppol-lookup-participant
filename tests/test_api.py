from fastapi.testclient import TestClient

from app.main import create_app
from app.shared.config import Settings


def test_api_info_returns_service_metadata() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    response = client.get("/api")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Peppol Lookup API"
    assert body["status"] == "running"


def test_health_returns_ok() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

