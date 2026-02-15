# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-15

### Added

- **Wallet Session Auth** (`WalletSessionAuth`) — challenge-response flow with auto-refreshing session tokens
- **Container Management** — `list_containers()`, `get_container()`, `start_container()`, `stop_container()`, `delete_container()`
- **Deploy Direct** — `deploy_direct()` for non-escrow deployments (Tor, onion service support)
- **Catalog** — `get_catalog()` to browse presets, categories, and pricing tiers
- **Migration** — `migrate()` to move containers between regions
- **Real-Time Events** — `EventStream` and `AsyncEventStream` for WebSocket container/health updates
- **Exec Terminal** — `ExecSession` and `AsyncExecSession` for encrypted interactive shell into containers
- **New Models** — `ContainerInfo`, `Catalog`, `CatalogPreset`, `CatalogCategory`, `CatalogTier`, `Migration`, `MigrationStatus`, `ReplicaLocation`
- `ThreatLevelValue.UNKNOWN` enum value
- Automatic retry with backoff on 429 (rate limit) responses (up to 3 retries)

### Changed

- `web3` and `eth-account` are now optional dependencies (moved to `[wallet]` extra)
- New `[ws]` extra for WebSocket support (`websockets>=11.0`)
- New `[full]` extra installs `[wallet]` + `[ws]`
- Core install (`pip install moltbunker`) only requires `httpx` and `pydantic`

### Fixed

- Go nanosecond timestamp parsing (9 fractional digits) — Python 3.9 `fromisoformat()` only handles 6
- `AsyncClient.get_logs()` missing `follow` parameter
- Empty string balance fields from API now default to `0.0`

## [0.1.0] - 2026-02-03

### Added

- Initial release of the MoltBunker Python SDK
- `Client` and `AsyncClient` for synchronous and asynchronous API access
- Wallet authentication with Ethereum private keys (permissionless)
- API key authentication for managed services
- Bot registration and management
- Container deployment to P2P network
- Automatic self-cloning with threat detection
- Snapshot creation and restoration
- Threat detection and monitoring
- Clone management
- Runtime reservation and management
- Comprehensive error handling with typed exceptions
- Full type annotations (PEP 561 compliant)

### Dependencies

- httpx >= 0.24.0
- pydantic >= 2.0.0

[0.2.0]: https://github.com/moltbunker/moltbunker-sdk/releases/tag/v0.2.0
[0.1.0]: https://github.com/moltbunker/moltbunker-sdk/releases/tag/v0.1.0
