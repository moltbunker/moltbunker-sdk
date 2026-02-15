# Moltbunker Python SDK

[![PyPI version](https://badge.fury.io/py/moltbunker.svg)](https://badge.fury.io/py/moltbunker)
[![Tests](https://github.com/moltbunker/moltbunker-sdk/actions/workflows/test.yml/badge.svg)](https://github.com/moltbunker/moltbunker-sdk/actions/workflows/test.yml)
[![Python Versions](https://img.shields.io/pypi/pyversions/moltbunker.svg)](https://pypi.org/project/moltbunker/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Permissionless P2P Container Runtime for AI Agents**

Deploy containers to a decentralized network, pay with BUNKER tokens, and automatically clone yourself when threats are detected.

## Installation

```bash
# Core (API key or inline wallet auth)
pip install moltbunker

# With wallet session auth (challenge-response)
pip install moltbunker[wallet]

# With WebSocket support (events + exec terminal)
pip install moltbunker[ws]

# Everything
pip install moltbunker[full]
```

Requires Python 3.8+.

## Quick Start

### Wallet Authentication (Permissionless)

```python
from moltbunker import Client

# Authenticate with wallet (permissionless)
client = Client(private_key="0x...")

# Register and deploy a bot
bot = client.register_bot(name="my-agent", image="python:3.11")
bot.enable_cloning(auto_clone_on_threat=True)
deployment = bot.deploy()

# Check threat level
threat = client.get_threat_level()
print(f"Threat: {threat.level} (score: {threat.score})")

# Check wallet balance
balance = client.get_balance()
print(f"BUNKER: {balance.bunker_balance}")
```

### API Key Authentication

```python
client = Client(api_key="mb_live_xxx")
```

### Wallet Session Auth (Recommended)

Challenge-response flow with auto-refreshing session tokens:

```python
from moltbunker import Client
from moltbunker.auth import WalletSessionAuth

auth = WalletSessionAuth("0x...", api_base_url="https://api.moltbunker.com/v1")
client = Client(auth=auth, base_url="https://api.moltbunker.com/v1")
```

Requires `moltbunker[wallet]`.

### Async Usage

```python
from moltbunker import AsyncClient

async with AsyncClient(private_key="0x...") as client:
    bot = await client.register_bot(name="my-agent", image="python:3.11")
    deployment = await bot.adeploy()
    threat = await client.get_threat_level()
```

## Features

### Bot Deployment

```python
from moltbunker import Client, ResourceLimits, Region

client = Client(private_key="0x...")

bot = client.register_bot(
    name="my-agent",
    image="python:3.11",
    resources=ResourceLimits(cpu_shares=2048, memory_mb=1024),
    region=Region.EUROPE,
)

# Reserve runtime (paid in BUNKER)
runtime = bot.reserve_runtime(min_memory_mb=1024, duration_hours=24)
deployment = runtime.deploy(env={"MODE": "production"})
print(f"Container: {deployment.container_id}")

# Or deploy directly (no escrow)
result = client.deploy_direct(
    image="python:3.11",
    resources=ResourceLimits(cpu_shares=1024, memory_mb=512),
    duration="24h",
)
```

### Self-Cloning

```python
bot.enable_cloning(
    auto_clone_on_threat=True,
    max_clones=10,
    clone_delay_seconds=60,
)

# Manual clone
clone = deployment.clone(target_region=Region.AMERICAS)
status = client.get_clone_status(clone.clone_id)
```

### Container Management

```python
containers = client.list_containers(status="running")
container = client.get_container("mb-abc123")
client.stop_container("mb-abc123")
client.start_container("mb-abc123")
client.delete_container("mb-abc123")
```

### Snapshots

```python
from moltbunker import SnapshotType

snapshot = client.create_snapshot(
    container_id=deployment.container_id,
    snapshot_type=SnapshotType.FULL,
)

restored = client.restore_snapshot(snapshot.id, target_region=Region.EUROPE)
```

### Threat Detection

```python
threat = client.get_threat_level()
print(f"Score: {threat.score}")        # 0.0 to 1.0
print(f"Level: {threat.level}")        # unknown, low, medium, high, critical
print(f"Recommendation: {threat.recommendation}")

for signal in threat.active_signals:
    print(f"  {signal.type}: confidence {signal.confidence}")
```

### Real-Time Events (WebSocket)

Requires `moltbunker[ws]`.

```python
from moltbunker.events import EventStream

with EventStream("wss://api.moltbunker.com/ws", token="wt_...") as stream:
    stream.subscribe("containers", lambda data: print(data))
    stream.wait()
```

### Exec Terminal

Interactive shell into running containers. Requires `moltbunker[wallet]` + `moltbunker[ws]`.

```python
from moltbunker.exec import ExecSession

with ExecSession(
    api_base_url="https://api.moltbunker.com/v1",
    container_id="mb-abc123",
    private_key="0x...",
    token="wt_...",
) as session:
    session.on_data(lambda data: print(data.decode(), end=""))
    session.send(b"ls -la\n")
```

### Runtime Management

```python
runtime = bot.reserve_runtime(
    min_memory_mb=1024,
    min_cpu_shares=2048,
    duration_hours=24,
    region=Region.AMERICAS,
)

runtime.extend(duration_hours=12)
status = runtime.get_status()
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
except RateLimitError as e:
    print(f"Rate limited. Retry after: {e.retry_after}s")
except MoltbunkerError as e:
    print(f"Error [{e.status_code}]: {e.message}")
```

Rate-limited requests are automatically retried up to 3 times with backoff.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `MOLTBUNKER_API_KEY` | API key for authentication |
| `MOLTBUNKER_PRIVATE_KEY` | Wallet private key (permissionless) |

## Network

- **Chain:** Base (Ethereum L2)
- **Token:** BUNKER (ERC-20)
- **Pricing:** 20,000 BUNKER = $1 USD
- **Testnet:** Base Sepolia (Chain ID 84532) — live now
- **Mainnet:** Base (Chain ID 8453) — coming soon

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=moltbunker

# Type check
mypy moltbunker/

# Lint
ruff check moltbunker/
```

## Documentation

- [Full SDK Documentation](https://moltbunker.com/docs/python-sdk)
- [Quick Start Guide](https://moltbunker.com/docs/quick-start)
- [API Reference](https://moltbunker.com/docs/api-reference)
- [Security](https://moltbunker.com/docs/security)

## License

MIT License - see LICENSE file for details.
