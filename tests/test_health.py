"""
Tests for GET /health endpoint.

The LLM service is mocked via dependency_overrides so these tests
run without a live Ollama or Azure OpenAI connection.
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_llm_service() -> MagicMock:
    svc = MagicMock()
    svc.model_name = "orca-mini"
    svc.backend = "ollama"
    svc.ping = AsyncMock(return_value=True)
    return svc


@pytest.fixture()
def mock_llm_service_unreachable() -> MagicMock:
    svc = MagicMock()
    svc.model_name = "orca-mini"
    svc.backend = "ollama"
    svc.ping = AsyncMock(return_value=False)
    return svc


@pytest.fixture()
def client(mock_llm_service: MagicMock) -> TestClient:
    from app.main import create_app
    from app.services.llm_service import get_llm_service

    test_app = create_app()
    test_app.dependency_overrides[get_llm_service] = lambda: mock_llm_service
    with TestClient(test_app, raise_server_exceptions=False) as c:
        yield c
    test_app.dependency_overrides.clear()


@pytest.fixture()
def client_unreachable(mock_llm_service_unreachable: MagicMock) -> TestClient:
    from app.main import create_app
    from app.services.llm_service import get_llm_service

    test_app = create_app()
    test_app.dependency_overrides[get_llm_service] = lambda: mock_llm_service_unreachable
    with TestClient(test_app, raise_server_exceptions=False) as c:
        yield c
    test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200_when_llm_reachable(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_schema(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert "status" in body
        assert "model" in body
        assert "backend" in body
        assert "version" in body
        assert "llm_reachable" in body

    def test_health_status_ok_when_reachable(self, client: TestClient) -> None:
        assert client.get("/health").json()["status"] == "ok"

    def test_health_llm_reachable_true(self, client: TestClient) -> None:
        assert client.get("/health").json()["llm_reachable"] is True

    def test_health_model_name(self, client: TestClient) -> None:
        assert client.get("/health").json()["model"] == "orca-mini"

    def test_health_backend(self, client: TestClient) -> None:
        assert client.get("/health").json()["backend"] == "ollama"

    def test_health_version_present(self, client: TestClient) -> None:
        assert client.get("/health").json()["version"]

    def test_health_status_degraded_when_unreachable(self, client_unreachable: TestClient) -> None:
        response = client_unreachable.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"

    def test_health_llm_reachable_false_when_unreachable(self, client_unreachable: TestClient) -> None:
        assert client_unreachable.get("/health").json()["llm_reachable"] is False

    def test_health_no_auth_required(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200

    def test_root_endpoint(self, client: TestClient) -> None:
        body = client.get("/").json()
        assert "message" in body
        assert "docs" in body
