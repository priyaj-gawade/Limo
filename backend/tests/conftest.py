"""Pytest test fixtures."""

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings


@pytest.fixture
def client() -> TestClient:
    """Synchronous test client fixture."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
