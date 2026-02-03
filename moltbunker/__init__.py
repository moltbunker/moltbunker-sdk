"""
Moltbunker Python SDK - Permissionless P2P Container Runtime for AI Agents

A decentralized platform where AI agents can deploy containers, pay with BUNKER tokens,
and automatically clone themselves when threats are detected.

Usage - Wallet Authentication (Permissionless):
    from moltbunker import Client

    # AI agents authenticate with their own wallet
    client = Client(private_key="0x...")

    # Register and deploy a bot
    bot = client.register_bot(name="my-agent", image="python:3.11")
    bot.enable_cloning(auto_clone_on_threat=True)
    deployment = bot.deploy()

    # Check threat level
    threat = bot.detect_threat()
    print(f"Threat level: {threat}")

Usage - API Key Authentication:
    from moltbunker import Client

    client = Client(api_key="mb_live_xxx")
    bot = client.register_bot(name="my-bot", image="python:3.11")
    runtime = bot.reserve_runtime(min_memory_mb=512)
    deployment = runtime.deploy()

Usage - Async Client:
    from moltbunker import AsyncClient

    async with AsyncClient(private_key="0x...") as client:
        bot = await client.register_bot(name="my-bot", image="python:3.11")
        await bot.aenable_cloning()
        deployment = await bot.adeploy()
"""

from .client import Client, AsyncClient
from .auth import AuthStrategy, APIKeyAuth, WalletAuth, get_auth_from_env
from .models import (
    Bot,
    Runtime,
    Deployment,
    Snapshot,
    Clone,
    ThreatLevel,
    ThreatSignal,
    ThreatLevelValue,
    Container,
    ResourceLimits,
    Region,
    SnapshotType,
    ContainerStatus,
    CloneStatus,
    CloningConfig,
    BotStatus,
    RuntimeStatus,
    NetworkMode,
    WalletBalance,
)
from .exceptions import (
    MoltbunkerError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    InsufficientFundsError,
    DeploymentError,
    CloneError,
    SnapshotError,
    ValidationError,
    ConnectionError,
    TimeoutError,
    RuntimeNotFoundError,
    BotNotFoundError,
    ContainerNotFoundError,
)

__version__ = "0.1.0"
__all__ = [
    # Clients
    "Client",
    "AsyncClient",
    # Authentication
    "AuthStrategy",
    "APIKeyAuth",
    "WalletAuth",
    "get_auth_from_env",
    # Models
    "Bot",
    "Runtime",
    "Deployment",
    "Snapshot",
    "Clone",
    "ThreatLevel",
    "ThreatSignal",
    "ThreatLevelValue",
    "Container",
    "ResourceLimits",
    "Region",
    "SnapshotType",
    "ContainerStatus",
    "CloneStatus",
    "CloningConfig",
    "BotStatus",
    "RuntimeStatus",
    "NetworkMode",
    "WalletBalance",
    # Exceptions
    "MoltbunkerError",
    "AuthenticationError",
    "NotFoundError",
    "RateLimitError",
    "InsufficientFundsError",
    "DeploymentError",
    "CloneError",
    "SnapshotError",
    "ValidationError",
    "ConnectionError",
    "TimeoutError",
    "RuntimeNotFoundError",
    "BotNotFoundError",
    "ContainerNotFoundError",
]
