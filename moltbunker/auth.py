"""Moltbunker SDK Authentication Strategies

Supports:
- API Key authentication (for managed services)
- Wallet authentication (permissionless, for AI agents)
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional

try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False


class AuthStrategy(ABC):
    """Base authentication strategy"""

    @abstractmethod
    def get_auth_headers(self, message: Optional[str] = None) -> Dict[str, str]:
        """Get authentication headers for a request.

        Args:
            message: Optional message to sign (for wallet auth)

        Returns:
            Dictionary of headers to include in the request
        """
        pass

    @property
    @abstractmethod
    def identifier(self) -> str:
        """Returns user identifier (api_key prefix or wallet address)"""
        pass

    @property
    @abstractmethod
    def auth_type(self) -> str:
        """Returns authentication type name"""
        pass


class APIKeyAuth(AuthStrategy):
    """API Key authentication strategy.

    Used for managed services with pre-registered API keys.
    """

    def __init__(self, api_key: str):
        """Initialize API key authentication.

        Args:
            api_key: The API key (format: mb_live_xxx or mb_test_xxx)
        """
        if not api_key:
            raise ValueError("api_key cannot be empty")
        self.api_key = api_key

    def get_auth_headers(self, message: Optional[str] = None) -> Dict[str, str]:
        """Get Bearer token authorization header."""
        return {"Authorization": f"Bearer {self.api_key}"}

    @property
    def identifier(self) -> str:
        """Returns masked API key."""
        if len(self.api_key) > 20:
            return self.api_key[:20] + "..."
        return self.api_key[:8] + "..."

    @property
    def auth_type(self) -> str:
        return "api_key"


class WalletAuth(AuthStrategy):
    """Wallet-based authentication strategy.

    Permissionless authentication for AI agents using Ethereum wallets.
    Signs messages with private key to prove wallet ownership.
    """

    def __init__(self, private_key: str, wallet_address: Optional[str] = None):
        """Initialize wallet authentication.

        Args:
            private_key: Ethereum private key (hex string, with or without 0x prefix)
            wallet_address: Optional wallet address (derived from key if not provided)

        Raises:
            ImportError: If web3/eth-account not installed
            ValueError: If private key is invalid
        """
        if not HAS_WEB3:
            raise ImportError(
                "Wallet authentication requires web3 and eth-account. "
                "Install with: pip install moltbunker"
            )

        if not private_key:
            raise ValueError("private_key cannot be empty")

        # Normalize private key format
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key

        self.private_key = private_key
        self.account = Account.from_key(private_key)
        self.wallet_address = wallet_address or self.account.address

    def get_auth_headers(self, message: Optional[str] = None) -> Dict[str, str]:
        """Get wallet signature authentication headers.

        Creates a signed message proving wallet ownership.

        Args:
            message: Optional custom message to sign. If not provided,
                    generates a timestamped auth message.

        Returns:
            Headers with wallet address, signature, and message
        """
        if message is None:
            timestamp = int(time.time())
            message = f"moltbunker-auth:{timestamp}"

        # Sign the message
        message_encoded = encode_defunct(text=message)
        signed = self.account.sign_message(message_encoded)

        return {
            "X-Wallet-Address": self.wallet_address,
            "X-Wallet-Signature": signed.signature.hex(),
            "X-Wallet-Message": message,
        }

    @property
    def identifier(self) -> str:
        """Returns wallet address."""
        return self.wallet_address

    @property
    def auth_type(self) -> str:
        return "wallet"

    def sign_transaction(self, transaction: Dict) -> str:
        """Sign a transaction for on-chain operations.

        Args:
            transaction: Transaction dictionary

        Returns:
            Signed transaction as hex string
        """
        signed = self.account.sign_transaction(transaction)
        return signed.rawTransaction.hex()


def get_auth_from_env() -> Optional[AuthStrategy]:
    """Get authentication strategy from environment variables.

    Checks for:
    - MOLTBUNKER_API_KEY: API key authentication
    - MOLTBUNKER_PRIVATE_KEY: Wallet authentication
    - MOLTBUNKER_WALLET_ADDRESS: Optional wallet address override

    Returns:
        AuthStrategy or None if no credentials found
    """
    api_key = os.environ.get("MOLTBUNKER_API_KEY")
    if api_key:
        return APIKeyAuth(api_key)

    private_key = os.environ.get("MOLTBUNKER_PRIVATE_KEY")
    if private_key:
        wallet_address = os.environ.get("MOLTBUNKER_WALLET_ADDRESS")
        return WalletAuth(private_key, wallet_address)

    return None
