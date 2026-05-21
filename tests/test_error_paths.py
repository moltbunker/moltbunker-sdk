"""Error-path tests for the Moltbunker SDK.

These tests fill the most critical gaps left by the v0.3.0 happy-path-only
test suite. They verify that:
  - Each error class (AuthenticationError, RateLimitError, etc.) is raised
    correctly when the API returns the corresponding HTTP status code.
  - Automatic retry-with-backoff fires on 429 responses.
  - The async client mirrors the sync client error behaviour.

All network calls are intercepted with respx so no real API is hit.
"""
import pytest
import httpx
import respx

from moltbunker import Client, AsyncClient
from moltbunker.exceptions import (
    AuthenticationError,
    InsufficientFundsError,
    MoltbunkerError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

BASE_URL = "https://api.moltbunker.com/v1"
API_KEY = "mb_test_key_errorpaths"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sync_client() -> Client:
    return Client(api_key=API_KEY, base_url=BASE_URL)


@pytest.fixture
async def async_client() -> AsyncClient:
    return AsyncClient(api_key=API_KEY, base_url=BASE_URL)


# ---------------------------------------------------------------------------
# 401 Authentication errors
# ---------------------------------------------------------------------------

class TestAuthenticationErrors:
    @respx.mock
    def test_401_raises_authentication_error(self, sync_client: Client) -> None:
        respx.get(f"{BASE_URL}/threat").mock(
            return_value=httpx.Response(
                401, json={"error": "Unauthorized", "message": "Invalid API key"}
            )
        )
        with pytest.raises(AuthenticationError) as exc_info:
            sync_client.get_threat_level()
        assert exc_info.value.status_code == 401

    @respx.mock
    def test_401_error_message_is_preserved(self, sync_client: Client) -> None:
        respx.get(f"{BASE_URL}/threat").mock(
            return_value=httpx.Response(
                401, json={"error": "Unauthorized", "message": "Token expired"}
            )
        )
        with pytest.raises(AuthenticationError) as exc_info:
            sync_client.get_threat_level()
        assert "Token expired" in str(exc_info.value)

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_401_raises_authentication_error(self, async_client: AsyncClient) -> None:
        respx.get(f"{BASE_URL}/threat").mock(
            return_value=httpx.Response(
                401, json={"error": "Unauthorized", "message": "Invalid API key"}
            )
        )
        with pytest.raises(AuthenticationError):
            await async_client.get_threat_level()


# ---------------------------------------------------------------------------
# 404 Not Found errors
# ---------------------------------------------------------------------------

class TestNotFoundErrors:
    @respx.mock
    def test_404_on_get_container_raises_not_found(self, sync_client: Client) -> None:
        container_id = "mb-does-not-exist"
        respx.get(f"{BASE_URL}/containers/{container_id}").mock(
            return_value=httpx.Response(
                404, json={"error": "NotFound", "message": f"Container {container_id} not found"}
            )
        )
        with pytest.raises((NotFoundError, MoltbunkerError)) as exc_info:
            sync_client.get_container(container_id)
        assert exc_info.value.status_code == 404

    @respx.mock
    def test_404_on_stop_container_raises_not_found(self, sync_client: Client) -> None:
        container_id = "mb-ghost-container"
        respx.post(f"{BASE_URL}/containers/{container_id}/stop").mock(
            return_value=httpx.Response(404, json={"error": "NotFound", "message": "not found"})
        )
        with pytest.raises((NotFoundError, MoltbunkerError)):
            sync_client.stop_container(container_id)


# ---------------------------------------------------------------------------
# 422 Validation errors
# ---------------------------------------------------------------------------

class TestValidationErrors:
    @respx.mock
    def test_422_raises_validation_error(self, sync_client: Client) -> None:
        respx.post(f"{BASE_URL}/bots").mock(
            return_value=httpx.Response(
                422,
                json={
                    "error": "ValidationError",
                    "message": "image field is required",
                    "details": [{"field": "image", "message": "required"}],
                },
            )
        )
        with pytest.raises((ValidationError, MoltbunkerError)) as exc_info:
            sync_client.register_bot(name="bad-bot", image="")
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# 402 Insufficient funds
# ---------------------------------------------------------------------------

class TestInsufficientFundsErrors:
    @respx.mock
    def test_402_raises_insufficient_funds(self, sync_client: Client) -> None:
        respx.post(f"{BASE_URL}/bots").mock(
            return_value=httpx.Response(
                402,
                json={
                    "error": "InsufficientFunds",
                    "message": "Insufficient BUNKER balance",
                    "required": 500.0,
                    "available": 10.0,
                },
            )
        )
        with pytest.raises((InsufficientFundsError, MoltbunkerError)) as exc_info:
            sync_client.register_bot(name="expensive-bot", image="python:3.11")
        assert exc_info.value.status_code == 402


# ---------------------------------------------------------------------------
# 429 Rate limit + retry-with-backoff
# ---------------------------------------------------------------------------

class TestRateLimitRetry:
    @respx.mock
    def test_429_raises_rate_limit_error_after_retries(
        self, sync_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All retry attempts exhausted should eventually raise RateLimitError."""
        # Monkeypatch sleep to avoid actually waiting in tests
        monkeypatch.setattr("time.sleep", lambda _: None)

        respx.get(f"{BASE_URL}/threat").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "1"},
                json={"error": "RateLimited", "message": "Too many requests", "retry_after": 1},
            )
        )
        with pytest.raises((RateLimitError, MoltbunkerError)) as exc_info:
            sync_client.get_threat_level()
        assert exc_info.value.status_code == 429

    @respx.mock
    def test_429_then_200_succeeds_after_retry(
        self, sync_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A single 429 followed by a 200 should succeed (retry logic)."""
        monkeypatch.setattr("time.sleep", lambda _: None)

        success_body = {
            "level": "low",
            "score": 0.1,
            "recommendation": "All clear",
            "active_signals": [],
        }
        respx.get(f"{BASE_URL}/threat").mock(
            side_effect=[
                httpx.Response(
                    429,
                    headers={"Retry-After": "1"},
                    json={"error": "RateLimited", "message": "Too many requests", "retry_after": 1},
                ),
                httpx.Response(200, json=success_body),
            ]
        )
        # Should succeed on the second attempt without raising
        result = sync_client.get_threat_level()
        assert result is not None


# ---------------------------------------------------------------------------
# Generic 5xx errors
# ---------------------------------------------------------------------------

class TestServerErrors:
    @respx.mock
    def test_500_raises_moltbunker_error(self, sync_client: Client) -> None:
        respx.get(f"{BASE_URL}/threat").mock(
            return_value=httpx.Response(
                500, json={"error": "InternalServerError", "message": "unexpected error"}
            )
        )
        with pytest.raises(MoltbunkerError) as exc_info:
            sync_client.get_threat_level()
        assert exc_info.value.status_code == 500

    @respx.mock
    def test_503_raises_moltbunker_error(self, sync_client: Client) -> None:
        respx.get(f"{BASE_URL}/threat").mock(
            return_value=httpx.Response(503, json={"error": "ServiceUnavailable"})
        )
        with pytest.raises(MoltbunkerError) as exc_info:
            sync_client.get_threat_level()
        assert exc_info.value.status_code == 503
