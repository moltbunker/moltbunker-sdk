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

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from .auth import APIKeyAuth, AuthStrategy, WalletAuth, get_auth_from_env
from .exceptions import (
    AuthenticationError,
    ConnectionError,
    InsufficientFundsError,
    MoltbunkerError,
    NotFoundError,
    RateLimitError,
    TimeoutError,
)
from .models import (
    Bot,
    Catalog,
    CatalogCategory,
    CatalogPreset,
    CatalogTier,
    Clone,
    ContainerInfo,
    Deployment,
    Migration,
    Region,
    ReplicaLocation,
    ResourceLimits,
    Runtime,
    Snapshot,
    SnapshotType,
    ThreatLevel,
    ThreatLevelValue,
    ThreatSignal,
    WalletBalance,
)

DEFAULT_BASE_URL = "https://api.moltbunker.com/v1"
DEFAULT_TIMEOUT = 30.0


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime string, handling Z suffix and Go nanoseconds."""
    if not raw:
        return None
    s = raw.replace("Z", "+00:00")
    # Go marshals with nanosecond precision (9 digits) but Python 3.9's
    # fromisoformat only handles up to 6 (microseconds). Truncate.
    import re
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    return datetime.fromisoformat(s)


def _parse_container_info(data: Dict[str, Any]) -> ContainerInfo:
    """Parse a ContainerInfo dict from the API."""
    return ContainerInfo(
        id=data["id"],
        image=data["image"],
        status=data["status"],
        created_at=_parse_dt(data["created_at"]) or datetime.now(),
        started_at=_parse_dt(data.get("started_at")),
        encrypted=data.get("encrypted", False),
        onion_address=data.get("onion_address"),
        regions=data.get("regions", []),
        locations=[ReplicaLocation(**loc) for loc in data.get("locations", [])],
        owner=data.get("owner"),
        stopped_at=_parse_dt(data.get("stopped_at")),
        volume_expires_at=_parse_dt(data.get("volume_expires_at")),
        has_volume=data.get("has_volume", False),
    )


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
            "User-Agent": "moltbunker-python/0.2.0",
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
        auth: Optional[AuthStrategy] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        network: str = "base",
    ):
        """Initialize the Moltbunker client.

        Args:
            api_key: API key for authentication (mb_live_xxx or mb_test_xxx)
            private_key: Ethereum private key for wallet authentication
            wallet_address: Optional wallet address override
            auth: Pre-configured auth strategy (e.g. WalletSessionAuth)
            base_url: API base URL
            timeout: Request timeout in seconds
            network: Blockchain network (default: "base")

        Raises:
            ValueError: If no authentication credentials provided
        """
        # Determine auth strategy
        resolved_auth: Optional[AuthStrategy] = auth

        if resolved_auth is None:
            if api_key:
                resolved_auth = APIKeyAuth(api_key)
            elif private_key:
                resolved_auth = WalletAuth(private_key, wallet_address)
            else:
                # Try environment variables
                resolved_auth = get_auth_from_env()

        if resolved_auth is None:
            raise ValueError(
                "Authentication required. Provide api_key, private_key, auth, "
                "or set MOLTBUNKER_API_KEY/MOLTBUNKER_PRIVATE_KEY environment variables."
            )

        super().__init__(resolved_auth, base_url, timeout, network)
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
        _retries: int = 3,
    ) -> Dict[str, Any]:
        """Make an HTTP request with automatic retry on 429."""
        last_error: Optional[Exception] = None
        for attempt in range(_retries):
            try:
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

            except RateLimitError as e:
                last_error = e
                if attempt < _retries - 1:
                    wait = e.retry_after if e.retry_after else 2 * (attempt + 1)
                    time.sleep(wait)
                    continue
                raise
            except httpx.ConnectError as e:
                raise ConnectionError(f"Failed to connect to API: {e}")
            except httpx.TimeoutException as e:
                raise TimeoutError(f"Request timed out: {e}")
        raise last_error  # type: ignore[misc]

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
            created_at=_parse_dt(data["created_at"]),
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
            created_at=_parse_dt(data["created_at"]),
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
                created_at=_parse_dt(item["created_at"]),
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
            expires_at=_parse_dt(data["expires_at"]),
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
            expires_at=_parse_dt(data["expires_at"]),
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
            created_at=_parse_dt(data["created_at"]),
            started_at=_parse_dt(data["started_at"])
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
            created_at=_parse_dt(data["created_at"]),
            started_at=_parse_dt(data["started_at"])
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
                created_at=_parse_dt(item["created_at"]),
                started_at=_parse_dt(item["started_at"])
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
            created_at=_parse_dt(data["created_at"]),
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
            created_at=_parse_dt(data["created_at"]),
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
                created_at=_parse_dt(item["created_at"]),
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
            created_at=_parse_dt(data["created_at"]),
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
            created_at=_parse_dt(data["created_at"]),
            completed_at=_parse_dt(data["completed_at"])
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
            created_at=_parse_dt(data["created_at"]),
            completed_at=_parse_dt(data["completed_at"])
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
                created_at=_parse_dt(item["created_at"]),
                completed_at=_parse_dt(item["completed_at"])
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
                    timestamp=_parse_dt(sig["timestamp"]),
                )
                for sig in data.get("active_signals", [])
            ],
            timestamp=_parse_dt(data["timestamp"]),
        )

    def detect_threat(self) -> float:
        """Detect current threat level.

        Convenience method that returns just the threat score.

        Returns:
            Threat score from 0.0 to 1.0
        """
        threat = self.get_threat_level()
        return threat.score

    # Container Management

    def list_containers(self, **filters: Any) -> List[ContainerInfo]:
        """List containers.

        Args:
            **filters: Optional query filters (status, owner, etc.)

        Returns:
            List of ContainerInfo
        """
        params = {k: v for k, v in filters.items() if v is not None}
        data = self._request("GET", "/containers", params=params or None)
        items = data if isinstance(data, list) else data.get("containers", [])
        return [_parse_container_info(item) for item in items]

    def get_container(self, container_id: str) -> ContainerInfo:
        """Get container by ID."""
        data = self._request("GET", f"/containers/{container_id}")
        return _parse_container_info(data)

    def stop_container(self, container_id: str) -> None:
        """Stop a container."""
        self._request("POST", f"/containers/{container_id}/stop")

    def start_container(self, container_id: str) -> None:
        """Start a stopped container."""
        self._request("POST", f"/containers/{container_id}/start")

    def delete_container(self, container_id: str) -> None:
        """Delete a container."""
        self._request("DELETE", f"/containers/{container_id}")

    # Deploy Direct

    def deploy_direct(
        self,
        image: str,
        resources: Optional[ResourceLimits] = None,
        duration: str = "720h",
        tor_only: bool = False,
        onion_service: bool = False,
        onion_port: int = 80,
        wait_for_replicas: bool = False,
        reservation_id: Optional[str] = None,
        min_provider_tier: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Deploy a container directly (non-escrow path).

        Args:
            image: OCI image reference
            resources: Resource limits
            duration: Duration string (e.g. "24h", "720h")
            tor_only: Route all traffic through Tor
            onion_service: Expose as .onion hidden service
            onion_port: Port for onion service (default 80)
            wait_for_replicas: Wait for all replicas before returning
            reservation_id: On-chain escrow reservation ID
            min_provider_tier: Minimum provider tier ("confidential", "standard", "dev")
            env: Environment variables

        Returns:
            Deploy response dict (container_id, status, regions, etc.)
        """
        payload: Dict[str, Any] = {"image": image}
        if resources:
            payload["resources"] = resources.model_dump()
        if duration != "720h":
            payload["duration"] = duration
        if tor_only:
            payload["tor_only"] = True
        if onion_service:
            payload["onion_service"] = True
            payload["onion_port"] = onion_port
        if wait_for_replicas:
            payload["wait_for_replicas"] = True
        if reservation_id:
            payload["reservation_id"] = reservation_id
        if min_provider_tier:
            payload["min_provider_tier"] = min_provider_tier
        if env:
            payload["env"] = env

        return self._request("POST", "/deploy", json=payload)

    # Migration

    def migrate(
        self,
        container_id: str,
        target_region: Optional[str] = None,
        keep_original: bool = False,
    ) -> Migration:
        """Migrate a container to a different region.

        Args:
            container_id: Container to migrate
            target_region: Target region (auto-selected if not provided)
            keep_original: Keep the original container after migration

        Returns:
            Migration object with status
        """
        payload: Dict[str, Any] = {"container_id": container_id}
        if target_region:
            payload["target_region"] = target_region
        if keep_original:
            payload["keep_original"] = True

        data = self._request("POST", "/migrate", json=payload)
        return Migration(
            migration_id=data["migration_id"],
            status=data.get("status", "pending"),
            source_region=data.get("source_region", ""),
            target_region=data.get("target_region", ""),
            started_at=_parse_dt(data.get("started_at")),
        )

    # Catalog

    def get_catalog(self) -> Catalog:
        """Get the public deployment catalog.

        Returns:
            Catalog with presets, categories, and tiers
        """
        data = self._request("GET", "/catalog")
        return Catalog(
            presets=[CatalogPreset(**p) for p in data.get("presets", [])],
            categories=[CatalogCategory(**c) for c in data.get("categories", [])],
            tiers=[CatalogTier(**t) for t in data.get("tiers", [])],
            updated_at=_parse_dt(data.get("updated_at")),
            version=data.get("version", 0),
        )

    # Wallet / Balance

    def get_balance(self, address: Optional[str] = None) -> WalletBalance:
        """Get wallet balance.

        Args:
            address: Wallet address to query (defaults to authenticated wallet)

        Returns:
            WalletBalance with BUNKER and ETH balances
        """
        params = {"address": address} if address else None
        data = self._request("GET", "/balance", params=params)
        return _parse_balance(data)

    # Status

    def get_status(self) -> Dict[str, Any]:
        """Get API status."""
        return self._request("GET", "/status")


