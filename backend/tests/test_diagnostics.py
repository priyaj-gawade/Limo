"""Tests for Phase D3.12: Error Handling, Request Diagnostics, and Secret Redaction."""

import logging
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.core.middleware import RequestDiagnosticsMiddleware, current_request_id, validate_request_id
from app.exceptions import (
    BadRequestError,
    EntityNotFoundError,
    InvalidStateError,
    LimoException,
    generic_exception_handler,
    limo_exception_handler,
    validation_exception_handler,
)
from app.logging import is_sensitive_key, log_operation, mask_sensitive_data
from app.main import app


@pytest.fixture
def client():
    """FastAPI TestClient with initialized app and middleware."""
    with TestClient(app) as test_client:
        yield test_client


def test_request_id_generated_when_header_missing(client: TestClient) -> None:
    """Verify X-Request-ID header is generated and attached to response when missing."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    req_id = res.headers.get("X-Request-ID")
    assert req_id is not None
    assert req_id.startswith("req_")
    assert len(req_id) >= 16


def test_request_id_preserved_when_header_valid(client: TestClient) -> None:
    """Verify valid incoming X-Request-ID is trusted and propagated to response."""
    custom_id = "trace-client-session-987654321"
    res = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id


def test_malicious_or_invalid_request_id_rejected_and_replaced(client: TestClient) -> None:
    """Verify malicious or overly long X-Request-ID headers are sanitized and replaced."""
    # 1. Dangerous injection string
    res = client.get("/api/v1/health", headers={"X-Request-ID": "<script>alert('xss')</script>"})
    assert res.status_code == 200
    assert "<script>" not in res.headers.get("X-Request-ID")
    assert res.headers.get("X-Request-ID").startswith("req_")

    # 2. Overly long string (> 64 chars)
    overlong = "a" * 128
    res = client.get("/api/v1/health", headers={"X-Request-ID": overlong})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") != overlong
    assert res.headers.get("X-Request-ID").startswith("req_")

    # 3. Too short string (< 4 chars)
    res = client.get("/api/v1/health", headers={"X-Request-ID": "ab"})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID").startswith("req_")


def test_structured_error_response_contains_request_id_and_resource_id(client: TestClient) -> None:
    """Verify 404 EntityNotFoundError returns structured error containing request_id and resource_id."""
    missing_id = "proj_missing_8888"
    custom_trace = "trace-error-probe-404"
    res = client.get(f"/api/v1/projects/{missing_id}", headers={"X-Request-ID": custom_trace})
    assert res.status_code == 404
    data = res.json()

    assert "error" in data
    error = data["error"]
    assert error["code"] == "ENTITY_NOT_FOUND"
    assert missing_id in error["message"]
    assert error["status"] == 404
    assert error["request_id"] == custom_trace
    assert error["resource_id"] == missing_id
    assert error["details"]["entity"] == "Project"
    assert "timestamp" in error


def test_validation_error_contains_request_id(client: TestClient) -> None:
    """Verify 422 validation error returns structured error containing request_id."""
    custom_trace = "trace-validation-probe-422"
    res = client.post(
        "/api/v1/projects",
        json={"name": 12345},  # Invalid payload format for expected string or structure
        headers={"X-Request-ID": custom_trace},
    )
    # If name is integer, pydantic might coerce it; send completely malformed body
    res = client.post(
        "/api/v1/sources/text",
        json={"name": "test"},  # Missing required 'text' field
        headers={"X-Request-ID": custom_trace},
    )
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    error = data["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["status"] == 422
    assert error["request_id"] == custom_trace
    assert error["resource_id"] is None
    assert isinstance(error["details"], list)


def test_500_internal_error_hides_server_details_from_client() -> None:
    """Verify unhandled 500 error sanitizes client response and hides internal traces."""
    from fastapi.exceptions import RequestValidationError
    test_app = FastAPI()
    test_app.add_middleware(RequestDiagnosticsMiddleware)
    test_app.add_exception_handler(LimoException, limo_exception_handler)
    test_app.add_exception_handler(RequestValidationError, validation_exception_handler)
    test_app.add_exception_handler(Exception, generic_exception_handler)

    @test_app.get("/crash")
    def crash_route():
        # Raise internal exception with sensitive technical message
        raise RuntimeError("DB Connection crashed: root:password@10.0.0.1:5432/secrets")

    with TestClient(test_app, raise_server_exceptions=False) as tc:
        res = tc.get("/crash", headers={"X-Request-ID": "trace-500-probe"})
        assert res.status_code == 500
        data = res.json()

        assert "error" in data
        error = data["error"]
        assert error["code"] == "INTERNAL_ERROR"
        assert error["message"] == "An internal server error occurred."
        assert error["request_id"] == "trace-500-probe"
        assert error["resource_id"] is None
        assert error["details"] is None  # Strict anti-leak: Never expose internal traces to client!
        assert "password" not in res.text
        assert "secrets" not in res.text


def test_mask_sensitive_data_redacts_credentials_accurately() -> None:
    """Verify mask_sensitive_data accurately redacts secrets without false-positive hits."""
    payload = {
        "api_key": "sk-proj-super-secret-key-12345",
        "access_token": "bearer-eyJh...",
        "refresh_token": "rfr-123...",
        "authorization": "Bearer secret-token",
        "password": "ProductionPassword123!",
        "client_secret": "cs_live_secret",
        "custom_secret": "my-secret-value",
        "cookie": "sessionid=abc123xyz",
        # Non-sensitive keys containing "key" that MUST NOT be masked
        "keywords": ["finance", "quarterly", "growth"],
        "key_findings": "Revenue increased by 18%",
        "primary_key": "proj_12345",
        "public_title": "Quarterly Synthesis",
        # Nested structures
        "nested": {
            "auth_token": "sub-token-secret",
            "normal_field": 42,
            "sub_list": [
                {"private_key": "PRIVATE_KEY_DATA"},
                {"public_item": "ok"},
            ],
        },
    }

    masked = mask_sensitive_data(payload)

    # Assert redactions
    assert masked["api_key"] == "***REDACTED***"
    assert masked["access_token"] == "***REDACTED***"
    assert masked["refresh_token"] == "***REDACTED***"
    assert masked["authorization"] == "***REDACTED***"
    assert masked["password"] == "***REDACTED***"
    assert masked["client_secret"] == "***REDACTED***"
    assert masked["custom_secret"] == "***REDACTED***"
    assert masked["cookie"] == "***REDACTED***"
    assert masked["nested"]["auth_token"] == "***REDACTED***"
    assert masked["nested"]["sub_list"][0]["private_key"] == "***REDACTED***"

    # Assert preservation of normal fields
    assert masked["keywords"] == ["finance", "quarterly", "growth"]
    assert masked["key_findings"] == "Revenue increased by 18%"
    assert masked["primary_key"] == "proj_12345"
    assert masked["public_title"] == "Quarterly Synthesis"
    assert masked["nested"]["normal_field"] == 42
    assert masked["nested"]["sub_list"][1]["public_item"] == "ok"


def test_context_var_cleanup_on_request(client: TestClient) -> None:
    """Verify current_request_id ContextVar is cleaned up after request lifecycle."""
    assert current_request_id.get() is None

    res = client.get("/api/v1/health")
    assert res.status_code == 200

    # Outside the request execution, contextvar must be reset
    assert current_request_id.get() is None


def test_log_operation_formatting(caplog) -> None:
    """Verify log_operation records structured fields and masks extra parameters."""
    test_logger = logging.getLogger("test.diagnostics")
    with caplog.at_level(logging.INFO):
        log_operation(
            test_logger,
            service="SourceService",
            operation="register_file",
            status="success",
            resource_id="src_12345",
            api_key="leaked-token",
            filename="report.pdf",
        )

    log_output = caplog.text
    assert "[SourceService:register_file]" in log_output
    assert "status=success" in log_output
    assert "resource_id=src_12345" in log_output
    assert "filename=report.pdf" in log_output
    assert "api_key=***REDACTED***" in log_output
    assert "leaked-token" not in log_output
