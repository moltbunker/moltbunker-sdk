"""Moltbunker SDK Exec Terminal Sessions

Interactive container exec over WebSocket with binary frame protocol.
Requires [wallet] + [ws] extras: pip install 'moltbunker[full]'
"""

import json
import logging
import struct
import threading
from typing import Any, Callable, Dict, Optional

try:
    import websockets

    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

try:
    from eth_account import Account
    from eth_account.messages import encode_defunct

    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False

logger = logging.getLogger("moltbunker.exec")

# Binary frame types
FRAME_DATA = 0x01
FRAME_RESIZE = 0x02
FRAME_PING = 0x03
FRAME_PONG = 0x04
FRAME_CLOSE = 0x05
FRAME_ERROR = 0x06


def _require_deps() -> None:
    if not HAS_WEBSOCKETS:
        raise ImportError(
            "Exec sessions require websockets. "
            "Install with: pip install 'moltbunker[ws]'"
        )
    if not HAS_WEB3:
        raise ImportError(
            "Exec sessions require wallet signing. "
            "Install with: pip install 'moltbunker[wallet]'"
        )


def _exec_challenge(
    api_base_url: str,
    container_id: str,
    token: str,
) -> Dict[str, Any]:
    """Get exec challenge from API."""
    import httpx

    resp = httpx.get(
        f"{api_base_url}/exec/challenge",
        params={"container_id": container_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def _sign_challenge(private_key: str, message: str) -> str:
    """Sign a challenge message with EIP-191."""
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    account = Account.from_key(private_key)
    msg_encoded = encode_defunct(text=message)
    signed = account.sign_message(msg_encoded)
    return "0x" + signed.signature.hex()


class ExecSession:
    """Synchronous interactive exec session over WebSocket.

    Usage::

        with ExecSession(
            api_base_url="https://api.moltbunker.com/v1",
            container_id="mb-abc123",
            private_key="0x...",
            token="wt_...",
        ) as session:
            session.on_data(lambda data: sys.stdout.buffer.write(data))
            session.send(b"ls -la\\n")
            session.resize(120, 40)
    """

    def __init__(
        self,
        api_base_url: str,
        container_id: str,
        private_key: str,
        token: str,
        cols: int = 80,
        rows: int = 24,
    ):
        _require_deps()
        self._api_base_url = api_base_url.rstrip("/")
        self._container_id = container_id
        self._private_key = private_key
        self._token = token
        self._cols = cols
        self._rows = rows
        self._ws: Any = None
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._data_callback: Optional[Callable[[bytes], None]] = None
        self._error_callback: Optional[Callable[[str], None]] = None

    def __enter__(self) -> "ExecSession":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def connect(self) -> None:
        """Perform challenge-response auth and open WebSocket."""
        import websockets.sync.client as ws_sync

        # Step 1: Get challenge
        challenge = _exec_challenge(
            self._api_base_url, self._container_id, self._token
        )

        # Step 2: Sign challenge
        nonce = challenge.get("nonce", challenge.get("message", ""))
        signature = _sign_challenge(self._private_key, nonce)

        # Step 3: Open WebSocket with signed params
        ws_url = self._api_base_url.replace("https://", "wss://").replace(
            "http://", "ws://"
        )
        url = (
            f"{ws_url}/exec"
            f"?nonce={nonce}"
            f"&signature={signature}"
            f"&container_id={self._container_id}"
            f"&cols={self._cols}"
            f"&rows={self._rows}"
        )

        self._ws = ws_sync.connect(
            url,
            additional_headers={"Authorization": f"Bearer {self._token}"},
        )
        self._running = True

        # Start receive thread
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def _recv_loop(self) -> None:
        while self._running and self._ws:
            try:
                msg = self._ws.recv(timeout=1.0)
                if isinstance(msg, bytes) and len(msg) >= 1:
                    frame_type = msg[0]
                    payload = msg[1:]

                    if frame_type == FRAME_DATA and self._data_callback:
                        self._data_callback(payload)
                    elif frame_type == FRAME_PING:
                        self._send_frame(FRAME_PONG, b"")
                    elif frame_type == FRAME_CLOSE:
                        self._running = False
                        break
                    elif frame_type == FRAME_ERROR and self._error_callback:
                        self._error_callback(payload.decode("utf-8", errors="replace"))
            except TimeoutError:
                continue
            except Exception:
                if self._running:
                    logger.debug("Exec recv error", exc_info=True)
                break

    def _send_frame(self, frame_type: int, data: bytes) -> None:
        if self._ws:
            try:
                self._ws.send(bytes([frame_type]) + data)
            except Exception:
                logger.debug("Exec send failed", exc_info=True)

    def send(self, data: bytes) -> None:
        """Send stdin data to the container."""
        self._send_frame(FRAME_DATA, data)

    def resize(self, cols: int, rows: int) -> None:
        """Send terminal resize event."""
        self._send_frame(FRAME_RESIZE, struct.pack(">HH", cols, rows))

    def recv(self, timeout: float = 5.0) -> Optional[bytes]:
        """Receive stdout data (blocking). Returns None on close."""
        if not self._ws:
            return None
        try:
            msg = self._ws.recv(timeout=timeout)
            if isinstance(msg, bytes) and len(msg) >= 1 and msg[0] == FRAME_DATA:
                return msg[1:]
        except TimeoutError:
            pass
        except Exception:
            pass
        return None

    def on_data(self, callback: Callable[[bytes], None]) -> None:
        """Set callback for received stdout data."""
        self._data_callback = callback

    def on_error(self, callback: Callable[[str], None]) -> None:
        """Set callback for error frames."""
        self._error_callback = callback

    def close(self) -> None:
        """Gracefully close the exec session."""
        self._running = False
        if self._ws:
            try:
                self._send_frame(FRAME_CLOSE, b"")
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=3.0)


class AsyncExecSession:
    """Async interactive exec session over WebSocket.

    Usage::

        async with AsyncExecSession(
            api_base_url="https://api.moltbunker.com/v1",
            container_id="mb-abc123",
            private_key="0x...",
            token="wt_...",
        ) as session:
            session.on_data(lambda data: print(data.decode()))
            await session.send(b"ls -la\\n")
    """

    def __init__(
        self,
        api_base_url: str,
        container_id: str,
        private_key: str,
        token: str,
        cols: int = 80,
        rows: int = 24,
    ):
        _require_deps()
        self._api_base_url = api_base_url.rstrip("/")
        self._container_id = container_id
        self._private_key = private_key
        self._token = token
        self._cols = cols
        self._rows = rows
        self._ws: Any = None
        self._running = False
        self._recv_task: Any = None
        self._data_callback: Optional[Callable[[bytes], Any]] = None
        self._error_callback: Optional[Callable[[str], Any]] = None

    async def __aenter__(self) -> "AsyncExecSession":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def connect(self) -> None:
        """Perform challenge-response auth and open WebSocket."""
        import asyncio

        import httpx
        from websockets.asyncio.client import connect

        # Step 1: Get challenge (async)
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{self._api_base_url}/exec/challenge",
                params={"container_id": self._container_id},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            challenge = resp.json()

        # Step 2: Sign challenge
        nonce = challenge.get("nonce", challenge.get("message", ""))
        signature = _sign_challenge(self._private_key, nonce)

        # Step 3: Open WebSocket
        ws_url = self._api_base_url.replace("https://", "wss://").replace(
            "http://", "ws://"
        )
        url = (
            f"{ws_url}/exec"
            f"?nonce={nonce}"
            f"&signature={signature}"
            f"&container_id={self._container_id}"
            f"&cols={self._cols}"
            f"&rows={self._rows}"
        )

        self._ws = await connect(
            url,
            additional_headers={"Authorization": f"Bearer {self._token}"},
        )
        self._running = True

        # Start receive task
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def _recv_loop(self) -> None:
        import asyncio
        import inspect

        while self._running and self._ws:
            try:
                msg = await asyncio.wait_for(self._ws.recv(), timeout=30.0)
                if isinstance(msg, bytes) and len(msg) >= 1:
                    frame_type = msg[0]
                    payload = msg[1:]

                    if frame_type == FRAME_DATA and self._data_callback:
                        result = self._data_callback(payload)
                        if inspect.isawaitable(result):
                            await result
                    elif frame_type == FRAME_PING:
                        await self._send_frame(FRAME_PONG, b"")
                    elif frame_type == FRAME_CLOSE:
                        self._running = False
                        break
                    elif frame_type == FRAME_ERROR and self._error_callback:
                        error_msg = payload.decode("utf-8", errors="replace")
                        result = self._error_callback(error_msg)
                        if inspect.isawaitable(result):
                            await result
            except asyncio.TimeoutError:
                # Send ping to keep alive
                await self._send_frame(FRAME_PING, b"")
            except Exception:
                if self._running:
                    logger.debug("Async exec recv error", exc_info=True)
                break

    async def _send_frame(self, frame_type: int, data: bytes) -> None:
        if self._ws:
            try:
                await self._ws.send(bytes([frame_type]) + data)
            except Exception:
                logger.debug("Async exec send failed", exc_info=True)

    async def send(self, data: bytes) -> None:
        """Send stdin data."""
        await self._send_frame(FRAME_DATA, data)

    async def resize(self, cols: int, rows: int) -> None:
        """Send terminal resize."""
        await self._send_frame(FRAME_RESIZE, struct.pack(">HH", cols, rows))

    def on_data(self, callback: Callable[[bytes], Any]) -> None:
        """Set callback for stdout data."""
        self._data_callback = callback

    def on_error(self, callback: Callable[[str], Any]) -> None:
        """Set callback for errors."""
        self._error_callback = callback

    async def close(self) -> None:
        """Gracefully close."""
        self._running = False
        if self._ws:
            try:
                await self._send_frame(FRAME_CLOSE, b"")
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except Exception:
                pass
