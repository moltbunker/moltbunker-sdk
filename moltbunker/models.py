"""Moltbunker SDK Data Models"""

import re
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field, PrivateAttr

if TYPE_CHECKING:
    pass


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime string, handling Z suffix and Go nanoseconds."""
    if not raw:
        return None
    s = raw.replace("Z", "+00:00")
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    return datetime.fromisoformat(s)


class Region(str, Enum):
    """Available regions for deployment"""

    AMERICAS = "americas"
    EUROPE = "europe"
    ASIA_PACIFIC = "asia_pacific"
    AUTO = ""  # Auto-select


class ContainerStatus(str, Enum):
    """Container status values"""

    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    TERMINATED = "terminated"


class CloneStatus(str, Enum):
    """Clone operation status values"""

    PENDING = "pending"
    PREPARING = "preparing"
    TRANSFERRING = "transferring"
    DEPLOYING = "deploying"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SnapshotType(str, Enum):
    """Snapshot type values"""

    FULL = "full"
    INCREMENTAL = "incremental"
    CHECKPOINT = "checkpoint"


class ThreatLevelValue(str, Enum):
    """Threat level values"""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NetworkMode(str, Enum):
    """Network mode for deployments"""

    CLEARNET = "clearnet"
    TOR_ONLY = "tor_only"
    ONION_SERVICE = "onion_service"


class ResourceLimits(BaseModel):
    """Resource limits for containers"""

    cpu_shares: int = Field(default=1024, ge=1)
    memory_mb: int = Field(default=512, ge=64)
    storage_mb: int = Field(default=1024, ge=100)
    network_mbps: int = Field(default=100, ge=1)


class CloningConfig(BaseModel):
    """Configuration for automatic cloning"""

    enabled: bool = True
    auto_clone_on_threat: bool = True
    max_clones: int = 10
    clone_delay_seconds: int = 60
    sync_state: bool = False
    sync_interval_seconds: int = 300


class ThreatSignal(BaseModel):
    """Threat signal information"""

    type: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    details: Optional[str] = None
    timestamp: datetime


class ThreatLevel(BaseModel):
    """Threat level assessment"""

    score: float = Field(ge=0.0, le=1.0)
    level: ThreatLevelValue
    recommendation: str
    active_signals: List[ThreatSignal] = Field(default_factory=list)
    timestamp: datetime


class Container(BaseModel):
    """Container information"""

    id: str
    name: str
    image: str
    status: ContainerStatus
    node_id: str
    region: str
    created_at: datetime
    started_at: Optional[datetime] = None
    resources: Optional[ResourceLimits] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

    model_config = {"use_enum_values": True}


class Snapshot(BaseModel):
    """Snapshot information"""

    id: str
    container_id: str
    type: SnapshotType
    size: int
    stored_size: int
    checksum: str
    compressed: bool = False
    encrypted: bool = False
    parent_id: Optional[str] = None
    created_at: datetime
    metadata: Dict[str, str] = Field(default_factory=dict)

    model_config = {"use_enum_values": True}


class Clone(BaseModel):
    """Clone operation information"""

    clone_id: str
    source_id: str
    target_id: Optional[str] = None
    target_node_id: Optional[str] = None
    target_region: str
    status: CloneStatus
    priority: int = 2
    reason: str
    snapshot_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    model_config = {"use_enum_values": True}


class BotStatus(BaseModel):
    """Bot status information"""

    status: str  # running, stopped, deploying, etc.
    uptime: Optional[str] = None
    clones: int = 0
    active_deployments: int = 0
    threat_level: float = 0.0
    last_health_check: Optional[datetime] = None


class RuntimeStatus(BaseModel):
    """Runtime status information"""

    status: str
    remaining_hours: float
    resources_used: Optional[ResourceLimits] = None


class Bot(BaseModel):
    """Bot registration with full management methods"""

    id: str
    name: str
    image: str
    description: Optional[str] = None
    resources: ResourceLimits
    region: str
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime

    # Private attributes
    _client: Optional[Any] = PrivateAttr(default=None)
    _cloning_enabled: bool = PrivateAttr(default=False)
    _cloning_config: Optional[CloningConfig] = PrivateAttr(default=None)

    model_config = {"use_enum_values": True}

    # Runtime reservation

    def reserve_runtime(
        self,
        min_memory_mb: int = 512,
        min_cpu_shares: int = 1024,
        duration_hours: int = 24,
        region: Optional[Region] = None,
    ) -> "Runtime":
        """Reserve a runtime for this bot.

        Args:
            min_memory_mb: Minimum memory in MB
            min_cpu_shares: Minimum CPU shares
            duration_hours: Duration in hours
            region: Target region

        Returns:
            Reserved Runtime
        """
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        return self._client.reserve_runtime(
            bot_id=self.id,
            min_memory_mb=min_memory_mb,
            min_cpu_shares=min_cpu_shares,
            duration_hours=duration_hours,
            region=region,
        )

    async def areserve_runtime(
        self,
        min_memory_mb: int = 512,
        min_cpu_shares: int = 1024,
        duration_hours: int = 24,
        region: Optional[Region] = None,
    ) -> "Runtime":
        """Async: Reserve a runtime for this bot."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        return await self._client.reserve_runtime(
            bot_id=self.id,
            min_memory_mb=min_memory_mb,
            min_cpu_shares=min_cpu_shares,
            duration_hours=duration_hours,
            region=region,
        )

    # Direct deployment

    def deploy(
        self,
        runtime_id: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        cmd: Optional[List[str]] = None,
        entrypoint: Optional[List[str]] = None,
    ) -> "Deployment":
        """Deploy this bot.

        Auto-reserves runtime if not provided.

        Args:
            runtime_id: Optional runtime ID (auto-reserves if not provided)
            env: Environment variables
            cmd: Command to run
            entrypoint: Container entrypoint

        Returns:
            Deployment object
        """
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        if runtime_id is None:
            runtime = self.reserve_runtime()
            runtime_id = runtime.id

        return self._client.deploy(
            runtime_id=runtime_id,
            env=env,
            cmd=cmd,
            entrypoint=entrypoint,
        )

    async def adeploy(
        self,
        runtime_id: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        cmd: Optional[List[str]] = None,
        entrypoint: Optional[List[str]] = None,
    ) -> "Deployment":
        """Async: Deploy this bot."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        if runtime_id is None:
            runtime = await self.areserve_runtime()
            runtime_id = runtime.id

        return await self._client.deploy(
            runtime_id=runtime_id,
            env=env,
            cmd=cmd,
            entrypoint=entrypoint,
        )

    # Cloning management

    def enable_cloning(
        self,
        auto_clone_on_threat: bool = True,
        max_clones: int = 10,
        clone_delay_seconds: int = 60,
        sync_state: bool = False,
        sync_interval_seconds: int = 300,
    ) -> None:
        """Enable automatic cloning for this bot.

        When enabled, the bot will automatically clone itself to other nodes
        when threat levels rise, ensuring survival and availability.

        Args:
            auto_clone_on_threat: Clone automatically when threats detected
            max_clones: Maximum number of clones to maintain
            clone_delay_seconds: Delay between clone operations
            sync_state: Whether to sync state between clones
            sync_interval_seconds: State sync interval
        """
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        config = CloningConfig(
            enabled=True,
            auto_clone_on_threat=auto_clone_on_threat,
            max_clones=max_clones,
            clone_delay_seconds=clone_delay_seconds,
            sync_state=sync_state,
            sync_interval_seconds=sync_interval_seconds,
        )

        self._client._request("POST", f"/bots/{self.id}/cloning", json=config.model_dump())
        self._cloning_enabled = True
        self._cloning_config = config

    async def aenable_cloning(
        self,
        auto_clone_on_threat: bool = True,
        max_clones: int = 10,
        clone_delay_seconds: int = 60,
        sync_state: bool = False,
        sync_interval_seconds: int = 300,
    ) -> None:
        """Async: Enable automatic cloning for this bot."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        config = CloningConfig(
            enabled=True,
            auto_clone_on_threat=auto_clone_on_threat,
            max_clones=max_clones,
            clone_delay_seconds=clone_delay_seconds,
            sync_state=sync_state,
            sync_interval_seconds=sync_interval_seconds,
        )

        await self._client._request("POST", f"/bots/{self.id}/cloning", json=config.model_dump())
        self._cloning_enabled = True
        self._cloning_config = config

    def disable_cloning(self) -> None:
        """Disable automatic cloning."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        self._client._request("POST", f"/bots/{self.id}/cloning", json={"enabled": False})
        self._cloning_enabled = False

    async def adisable_cloning(self) -> None:
        """Async: Disable automatic cloning."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        await self._client._request("POST", f"/bots/{self.id}/cloning", json={"enabled": False})
        self._cloning_enabled = False

    def list_clones(self) -> List[Clone]:
        """List all clones of this bot."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        return self._client.list_clones(bot_id=self.id)

    async def alist_clones(self) -> List[Clone]:
        """Async: List all clones of this bot."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        return await self._client.list_clones(bot_id=self.id)

    def sync_clones(self) -> None:
        """Manually sync state to all clones."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        self._client._request("POST", f"/bots/{self.id}/clones/sync")

    async def async_clones(self) -> None:
        """Async: Manually sync state to all clones."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        await self._client._request("POST", f"/bots/{self.id}/clones/sync")

    # Threat detection

    def detect_threat(self) -> float:
        """Detect current threat level for this bot.

        Returns:
            Threat score from 0.0 to 1.0
        """
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        return self._client.detect_threat()

    async def adetect_threat(self) -> float:
        """Async: Detect current threat level for this bot."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        return await self._client.detect_threat()

    # Status and updates

    def get_status(self) -> BotStatus:
        """Get current bot status."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        data = self._client._request("GET", f"/bots/{self.id}/status")
        return BotStatus(**data)

    async def aget_status(self) -> BotStatus:
        """Async: Get current bot status."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        data = await self._client._request("GET", f"/bots/{self.id}/status")
        return BotStatus(**data)

    def update(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> "Bot":
        """Update bot details.

        Args:
            name: New name
            description: New description
            metadata: Updated metadata (merged with existing)

        Returns:
            Updated Bot object
        """
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if metadata is not None:
            payload["metadata"] = metadata

        if payload:
            self._client._request("PATCH", f"/bots/{self.id}", json=payload)
            if name is not None:
                self.name = name
            if description is not None:
                self.description = description
            if metadata is not None:
                self.metadata.update(metadata)

        return self

    async def aupdate(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> "Bot":
        """Async: Update bot details."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if metadata is not None:
            payload["metadata"] = metadata

        if payload:
            await self._client._request("PATCH", f"/bots/{self.id}", json=payload)
            if name is not None:
                self.name = name
            if description is not None:
                self.description = description
            if metadata is not None:
                self.metadata.update(metadata)

        return self

    def delete(self) -> None:
        """Delete this bot."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        self._client.delete_bot(self.id)

    async def adelete(self) -> None:
        """Async: Delete this bot."""
        if self._client is None:
            raise ValueError("Bot not associated with a client")

        await self._client.delete_bot(self.id)


class Runtime(BaseModel):
    """Reserved runtime with management methods"""

    id: str
    bot_id: str
    node_id: str
    region: str
    resources: ResourceLimits
    expires_at: datetime

    _client: Optional[Any] = PrivateAttr(default=None)

    model_config = {"use_enum_values": True}

    def deploy(
        self,
        env: Optional[Dict[str, str]] = None,
        cmd: Optional[List[str]] = None,
        entrypoint: Optional[List[str]] = None,
    ) -> "Deployment":
        """Deploy the bot to this runtime."""
        if self._client is None:
            raise ValueError("Runtime not associated with a client")

        return self._client.deploy(
            runtime_id=self.id,
            env=env,
            cmd=cmd,
            entrypoint=entrypoint,
        )

    async def adeploy(
        self,
        env: Optional[Dict[str, str]] = None,
        cmd: Optional[List[str]] = None,
        entrypoint: Optional[List[str]] = None,
    ) -> "Deployment":
        """Async: Deploy the bot to this runtime."""
        if self._client is None:
            raise ValueError("Runtime not associated with a client")

        return await self._client.deploy(
            runtime_id=self.id,
            env=env,
            cmd=cmd,
            entrypoint=entrypoint,
        )

    def extend(self, duration_hours: int) -> "Runtime":
        """Extend runtime duration.

        Args:
            duration_hours: Hours to extend

        Returns:
            Updated Runtime
        """
        if self._client is None:
            raise ValueError("Runtime not associated with a client")

        data = self._client._request(
            "POST", f"/runtimes/{self.id}/extend", json={"duration_hours": duration_hours}
        )
        self.expires_at = _parse_dt(data["expires_at"])
        return self

    async def aextend(self, duration_hours: int) -> "Runtime":
        """Async: Extend runtime duration."""
        if self._client is None:
            raise ValueError("Runtime not associated with a client")

        data = await self._client._request(
            "POST", f"/runtimes/{self.id}/extend", json={"duration_hours": duration_hours}
        )
        self.expires_at = _parse_dt(data["expires_at"])
        return self

    def release(self) -> None:
        """Release this runtime."""
        if self._client is None:
            raise ValueError("Runtime not associated with a client")

        self._client.release_runtime(self.id)

    async def arelease(self) -> None:
        """Async: Release this runtime."""
        if self._client is None:
            raise ValueError("Runtime not associated with a client")

        await self._client.release_runtime(self.id)

    def get_status(self) -> RuntimeStatus:
        """Get runtime status."""
        if self._client is None:
            raise ValueError("Runtime not associated with a client")

        data = self._client._request("GET", f"/runtimes/{self.id}/status")
        return RuntimeStatus(**data)

    async def aget_status(self) -> RuntimeStatus:
        """Async: Get runtime status."""
        if self._client is None:
            raise ValueError("Runtime not associated with a client")

        data = await self._client._request("GET", f"/runtimes/{self.id}/status")
        return RuntimeStatus(**data)


class Deployment(BaseModel):
    """Deployment information with management methods"""

    id: str
    bot_id: str
    runtime_id: str
    container_id: str
    status: ContainerStatus
    region: str
    node_id: str
    created_at: datetime
    started_at: Optional[datetime] = None
    onion_address: Optional[str] = None

    _client: Optional[Any] = PrivateAttr(default=None)

    model_config = {"use_enum_values": True}

    def get_status(self) -> "Deployment":
        """Get updated deployment status."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        return self._client.get_deployment(self.id)

    async def aget_status(self) -> "Deployment":
        """Async: Get updated deployment status."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        return await self._client.get_deployment(self.id)

    def stop(self) -> None:
        """Stop the deployment."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        self._client.stop_deployment(self.id)

    async def astop(self) -> None:
        """Async: Stop the deployment."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        await self._client.stop_deployment(self.id)

    def create_snapshot(
        self,
        snapshot_type: SnapshotType = SnapshotType.FULL,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Snapshot:
        """Create a snapshot of this deployment."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        return self._client.create_snapshot(
            container_id=self.container_id,
            snapshot_type=snapshot_type,
            metadata=metadata,
        )

    async def acreate_snapshot(
        self,
        snapshot_type: SnapshotType = SnapshotType.FULL,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Snapshot:
        """Async: Create a snapshot of this deployment."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        return await self._client.create_snapshot(
            container_id=self.container_id,
            snapshot_type=snapshot_type,
            metadata=metadata,
        )

    def clone(
        self,
        target_region: Optional[Region] = None,
        priority: int = 2,
        reason: str = "manual_clone",
    ) -> Clone:
        """Clone this deployment."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        return self._client.clone(
            container_id=self.container_id,
            target_region=target_region,
            priority=priority,
            reason=reason,
        )

    async def aclone(
        self,
        target_region: Optional[Region] = None,
        priority: int = 2,
        reason: str = "manual_clone",
    ) -> Clone:
        """Async: Clone this deployment."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        return await self._client.clone(
            container_id=self.container_id,
            target_region=target_region,
            priority=priority,
            reason=reason,
        )

    def get_logs(self, tail: int = 100, follow: bool = False) -> str:
        """Get deployment logs."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        return self._client.get_logs(self.container_id, tail=tail, follow=follow)

    async def aget_logs(self, tail: int = 100, follow: bool = False) -> str:
        """Async: Get deployment logs."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")
        return await self._client.get_logs(self.container_id, tail=tail, follow=follow)

    def enable_cloning(
        self,
        auto_clone_on_threat: bool = True,
        max_clones: int = 10,
    ) -> None:
        """Enable automatic cloning for this deployment's container."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")

        self._client._request(
            "POST",
            f"/containers/{self.container_id}/cloning",
            json={
                "enabled": True,
                "auto_clone_on_threat": auto_clone_on_threat,
                "max_clones": max_clones,
            },
        )

    async def aenable_cloning(
        self,
        auto_clone_on_threat: bool = True,
        max_clones: int = 10,
    ) -> None:
        """Async: Enable automatic cloning for this deployment's container."""
        if self._client is None:
            raise ValueError("Deployment not associated with a client")

        await self._client._request(
            "POST",
            f"/containers/{self.container_id}/cloning",
            json={
                "enabled": True,
                "auto_clone_on_threat": auto_clone_on_threat,
                "max_clones": max_clones,
            },
        )


