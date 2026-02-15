"""Tests for container management endpoints"""

import pytest
import httpx
import respx

from moltbunker import Client, AsyncClient
from moltbunker.models import ContainerInfo, Catalog, Migration


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


CONTAINER_RESPONSE = {
    "id": "mb-abc123",
    "image": "python:3.11",
    "status": "running",
    "created_at": "2024-06-01T00:00:00Z",
    "started_at": "2024-06-01T00:00:05Z",
    "encrypted": True,
    "onion_address": "abc123.onion",
    "regions": ["europe", "americas"],
    "locations": [
        {"region": "europe", "country": "DE", "country_name": "Germany", "city": "Frankfurt"},
    ],
    "owner": "0x1234",
    "has_volume": True,
}


class TestContainerManagement:
    """Tests for sync container methods"""

    @respx.mock
    def test_list_containers(self, client, base_url):
        """Test listing containers"""
        respx.get(f"{base_url}/containers").mock(
            return_value=httpx.Response(
                200,
                json={"containers": [CONTAINER_RESPONSE]},
            )
        )

        containers = client.list_containers()

        assert len(containers) == 1
        c = containers[0]
        assert isinstance(c, ContainerInfo)
        assert c.id == "mb-abc123"
        assert c.image == "python:3.11"
        assert c.status == "running"
        assert c.encrypted is True
        assert c.onion_address == "abc123.onion"
        assert len(c.regions) == 2
        assert len(c.locations) == 1
        assert c.locations[0].country == "DE"
        assert c.has_volume is True

    @respx.mock
    def test_list_containers_array_response(self, client, base_url):
        """Test listing containers when API returns array directly"""
        respx.get(f"{base_url}/containers").mock(
            return_value=httpx.Response(200, json=[CONTAINER_RESPONSE])
        )

        containers = client.list_containers()
        assert len(containers) == 1

    @respx.mock
    def test_list_containers_with_filter(self, client, base_url):
        """Test listing containers with filters"""
        route = respx.get(f"{base_url}/containers").mock(
            return_value=httpx.Response(200, json={"containers": []})
        )

        client.list_containers(status="running")

        assert route.called
        assert route.calls[0].request.url.params["status"] == "running"

    @respx.mock
    def test_get_container(self, client, base_url):
        """Test getting a single container"""
        respx.get(f"{base_url}/containers/mb-abc123").mock(
            return_value=httpx.Response(200, json=CONTAINER_RESPONSE)
        )

        c = client.get_container("mb-abc123")

        assert isinstance(c, ContainerInfo)
        assert c.id == "mb-abc123"
        assert c.owner == "0x1234"

    @respx.mock
    def test_stop_container(self, client, base_url):
        """Test stopping a container"""
        route = respx.post(f"{base_url}/containers/mb-abc123/stop").mock(
            return_value=httpx.Response(200, json={"status": "stopped"})
        )

        client.stop_container("mb-abc123")
        assert route.called

    @respx.mock
    def test_start_container(self, client, base_url):
        """Test starting a container"""
        route = respx.post(f"{base_url}/containers/mb-abc123/start").mock(
            return_value=httpx.Response(200, json={"status": "started"})
        )

        client.start_container("mb-abc123")
        assert route.called

    @respx.mock
    def test_delete_container(self, client, base_url):
        """Test deleting a container"""
        route = respx.delete(f"{base_url}/containers/mb-abc123").mock(
            return_value=httpx.Response(204)
        )

        client.delete_container("mb-abc123")
        assert route.called


class TestDeployDirect:
    """Tests for direct deploy"""

    @respx.mock
    def test_deploy_direct_minimal(self, client, base_url):
        """Test deploy_direct with minimal params"""
        respx.post(f"{base_url}/deploy").mock(
            return_value=httpx.Response(
                200,
                json={
                    "container_id": "mb-new123",
                    "status": "pending",
                    "regions": ["europe"],
                    "replica_count": 1,
                },
            )
        )

        result = client.deploy_direct(image="python:3.11")

        assert result["container_id"] == "mb-new123"
        assert result["status"] == "pending"

    @respx.mock
    def test_deploy_direct_full(self, client, base_url):
        """Test deploy_direct with all params"""
        from moltbunker.models import ResourceLimits

        route = respx.post(f"{base_url}/deploy").mock(
            return_value=httpx.Response(
                200,
                json={
                    "container_id": "mb-full123",
                    "status": "running",
                    "regions": ["europe", "americas", "asia_pacific"],
                    "replica_count": 3,
                    "onion_address": "xyz.onion",
                },
            )
        )

        result = client.deploy_direct(
            image="nginx:latest",
            resources=ResourceLimits(cpu_shares=2048, memory_mb=1024),
            duration="24h",
            tor_only=True,
            onion_service=True,
            onion_port=8080,
            wait_for_replicas=True,
            min_provider_tier="standard",
            env={"DEBUG": "1"},
        )

        assert result["replica_count"] == 3
        assert route.called


