"""Tests for Crawl and Agent API methods"""

import pytest
import httpx
import respx

from moltbunker import Client, AsyncClient
from moltbunker.models import (
    AgentDeployment,
    AgentInvokeResponse,
    AgentSpec,
    AgentStatus,
    CrawlConfig,
    CrawlJob,
    CrawlJobStatus,
    CrawlResult,
    CrawlStats,
    MCPToolDef,
    MemoryEntry,
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


# --- Crawl Tests ---


class TestCrawlSync:
    """Synchronous crawl method tests"""

    @respx.mock
    def test_create_crawl_job(self, client, base_url):
        respx.post(f"{base_url}/crawl/jobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "crawl_001",
                    "owner": "0xabc",
                    "status": "pending",
                    "config": {
                        "urls": ["https://example.com"],
                        "max_depth": 2,
                        "max_pages": 50,
                    },
                    "created_at": "2026-03-01T00:00:00Z",
                    "pages_crawled": 0,
                    "total_bytes": 0,
                },
            )
        )

        job = client.create_crawl_job(
            urls=["https://example.com"],
            max_depth=2,
            max_pages=50,
        )

        assert job.id == "crawl_001"
        assert job.status == "pending"
        assert job.config is not None
        assert job.config.urls == ["https://example.com"]
        assert job.config.max_depth == 2

    @respx.mock
    def test_list_crawl_jobs(self, client, base_url):
        respx.get(f"{base_url}/crawl/jobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": "crawl_001",
                            "status": "completed",
                            "created_at": "2026-03-01T00:00:00Z",
                            "pages_crawled": 10,
                            "total_bytes": 50000,
                        },
                        {
                            "id": "crawl_002",
                            "status": "running",
                            "created_at": "2026-03-01T01:00:00Z",
                            "pages_crawled": 3,
                            "total_bytes": 12000,
                        },
                    ]
                },
            )
        )

        jobs = client.list_crawl_jobs()

        assert len(jobs) == 2
        assert jobs[0].id == "crawl_001"
        assert jobs[0].pages_crawled == 10
        assert jobs[1].status == "running"

    @respx.mock
    def test_get_crawl_job(self, client, base_url):
        respx.get(f"{base_url}/crawl/jobs/crawl_001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "crawl_001",
                    "status": "completed",
                    "created_at": "2026-03-01T00:00:00Z",
                    "completed_at": "2026-03-01T00:05:00Z",
                    "pages_crawled": 10,
                    "total_bytes": 50000,
                },
            )
        )

        job = client.get_crawl_job("crawl_001")

        assert job.id == "crawl_001"
        assert job.status == "completed"
        assert job.completed_at is not None

    @respx.mock
    def test_get_crawl_results(self, client, base_url):
        respx.get(f"{base_url}/crawl/jobs/crawl_001/results").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.com",
                            "status_code": 200,
                            "content_type": "text/html",
                            "title": "Example Domain",
                            "text": "This domain is for examples.",
                            "links": ["https://www.iana.org/domains/example"],
                            "crawled_at": "2026-03-01T00:00:01Z",
                            "duration_ms": 250,
                            "byte_size": 1256,
                        }
                    ]
                },
            )
        )

        results = client.get_crawl_results("crawl_001")

        assert len(results) == 1
        assert results[0].url == "https://example.com"
        assert results[0].status_code == 200
        assert results[0].title == "Example Domain"
        assert results[0].byte_size == 1256

    @respx.mock
    def test_cancel_crawl_job(self, client, base_url):
        respx.post(f"{base_url}/crawl/jobs/crawl_001/cancel").mock(
            return_value=httpx.Response(204)
        )

        client.cancel_crawl_job("crawl_001")

    @respx.mock
    def test_crawl_page(self, client, base_url):
        respx.post(f"{base_url}/crawl/pages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "crawl_003",
                    "status": "completed",
                    "created_at": "2026-03-01T00:00:00Z",
                    "pages_crawled": 1,
                    "total_bytes": 2048,
                    "results": [
                        {
                            "url": "https://example.com",
                            "status_code": 200,
                            "title": "Example",
                            "crawled_at": "2026-03-01T00:00:00Z",
                            "duration_ms": 150,
                            "byte_size": 2048,
                        }
                    ],
                },
            )
        )

        job = client.crawl_page(url="https://example.com", javascript=True)

        assert job.id == "crawl_003"
        assert job.pages_crawled == 1
        assert len(job.results) == 1

    @respx.mock
    def test_get_crawl_stats(self, client, base_url):
        respx.get(f"{base_url}/crawl/stats").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_jobs": 42,
                    "running_jobs": 3,
                    "completed_jobs": 35,
                    "failed_jobs": 4,
                    "total_pages_crawled": 1500,
                    "total_bytes": 75000000,
                },
            )
        )

        stats = client.get_crawl_stats()

        assert stats.total_jobs == 42
        assert stats.running_jobs == 3
        assert stats.total_pages_crawled == 1500


