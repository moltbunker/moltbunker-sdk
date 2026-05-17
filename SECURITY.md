# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities by email to **security@moltbunker.com**.

You can expect:

- An acknowledgement within **48 hours**.
- An initial assessment within **7 days**.
- A coordinated disclosure timeline agreed with you before any public details are shared.

Please do **not** open a public GitHub issue, social media post, or other public channel for security issues.

## Scope

This policy covers the `moltbunker` Python SDK only. Server-side issues (the daemon, HTTP API, smart contracts) belong to the main `moltbunker` repository's security policy.

In-scope examples:

- Vulnerabilities in the SDK's wallet authentication flow.
- Cryptographic mistakes in the exec terminal client.
- Insecure handling of private keys, API tokens, or session tokens.
- Bypasses of server-enforced rate limits or authorization that originate in SDK logic.
- Supply-chain risks in the SDK's declared dependencies.

Out of scope:

- Vulnerabilities in user code that *uses* the SDK (e.g., a downstream app that commits its `.env` to a public repo).
- Server-side bugs reachable via the SDK that are not exploitable through SDK code paths.

## Supported Versions

Until 1.0.0, only the latest released version on PyPI is supported with security fixes. Older releases will not be back-patched.

## Safe Harbor

We will not pursue legal action against good-faith security research that follows this policy.

## Recognition

Researchers who report valid in-scope issues will be credited in `CHANGELOG.md`, with their permission.
