from fastapi.testclient import TestClient

from app.api.server import app


client = TestClient(app)


def test_healthz_returns_status_payload():
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "MendCode"
    assert payload["status"] == "ok"
    assert "timestamp" in payload
    assert "traces_dir" in payload
