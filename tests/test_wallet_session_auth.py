"""Tests for WalletSessionAuth challenge-response flow"""

import pytest
from unittest.mock import patch, MagicMock


class TestWalletSessionAuth:
    """Tests for wallet session authentication"""

    def test_requires_web3(self):
        """Test that WalletSessionAuth raises ImportError without web3"""
        from moltbunker.auth import HAS_WEB3

        if not HAS_WEB3:
            from moltbunker.auth import WalletSessionAuth

            with pytest.raises(ImportError, match="wallet"):
                WalletSessionAuth("0x" + "a" * 64)

    def test_empty_key_raises(self):
        """Test that empty private key raises ValueError"""
        from moltbunker.auth import HAS_WEB3

        if HAS_WEB3:
            from moltbunker.auth import WalletSessionAuth

            with pytest.raises(ValueError, match="cannot be empty"):
                WalletSessionAuth("")

    def test_auth_type(self):
        """Test auth_type property"""
        from moltbunker.auth import HAS_WEB3

        if not HAS_WEB3:
            pytest.skip("web3 not installed")

        from moltbunker.auth import WalletSessionAuth

        with patch("httpx.post"):
            auth = WalletSessionAuth.__new__(WalletSessionAuth)
            auth._private_key = "0x" + "a" * 64
            auth._wallet_address = "0x1234567890abcdef1234567890abcdef12345678"
            auth._api_base_url = "https://api.moltbunker.com/v1"
            auth._session_token = None
            auth._token_expires_at = 0.0

            assert auth.auth_type == "wallet_session"
            assert auth.identifier == "0x1234567890abcdef1234567890abcdef12345678"

    @patch("httpx.post")
    def test_challenge_response_flow(self, mock_post):
        """Test full challenge-response authentication flow"""
        from moltbunker.auth import HAS_WEB3

        if not HAS_WEB3:
            pytest.skip("web3 not installed")

        from moltbunker.auth import WalletSessionAuth

        # Mock challenge response
        challenge_resp = MagicMock()
        challenge_resp.status_code = 200
        challenge_resp.json.return_value = {
            "message": "Sign this message to authenticate: abc123",
            "expires_in": 300,
        }
        challenge_resp.raise_for_status = MagicMock()

        # Mock verify response
        verify_resp = MagicMock()
        verify_resp.status_code = 200
        verify_resp.json.return_value = {
            "access_token": "wt_session_token_hex",
            "expires_in": 3600,
            "wallet": "0x1234",
            "auth_type": "wallet",
        }
        verify_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [challenge_resp, verify_resp]

        test_key = "0x" + "a" * 64
        auth = WalletSessionAuth(
            test_key, api_base_url="https://test.api.com/v1"
        )

        headers = auth.get_auth_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer wt_session_token_hex"
        assert mock_post.call_count == 2

        # First call should be challenge
        challenge_call = mock_post.call_args_list[0]
        assert "/auth/challenge" in challenge_call[0][0]

        # Second call should be verify
        verify_call = mock_post.call_args_list[1]
        assert "/auth/verify" in verify_call[0][0]

    @patch("httpx.post")
    def test_token_reuse(self, mock_post):
        """Test that valid tokens are reused without re-authenticating"""
        from moltbunker.auth import HAS_WEB3

        if not HAS_WEB3:
            pytest.skip("web3 not installed")

        from moltbunker.auth import WalletSessionAuth

        challenge_resp = MagicMock()
        challenge_resp.json.return_value = {
            "message": "Sign this: abc",
            "expires_in": 300,
        }
        challenge_resp.raise_for_status = MagicMock()

        verify_resp = MagicMock()
        verify_resp.json.return_value = {
            "access_token": "wt_valid_token",
            "expires_in": 3600,
        }
        verify_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [challenge_resp, verify_resp]

        auth = WalletSessionAuth("0x" + "a" * 64)

        # First call triggers auth
        headers1 = auth.get_auth_headers()
        assert mock_post.call_count == 2

        # Second call should reuse token
        headers2 = auth.get_auth_headers()
        assert mock_post.call_count == 2  # No additional calls
        assert headers1 == headers2

    @patch("httpx.post")
    def test_refresh_clears_token(self, mock_post):
        """Test that refresh() forces re-authentication"""
        from moltbunker.auth import HAS_WEB3

        if not HAS_WEB3:
            pytest.skip("web3 not installed")

        from moltbunker.auth import WalletSessionAuth

        challenge_resp = MagicMock()
        challenge_resp.json.return_value = {
            "message": "Sign: xyz",
            "expires_in": 300,
        }
        challenge_resp.raise_for_status = MagicMock()

        verify_resp = MagicMock()
        verify_resp.json.return_value = {
            "access_token": "wt_new_token",
            "expires_in": 3600,
        }
        verify_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [
            challenge_resp,
            verify_resp,
            challenge_resp,
            verify_resp,
        ]

        auth = WalletSessionAuth("0x" + "a" * 64)
        auth.get_auth_headers()
        assert mock_post.call_count == 2

        # Force refresh
        auth.refresh()
        assert mock_post.call_count == 4  # 2 more calls (challenge + verify)
