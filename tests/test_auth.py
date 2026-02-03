"""Tests for authentication strategies"""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestAPIKeyAuth:
    """Tests for API key authentication"""

    def test_api_key_auth_creation(self):
        from moltbunker.auth import APIKeyAuth

        auth = APIKeyAuth("mb_live_test123456789")
        assert auth.api_key == "mb_live_test123456789"
        assert auth.auth_type == "api_key"

    def test_api_key_auth_headers(self):
        from moltbunker.auth import APIKeyAuth

        auth = APIKeyAuth("mb_live_test123456789")
        headers = auth.get_auth_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer mb_live_test123456789"

    def test_api_key_auth_identifier(self):
        from moltbunker.auth import APIKeyAuth

        # Long key (>20 chars) - shows first 20 + "..."
        auth = APIKeyAuth("mb_live_test123456789abcdef")
        identifier = auth.identifier
        assert identifier == "mb_live_test12345678..."

        # Short key (<=20 chars) - shows first 8 + "..."
        auth2 = APIKeyAuth("mb_test_123")
        assert auth2.identifier == "mb_test_..."

    def test_api_key_auth_empty_key_raises(self):
        from moltbunker.auth import APIKeyAuth

        with pytest.raises(ValueError, match="cannot be empty"):
            APIKeyAuth("")

    def test_api_key_auth_none_key_raises(self):
        from moltbunker.auth import APIKeyAuth

        with pytest.raises(ValueError):
            APIKeyAuth(None)


class TestWalletAuth:
    """Tests for wallet authentication"""

    @pytest.fixture
    def mock_web3(self):
        """Mock web3 dependencies"""
        with patch.dict('sys.modules', {
            'eth_account': MagicMock(),
            'eth_account.messages': MagicMock(),
        }):
            yield

    def test_wallet_auth_requires_web3(self):
        """Test that WalletAuth raises ImportError without web3"""
        # This test verifies the import check works
        from moltbunker.auth import HAS_WEB3

        if not HAS_WEB3:
            from moltbunker.auth import WalletAuth
            with pytest.raises(ImportError, match="web3"):
                WalletAuth("0x" + "a" * 64)

    def test_wallet_auth_creation(self):
        """Test wallet auth creation with real web3"""
        from moltbunker.auth import WalletAuth

        # Test private key (DO NOT USE IN PRODUCTION)
        test_key = "0x" + "a" * 64
        auth = WalletAuth(test_key)

        assert auth.auth_type == "wallet"
        assert auth.wallet_address.startswith("0x")

    def test_wallet_auth_headers(self):
        """Test wallet auth generates proper headers"""
        from moltbunker.auth import WalletAuth

        test_key = "0x" + "a" * 64
        auth = WalletAuth(test_key)
        headers = auth.get_auth_headers()

        assert "X-Wallet-Address" in headers
        assert "X-Wallet-Signature" in headers
        assert "X-Wallet-Message" in headers
        assert headers["X-Wallet-Message"].startswith("moltbunker-auth:")

    def test_wallet_auth_empty_key_raises(self):
        """Test that empty private key raises ValueError"""
        from moltbunker.auth import HAS_WEB3

        if HAS_WEB3:
            from moltbunker.auth import WalletAuth
            with pytest.raises(ValueError, match="cannot be empty"):
                WalletAuth("")


class TestGetAuthFromEnv:
    """Tests for environment-based auth detection"""

    def test_api_key_from_env(self):
        from moltbunker.auth import get_auth_from_env

        with patch.dict(os.environ, {"MOLTBUNKER_API_KEY": "mb_test_123"}):
            auth = get_auth_from_env()
            assert auth is not None
            assert auth.auth_type == "api_key"

    def test_no_credentials_returns_none(self):
        from moltbunker.auth import get_auth_from_env

        with patch.dict(os.environ, {}, clear=True):
            # Clear any existing env vars
            os.environ.pop("MOLTBUNKER_API_KEY", None)
            os.environ.pop("MOLTBUNKER_PRIVATE_KEY", None)
            auth = get_auth_from_env()
            assert auth is None

    def test_private_key_from_env(self):
        from moltbunker.auth import get_auth_from_env

        test_key = "0x" + "a" * 64
        with patch.dict(os.environ, {"MOLTBUNKER_PRIVATE_KEY": test_key}):
            auth = get_auth_from_env()
            assert auth is not None
            assert auth.auth_type == "wallet"
