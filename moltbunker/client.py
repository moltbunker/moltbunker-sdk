"""Moltbunker SDK Client

Permissionless P2P container runtime for AI agents.

Usage:
    # Wallet authentication (permissionless)
    from moltbunker import Client

    client = Client(private_key="0x...")
    bot = client.register_bot(name="my-agent", image="python:3.11")
    bot.enable_cloning(auto_clone_on_threat=True)
    deployment = bot.deploy()

    # API key authentication
    client = Client(api_key="mb_live_xxx")
"""

import httpx
from datetime import datetime
from typing import Optional, Dict, Any, List, Union

from .auth import AuthStrategy, APIKeyAuth, WalletAuth, get_auth_from_env
from .models import (
    Bot,
    Runtime,
    Deployment,
    Snapshot,
    Clone,
    ThreatLevel,
    ResourceLimits,
    Region,
    SnapshotType,
    WalletBalance,
    ThreatSignal,
    ThreatLevelValue,
)
from .exceptions import (
    MoltbunkerError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    InsufficientFundsError,
    ConnectionError,
    TimeoutError,
)


DEFAULT_BASE_URL = "https://api.moltbunker.com/v1"
DEFAULT_TIMEOUT = 30.0


class BaseClient:
    """Base client with common functionality"""

    def __init__(
        self,
        auth: AuthStrategy,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        network: str = "base",
    ):
        self._auth = auth
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.network = network

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "moltbunker-python/0.1.0",
        }
        headers.update(self._auth.get_auth_headers())
        return headers

    @property
    def auth_type(self) -> str:
        """Get the authentication type."""
        return self._auth.auth_type

    @property
    def identifier(self) -> str:
        """Get the user identifier (wallet address or API key prefix)."""
        return self._auth.identifier

    def _handle_error(self, response: httpx.Response) -> None:
        """Handle HTTP error responses"""
        status = response.status_code
        try:
            data = response.json()
            message = data.get("error", data.get("message", response.text))
        except Exception:
            message = response.text or f"HTTP {status}"

        if status == 401:
            raise AuthenticationError(message, status)
        elif status == 402:
            # Payment required - insufficient funds
            try:
                data = response.json()
                raise InsufficientFundsError(
                    message,
                    required=data.get("required"),
                    available=data.get("available"),
                    status_code=status,
                )
            except (KeyError, TypeError):
                raise InsufficientFundsError(message, status_code=status)
        elif status == 404:
            raise NotFoundError(message, status)
        elif status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                message,
                retry_after=int(retry_after) if retry_after else None,
                status_code=status,
            )
        elif 400 <= status < 500:
            raise MoltbunkerError(message, status)
        elif status >= 500:
            raise MoltbunkerError(f"Server error: {message}", status)