class TestMigration:
    """Tests for container migration"""

    @respx.mock
    def test_migrate(self, client, base_url):
        """Test migrating a container"""
        respx.post(f"{base_url}/migrate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "migration_id": "mig-123",
                    "status": "pending",
                    "source_region": "europe",
                    "target_region": "americas",
                    "started_at": "2024-06-01T12:00:00Z",
                },
            )
        )

        migration = client.migrate("mb-abc123", target_region="americas")

        assert isinstance(migration, Migration)
        assert migration.migration_id == "mig-123"
        assert migration.status == "pending"
        assert migration.target_region == "americas"


class TestCatalog:
    """Tests for catalog endpoint"""

    @respx.mock
    def test_get_catalog(self, client, base_url):
        """Test getting the catalog"""
        respx.get(f"{base_url}/catalog").mock(
            return_value=httpx.Response(
                200,
                json={
                    "presets": [
                        {
                            "id": "python-basic",
                            "name": "Python Basic",
                            "image": "python:3.11",
                            "description": "Basic Python environment",
                            "category_id": "compute",
                            "default_tier": "starter",
                            "tags": ["python", "ml"],
                            "enabled": True,
                            "sort_order": 1,
                        }
                    ],
                    "categories": [
                        {
                            "id": "compute",
                            "label": "Compute",
                            "enabled": True,
                            "sort_order": 0,
                        }
                    ],
                    "tiers": [
                        {
                            "id": "starter",
                            "name": "Starter",
                            "description": "1 vCPU, 1GB RAM",
                            "cpu": "1 vCPU",
                            "memory": "1 GB",
                            "storage": "10 GB",
                            "monthly": 50000,
                            "enabled": True,
                            "popular": True,
                            "sort_order": 0,
                        }
                    ],
                    "updated_at": "2024-06-01T00:00:00Z",
                    "version": 3,
                },
            )
        )

        catalog = client.get_catalog()

        assert isinstance(catalog, Catalog)
        assert len(catalog.presets) == 1
        assert catalog.presets[0].id == "python-basic"
        assert catalog.presets[0].tags == ["python", "ml"]
        assert len(catalog.categories) == 1
        assert catalog.categories[0].label == "Compute"
        assert len(catalog.tiers) == 1
        assert catalog.tiers[0].monthly == 50000
        assert catalog.tiers[0].popular is True
        assert catalog.version == 3


class TestBalance:
    """Tests for balance with optional address"""

    @respx.mock
    def test_get_balance_default(self, client, base_url):
        """Test getting own balance"""
        respx.get(f"{base_url}/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "wallet_address": "0xabc",
                    "bunker_balance": "1000.0",
                    "eth_balance": "0.5",
                    "deposited": "500.0",
                    "reserved": "100.0",
                    "available": "400.0",
                },
            )
        )

        balance = client.get_balance()
        assert balance.wallet_address == "0xabc"

    @respx.mock
    def test_get_balance_other_address(self, client, base_url):
        """Test getting another wallet's balance"""
        route = respx.get(f"{base_url}/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "wallet_address": "0xother",
                    "bunker_balance": "200.0",
                    "eth_balance": "0.1",
                    "deposited": "100.0",
                    "reserved": "0.0",
                    "available": "100.0",
                },
            )
        )

        balance = client.get_balance(address="0xother")
        assert balance.wallet_address == "0xother"
        assert route.calls[0].request.url.params["address"] == "0xother"


class TestAsyncContainers:
    """Tests for async container methods"""

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_containers_async(self, async_client, base_url):
        """Test async listing containers"""
        respx.get(f"{base_url}/containers").mock(
            return_value=httpx.Response(
                200,
                json={"containers": [CONTAINER_RESPONSE]},
            )
        )

        containers = await async_client.list_containers()

        assert len(containers) == 1
        assert containers[0].id == "mb-abc123"

        await async_client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_deploy_direct_async(self, async_client, base_url):
        """Test async deploy_direct"""
        respx.post(f"{base_url}/deploy").mock(
            return_value=httpx.Response(
                200,
                json={
                    "container_id": "mb-async123",
                    "status": "pending",
                    "regions": ["europe"],
                    "replica_count": 1,
                },
            )
        )

        result = await async_client.deploy_direct(image="python:3.11")
        assert result["container_id"] == "mb-async123"

        await async_client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_catalog_async(self, async_client, base_url):
        """Test async get_catalog"""
        respx.get(f"{base_url}/catalog").mock(
            return_value=httpx.Response(
                200,
                json={
                    "presets": [],
                    "categories": [],
                    "tiers": [],
                    "version": 1,
                },
            )
        )

        catalog = await async_client.get_catalog()
        assert isinstance(catalog, Catalog)
        assert catalog.version == 1

        await async_client.close()