# --- Agent Tests ---


class TestAgentSync:
    """Synchronous agent method tests"""

    @respx.mock
    def test_deploy_agent(self, client, base_url):
        respx.post(f"{base_url}/agents").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "agent_001",
                    "spec": {
                        "name": "my-agent",
                        "framework": "langgraph",
                        "image": "python:3.12-slim",
                        "env": {"FRAMEWORK": "langgraph"},
                        "mcp_tools": [
                            {"name": "web_fetch", "description": "Fetch URL"},
                        ],
                    },
                    "status": "pending",
                    "created_at": "2026-03-01T00:00:00Z",
                    "tokens_used": 0,
                    "invocation_count": 0,
                },
            )
        )

        agent = client.deploy_agent(
            name="my-agent",
            framework="langgraph",
            mcp_tools=[MCPToolDef(name="web_fetch", description="Fetch URL")],
        )

        assert agent.id == "agent_001"
        assert agent.status == "pending"
        assert agent.spec is not None
        assert agent.spec.framework == "langgraph"
        assert len(agent.spec.mcp_tools) == 1

    @respx.mock
    def test_list_agents(self, client, base_url):
        respx.get(f"{base_url}/agents").mock(
            return_value=httpx.Response(
                200,
                json={
                    "agents": [
                        {
                            "id": "agent_001",
                            "status": "running",
                            "created_at": "2026-03-01T00:00:00Z",
                            "tokens_used": 500,
                            "invocation_count": 10,
                        },
                    ]
                },
            )
        )

        agents = client.list_agents()

        assert len(agents) == 1
        assert agents[0].id == "agent_001"
        assert agents[0].tokens_used == 500

    @respx.mock
    def test_get_agent(self, client, base_url):
        respx.get(f"{base_url}/agents/agent_001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "agent_001",
                    "spec": {"name": "my-agent", "framework": "custom"},
                    "status": "running",
                    "container_id": "mb-container-123",
                    "node_id": "node-456",
                    "created_at": "2026-03-01T00:00:00Z",
                    "started_at": "2026-03-01T00:00:05Z",
                    "tokens_used": 1200,
                    "invocation_count": 25,
                },
            )
        )

        agent = client.get_agent("agent_001")

        assert agent.id == "agent_001"
        assert agent.container_id == "mb-container-123"
        assert agent.invocation_count == 25

    @respx.mock
    def test_delete_agent(self, client, base_url):
        respx.delete(f"{base_url}/agents/agent_001").mock(
            return_value=httpx.Response(204)
        )

        client.delete_agent("agent_001")

    @respx.mock
    def test_invoke_agent(self, client, base_url):
        respx.post(f"{base_url}/agents/agent_001/invoke").mock(
            return_value=httpx.Response(
                200,
                json={
                    "agent_id": "agent_001",
                    "response": "Hello! I'm your AI agent.",
                    "tokens_used": 42,
                    "duration_ms": 1500,
                },
            )
        )

        resp = client.invoke_agent(
            agent_id="agent_001",
            message="Hello!",
            context={"session": "abc"},
        )

        assert resp.agent_id == "agent_001"
        assert resp.response == "Hello! I'm your AI agent."
        assert resp.tokens_used == 42
        assert resp.duration_ms == 1500

    @respx.mock
    def test_stop_agent(self, client, base_url):
        respx.post(f"{base_url}/agents/agent_001/stop").mock(
            return_value=httpx.Response(204)
        )

        client.stop_agent("agent_001")

    @respx.mock
    def test_list_agent_memory(self, client, base_url):
        respx.get(f"{base_url}/agents/agent_001/memory").mock(
            return_value=httpx.Response(
                200,
                json={
                    "entries": [
                        {
                            "key": "user_pref",
                            "value": "dark_mode",
                            "updated_at": "2026-03-01T00:00:00Z",
                        },
                        {
                            "key": "last_topic",
                            "value": "python",
                            "updated_at": "2026-03-01T01:00:00Z",
                        },
                    ]
                },
            )
        )

        entries = client.list_agent_memory("agent_001")

        assert len(entries) == 2
        assert entries[0].key == "user_pref"
        assert entries[0].value == "dark_mode"
        assert entries[1].key == "last_topic"

    @respx.mock
    def test_set_agent_memory(self, client, base_url):
        respx.post(f"{base_url}/agents/agent_001/memory").mock(
            return_value=httpx.Response(204)
        )

        client.set_agent_memory("agent_001", key="mood", value="happy")

    @respx.mock
    def test_delete_agent_memory(self, client, base_url):
        respx.delete(f"{base_url}/agents/agent_001/memory").mock(
            return_value=httpx.Response(204)
        )

        client.delete_agent_memory("agent_001", key="mood")


