"""Tests for exec terminal session"""

import struct
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestExecFrameProtocol:
    """Test binary frame constants and encoding"""

    def test_frame_type_constants(self):
        """Test frame type byte values"""
        from moltbunker.exec import (
            FRAME_DATA,
            FRAME_RESIZE,
            FRAME_PING,
            FRAME_PONG,
            FRAME_CLOSE,
            FRAME_ERROR,
        )

        assert FRAME_DATA == 0x01
        assert FRAME_RESIZE == 0x02
        assert FRAME_PING == 0x03
        assert FRAME_PONG == 0x04
        assert FRAME_CLOSE == 0x05
        assert FRAME_ERROR == 0x06

    def test_resize_frame_encoding(self):
        """Test that resize encodes cols/rows as big-endian uint16"""
        cols, rows = 120, 40
        encoded = struct.pack(">HH", cols, rows)

        assert len(encoded) == 4
        decoded_cols, decoded_rows = struct.unpack(">HH", encoded)
        assert decoded_cols == 120
        assert decoded_rows == 40

    def test_data_frame_construction(self):
        """Test data frame: type byte + payload"""
        from moltbunker.exec import FRAME_DATA

        payload = b"ls -la\n"
        frame = bytes([FRAME_DATA]) + payload

        assert frame[0] == 0x01
        assert frame[1:] == payload

    def test_close_frame_construction(self):
        """Test close frame: type byte + empty payload"""
        from moltbunker.exec import FRAME_CLOSE

        frame = bytes([FRAME_CLOSE]) + b""

        assert frame == bytes([0x05])


class TestExecSessionImportGuard:
    """Test import guards"""

    def test_requires_websockets(self):
        """ExecSession should require websockets"""
        from moltbunker.exec import HAS_WEBSOCKETS, HAS_WEB3

        if not HAS_WEBSOCKETS or not HAS_WEB3:
            from moltbunker.exec import ExecSession

            with pytest.raises(ImportError):
                ExecSession(
                    api_base_url="https://test.api.com/v1",
                    container_id="mb-123",
                    private_key="0x" + "a" * 64,
                    token="wt_test",
                )


class TestExecSessionLogic:
    """Test exec session send/receive logic"""

    def test_send_frame(self):
        """Test _send_frame composes correct binary message"""
        from moltbunker.exec import HAS_WEBSOCKETS, HAS_WEB3

        if not HAS_WEBSOCKETS or not HAS_WEB3:
            pytest.skip("websockets or web3 not installed")

        from moltbunker.exec import ExecSession, FRAME_DATA

        session = ExecSession.__new__(ExecSession)
        session._ws = MagicMock()

        session._send_frame(FRAME_DATA, b"hello")

        session._ws.send.assert_called_once_with(bytes([0x01]) + b"hello")

    def test_send_frame_no_ws(self):
        """Test _send_frame is safe when ws is None"""
        from moltbunker.exec import HAS_WEBSOCKETS, HAS_WEB3

        if not HAS_WEBSOCKETS or not HAS_WEB3:
            pytest.skip("websockets or web3 not installed")

        from moltbunker.exec import ExecSession, FRAME_DATA

        session = ExecSession.__new__(ExecSession)
        session._ws = None

        # Should not raise
        session._send_frame(FRAME_DATA, b"hello")

    def test_send_wraps_data(self):
        """Test send() wraps data with DATA frame type"""
        from moltbunker.exec import HAS_WEBSOCKETS, HAS_WEB3

        if not HAS_WEBSOCKETS or not HAS_WEB3:
            pytest.skip("websockets or web3 not installed")

        from moltbunker.exec import ExecSession, FRAME_DATA

        session = ExecSession.__new__(ExecSession)
        session._ws = MagicMock()

        session.send(b"echo test\n")

        session._ws.send.assert_called_once()
        sent = session._ws.send.call_args[0][0]
        assert sent[0] == FRAME_DATA
        assert sent[1:] == b"echo test\n"

    def test_resize_sends_correct_frame(self):
        """Test resize sends RESIZE frame with encoded dimensions"""
        from moltbunker.exec import HAS_WEBSOCKETS, HAS_WEB3

        if not HAS_WEBSOCKETS or not HAS_WEB3:
            pytest.skip("websockets or web3 not installed")

        from moltbunker.exec import ExecSession, FRAME_RESIZE

        session = ExecSession.__new__(ExecSession)
        session._ws = MagicMock()

        session.resize(120, 40)

        sent = session._ws.send.call_args[0][0]
        assert sent[0] == FRAME_RESIZE
        cols, rows = struct.unpack(">HH", sent[1:5])
        assert cols == 120
        assert rows == 40

    def test_on_data_callback(self):
        """Test on_data sets the callback"""
        from moltbunker.exec import HAS_WEBSOCKETS, HAS_WEB3

        if not HAS_WEBSOCKETS or not HAS_WEB3:
            pytest.skip("websockets or web3 not installed")

        from moltbunker.exec import ExecSession

        session = ExecSession.__new__(ExecSession)
        session._data_callback = None

        cb = MagicMock()
        session.on_data(cb)

        assert session._data_callback is cb

    def test_close_sends_close_frame(self):
        """Test close() sends CLOSE frame and closes ws"""
        from moltbunker.exec import HAS_WEBSOCKETS, HAS_WEB3

        if not HAS_WEBSOCKETS or not HAS_WEB3:
            pytest.skip("websockets or web3 not installed")

        from moltbunker.exec import ExecSession, FRAME_CLOSE

        session = ExecSession.__new__(ExecSession)
        mock_ws = MagicMock()
        session._ws = mock_ws
        session._running = True
        session._recv_thread = None

        session.close()

        assert session._running is False
        # close() sets _ws = None, but the mock captured the calls
        calls = mock_ws.send.call_args_list
        assert any(args[0][0][0] == FRAME_CLOSE for args in calls)
        mock_ws.close.assert_called_once()


class TestSignChallenge:
    """Test challenge signing helper"""

    def test_sign_challenge(self):
        """Test _sign_challenge produces a valid signature"""
        from moltbunker.exec import HAS_WEB3

        if not HAS_WEB3:
            pytest.skip("web3 not installed")

        from moltbunker.exec import _sign_challenge

        sig = _sign_challenge("0x" + "a" * 64, "test message")

        assert sig.startswith("0x")
        assert len(sig) > 10

    def test_sign_challenge_normalizes_key(self):
        """Test that key without 0x prefix is normalized"""
        from moltbunker.exec import HAS_WEB3

        if not HAS_WEB3:
            pytest.skip("web3 not installed")

        from moltbunker.exec import _sign_challenge

        sig1 = _sign_challenge("0x" + "a" * 64, "msg")
        sig2 = _sign_challenge("a" * 64, "msg")

        assert sig1 == sig2
