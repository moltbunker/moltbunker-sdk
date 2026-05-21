#!/usr/bin/env python3
"""Example: API key authentication — list containers and check threat level.

Usage:
    export MOLTBUNKER_API_KEY=mb_live_xxx
    python examples/api_key_auth.py

If the env-var is not set the script prints instructions and exits gracefully.
Suitable for managed/server-side deployments where a wallet is not available.
"""
import os
import sys

API_KEY = os.environ.get("MOLTBUNKER_API_KEY")
if not API_KEY:
    print(
        "WARNING: MOLTBUNKER_API_KEY is not set.\n"
        "Set it to your managed API key to run this example.\n"
        "Example:\n"
        "  export MOLTBUNKER_API_KEY=mb_live_<your-key>\n"
        "  python examples/api_key_auth.py"
    )
    sys.exit(0)

from moltbunker import Client  # noqa: E402


def main() -> None:
    print("Connecting with API key authentication...")
    client = Client(api_key=API_KEY)

    # 1. Threat level (always a good first check)
    threat = client.get_threat_level()
    print(f"Threat level: {threat.level}  score={threat.score:.2f}")

    # 2. List all containers (all statuses)
    containers = client.list_containers()
    print(f"Total containers: {len(containers)}")
    for c in containers[:10]:
        status = getattr(c, 'status', 'unknown')
        print(f"  {c.id}  status={status}")

    # 3. Snapshot example (commented out to avoid unintended side effects)
    # If you have a running container you can snapshot it like this:
    #
    # from moltbunker import SnapshotType
    # snapshot = client.create_snapshot(
    #     container_id="mb-abc123",
    #     snapshot_type=SnapshotType.FULL,
    # )
    # print(f"Snapshot created: {snapshot.id}")

    print("\nDone.")


if __name__ == "__main__":
    main()
