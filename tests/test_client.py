"""Tests for the Moltbunker client"""

import os
import pytest
import httpx
import respx
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from moltbunker import Client, AsyncClient
from moltbunker.models import ResourceLimits, Region, SnapshotType, CloningConfig
from moltbunker.exceptions import (
    NotFoundError,
    AuthenticationError,
    InsufficientFundsError,
    RateLimitError,
)


@pytest.fixture
def api_key():
    return "mb_test_api_key_12345"


@pytest.fixture
def base_url():
    return "https://api.moltbunker.com/v1"


@pytest.fixture
def client(api_key, base_url):
    return Client(api_key=api_key, base_url=base_url)


@pytest.fixture
def async_client(api_key, base_url):
    return AsyncClient(api_key=api_key, base_url=base_url)


class TestClientCreation:
    """Tests for client instantiation"""

    def test_client_with_api_key(self):
        """Test creating client with API key"""
        client = Client(api_key="mb_test_123456789")
        assert client.auth_type == "api_key"
        # Short keys (<=20 chars) show first 8 + "..."
        assert client.identifier == "mb_test_..."

    def test_client_from_env_api_key(self):
        """Test creating client from environment API key"""
        with patch.dict(os.environ, {"MOLTBUNKER_API_KEY": "mb_test_env123"}):
            client = Client()
            assert client.auth_type == "api_key"

    def test_client_no_auth_raises(self):
        """Test that client without auth raises ValueError"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MOLTBUNKER_API_KEY", None)
            os.environ.pop("MOLTBUNKER_PRIVATE_KEY", None)
            with pytest.raises(ValueError, match="Authentication required"):
                Client()

    def test_client_custom_base_url(self):
        """Test client with custom base URL"""
        client = Client(api_key="mb_test_123", base_url="https://custom.api.com/v1")
        assert client.base_url == "https://custom.api.com/v1"

    def test_client_custom_timeout(self):
        """Test client with custom timeout"""
        client = Client(api_key="mb_test_123", timeout=60.0)
        assert client.timeout == 60.0

    def test_client_network_setting(self):
        """Test client with custom network"""
        client = Client(api_key="mb_test_123", network="ethereum")
        assert client.network == "ethereum"


class TestClient:
    """Tests for synchronous client"""

    @respx.mock
    def test_register_bot(self, client, base_url):
        """Test bot registration"""
        respx.post(f"{base_url}/bots").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "bot_123",
                    "name": "test-bot",
                    "image": "python:3.11",
                    "resources": {
                        "cpu_shares": 1024,
                        "memory_mb": 512,
                        "storage_mb": 1024,
                        "network_mbps": 100,
                    },
                    "region": "americas",
                    "metadata": {},
                    "created_at": "2024-01-01T00:00:00Z",
                },
            )
        )

        bot = client.register_bot(name="test-bot", image="python:3.11")

        assert bot.id == "bot_123"
        assert bot.name == "test-bot"
        assert bot.image == "python:3.11"
        assert bot.resources.memory_mb == 512

    @respx.mock
    def test_get_bot_not_found(self, client, base_url):
        """Test getting non-existent bot"""
        respx.get(f"{base_url}/bots/nonexistent").mock(
            return_value=httpx.Response(
                404,
                json={"error": "Bot not found"},
            )
        )

        with pytest.raises(NotFoundError):
            client.get_bot("nonexistent")

    @respx.mock
    def test_authentication_error(self, client, base_url):
        """Test authentication error"""
        respx.get(f"{base_url}/bots").mock(
            return_value=httpx.Response(
                401,
                json={"error": "Invalid API key"},
            )
        )

        with pytest.raises(AuthenticationError):
            client.list_bots()

    @respx.mock
    def test_insufficient_funds_error(self, client, base_url):
        """Test insufficient funds error"""
        respx.post(f"{base_url}/deployments").mock(
            return_value=httpx.Response(
                402,
                json={
                    "error": "Insufficient BUNKER tokens",
                    "required": 100.0,
                    "available": 50.0,
                },
            )
        )

        with pytest.raises(InsufficientFundsError) as exc_info:
            client.deploy(runtime_id="rt_123")

        assert exc_info.value.required == 100.0
        assert exc_info.value.available == 50.0

    @respx.mock
    def test_rate_limit_error(self, client, base_url):
        """Test rate limit error"""
        respx.get(f"{base_url}/bots").mock(
            return_value=httpx.Response(
                429,
                json={"error": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            client.list_bots()

        assert exc_info.value.retry_after == 60

    @respx.mock
    def test_reserve_runtime(self, client, base_url):
        """Test runtime reservation"""
        respx.post(f"{base_url}/runtimes/reserve").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "runtime_123",
                    "bot_id": "bot_123",
                    "node_id": "node_456",
                    "region": "americas",
                    "resources": {
                        "cpu_shares": 1024,
                        "memory_mb": 512,
                        "storage_mb": 1024,
                        "network_mbps": 100,
                    },
                    "expires_at": "2024-01-01T01:00:00Z",
                },
            )
        )

        runtime = client.reserve_runtime(
            bot_id="bot_123",
            min_memory_mb=512,
        )

        assert runtime.id == "runtime_123"
        assert runtime.bot_id == "bot_123"
        assert runtime.region == "americas"

    @respx.mock
    def test_deploy(self, client, base_url):
        """Test deployment"""
        respx.post(f"{base_url}/deployments").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "deployment_123",
                    "bot_id": "bot_123",
                    "runtime_id": "runtime_123",
                    "container_id": "container_789",
                    "status": "running",
                    "region": "americas",
                    "node_id": "node_456",
                    "created_at": "2024-01-01T00:00:00Z",
                    "started_at": "2024-01-01T00:00:05Z",
                },
            )
        )

        deployment = client.deploy(
            runtime_id="runtime_123",
            env={"DEBUG": "true"},
        )

        assert deployment.id == "deployment_123"
        assert deployment.status == "running"
        assert deployment.container_id == "container_789"

    @respx.mock
    def test_create_snapshot(self, client, base_url):
        """Test snapshot creation"""
        respx.post(f"{base_url}/snapshots").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "snapshot_123",
                    "container_id": "container_789",
                    "type": "full",
                    "size": 1024000,
                    "stored_size": 512000,
                    "checksum": "abc123",
                    "compressed": True,
                    "encrypted": True,
                    "created_at": "2024-01-01T00:00:00Z",
                    "metadata": {},
                },
            )
        )

        snapshot = client.create_snapshot(
            container_id="container_789",
            snapshot_type=SnapshotType.FULL,
        )

        assert snapshot.id == "snapshot_123"
        assert snapshot.compressed is True
        assert snapshot.encrypted is True
        assert snapshot.stored_size < snapshot.size

    @respx.mock
    def test_clone(self, client, base_url):
        """Test cloning"""
        respx.post(f"{base_url}/clones").mock(
            return_value=httpx.Response(
                200,
                json={
                    "clone_id": "clone_123",
                    "source_id": "container_789",
                    "target_region": "europe",
                    "status": "pending",
                    "priority": 2,
                    "reason": "manual_clone",
                    "created_at": "2024-01-01T00:00:00Z",
                },
            )
        )

        clone = client.clone(
            container_id="container_789",
            target_region=Region.EUROPE,
        )

        assert clone.clone_id == "clone_123"
        assert clone.target_region == "europe"
        assert clone.status == "pending"

    @respx.mock
    def test_get_threat_level(self, client, base_url):
        """Test getting threat level"""
        respx.get(f"{base_url}/threat").mock(
            return_value=httpx.Response(
                200,
                json={
                    "score": 0.3,
                    "level": "low",
                    "recommendation": "continue_normal",
                    "active_signals": [
                        {
                            "type": "network_anomaly",
                            "score": 0.3,
                            "confidence": 0.8,
                            "source": "network_monitor",
                            "details": "Unusual traffic pattern",
                            "timestamp": "2024-01-01T00:00:00Z",
                        }
                    ],
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            )
        )

        threat = client.get_threat_level()

        assert threat.score == 0.3
        assert threat.level.value == "low"
        assert len(threat.active_signals) == 1
        assert threat.active_signals[0].type == "network_anomaly"

    @respx.mock
    def test_detect_threat(self, client, base_url):
        """Test detect_threat returns float score"""
        respx.get(f"{base_url}/threat").mock(
            return_value=httpx.Response(
                200,
                json={
                    "score": 0.15,
                    "level": "low",
                    "recommendation": "continue_normal",
                    "active_signals": [],
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            )
        )

        score = client.detect_threat()

        assert score == 0.15
        assert isinstance(score, float)

    @respx.mock
    def test_get_balance(self, client, base_url):
        """Test getting wallet balance"""
        respx.get(f"{base_url}/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "wallet_address": "0x1234567890abcdef",
                    "bunker_balance": "100.5",
                    "eth_balance": "0.1",
                    "deposited": "50.0",
                    "reserved": "20.0",
                    "available": "30.0",
                },
            )
        )

        balance = client.get_balance()

        assert balance.wallet_address == "0x1234567890abcdef"
        assert balance.bunker_balance == 100.5
        assert balance.available == 30.0


class TestBotMethods:
    """Tests for Bot object methods"""

    @pytest.fixture
    def mock_bot(self):
        """Create a bot with mocked client"""
        from moltbunker.models import Bot

        bot = Bot(
            id="bot-123",
            name="test-bot",
            image="python:3.11",
            resources=ResourceLimits(),
            region="americas",
            created_at=datetime.now(timezone.utc),
        )

        mock_client = MagicMock()
        bot._client = mock_client
        return bot

    def test_bot_reserve_runtime(self, mock_bot):
        """Test bot reserve_runtime method"""
        from moltbunker.models import Runtime

        mock_bot._client.reserve_runtime.return_value = Runtime(
            id="rt-123",
            bot_id="bot-123",
            node_id="node-1",
            region="americas",
            resources=ResourceLimits(),
            expires_at=datetime.now(timezone.utc),
        )

        runtime = mock_bot.reserve_runtime(min_memory_mb=1024)

        assert runtime.id == "rt-123"
        mock_bot._client.reserve_runtime.assert_called_once()

    def test_bot_deploy(self, mock_bot):
        """Test bot deploy method"""
        from moltbunker.models import Runtime, Deployment

        mock_bot._client.reserve_runtime.return_value = Runtime(
            id="rt-456",
            bot_id="bot-123",
            node_id="node-1",
            region="americas",
            resources=ResourceLimits(),
            expires_at=datetime.now(timezone.utc),
        )

        mock_bot._client.deploy.return_value = Deployment(
            id="dep-123",
            bot_id="bot-123",
            runtime_id="rt-456",
            container_id="mb-789",
            status="running",
            region="americas",
            node_id="node-1",
            created_at=datetime.now(timezone.utc),
        )

        deployment = mock_bot.deploy()

        assert deployment.id == "dep-123"
        assert deployment.container_id == "mb-789"

    def test_bot_enable_cloning(self, mock_bot):
        """Test bot enable_cloning method"""
        mock_bot._client._request.return_value = {}

        mock_bot.enable_cloning(
            auto_clone_on_threat=True,
            max_clones=5,
        )

        mock_bot._client._request.assert_called_once()
        call_args = mock_bot._client._request.call_args
        assert call_args[0][0] == "POST"
        assert "/cloning" in call_args[0][1]

    def test_bot_detect_threat(self, mock_bot):
        """Test bot detect_threat method"""
        mock_bot._client.detect_threat.return_value = 0.25

        threat = mock_bot.detect_threat()

        assert threat == 0.25
        mock_bot._client.detect_threat.assert_called_once()

    def test_bot_without_client_raises(self):
        """Test that bot methods raise without client"""
        from moltbunker.models import Bot

        bot = Bot(
            id="bot-123",
            name="test-bot",
            image="python:3.11",
            resources=ResourceLimits(),
            region="americas",
            created_at=datetime.now(timezone.utc),
        )

        with pytest.raises(ValueError, match="not associated with a client"):
            bot.reserve_runtime()


class TestAsyncClient:
    """Tests for asynchronous client"""

    @respx.mock
    @pytest.mark.asyncio
    async def test_register_bot_async(self, async_client, base_url):
        """Test async bot registration"""
        respx.post(f"{base_url}/bots").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "bot_123",
                    "name": "test-bot",
                    "image": "python:3.11",
                    "resources": {
                        "cpu_shares": 1024,
                        "memory_mb": 512,
                        "storage_mb": 1024,
                        "network_mbps": 100,
                    },
                    "region": "americas",
                    "metadata": {},
                    "created_at": "2024-01-01T00:00:00Z",
                },
            )
        )

        bot = await async_client.register_bot(name="test-bot", image="python:3.11")

        assert bot.id == "bot_123"
        assert bot.name == "test-bot"

        await async_client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_deploy_async(self, async_client, base_url):
        """Test async deployment"""
        respx.post(f"{base_url}/deployments").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "deployment_123",
                    "bot_id": "bot_123",
                    "runtime_id": "runtime_123",
                    "container_id": "container_789",
                    "status": "running",
                    "region": "americas",
                    "node_id": "node_456",
                    "created_at": "2024-01-01T00:00:00Z",
                },
            )
        )

        deployment = await async_client.deploy(runtime_id="runtime_123")

        assert deployment.id == "deployment_123"
        assert deployment.status == "running"

        await async_client.close()


class TestModels:
    """Tests for data models"""

    def test_resource_limits_defaults(self):
        """Test ResourceLimits defaults"""
        limits = ResourceLimits()
        assert limits.cpu_shares == 1024
        assert limits.memory_mb == 512
        assert limits.storage_mb == 1024
        assert limits.network_mbps == 100

    def test_resource_limits_custom(self):
        """Test custom ResourceLimits"""
        limits = ResourceLimits(
            cpu_shares=2048,
            memory_mb=1024,
            storage_mb=2048,
            network_mbps=200,
        )
        assert limits.cpu_shares == 2048
        assert limits.memory_mb == 1024

    def test_region_values(self):
        """Test Region enum values"""
        assert Region.AMERICAS.value == "americas"
        assert Region.EUROPE.value == "europe"
        assert Region.ASIA_PACIFIC.value == "asia_pacific"

    def test_snapshot_type_values(self):
        """Test SnapshotType enum values"""
        assert SnapshotType.FULL.value == "full"
        assert SnapshotType.INCREMENTAL.value == "incremental"
        assert SnapshotType.CHECKPOINT.value == "checkpoint"

    def test_cloning_config(self):
        """Test CloningConfig model"""
        config = CloningConfig(
            enabled=True,
            auto_clone_on_threat=True,
            max_clones=5,
        )

        assert config.enabled is True
        assert config.max_clones == 5
        assert config.clone_delay_seconds == 60  # default

    def test_cloning_config_defaults(self):
        """Test CloningConfig defaults"""
        config = CloningConfig()

        assert config.enabled is True
        assert config.auto_clone_on_threat is True
        assert config.max_clones == 10
        assert config.sync_state is False