# --- Async Tests ---


class TestCrawlAsync:
    """Async crawl method tests"""

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_crawl_job_async(self, async_client, base_url):
        respx.post(f"{base_url}/crawl/jobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "crawl_async_001",
                    "status": "pending",
                    "config": {"urls": ["https://example.com"], "max_depth": 1, "max_pages": 10},
                    "created_at": "2026-03-01T00:00:00Z",
                    "pages_crawled": 0,
                    "total_bytes": 0,
                },
            )
        )

        job = await async_client.create_crawl_job(urls=["https://example.com"], max_depth=1)

        assert job.id == "crawl_async_001"
        assert job.status == "pending"

        await async_client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_crawl_stats_async(self, async_client, base_url):
        respx.get(f"{base_url}/crawl/stats").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_jobs": 10,
                    "running_jobs": 1,
                    "completed_jobs": 8,
                    "failed_jobs": 1,
                    "total_pages_crawled": 200,
                    "total_bytes": 5000000,
                },
            )
        )

        stats = await async_client.get_crawl_stats()

        assert stats.total_jobs == 10
        assert stats.completed_jobs == 8

        await async_client.close()


class TestAgentAsync:
    """Async agent method tests"""

    @respx.mock
    @pytest.mark.asyncio
    async def test_deploy_agent_async(self, async_client, base_url):
        respx.post(f"{base_url}/agents").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "agent_async_001",
                    "spec": {"name": "async-agent", "framework": "crewai"},
                    "status": "pending",
                    "created_at": "2026-03-01T00:00:00Z",
                    "tokens_used": 0,
                    "invocation_count": 0,
                },
            )
        )

        agent = await async_client.deploy_agent(name="async-agent", framework="crewai")

        assert agent.id == "agent_async_001"
        assert agent.spec.framework == "crewai"

        await async_client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_invoke_agent_async(self, async_client, base_url):
        respx.post(f"{base_url}/agents/agent_001/invoke").mock(
            return_value=httpx.Response(
                200,
                json={
                    "agent_id": "agent_001",
                    "response": "Async response!",
                    "tokens_used": 30,
                    "duration_ms": 800,
                },
            )
        )

        resp = await async_client.invoke_agent(agent_id="agent_001", message="Hi")

        assert resp.response == "Async response!"
        assert resp.tokens_used == 30

        await async_client.close()


# --- Model Tests ---


class TestCrawlAgentModels:
    """Tests for new model classes"""

    def test_crawl_config_defaults(self):
        config = CrawlConfig()
        assert config.max_depth == 0
        assert config.max_pages == 100
        assert config.screenshot is False
        assert config.use_tor is False

    def test_crawl_job_status_enum(self):
        assert CrawlJobStatus.PENDING.value == "pending"
        assert CrawlJobStatus.RUNNING.value == "running"
        assert CrawlJobStatus.COMPLETED.value == "completed"
        assert CrawlJobStatus.CANCELLED.value == "cancelled"

    def test_agent_status_enum(self):
        assert AgentStatus.PENDING.value == "pending"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.STOPPED.value == "stopped"

    def test_agent_spec_defaults(self):
        spec = AgentSpec(name="test")
        assert spec.framework == "custom"
        assert spec.image == ""
        assert spec.max_tokens == 0
        assert spec.mcp_tools == []

    def test_mcp_tool_def(self):
        tool = MCPToolDef(name="web_fetch", description="Fetch a URL")
        assert tool.name == "web_fetch"
        assert tool.parameters == {}

    def test_memory_entry(self):
        entry = MemoryEntry(key="k", value="v")
        assert entry.key == "k"
        assert entry.updated_at is None

    def test_crawl_stats_defaults(self):
        stats = CrawlStats()
        assert stats.total_jobs == 0
        assert stats.total_bytes == 0

    def test_agent_invoke_response(self):
        resp = AgentInvokeResponse(
            agent_id="a1", response="hello", tokens_used=10, duration_ms=50
        )
        assert resp.agent_id == "a1"
        assert resp.error == ""
