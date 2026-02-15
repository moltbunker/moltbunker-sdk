"""Moltbunker SDK WebSocket Event Streams

Real-time event subscriptions using WebSocket connections.
Requires the [ws] extra: pip install 'moltbunker[ws]'
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

try:
    import websockets
    import websockets.sync.client as ws_sync

    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

logger = logging.getLogger("moltbunker.events")

# Reconnect backoff
_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0
_PING_INTERVAL = 25.0


def _require_websockets() -> None:
    if not HAS_WEBSOCKETS:
        raise ImportError(
            "WebSocket events require the websockets library. "
            "Install with: pip install 'moltbunker[ws]'"
        )


class EventStream:
    """Synchronous WebSocket event stream with auto-reconnect.

    Usage::

        with EventStream("wss://api.moltbunker.com/ws", token="wt_...") as stream:
            stream.subscribe("containers", on_container_update)
            stream.subscribe("health", on_health_update)
            stream.wait()  # blocks until close() is called
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        auto_reconnect: bool = True,
    ):
        _require_websockets()
        self._url = url
        self._token = token
        self._auto_reconnect = auto_reconnect
        self._callbacks: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._ws: Any = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._close_event = threading.Event()

    def __enter__(self) -> "EventStream":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def connect(self) -> None:
        """Connect and start the receive loop in a background thread."""
        self._running = True
        self._close_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _run_loop(self) -> None:
        backoff = _INITIAL_BACKOFF
        while self._running:
            try:
                headers = self._build_headers()
                self._ws = ws_sync.connect(
                    self._url,
                    additional_headers=headers,
                )
                backoff = _INITIAL_BACKOFF
                logger.info("WebSocket connected to %s", self._url)

                # Re-subscribe to channels
                with self._lock:
                    channels = list(self._callbacks.keys())
                if channels:
                    self._send({"type": "subscribe", "data": {"channels": channels}})

                # Start ping timer
                last_ping = time.monotonic()

                while self._running:
                    try:
                        # Check if ping needed
                        now = time.monotonic()
                        if now - last_ping >= _PING_INTERVAL:
                            self._send({"type": "ping"})
                            last_ping = now

                        msg = self._ws.recv(timeout=1.0)
                        if isinstance(msg, str):
                            self._handle_message(json.loads(msg))
                    except TimeoutError:
                        continue
                    except Exception:
                        if self._running:
                            logger.debug("WebSocket recv error", exc_info=True)
                        break

            except Exception:
                if not self._running:
                    break
                logger.warning(
                    "WebSocket connection failed, retrying in %.1fs", backoff
                )

            finally:
                if self._ws:
                    try:
                        self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

            if not self._running or not self._auto_reconnect:
                break

            time.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)

        self._close_event.set()

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        msg_type = msg.get("type", "")
        if msg_type == "ping":
            self._send({"type": "pong"})
        elif msg_type == "pong":
            pass  # keepalive ack
        elif msg_type in ("subscribed", "unsubscribed"):
            logger.debug("Server ack: %s channels=%s", msg_type, msg.get("data"))
        elif msg_type == "update":
            channel = msg.get("channel", "")
            with self._lock:
                cb = self._callbacks.get(channel)
            if cb:
                try:
                    cb(msg.get("data", {}))
                except Exception:
                    logger.exception("Callback error for channel %s", channel)

    def _send(self, data: Dict[str, Any]) -> None:
        if self._ws:
            try:
                self._ws.send(json.dumps(data))
            except Exception:
                logger.debug("WebSocket send failed", exc_info=True)

    def subscribe(
        self,
        channel: str,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Subscribe to a channel with a callback."""
        with self._lock:
            self._callbacks[channel] = callback
        self._send({"type": "subscribe", "data": {"channels": [channel]}})

    def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel."""
        with self._lock:
            self._callbacks.pop(channel, None)
        self._send({"type": "unsubscribe", "data": {"channels": [channel]}})

    def wait(self) -> None:
        """Block until the stream is closed."""
        self._close_event.wait()

    def close(self) -> None:
        """Close the connection and stop the background thread."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)


class AsyncEventStream:
    """Async WebSocket event stream with auto-reconnect.

    Usage::

        async with AsyncEventStream("wss://api.moltbunker.com/ws") as stream:
            await stream.subscribe("containers", on_update)
            await stream.wait()
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        auto_reconnect: bool = True,
    ):
        _require_websockets()
        self._url = url
        self._token = token
        self._auto_reconnect = auto_reconnect
        self._callbacks: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._ws: Any = None
        self._running = False
        self._task: Any = None

    async def __aenter__(self) -> "AsyncEventStream":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def connect(self) -> None:
        """Connect and start the async receive loop."""
        import asyncio

        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _run_loop(self) -> None:
        import asyncio

        from websockets.asyncio.client import connect

        backoff = _INITIAL_BACKOFF
        while self._running:
            try:
                headers = self._build_headers()
                async with connect(
                    self._url,
                    additional_headers=headers,
                ) as ws:
                    self._ws = ws
                    backoff = _INITIAL_BACKOFF
                    logger.info("Async WebSocket connected to %s", self._url)

                    # Re-subscribe
                    channels = list(self._callbacks.keys())
                    if channels:
                        await self._send(
                            {"type": "subscribe", "data": {"channels": channels}}
                        )

                    last_ping = asyncio.get_event_loop().time()

                    while self._running:
                        try:
                            msg_str = await asyncio.wait_for(
                                ws.recv(), timeout=_PING_INTERVAL
                            )
                            if isinstance(msg_str, str):
                                await self._handle_message(json.loads(msg_str))
                        except asyncio.TimeoutError:
                            # Send ping
                            await self._send({"type": "ping"})
                        except Exception:
                            if self._running:
                                logger.debug("Async recv error", exc_info=True)
                            break

            except Exception:
                if not self._running:
                    break
                logger.warning(
                    "Async WebSocket connection failed, retrying in %.1fs", backoff
                )
            finally:
                self._ws = None

            if not self._running or not self._auto_reconnect:
                break

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)

    async def _handle_message(self, msg: Dict[str, Any]) -> None:
        import asyncio
        import inspect

        msg_type = msg.get("type", "")
        if msg_type == "ping":
            await self._send({"type": "pong"})
        elif msg_type == "pong":
            pass
        elif msg_type in ("subscribed", "unsubscribed"):
            logger.debug("Server ack: %s", msg_type)
        elif msg_type == "update":
            channel = msg.get("channel", "")
            cb = self._callbacks.get(channel)
            if cb:
                try:
                    result = cb(msg.get("data", {}))
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("Callback error for channel %s", channel)

    async def _send(self, data: Dict[str, Any]) -> None:
        if self._ws:
            try:
                await self._ws.send(json.dumps(data))
            except Exception:
                logger.debug("Async send failed", exc_info=True)

    async def subscribe(
        self,
        channel: str,
        callback: Callable[[Dict[str, Any]], Any],
    ) -> None:
        """Subscribe to a channel."""
        self._callbacks[channel] = callback
        await self._send({"type": "subscribe", "data": {"channels": [channel]}})

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel."""
        self._callbacks.pop(channel, None)
        await self._send({"type": "unsubscribe", "data": {"channels": [channel]}})

    async def wait(self) -> None:
        """Wait until closed."""
        if self._task:
            await self._task

    async def close(self) -> None:
        """Close the connection."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
