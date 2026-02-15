"""Tests for WebSocket event streams"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class TestEventStreamImportGuard:
    """Test import guard for websockets"""

    def test_import_guard(self):
        """EventStream should work when websockets is available"""
        from moltbunker.events import HAS_WEBSOCKETS

        # If websockets is installed, the class should be importable
        if HAS_WEBSOCKETS:
            from moltbunker.events import EventStream, AsyncEventStream

            assert EventStream is not None
            assert AsyncEventStream is not None


class TestEventStreamMessageHandling:
    """Test message handling logic"""

    def test_handle_ping_sends_pong(self):
        """Test that ping messages are answered with pong"""
        from moltbunker.events import HAS_WEBSOCKETS

        if not HAS_WEBSOCKETS:
            pytest.skip("websockets not installed")

        from moltbunker.events import EventStream

        stream = EventStream.__new__(EventStream)
        stream._callbacks = {}
        stream._lock = __import__("threading").Lock()
        stream._ws = MagicMock()

        stream._handle_message({"type": "ping"})

        stream._ws.send.assert_called_once()
        sent = json.loads(stream._ws.send.call_args[0][0])
        assert sent["type"] == "pong"

    def test_handle_update_calls_callback(self):
        """Test that update messages dispatch to channel callback"""
        from moltbunker.events import HAS_WEBSOCKETS

        if not HAS_WEBSOCKETS:
            pytest.skip("websockets not installed")

        from moltbunker.events import EventStream

        stream = EventStream.__new__(EventStream)
        stream._lock = __import__("threading").Lock()
        stream._ws = MagicMock()

        callback = MagicMock()
        stream._callbacks = {"containers": callback}

        test_data = {"container_id": "mb-123", "status": "running"}
        stream._handle_message({
            "type": "update",
            "channel": "containers",
            "data": test_data,
        })

        callback.assert_called_once_with(test_data)

    def test_handle_update_no_callback(self):
        """Test that update for unsubscribed channel is ignored"""
        from moltbunker.events import HAS_WEBSOCKETS

        if not HAS_WEBSOCKETS:
            pytest.skip("websockets not installed")

        from moltbunker.events import EventStream

        stream = EventStream.__new__(EventStream)
        stream._lock = __import__("threading").Lock()
        stream._ws = MagicMock()
        stream._callbacks = {}

        # Should not raise
        stream._handle_message({
            "type": "update",
            "channel": "unknown",
            "data": {},
        })

    def test_handle_subscribed_ack(self):
        """Test that subscribed/unsubscribed acks are handled"""
        from moltbunker.events import HAS_WEBSOCKETS

        if not HAS_WEBSOCKETS:
            pytest.skip("websockets not installed")

        from moltbunker.events import EventStream

        stream = EventStream.__new__(EventStream)
        stream._callbacks = {}
        stream._lock = __import__("threading").Lock()
        stream._ws = MagicMock()

        # Should not raise
        stream._handle_message({"type": "subscribed", "data": {"channels": ["containers"]}})
        stream._handle_message({"type": "unsubscribed", "data": {"channels": ["containers"]}})

    def test_subscribe_sends_message(self):
        """Test that subscribe sends a subscribe message"""
        from moltbunker.events import HAS_WEBSOCKETS

        if not HAS_WEBSOCKETS:
            pytest.skip("websockets not installed")

        from moltbunker.events import EventStream

        stream = EventStream.__new__(EventStream)
        stream._callbacks = {}
        stream._lock = __import__("threading").Lock()
        stream._ws = MagicMock()

        callback = MagicMock()
        stream.subscribe("health", callback)

        assert "health" in stream._callbacks
        assert stream._callbacks["health"] is callback
        stream._ws.send.assert_called_once()
        sent = json.loads(stream._ws.send.call_args[0][0])
        assert sent["type"] == "subscribe"
        assert "health" in sent["data"]["channels"]

    def test_unsubscribe_removes_callback(self):
        """Test that unsubscribe removes the callback and sends message"""
        from moltbunker.events import HAS_WEBSOCKETS

        if not HAS_WEBSOCKETS:
            pytest.skip("websockets not installed")

        from moltbunker.events import EventStream

        stream = EventStream.__new__(EventStream)
        stream._lock = __import__("threading").Lock()
        stream._ws = MagicMock()
        stream._callbacks = {"containers": MagicMock()}

        stream.unsubscribe("containers")

        assert "containers" not in stream._callbacks

    def test_callback_error_does_not_crash(self):
        """Test that callback exceptions are caught"""
        from moltbunker.events import HAS_WEBSOCKETS

        if not HAS_WEBSOCKETS:
            pytest.skip("websockets not installed")

        from moltbunker.events import EventStream

        stream = EventStream.__new__(EventStream)
        stream._lock = __import__("threading").Lock()
        stream._ws = MagicMock()

        def bad_callback(data):
            raise RuntimeError("oops")

        stream._callbacks = {"test": bad_callback}

        # Should not raise
        stream._handle_message({
            "type": "update",
            "channel": "test",
            "data": {"foo": "bar"},
        })
