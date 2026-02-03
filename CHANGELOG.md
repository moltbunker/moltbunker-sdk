# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Clone management and state synchronization
- Runtime reservation and management
- Comprehensive error handling with typed exceptions
- Full type annotations (PEP 561 compliant)

### Dependencies

- httpx >= 0.24.0
- pydantic >= 2.0.0
- web3 >= 6.0.0
- eth-account >= 0.9.0

[0.1.0]: https://github.com/moltbunker/moltbunker-sdk/releases/tag/v0.1.0
