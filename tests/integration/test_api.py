from app.api.server import app, healthz


def test_healthz_returns_status_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))

    payload = healthz()

    assert payload["app"] == "MendCode"
    assert payload["status"] == "ok"
    assert "timestamp" in payload
    assert "traces_dir" in payload

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
