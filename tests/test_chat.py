"""
Tests for POST /v1/chat endpoint.

The LLM service is replaced with a mock, so no real model is needed.
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

VALID_API_KEY = "test-api-key-1234"
INVALID_API_KEY = "wrong-key"

SIMPLE_REQUEST = {
    "messages": [{"role": "user", "content": "Hello, world!"}],
    "stream": False,
}

MULTI_TURN_REQUEST = {
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "4"},
        {"role": "user", "content": "And 3+3?"},
    ],
    "stream": False,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_service(response_text: str = "This is a test response.") -> MagicMock:
    svc = MagicMock()
    svc.model_name = "orca-mini"
    svc.backend = "ollama"
    svc.ping = AsyncMock(return_value=True)
    svc.chat = AsyncMock(return_value=response_text)

    async def _stream_gen(*args, **kwargs):
        for word in response_text.split():
            yield word + " "

    svc.stream = _stream_gen
    return svc


@pytest.fixture(autouse=True)
def override_api_key(monkeypatch):
    """Set the API_KEY setting to our test value for every test."""
    monkeypatch.setattr("app.core.config.settings.API_KEY", VALID_API_KEY)
    monkeypatch.setattr("app.core.auth.settings.API_KEY", VALID_API_KEY)


@pytest.fixture()
def mock_service() -> MagicMock:
    return _make_mock_service()


@pytest.fixture()
def client(mock_service: MagicMock) -> TestClient:
    with patch(
        "app.services.llm_service.get_llm_service",
        return_value=mock_service,
    ):
        from app.main import create_app

        test_app = create_app()
        with TestClient(test_app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture()
def client_error() -> TestClient:
    """Client whose LLM service raises an exception."""
    svc = MagicMock()
    svc.model_name = "orca-mini"
    svc.backend = "ollama"
    svc.chat = AsyncMock(side_effect=RuntimeError("LLM exploded"))
    svc.ping = AsyncMock(return_value=True)

    async def _bad_stream(*args, **kwargs):
        raise RuntimeError("stream also exploded")
        yield  # make it a generator

    svc.stream = _bad_stream

    with patch(
        "app.services.llm_service.get_llm_service",
        return_value=svc,
    ):
        from app.main import create_app

        test_app = create_app()
        with TestClient(test_app, raise_server_exceptions=False) as c:
            yield c


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestChatAuth:
    def test_missing_api_key_returns_401(self, client: TestClient) -> None:
        """Request without X-API-Key must be rejected with 401."""
        response = client.post("/v1/chat", json=SIMPLE_REQUEST)
        assert response.status_code == 401

    def test_wrong_api_key_returns_401(self, client: TestClient) -> None:
        """Request with an incorrect API key must be rejected with 401."""
        response = client.post(
            "/v1/chat",
            json=SIMPLE_REQUEST,
            headers={"X-API-Key": INVALID_API_KEY},
        )
        assert response.status_code == 401

    def test_valid_api_key_accepted(self, client: TestClient) -> None:
        """Request with the correct API key must succeed."""
        response = client.post(
            "/v1/chat",
            json=SIMPLE_REQUEST,
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200

    def test_401_detail_message(self, client: TestClient) -> None:
        """401 response should include a helpful detail message."""
        response = client.post("/v1/chat", json=SIMPLE_REQUEST)
        body = response.json()
        assert "detail" in body


# ---------------------------------------------------------------------------
# Non-streaming response tests
# ---------------------------------------------------------------------------

class TestChatNonStreaming:
    def _post(self, client: TestClient, payload: dict) -> dict:
        response = client.post(
            "/v1/chat",
            json=payload,
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        return response.json()

    def test_response_has_id(self, client: TestClient) -> None:
        body = self._post(client, SIMPLE_REQUEST)
        assert "id" in body
        assert body["id"].startswith("chatcmpl-")

    def test_response_has_message(self, client: TestClient) -> None:
        body = self._post(client, SIMPLE_REQUEST)
        assert "message" in body
        msg = body["message"]
        assert msg["role"] == "assistant"
        assert isinstance(msg["content"], str)
        assert len(msg["content"]) > 0

    def test_response_message_content(self, client: TestClient) -> None:
        body = self._post(client, SIMPLE_REQUEST)
        assert body["message"]["content"] == "This is a test response."

    def test_response_has_model(self, client: TestClient) -> None:
        body = self._post(client, SIMPLE_REQUEST)
        assert body["model"] == "orca-mini"

    def test_response_has_usage(self, client: TestClient) -> None:
        body = self._post(client, SIMPLE_REQUEST)
        assert "usage" in body

    def test_multi_turn_conversation(self, client: TestClient) -> None:
        body = self._post(client, MULTI_TURN_REQUEST)
        assert body["message"]["role"] == "assistant"

    def test_max_tokens_override(self, client: TestClient) -> None:
        payload = {**SIMPLE_REQUEST, "max_tokens": 512}
        body = self._post(client, payload)
        assert body["message"]["content"]

    def test_temperature_override(self, client: TestClient) -> None:
        payload = {**SIMPLE_REQUEST, "temperature": 0.2}
        body = self._post(client, payload)
        assert body["message"]["content"]


# ---------------------------------------------------------------------------
# Streaming tests
# ---------------------------------------------------------------------------

class TestChatStreaming:
    def test_streaming_returns_event_stream_content_type(
        self, client: TestClient
    ) -> None:
        payload = {**SIMPLE_REQUEST, "stream": True}
        response = client.post(
            "/v1/chat",
            json=payload,
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_streaming_body_contains_data_events(self, client: TestClient) -> None:
        payload = {**SIMPLE_REQUEST, "stream": True}
        response = client.post(
            "/v1/chat",
            json=payload,
            headers={"X-API-Key": VALID_API_KEY},
        )
        body_text = response.text
        assert "data:" in body_text

    def test_streaming_ends_with_done(self, client: TestClient) -> None:
        payload = {**SIMPLE_REQUEST, "stream": True}
        response = client.post(
            "/v1/chat",
            json=payload,
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert "[DONE]" in response.text

    def test_streaming_requires_auth(self, client: TestClient) -> None:
        payload = {**SIMPLE_REQUEST, "stream": True}
        response = client.post("/v1/chat", json=payload)
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestChatValidation:
    def test_empty_messages_returns_422(self, client: TestClient) -> None:
        payload = {"messages": []}
        response = client.post(
            "/v1/chat",
            json=payload,
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 422

    def test_missing_messages_field_returns_422(self, client: TestClient) -> None:
        payload = {"stream": False}
        response = client.post(
            "/v1/chat",
            json=payload,
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 422

    def test_invalid_role_returns_422(self, client: TestClient) -> None:
        payload = {
            "messages": [{"role": "robot", "content": "Hi"}],
        }
        response = client.post(
            "/v1/chat",
            json=payload,
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Error-handling tests
# ---------------------------------------------------------------------------

class TestChatErrorHandling:
    def test_llm_error_returns_500(self, client_error: TestClient) -> None:
        response = client_error.post(
            "/v1/chat",
            json=SIMPLE_REQUEST,
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code in (500, 503)

    def test_llm_error_body_has_detail(self, client_error: TestClient) -> None:
        response = client_error.post(
            "/v1/chat",
            json=SIMPLE_REQUEST,
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert "detail" in response.json()
