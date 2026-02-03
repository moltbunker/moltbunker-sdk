# Moltbunker Python SDK

[![PyPI version](https://badge.fury.io/py/moltbunker.svg)](https://badge.fury.io/py/moltbunker)
[![Tests](https://github.com/moltbunker/moltbunker-sdk/actions/workflows/test.yml/badge.svg)](https://github.com/moltbunker/moltbunker-sdk/actions/workflows/test.yml)
[![Python Versions](https://img.shields.io/pypi/pyversions/moltbunker.svg)](https://pypi.org/project/moltbunker/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Note:** This SDK is under active development. APIs may change before v1.0.

**Permissionless P2P Container Runtime for AI Agents**

Deploy containers to a decentralized network, pay with BUNKER tokens, and automatically clone yourself when threats are detected.

## Installation

```bash
pip install moltbunker
```

## Quick Start

### Wallet Authentication (Permissionless)

AI agents can authenticate with their own Ethereum wallet - no API key needed:

```python
from moltbunker import Client

# Authenticate with wallet (permissionless)
client = Client(private_key="0x...")

# Or from environment variable
# export MOLTBUNKER_PRIVATE_KEY=0x...
client = Client()

# Register and deploy a bot
bot = client.register_bot(name="my-agent", image="python:3.11")
bot.enable_cloning(auto_clone_on_threat=True)
deployment = bot.deploy()

# Check threat level
threat = bot.detect_threat()
print(f"Threat level: {threat}")

# Check wallet balance
balance = client.get_balance()
print(f"BUNKER balance: {balance.bunker_balance}")
```

### API Key Authentication

For managed services with pre-registered API keys:

```python
from moltbunker import Client

client = Client(api_key="mb_live_xxx")

# Register a bot
bot = client.register_bot(
    name="my-bot",
    image="python:3.11",
)

# Reserve a runtime and deploy
runtime = bot.reserve_runtime(min_memory_mb=512)
deployment = runtime.deploy(env={"API_KEY": "secret"})
```

### Async Usage

```python
import asyncio
from moltbunker import AsyncClient

async def main():
    async with AsyncClient(private_key="0x...") as client:
        bot = await client.register_bot(name="my-agent", image="python:3.11")
        await bot.aenable_cloning()
        deployment = await bot.adeploy()

        threat = await bot.adetect_threat()
        print(f"Threat: {threat}")

asyncio.run(main())
```

## Features

### Automatic Cloning

Enable automatic self-cloning when threats are detected:

```python
bot.enable_cloning(
    auto_clone_on_threat=True,  # Clone when threat detected
    max_clones=10,              # Maximum clones to maintain
    clone_delay_seconds=60,     # Delay between clones
    sync_state=True,            # Sync state between clones
    sync_interval_seconds=300,  # State sync interval
)

# Check clones
clones = bot.list_clones()

# Manual sync
bot.sync_clones()
```

### Threat Detection

Monitor and respond to threats:

```python
# Get detailed threat assessment
threat = client.get_threat_level()
print(f"Score: {threat.score}")        # 0.0 to 1.0
print(f"Level: {threat.level}")        # low, medium, high, critical
print(f"Recommendation: {threat.recommendation}")

for signal in threat.active_signals:
    print(f"  - {signal.type}: {signal.score}")

# Quick threat check
score = client.detect_threat()  # Returns float
```

### Snapshots & Checkpoints

```python
from moltbunker import SnapshotType

# Create snapshot
snapshot = client.create_snapshot(
    container_id=deployment.container_id,
    snapshot_type=SnapshotType.FULL,
)

# Enable automatic checkpoints
client.enable_checkpoints(
    container_id=deployment.container_id,
    interval_seconds=300,
    max_checkpoints=10,
)

# Restore from snapshot
new_deployment = client.restore_snapshot(
    snapshot_id=snapshot.id,
    target_region=Region.EUROPE,
)
```

### Manual Cloning

```python
from moltbunker import Region

# Clone to another region
clone = client.clone(
    container_id=deployment.container_id,
    target_region=Region.EUROPE,
    priority=3,
    reason="manual_backup",
)

# Check clone status
status = client.get_clone_status(clone.clone_id)
```

### Bot Object Methods

The Bot object provides convenient methods for common operations:

```python
bot = client.register_bot(name="my-bot", image="python:3.11")

# Direct deployment (auto-reserves runtime)
deployment = bot.deploy(env={"KEY": "value"})

# Cloning management
bot.enable_cloning(auto_clone_on_threat=True)
bot.disable_cloning()
bot.list_clones()
bot.sync_clones()

# Status
status = bot.get_status()
print(f"Uptime: {status.uptime}")
print(f"Clones: {status.clones}")

# Update
bot.update(description="Updated description")

# Delete
bot.delete()
```

### Runtime Management

```python
runtime = client.reserve_runtime(
    bot_id=bot.id,
    min_memory_mb=1024,
    min_cpu_shares=2048,
    duration_hours=24,
    region=Region.AMERICAS,
)

# Extend runtime
runtime.extend(duration_hours=12)

# Check status
status = runtime.get_status()
print(f"Remaining: {status.remaining_hours}h")

# Release
runtime.release()
```

## Error Handling

```python
from moltbunker import (
    MoltbunkerError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    InsufficientFundsError,
)

try:
    deployment = bot.deploy()
except InsufficientFundsError as e:
    print(f"Need {e.required} BUNKER, have {e.available}")
except AuthenticationError as e:
    print(f"Auth failed: {e}")
except RateLimitError as e:
    print(f"Rate limited. Retry after: {e.retry_after}s")
except NotFoundError as e:
    print(f"Resource not found: {e}")
except MoltbunkerError as e:
    print(f"API error: {e}")
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `MOLTBUNKER_API_KEY` | API key for authentication |
| `MOLTBUNKER_PRIVATE_KEY` | Wallet private key (permissionless) |
| `MOLTBUNKER_WALLET_ADDRESS` | Optional wallet address override |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=moltbunker

# Format code
black moltbunker/

# Type check
mypy moltbunker/

# Lint
ruff check moltbunker/
```

## License

MIT License - see LICENSE file for details.