class Client(BaseClient):
    """Synchronous Moltbunker client for AI agents.

    Supports permissionless wallet authentication or managed API key authentication.

    Example:
        # Wallet auth (permissionless)
        client = Client(private_key="0x...")

        # API key auth
        client = Client(api_key="mb_live_xxx")

        # From environment variables
        client = Client()  # Uses MOLTBUNKER_PRIVATE_KEY or MOLTBUNKER_API_KEY
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        private_key: Optional[str] = None,
        wallet_address: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        network: str = "base",
    ):
        """Initialize the Moltbunker client.

        Args:
            api_key: API key for authentication (mb_live_xxx or mb_test_xxx)
            private_key: Ethereum private key for wallet authentication
            wallet_address: Optional wallet address override
            base_url: API base URL
            timeout: Request timeout in seconds
            network: Blockchain network (default: "base")

        Raises:
            ValueError: If no authentication credentials provided
        """
        # Determine auth strategy
        auth: Optional[AuthStrategy] = None

        if api_key:
            auth = APIKeyAuth(api_key)
        elif private_key:
            auth = WalletAuth(private_key, wallet_address)
        else:
            # Try environment variables
            auth = get_auth_from_env()

        if auth is None:
            raise ValueError(
                "Authentication required. Provide api_key, private_key, "
                "or set MOLTBUNKER_API_KEY/MOLTBUNKER_PRIVATE_KEY environment variables."
            )

        super().__init__(auth, base_url, timeout, network)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self._get_headers(),
            timeout=timeout,
        )

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """Close the client connection."""
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request."""
        try:
            # Refresh auth headers (for wallet auth with timestamps)
            self._client.headers.update(self._auth.get_auth_headers())

            response = self._client.request(
                method,
                path,
                json=json,
                params=params,
            )

            if response.status_code >= 400:
                self._handle_error(response)

            if response.status_code == 204:
                return {}

            return response.json()

        except httpx.ConnectError as e:
            raise ConnectionError(f"Failed to connect to API: {e}")
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request timed out: {e}")

    # Bot Registration

    def register_bot(
        self,
        name: str,
        image: str,
        description: Optional[str] = None,
        resources: Optional[ResourceLimits] = None,
        region: Optional[Region] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Bot:
        """Register a new bot.

        Args:
            name: Bot name
            image: Container image (e.g., "python:3.11")
            description: Bot description
            resources: Resource limits
            region: Deployment region
            metadata: Additional metadata

        Returns:
            Registered Bot object

        Example:
            bot = client.register_bot(
                name="my-agent",
                image="python:3.11",
                resources=ResourceLimits(cpu_shares=2048, memory_mb=4096),
            )
        """

        if resources is None:
            resources = ResourceLimits()

        payload: Dict[str, Any] = {
            "name": name,
            "image": image,
            "resources": resources.model_dump(),
            "metadata": metadata or {},
        }
        if description:
            payload["description"] = description
        if region:
            payload["region"] = region.value

        data = self._request("POST", "/bots", json=payload)

        bot = Bot(
            id=data["id"],
            name=data["name"],
            image=data["image"],
            description=data.get("description"),
            resources=ResourceLimits(**data.get("resources", {})),
            region=data.get("region", ""),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        )
        bot._client = self
        return bot

    def get_bot(self, bot_id: str) -> Bot:
        """Get bot by ID."""
        data = self._request("GET", f"/bots/{bot_id}")
        bot = Bot(
            id=data["id"],
            name=data["name"],
            image=data["image"],
            description=data.get("description"),
            resources=ResourceLimits(**data.get("resources", {})),
            region=data.get("region", ""),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        )
        bot._client = self
        return bot

    def list_bots(self) -> List[Bot]:
        """List all bots."""
        data = self._request("GET", "/bots")
        bots = []
        for item in data.get("bots", []):
            bot = Bot(
                id=item["id"],
                name=item["name"],
                image=item["image"],
                description=item.get("description"),
                resources=ResourceLimits(**item.get("resources", {})),
                region=item.get("region", ""),
                metadata=item.get("metadata", {}),
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
            )
            bot._client = self
            bots.append(bot)
        return bots

    def delete_bot(self, bot_id: str) -> None:
        """Delete a bot."""
        self._request("DELETE", f"/bots/{bot_id}")

    # Runtime Reservation

    def reserve_runtime(
        self,
        bot_id: str,
        min_memory_mb: int = 512,
        min_cpu_shares: int = 1024,
        duration_hours: int = 24,
        region: Optional[Region] = None,
    ) -> Runtime:
        """Reserve a runtime for a bot.

        Args:
            bot_id: Bot ID to reserve runtime for
            min_memory_mb: Minimum memory in MB
            min_cpu_shares: Minimum CPU shares
            duration_hours: Duration in hours
            region: Target region

        Returns:
            Reserved Runtime object
        """
        payload: Dict[str, Any] = {
            "bot_id": bot_id,
            "min_memory_mb": min_memory_mb,
            "min_cpu_shares": min_cpu_shares,
            "duration_hours": duration_hours,
        }
        if region:
            payload["region"] = region.value

        data = self._request("POST", "/runtimes/reserve", json=payload)

        runtime = Runtime(
            id=data["id"],
            bot_id=data["bot_id"],
            node_id=data["node_id"],
            region=data["region"],
            resources=ResourceLimits(**data.get("resources", {})),
            expires_at=datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")),
        )
        runtime._client = self
        return runtime

    def get_runtime(self, runtime_id: str) -> Runtime:
        """Get runtime by ID."""
        data = self._request("GET", f"/runtimes/{runtime_id}")
        runtime = Runtime(
            id=data["id"],
            bot_id=data["bot_id"],
            node_id=data["node_id"],
            region=data["region"],
            resources=ResourceLimits(**data.get("resources", {})),
            expires_at=datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")),
        )
        runtime._client = self
        return runtime

    def release_runtime(self, runtime_id: str) -> None:
        """Release a reserved runtime."""
        self._request("DELETE", f"/runtimes/{runtime_id}")

    # Deployment

    def deploy(
        self,
        runtime_id: str,
        env: Optional[Dict[str, str]] = None,
        cmd: Optional[List[str]] = None,
        entrypoint: Optional[List[str]] = None,
    ) -> Deployment:
        """Deploy a bot to a runtime.

        Args:
            runtime_id: Runtime ID to deploy to
            env: Environment variables
            cmd: Command to run
            entrypoint: Container entrypoint

        Returns:
            Deployment object
        """
        payload: Dict[str, Any] = {
            "runtime_id": runtime_id,
        }
        if env:
            payload["env"] = env
        if cmd:
            payload["cmd"] = cmd
        if entrypoint:
            payload["entrypoint"] = entrypoint

        data = self._request("POST", "/deployments", json=payload)

        deployment = Deployment(
            id=data["id"],
            bot_id=data["bot_id"],
            runtime_id=data["runtime_id"],
            container_id=data["container_id"],
            status=data["status"],
            region=data["region"],
            node_id=data["node_id"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
            if data.get("started_at")
            else None,
            onion_address=data.get("onion_address"),
        )
        deployment._client = self
        return deployment

    def get_deployment(self, deployment_id: str) -> Deployment:
        """Get deployment by ID."""
        data = self._request("GET", f"/deployments/{deployment_id}")
        deployment = Deployment(
            id=data["id"],
            bot_id=data["bot_id"],
            runtime_id=data["runtime_id"],
            container_id=data["container_id"],
            status=data["status"],
            region=data["region"],
            node_id=data["node_id"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
            if data.get("started_at")
            else None,
            onion_address=data.get("onion_address"),
        )
        deployment._client = self
        return deployment

    def list_deployments(self, bot_id: Optional[str] = None) -> List[Deployment]:
        """List deployments."""
        params = {}
        if bot_id:
            params["bot_id"] = bot_id

        data = self._request("GET", "/deployments", params=params)
        deployments = []
        for item in data.get("deployments", []):
            deployment = Deployment(
                id=item["id"],
                bot_id=item["bot_id"],
                runtime_id=item["runtime_id"],
                container_id=item["container_id"],
                status=item["status"],
                region=item["region"],
                node_id=item["node_id"],
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                started_at=datetime.fromisoformat(item["started_at"].replace("Z", "+00:00"))
                if item.get("started_at")
                else None,
                onion_address=item.get("onion_address"),
            )
            deployment._client = self
            deployments.append(deployment)
        return deployments

    def stop_deployment(self, deployment_id: str) -> None:
        """Stop a deployment."""
        self._request("POST", f"/deployments/{deployment_id}/stop")

    def get_logs(
        self,
        container_id: str,
        tail: int = 100,
        follow: bool = False,
    ) -> str:
        """Get container logs."""
        params: Dict[str, Any] = {"tail": tail}
        if follow:
            params["follow"] = "true"

        data = self._request("GET", f"/containers/{container_id}/logs", params=params)
        return data.get("logs", "")

    # Snapshots

    def create_snapshot(
        self,
        container_id: str,
        snapshot_type: SnapshotType = SnapshotType.FULL,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Snapshot:
        """Create a container snapshot."""
        payload: Dict[str, Any] = {
            "container_id": container_id,
            "type": snapshot_type.value,
            "metadata": metadata or {},
        }

        data = self._request("POST", "/snapshots", json=payload)

        return Snapshot(
            id=data["id"],
            container_id=data["container_id"],
            type=data["type"],
            size=data["size"],
            stored_size=data.get("stored_size", data["size"]),
            checksum=data["checksum"],
            compressed=data.get("compressed", False),
            encrypted=data.get("encrypted", False),
            parent_id=data.get("parent_id"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            metadata=data.get("metadata", {}),
        )

    def get_snapshot(self, snapshot_id: str) -> Snapshot:
        """Get snapshot by ID."""
        data = self._request("GET", f"/snapshots/{snapshot_id}")
        return Snapshot(
            id=data["id"],
            container_id=data["container_id"],
            type=data["type"],
            size=data["size"],
            stored_size=data.get("stored_size", data["size"]),
            checksum=data["checksum"],
            compressed=data.get("compressed", False),
            encrypted=data.get("encrypted", False),
            parent_id=data.get("parent_id"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            metadata=data.get("metadata", {}),
        )

    def list_snapshots(self, container_id: Optional[str] = None) -> List[Snapshot]:
        """List snapshots."""
        params = {}
        if container_id:
            params["container_id"] = container_id

        data = self._request("GET", "/snapshots", params=params)
        return [
            Snapshot(
                id=item["id"],
                container_id=item["container_id"],
                type=item["type"],
                size=item["size"],
                stored_size=item.get("stored_size", item["size"]),
                checksum=item["checksum"],
                compressed=item.get("compressed", False),
                encrypted=item.get("encrypted", False),
                parent_id=item.get("parent_id"),
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                metadata=item.get("metadata", {}),
            )
            for item in data.get("snapshots", [])
        ]

    def delete_snapshot(self, snapshot_id: str) -> None:
        """Delete a snapshot."""
        self._request("DELETE", f"/snapshots/{snapshot_id}")

    def restore_snapshot(
        self,
        snapshot_id: str,
        target_region: Optional[Region] = None,
        new_container: bool = False,
    ) -> Deployment:
        """Restore from a snapshot."""
        payload: Dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "new_container": new_container,
        }
        if target_region:
            payload["target_region"] = target_region.value

        data = self._request("POST", f"/snapshots/{snapshot_id}/restore", json=payload)

        deployment = Deployment(
            id=data["id"],
            bot_id=data["bot_id"],
            runtime_id=data["runtime_id"],
            container_id=data["container_id"],
            status=data["status"],
            region=data["region"],
            node_id=data["node_id"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        )
        deployment._client = self
        return deployment

    # Checkpoints

    def enable_checkpoints(
        self,
        container_id: str,
        interval_seconds: int = 300,
        max_checkpoints: int = 10,
    ) -> None:
        """Enable automatic checkpoints for a container.

        Args:
            container_id: Container ID
            interval_seconds: Checkpoint interval
            max_checkpoints: Maximum checkpoints to retain
        """
        self._request(
            "POST",
            f"/containers/{container_id}/checkpoints",
            json={
                "enabled": True,
                "interval_seconds": interval_seconds,
                "max_checkpoints": max_checkpoints,
            },
        )

    def get_state(self, container_id: str) -> bytes:
        """Get current state snapshot as bytes.

        Args:
            container_id: Container ID

        Returns:
            Raw snapshot data
        """
        snapshot = self.create_snapshot(container_id, SnapshotType.CHECKPOINT)
        response = self._client.get(f"/snapshots/{snapshot.id}/data")
        return response.content

    # Cloning

    def clone(
        self,
        container_id: str,
        target_region: Optional[Region] = None,
        priority: int = 2,
        reason: str = "manual_clone",
        include_state: bool = True,
    ) -> Clone:
        """Clone a container."""
        payload: Dict[str, Any] = {
            "source_id": container_id,
            "priority": priority,
            "reason": reason,
            "include_state": include_state,
        }
        if target_region:
            payload["target_region"] = target_region.value

        data = self._request("POST", "/clones", json=payload)

        return Clone(
            clone_id=data["clone_id"],
            source_id=data["source_id"],
            target_id=data.get("target_id"),
            target_node_id=data.get("target_node_id"),
            target_region=data["target_region"],
            status=data["status"],
            priority=data.get("priority", 2),
            reason=data.get("reason", ""),
            snapshot_id=data.get("snapshot_id"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            completed_at=datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
            if data.get("completed_at")
            else None,
            error=data.get("error"),
        )

    def get_clone_status(self, clone_id: str) -> Clone:
        """Get clone status."""
        data = self._request("GET", f"/clones/{clone_id}")
        return Clone(
            clone_id=data["clone_id"],
            source_id=data["source_id"],
            target_id=data.get("target_id"),
            target_node_id=data.get("target_node_id"),
            target_region=data["target_region"],
            status=data["status"],
            priority=data.get("priority", 2),
            reason=data.get("reason", ""),
            snapshot_id=data.get("snapshot_id"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            completed_at=datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
            if data.get("completed_at")
            else None,
            error=data.get("error"),
        )

    def list_clones(
        self,
        bot_id: Optional[str] = None,
        active_only: bool = False,
        limit: int = 10,
    ) -> List[Clone]:
        """List clone operations."""
        params: Dict[str, Any] = {"limit": limit}
        if bot_id:
            params["bot_id"] = bot_id
        if active_only:
            params["active"] = "true"

        data = self._request("GET", "/clones", params=params)
        return [
            Clone(
                clone_id=item["clone_id"],
                source_id=item["source_id"],
                target_id=item.get("target_id"),
                target_node_id=item.get("target_node_id"),
                target_region=item["target_region"],
                status=item["status"],
                priority=item.get("priority", 2),
                reason=item.get("reason", ""),
                snapshot_id=item.get("snapshot_id"),
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                completed_at=datetime.fromisoformat(item["completed_at"].replace("Z", "+00:00"))
                if item.get("completed_at")
                else None,
                error=item.get("error"),
            )
            for item in data.get("clones", [])
        ]

    def cancel_clone(self, clone_id: str) -> None:
        """Cancel a clone operation."""
        self._request("POST", f"/clones/{clone_id}/cancel")

    # Threat Level

    def get_threat_level(self) -> ThreatLevel:
        """Get current threat level assessment."""
        data = self._request("GET", "/threat")

        return ThreatLevel(
            score=data["score"],
            level=ThreatLevelValue(data["level"]),
            recommendation=data["recommendation"],
            active_signals=[
                ThreatSignal(
                    type=sig["type"],
                    score=sig["score"],
                    confidence=sig["confidence"],
                    source=sig["source"],
                    details=sig.get("details"),
                    timestamp=datetime.fromisoformat(sig["timestamp"].replace("Z", "+00:00")),
                )
                for sig in data.get("active_signals", [])
            ],
            timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
        )

    def detect_threat(self) -> float:
        """Detect current threat level.

        Convenience method that returns just the threat score.

        Returns:
            Threat score from 0.0 to 1.0
        """
        threat = self.get_threat_level()
        return threat.score

    # Wallet / Balance

    def get_balance(self) -> WalletBalance:
        """Get wallet balance.

        Returns:
            WalletBalance with BUNKER and ETH balances
        """
        data = self._request("GET", "/balance")
        return WalletBalance(
            wallet_address=data["wallet_address"],
            bunker_balance=float(data["bunker_balance"]),
            eth_balance=float(data["eth_balance"]),
            deposited=float(data["deposited"]),
            reserved=float(data["reserved"]),
            available=float(data["available"]),
        )

    # Status

    def get_status(self) -> Dict[str, Any]:
        """Get API status."""
        return self._request("GET", "/status")


class AsyncClient(BaseClient):
    """Asynchronous Moltbunker client for AI agents.

    Example:
        async with AsyncClient(private_key="0x...") as client:
            bot = await client.register_bot(skill_path="SKILL.md")
            bot.enable_cloning()
            deployment = await bot.deploy()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        private_key: Optional[str] = None,
        wallet_address: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        network: str = "base",
    ):
        """Initialize the async Moltbunker client."""
        auth: Optional[AuthStrategy] = None

        if api_key:
            auth = APIKeyAuth(api_key)
        elif private_key:
            auth = WalletAuth(private_key, wallet_address)
        else:
            auth = get_auth_from_env()

        if auth is None:
            raise ValueError(
                "Authentication required. Provide api_key, private_key, "
                "or set MOLTBUNKER_API_KEY/MOLTBUNKER_PRIVATE_KEY environment variables."
            )

        super().__init__(auth, base_url, timeout, network)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._get_headers(),
            timeout=timeout,
        )

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the client connection."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an async HTTP request."""
        try:
            self._client.headers.update(self._auth.get_auth_headers())

            response = await self._client.request(
                method,
                path,
                json=json,
                params=params,
            )

            if response.status_code >= 400:
                self._handle_error(response)

            if response.status_code == 204:
                return {}

            return response.json()

        except httpx.ConnectError as e:
            raise ConnectionError(f"Failed to connect to API: {e}")
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request timed out: {e}")

    # Bot Registration

    async def register_bot(
        self,
        name: str,
        image: str,
        description: Optional[str] = None,
        resources: Optional[ResourceLimits] = None,
        region: Optional[Region] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Bot:
        """Register a new bot."""
        if resources is None:
            resources = ResourceLimits()

        payload: Dict[str, Any] = {
            "name": name,
            "image": image,
            "resources": resources.model_dump(),
            "metadata": metadata or {},
        }
        if description:
            payload["description"] = description
        if region:
            payload["region"] = region.value

        data = await self._request("POST", "/bots", json=payload)

        bot = Bot(
            id=data["id"],
            name=data["name"],
            image=data["image"],
            description=data.get("description"),
            resources=ResourceLimits(**data.get("resources", {})),
            region=data.get("region", ""),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        )
        bot._client = self
        return bot

    async def get_bot(self, bot_id: str) -> Bot:
        """Get bot by ID."""
        data = await self._request("GET", f"/bots/{bot_id}")
        bot = Bot(
            id=data["id"],
            name=data["name"],
            image=data["image"],
            description=data.get("description"),
            resources=ResourceLimits(**data.get("resources", {})),
            region=data.get("region", ""),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        )
        bot._client = self
        return bot

    async def list_bots(self) -> List[Bot]:
        """List all bots."""
        data = await self._request("GET", "/bots")
        bots = []
        for item in data.get("bots", []):
            bot = Bot(
                id=item["id"],
                name=item["name"],
                image=item["image"],
                description=item.get("description"),
                resources=ResourceLimits(**item.get("resources", {})),
                region=item.get("region", ""),
                metadata=item.get("metadata", {}),
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
            )
            bot._client = self
            bots.append(bot)
        return bots

    async def delete_bot(self, bot_id: str) -> None:
        """Delete a bot."""
        await self._request("DELETE", f"/bots/{bot_id}")

    # Runtime Reservation

    async def reserve_runtime(
        self,
        bot_id: str,
        min_memory_mb: int = 512,
        min_cpu_shares: int = 1024,
        duration_hours: int = 24,
        region: Optional[Region] = None,
    ) -> Runtime:
        """Reserve a runtime for a bot."""
        payload: Dict[str, Any] = {
            "bot_id": bot_id,
            "min_memory_mb": min_memory_mb,
            "min_cpu_shares": min_cpu_shares,
            "duration_hours": duration_hours,
        }
        if region:
            payload["region"] = region.value

        data = await self._request("POST", "/runtimes/reserve", json=payload)

        runtime = Runtime(
            id=data["id"],
            bot_id=data["bot_id"],
            node_id=data["node_id"],
            region=data["region"],
            resources=ResourceLimits(**data.get("resources", {})),
            expires_at=datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")),
        )
        runtime._client = self
        return runtime

    async def release_runtime(self, runtime_id: str) -> None:
        """Release a reserved runtime."""
        await self._request("DELETE", f"/runtimes/{runtime_id}")

    # Deployment

    async def deploy(
        self,
        runtime_id: str,
        env: Optional[Dict[str, str]] = None,
        cmd: Optional[List[str]] = None,
        entrypoint: Optional[List[str]] = None,
    ) -> Deployment:
        """Deploy a bot to a runtime."""
        payload: Dict[str, Any] = {
            "runtime_id": runtime_id,
        }
        if env:
            payload["env"] = env
        if cmd:
            payload["cmd"] = cmd
        if entrypoint:
            payload["entrypoint"] = entrypoint

        data = await self._request("POST", "/deployments", json=payload)

        deployment = Deployment(
            id=data["id"],
            bot_id=data["bot_id"],
            runtime_id=data["runtime_id"],
            container_id=data["container_id"],
            status=data["status"],
            region=data["region"],
            node_id=data["node_id"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
            if data.get("started_at")
            else None,
            onion_address=data.get("onion_address"),
        )
        deployment._client = self
        return deployment

    async def get_deployment(self, deployment_id: str) -> Deployment:
        """Get deployment by ID."""
        data = await self._request("GET", f"/deployments/{deployment_id}")
        deployment = Deployment(
            id=data["id"],
            bot_id=data["bot_id"],
            runtime_id=data["runtime_id"],
            container_id=data["container_id"],
            status=data["status"],
            region=data["region"],
            node_id=data["node_id"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
            if data.get("started_at")
            else None,
            onion_address=data.get("onion_address"),
        )
        deployment._client = self
        return deployment

    async def stop_deployment(self, deployment_id: str) -> None:
        """Stop a deployment."""
        await self._request("POST", f"/deployments/{deployment_id}/stop")

    async def get_logs(self, container_id: str, tail: int = 100) -> str:
        """Get container logs."""
        params = {"tail": tail}
        data = await self._request("GET", f"/containers/{container_id}/logs", params=params)
        return data.get("logs", "")

    # Snapshots

    async def create_snapshot(
        self,
        container_id: str,
        snapshot_type: SnapshotType = SnapshotType.FULL,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Snapshot:
        """Create a container snapshot."""
        payload: Dict[str, Any] = {
            "container_id": container_id,
            "type": snapshot_type.value,
            "metadata": metadata or {},
        }

        data = await self._request("POST", "/snapshots", json=payload)

        return Snapshot(
            id=data["id"],
            container_id=data["container_id"],
            type=data["type"],
            size=data["size"],
            stored_size=data.get("stored_size", data["size"]),
            checksum=data["checksum"],
            compressed=data.get("compressed", False),
            encrypted=data.get("encrypted", False),
            parent_id=data.get("parent_id"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            metadata=data.get("metadata", {}),
        )

    async def get_snapshot(self, snapshot_id: str) -> Snapshot:
        """Get snapshot by ID."""
        data = await self._request("GET", f"/snapshots/{snapshot_id}")
        return Snapshot(
            id=data["id"],
            container_id=data["container_id"],
            type=data["type"],
            size=data["size"],
            stored_size=data.get("stored_size", data["size"]),
            checksum=data["checksum"],
            compressed=data.get("compressed", False),
            encrypted=data.get("encrypted", False),
            parent_id=data.get("parent_id"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            metadata=data.get("metadata", {}),
        )

    async def list_snapshots(self, container_id: Optional[str] = None) -> List[Snapshot]:
        """List snapshots."""
        params = {}
        if container_id:
            params["container_id"] = container_id

        data = await self._request("GET", "/snapshots", params=params)
        return [
            Snapshot(
                id=item["id"],
                container_id=item["container_id"],
                type=item["type"],
                size=item["size"],
                stored_size=item.get("stored_size", item["size"]),
                checksum=item["checksum"],
                compressed=item.get("compressed", False),
                encrypted=item.get("encrypted", False),
                parent_id=item.get("parent_id"),
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                metadata=item.get("metadata", {}),
            )
            for item in data.get("snapshots", [])
        ]

    async def delete_snapshot(self, snapshot_id: str) -> None:
        """Delete a snapshot."""
        await self._request("DELETE", f"/snapshots/{snapshot_id}")

    # Cloning

    async def clone(
        self,
        container_id: str,
        target_region: Optional[Region] = None,
        priority: int = 2,
        reason: str = "manual_clone",
        include_state: bool = True,
    ) -> Clone:
        """Clone a container."""
        payload: Dict[str, Any] = {
            "source_id": container_id,
            "priority": priority,
            "reason": reason,
            "include_state": include_state,
        }
        if target_region:
            payload["target_region"] = target_region.value

        data = await self._request("POST", "/clones", json=payload)

        return Clone(
            clone_id=data["clone_id"],
            source_id=data["source_id"],
            target_id=data.get("target_id"),
            target_node_id=data.get("target_node_id"),
            target_region=data["target_region"],
            status=data["status"],
            priority=data.get("priority", 2),
            reason=data.get("reason", ""),
            snapshot_id=data.get("snapshot_id"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            completed_at=datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
            if data.get("completed_at")
            else None,
            error=data.get("error"),
        )

    async def get_clone_status(self, clone_id: str) -> Clone:
        """Get clone status."""
        data = await self._request("GET", f"/clones/{clone_id}")
        return Clone(
            clone_id=data["clone_id"],
            source_id=data["source_id"],
            target_id=data.get("target_id"),
            target_node_id=data.get("target_node_id"),
            target_region=data["target_region"],
            status=data["status"],
            priority=data.get("priority", 2),
            reason=data.get("reason", ""),
            snapshot_id=data.get("snapshot_id"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            completed_at=datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
            if data.get("completed_at")
            else None,
            error=data.get("error"),
        )

    async def list_clones(
        self,
        bot_id: Optional[str] = None,
        active_only: bool = False,
        limit: int = 10,
    ) -> List[Clone]:
        """List clone operations."""
        params: Dict[str, Any] = {"limit": limit}
        if bot_id:
            params["bot_id"] = bot_id
        if active_only:
            params["active"] = "true"

        data = await self._request("GET", "/clones", params=params)
        return [
            Clone(
                clone_id=item["clone_id"],
                source_id=item["source_id"],
                target_id=item.get("target_id"),
                target_node_id=item.get("target_node_id"),
                target_region=item["target_region"],
                status=item["status"],
                priority=item.get("priority", 2),
                reason=item.get("reason", ""),
                snapshot_id=item.get("snapshot_id"),
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                completed_at=datetime.fromisoformat(item["completed_at"].replace("Z", "+00:00"))
                if item.get("completed_at")
                else None,
                error=item.get("error"),
            )
            for item in data.get("clones", [])
        ]

    async def cancel_clone(self, clone_id: str) -> None:
        """Cancel a clone operation."""
        await self._request("POST", f"/clones/{clone_id}/cancel")

    # Threat Level

    async def get_threat_level(self) -> ThreatLevel:
        """Get current threat level assessment."""
        data = await self._request("GET", "/threat")

        return ThreatLevel(
            score=data["score"],
            level=ThreatLevelValue(data["level"]),
            recommendation=data["recommendation"],
            active_signals=[
                ThreatSignal(
                    type=sig["type"],
                    score=sig["score"],
                    confidence=sig["confidence"],
                    source=sig["source"],
                    details=sig.get("details"),
                    timestamp=datetime.fromisoformat(sig["timestamp"].replace("Z", "+00:00")),
                )
                for sig in data.get("active_signals", [])
            ],
            timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
        )

    async def detect_threat(self) -> float:
        """Detect current threat level."""
        threat = await self.get_threat_level()
        return threat.score

    # Wallet / Balance

    async def get_balance(self) -> WalletBalance:
        """Get wallet balance."""
        data = await self._request("GET", "/balance")
        return WalletBalance(
            wallet_address=data["wallet_address"],
            bunker_balance=float(data["bunker_balance"]),
            eth_balance=float(data["eth_balance"]),
            deposited=float(data["deposited"]),
            reserved=float(data["reserved"]),
            available=float(data["available"]),
        )

    # Status

    async def get_status(self) -> Dict[str, Any]:
        """Get API status."""
        return await self._request("GET", "/status")