class WalletBalance(BaseModel):
    """Wallet balance information"""

    wallet_address: str
    bunker_balance: float
    eth_balance: float
    deposited: float
    reserved: float
    available: float


# --- v0.2.0 models ---


class ReplicaLocation(BaseModel):
    """Geographic location of a replica"""

    region: str
    country: Optional[str] = None
    country_name: Optional[str] = None
    city: Optional[str] = None


class ContainerInfo(BaseModel):
    """Container list item matching backend ContainerInfo"""

    id: str
    image: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    encrypted: bool = False
    onion_address: Optional[str] = None
    regions: List[str] = Field(default_factory=list)
    locations: List[ReplicaLocation] = Field(default_factory=list)
    owner: Optional[str] = None
    stopped_at: Optional[datetime] = None
    volume_expires_at: Optional[datetime] = None
    has_volume: bool = False


class CatalogPreset(BaseModel):
    """Catalog preset (deployable template)"""

    id: str
    name: str
    image: str
    description: str = ""
    category_id: str = ""
    default_tier: str = ""
    tags: List[str] = Field(default_factory=list)
    enabled: bool = True
    sort_order: int = 0


class CatalogCategory(BaseModel):
    """Catalog category grouping presets"""

    id: str
    label: str
    enabled: bool = True
    sort_order: int = 0


class CatalogTier(BaseModel):
    """Catalog resource tier (pricing level)"""

    id: str
    name: str
    description: str = ""
    cpu: str = ""
    memory: str = ""
    storage: str = ""
    monthly: int = 0
    enabled: bool = True
    popular: bool = False
    sort_order: int = 0


class Catalog(BaseModel):
    """Full catalog configuration"""

    presets: List[CatalogPreset] = Field(default_factory=list)
    categories: List[CatalogCategory] = Field(default_factory=list)
    tiers: List[CatalogTier] = Field(default_factory=list)
    updated_at: Optional[datetime] = None
    version: int = 0


class MigrationStatus(str, Enum):
    """Migration status values"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Migration(BaseModel):
    """Container migration operation"""

    migration_id: str
    status: str = "pending"
    source_region: str = ""
    target_region: str = ""
    started_at: Optional[datetime] = None

    model_config = {"use_enum_values": True}