def _safe_float(val: Any) -> float:
    """Convert to float, returning 0.0 for empty/missing values."""
    if not val and val != 0:
        return 0.0
    return float(val)


def _parse_balance(data: Dict[str, Any]) -> WalletBalance:
    """Parse balance response, handling empty strings from API."""
    return WalletBalance(
        wallet_address=data.get("wallet_address", ""),
        bunker_balance=_safe_float(data.get("bunker_balance")),
        eth_balance=_safe_float(data.get("eth_balance")),
        deposited=_safe_float(data.get("deposited")),
        reserved=_safe_float(data.get("reserved")),
        available=_safe_float(data.get("available")),
    )


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
        auth: Optional[AuthStrategy] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        network: str = "base",
    ):
        """Initialize the async Moltbunker client."""
        resolved_auth: Optional[AuthStrategy] = auth

        if resolved_auth is None:
            if api_key:
                resolved_auth = APIKeyAuth(api_key)
            elif private_key:
                resolved_auth = WalletAuth(private_key, wallet_address)
            else:
                resolved_auth = get_auth_from_env()

        if resolved_auth is None:
            raise ValueError(
                "Authentication required. Provide api_key, private_key, auth, "
                "or set MOLTBUNKER_API_KEY/MOLTBUNKER_PRIVATE_KEY environment variables."
            )

        super().__init__(resolved_auth, base_url, timeout, network)
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
        _retries: int = 3,
    ) -> Dict[str, Any]:
        """Make an async HTTP request with automatic retry on 429."""
        import asyncio

        last_error: Optional[Exception] = None
        for attempt in range(_retries):
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

            except RateLimitError as e:
                last_error = e
                if attempt < _retries - 1:
                    wait = e.retry_after if e.retry_after else 2 * (attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                raise
            except httpx.ConnectError as e:
                raise ConnectionError(f"Failed to connect to API: {e}")
            except httpx.TimeoutException as e:
                raise TimeoutError(f"Request timed out: {e}")
        raise last_error  # type: ignore[misc]

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
            created_at=_parse_dt(data["created_at"]),
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
            created_at=_parse_dt(data["created_at"]),
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
                created_at=_parse_dt(item["created_at"]),
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
            expires_at=_parse_dt(data["expires_at"]),
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
            created_at=_parse_dt(data["created_at"]),
            started_at=_parse_dt(data["started_at"])
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
            created_at=_parse_dt(data["created_at"]),
            started_at=_parse_dt(data["started_at"])
            if data.get("started_at")
            else None,
            onion_address=data.get("onion_address"),
        )
        deployment._client = self
        return deployment

    async def stop_deployment(self, deployment_id: str) -> None:
        """Stop a deployment."""
        await self._request("POST", f"/deployments/{deployment_id}/stop")

    async def get_logs(
        self,
        container_id: str,
        tail: int = 100,
        follow: bool = False,
    ) -> str:
        """Get container logs."""
        params: Dict[str, Any] = {"tail": tail}
        if follow:
            params["follow"] = "true"
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
            created_at=_parse_dt(data["created_at"]),
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
            created_at=_parse_dt(data["created_at"]),
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
                created_at=_parse_dt(item["created_at"]),
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
            created_at=_parse_dt(data["created_at"]),
            completed_at=_parse_dt(data["completed_at"])
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
            created_at=_parse_dt(data["created_at"]),
            completed_at=_parse_dt(data["completed_at"])
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
                created_at=_parse_dt(item["created_at"]),
                completed_at=_parse_dt(item["completed_at"])
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
                    timestamp=_parse_dt(sig["timestamp"]),
                )
                for sig in data.get("active_signals", [])
            ],
            timestamp=_parse_dt(data["timestamp"]),
        )

    async def detect_threat(self) -> float:
        """Detect current threat level."""
        threat = await self.get_threat_level()
        return threat.score

    # Container Management

    async def list_containers(self, **filters: Any) -> List[ContainerInfo]:
        """List containers."""
        params = {k: v for k, v in filters.items() if v is not None}
        data = await self._request("GET", "/containers", params=params or None)
        items = data if isinstance(data, list) else data.get("containers", [])
        return [_parse_container_info(item) for item in items]

    async def get_container(self, container_id: str) -> ContainerInfo:
        """Get container by ID."""
        data = await self._request("GET", f"/containers/{container_id}")
        return _parse_container_info(data)

    async def stop_container(self, container_id: str) -> None:
        """Stop a container."""
        await self._request("POST", f"/containers/{container_id}/stop")

    async def start_container(self, container_id: str) -> None:
        """Start a stopped container."""
        await self._request("POST", f"/containers/{container_id}/start")

    async def delete_container(self, container_id: str) -> None:
        """Delete a container."""
        await self._request("DELETE", f"/containers/{container_id}")

    # Deploy Direct

    async def deploy_direct(
        self,
        image: str,
        resources: Optional[ResourceLimits] = None,
        duration: str = "720h",
        tor_only: bool = False,
        onion_service: bool = False,
        onion_port: int = 80,
        wait_for_replicas: bool = False,
        reservation_id: Optional[str] = None,
        min_provider_tier: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Deploy a container directly (non-escrow path)."""
        payload: Dict[str, Any] = {"image": image}
        if resources:
            payload["resources"] = resources.model_dump()
        if duration != "720h":
            payload["duration"] = duration
        if tor_only:
            payload["tor_only"] = True
        if onion_service:
            payload["onion_service"] = True
            payload["onion_port"] = onion_port
        if wait_for_replicas:
            payload["wait_for_replicas"] = True
        if reservation_id:
            payload["reservation_id"] = reservation_id
        if min_provider_tier:
            payload["min_provider_tier"] = min_provider_tier
        if env:
            payload["env"] = env

        return await self._request("POST", "/deploy", json=payload)

    # Migration

    async def migrate(
        self,
        container_id: str,
        target_region: Optional[str] = None,
        keep_original: bool = False,
    ) -> Migration:
        """Migrate a container to a different region."""
        payload: Dict[str, Any] = {"container_id": container_id}
        if target_region:
            payload["target_region"] = target_region
        if keep_original:
            payload["keep_original"] = True

        data = await self._request("POST", "/migrate", json=payload)
        return Migration(
            migration_id=data["migration_id"],
            status=data.get("status", "pending"),
            source_region=data.get("source_region", ""),
            target_region=data.get("target_region", ""),
            started_at=_parse_dt(data.get("started_at")),
        )

    # Catalog

    async def get_catalog(self) -> Catalog:
        """Get the public deployment catalog."""
        data = await self._request("GET", "/catalog")
        return Catalog(
            presets=[CatalogPreset(**p) for p in data.get("presets", [])],
            categories=[CatalogCategory(**c) for c in data.get("categories", [])],
            tiers=[CatalogTier(**t) for t in data.get("tiers", [])],
            updated_at=_parse_dt(data.get("updated_at")),
            version=data.get("version", 0),
        )

    # Wallet / Balance

    async def get_balance(self, address: Optional[str] = None) -> WalletBalance:
        """Get wallet balance."""
        params = {"address": address} if address else None
        data = await self._request("GET", "/balance", params=params)
        return _parse_balance(data)

    # Status

    async def get_status(self) -> Dict[str, Any]:
        """Get API status."""
        return await self._request("GET", "/status")
