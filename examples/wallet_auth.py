#!/usr/bin/env python3
"""Example: Wallet authentication (permissionless) on Base Sepolia testnet.

Usage:
    export MOLTBUNKER_TESTNET_PRIVATE_KEY=0x...
    python examples/wallet_auth.py

If the env-var is not set the script prints a warning and exits gracefully.
"""
import os
import sys

# Guard: check for private key before importing so the error message is clear
PRIVATE_KEY = os.environ.get("MOLTBUNKER_TESTNET_PRIVATE_KEY")
if not PRIVATE_KEY:
    print(
        "WARNING: MOLTBUNKER_TESTNET_PRIVATE_KEY is not set.\n"
        "Set it to a Base Sepolia wallet private key to run this example.\n"
        "Example:\n"
        "  export MOLTBUNKER_TESTNET_PRIVATE_KEY=0x<your-32-byte-hex-key>\n"
        "  python examples/wallet_auth.py"
    )
    sys.exit(0)

from moltbunker import Client, ResourceLimits, Region  # noqa: E402

TESTNET_API = "https://api.moltbunker.com/v1"


def main() -> None:
    print("Connecting to MoltBunker testnet API...")
    client = Client(private_key=PRIVATE_KEY, base_url=TESTNET_API)

    # 1. Check wallet balance
    balance = client.get_balance()
    print(f"Wallet balance: {balance.bunker_balance} BUNKER")

    # 2. Check threat level
    threat = client.get_threat_level()
    print(f"Threat level : {threat.level} (score: {threat.score:.2f})")
    if threat.recommendation:
        print(f"Recommendation: {threat.recommendation}")

    # 3. List running containers
    containers = client.list_containers(status="running")
    print(f"Running containers: {len(containers)}")
    for c in containers[:5]:  # show at most 5
        print(f"  - {c.id}  region={getattr(c, 'region', 'n/a')}")

    # 4. Register a bot and deploy (commented out to avoid unintended charges)
    # Uncomment and adjust to actually deploy:
    #
    # bot = client.register_bot(
    #     name="example-agent",
    #     image="python:3.11-slim",
    #     resources=ResourceLimits(cpu_shares=512, memory_mb=256),
    #     region=Region.AUTO,
    # )
    # bot.enable_cloning(auto_clone_on_threat=True, max_clones=3)
    # deployment = bot.deploy()
    # print(f"Deployed container: {deployment.container_id}")

    print("\nDone.")


if __name__ == "__main__":
    main()
