from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_liveness_without_database():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "thaazhai-api"}


def test_readiness_failure_does_not_expose_credentials(monkeypatch):
    def fail():
        raise RuntimeError("postgresql://secret:password@host/db")

    monkeypatch.setattr("apps.api.main.get_engine", fail)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
