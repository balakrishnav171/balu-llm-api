"""
Tests for GET /health endpoint.

The LLM service is mocked so these tests run without a live Ollama or
Azure OpenAI connection.
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path when tests are run directly
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_llm_service() -> MagicMock:
    """Return a mock LLMService that responds successfully."""
    svc = MagicMock()
    svc.model_name = "orca-mini"
    svc.backend = "ollama"
    svc.ping = AsyncMock(return_value=True)
    return svc


@pytest.fixture()
def mock_llm_service_unreachable() -> MagicMock:
    """Return a mock LLMService where the backend is unreachable."""
    svc = MagicMock()
    svc.model_name = "orca-mini"
    svc.backend = "ollama"
    svc.ping = AsyncMock(return_value=False)
    return svc


@pytest.fixture()
def client(mock_llm_service: MagicMock) -> TestClient:
    """FastAPI TestClient with the LLM service mocked."""
    with patch(
        "app.services.llm_service.get_llm_service",
        return_value=mock_llm_service,
    ):
        # Import app AFTER patching so the lifespan uses the mock
        from app.main import create_app

        test_app = create_app()
        with TestClient(test_app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture()
def client_unreachable(mock_llm_service_unreachable: MagicMock) -> TestClient:
    """FastAPI TestClient where the LLM backend is unavailable."""
    with patch(
        "app.services.llm_service.get_llm_service",
        return_value=mock_llm_service_unreachable,
    ):
        from app.main import create_app

        test_app = create_app()
        with TestClient(test_app, raise_server_exceptions=False) as c:
            yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200_when_llm_reachable(self, client: TestClient) -> None:
        """GET /health should return 200 when the LLM backend responds."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_schema(self, client: TestClient) -> None:
        """The response body must match HealthResponse schema."""
        response = client.get("/health")
        body = response.json()

        assert "status" in body
        assert "model" in body
        assert "backend" in body
        assert "version" in body
        assert "llm_reachable" in body

    def test_health_status_ok_when_reachable(self, client: TestClient) -> None:
        """status field should be 'ok' when LLM is reachable."""
        response = client.get("/health")
        assert response.json()["status"] == "ok"

    def test_health_llm_reachable_true(self, client: TestClient) -> None:
        """llm_reachable should be True when the mock ping succeeds."""
        response = client.get("/health")
        assert response.json()["llm_reachable"] is True

    def test_health_model_name(self, client: TestClient) -> None:
        """model field should reflect the configured model name."""
        response = client.get("/health")
        assert response.json()["model"] == "orca-mini"

    def test_health_backend(self, client: TestClient) -> None:
        """backend field should be 'ollama'."""
        response = client.get("/health")
        assert response.json()["backend"] == "ollama"

    def test_health_version_present(self, client: TestClient) -> None:
        """version field must be a non-empty string."""
        response = client.get("/health")
        assert response.json()["version"]

    def test_health_status_degraded_when_unreachable(
        self, client_unreachable: TestClient
    ) -> None:
        """status should be 'degraded' when LLM cannot be pinged."""
        response = client_unreachable.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"

    def test_health_llm_reachable_false_when_unreachable(
        self, client_unreachable: TestClient
    ) -> None:
        """llm_reachable should be False when backend is unreachable."""
        response = client_unreachable.get("/health")
        assert response.json()["llm_reachable"] is False

    def test_health_no_auth_required(self, client: TestClient) -> None:
        """The /health endpoint must work WITHOUT an API key."""
        response = client.get("/health")  # No X-API-Key header
        assert response.status_code == 200

    def test_root_endpoint(self, client: TestClient) -> None:
        """GET / should return a welcome message."""
        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert "message" in body
        assert "docs" in body
