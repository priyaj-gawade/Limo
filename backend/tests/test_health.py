"""Tests for D3.1: Health endpoint, CORS, and error handling."""

from fastapi.testclient import TestClient
from app.config import settings
from app.exceptions import LimoException


def test_health_check_development(client: TestClient) -> None:
    """Verify health check succeeds and returns valid metadata in development."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == settings.app_name
    assert data["version"] == settings.app_version
    assert "timestamp" in data
    # In development mode, environment is provided
    assert data.get("environment") == "development"


def test_health_check_production_omits_environment(client: TestClient, monkeypatch) -> None:
    """Verify health check omits internal environment information in production mode."""
    monkeypatch.setattr(settings, "environment", "production")
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" not in data


def test_cors_headers_on_desktop_origin(client: TestClient) -> None:
    """Verify CORS allow-origin header returns for approved desktop origins."""
    headers = {
        "Origin": "http://localhost:5190",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/api/v1/health", headers=headers)
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5190"


def test_structured_error_on_limo_exception() -> None:
    """Verify custom LimoException produces structured error response payload."""
    from app.main import create_app

    test_app = create_app()

    @test_app.get("/test-error-trigger")
    def trigger_error():
        raise LimoException("Custom error occurred", error_code="TEST_CODE", status_code=400, details={"test": True})

    with TestClient(test_app) as client:
        response = client.get("/test-error-trigger")
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "TEST_CODE"
        assert data["error"]["message"] == "Custom error occurred"
        assert data["error"]["details"] == {"test": True}
        assert "timestamp" in data["error"]


def test_404_not_found(client: TestClient) -> None:
    """Verify non-existent route returns 404."""
    response = client.get("/api/v1/non-existent-endpoint")
    assert response.status_code == 404


def test_validation_error_format() -> None:
    """Verify request validation error returns 422 with structured error payload."""
    from pydantic import BaseModel, Field
    from app.main import create_app

    test_app = create_app()

    class SampleBody(BaseModel):
        required_num: int = Field(ge=1)

    @test_app.post("/test-validation")
    def trigger_validation(body: SampleBody):
        return {"ok": True}

    with TestClient(test_app) as client:
        # Send invalid payload (string instead of int)
        response = client.post("/test-validation", json={"required_num": "not_an_int"})
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["status"] == 422
        assert "details" in data["error"]

