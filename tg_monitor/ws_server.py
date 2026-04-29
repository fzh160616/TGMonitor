"""Local WebSocket server.

Runs in its own thread + asyncio loop. Accepts inbound client connections;
on each new client, pushes the most recent N mentions as a `mentions_batch`,
then keeps the connection open. New mentions captured on the main thread
are broadcast to all connected clients via run_coroutine_threadsafe.

Reconfigures itself when ws_port/ws_host in config changes (polled every 2s).
"""

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional, Set

log = logging.getLogger(__name__)

BATCH_LIMIT = 200


def _build_payload(m) -> dict:
    """Build the per-mention JSON payload from a Mention object."""
    chat_username = getattr(m, "chat_username", "") or ""
    sender_username = getattr(m, "sender_username", "") or ""
    link = (
        f"https://t.me/{chat_username}/{m.tg_message_id}" if chat_username else ""
    )
    ts = datetime.fromtimestamp(m.received_at, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {
        "client_key": f"{m.chat_id}:{m.tg_message_id}",
        "chat_id": m.chat_id,
        "message_id": m.tg_message_id,
        "chat_title": m.chat_title,
        "chat_username": chat_username,
        "from_user_id": m.sender_id,
        "from_user_name": m.sender_name,
        "from_user_username": sender_username,
        "from_user_avatar": "",
        "message_text": m.text,
        "message_html": "",
        "message_link": link,
        "mentioned_at": ts,
        "read": m.seen_at is not None,
        "done": False,
    }


class WsServer:
    def __init__(
        self,
        get_port: Callable[[], int],
        get_host: Callable[[], str],
    ) -> None:
        self._get_port = get_port
        self._get_host = get_host
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._server = None  # websockets.Server instance
        self._clients: Set = set()
        self._current_port = 0
        self._current_host = ""

    # ---------- public API ----------

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="ws-server", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)

    def broadcast(self, mention) -> None:
        """Called from the main thread. Schedules an async broadcast on the loop."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        if not self._clients:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(mention), loop)
        except Exception:
            log.exception("ws broadcast: schedule failed")

    def client_count(self) -> int:
        return len(self._clients)

    # ---------- internals ----------

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception:
            log.exception("ws server crashed")
        finally:
            loop.close()

    async def _main(self) -> None:
        try:
            import websockets  # noqa: F401
        except ImportError:
            log.error("websockets package not installed; ws server disabled")
            return

        while not self._stop.is_set():
            port = self._get_port()
            host = self._get_host()
            if port == self._current_port and host == self._current_host:
                await self._sleep_interruptible(2)
                continue

            # Config changed — tear down old server before rebinding.
            if self._server is not None:
                await self._close_server()

            if port <= 0:
                self._current_port = 0
                self._current_host = ""
                await self._sleep_interruptible(2)
                continue

            try:
                import websockets

                self._server = await websockets.serve(
                    self._on_client, host, port
                )
                self._current_port = port
                self._current_host = host
                log.info("ws server listening on %s:%d", host, port)
            except Exception as e:
                log.exception("ws server: bind failed on %s:%d (%s)", host, port, e)
                self._current_port = 0
                self._current_host = ""
                await self._sleep_interruptible(5)

        await self._close_server()

    async def _on_client(self, ws) -> None:
        peer = "%s:%s" % ws.remote_address[:2]
        log.info(
            "ws client connected: %s (total=%d)", peer, len(self._clients) + 1
        )
        try:
            await self._send_batch(ws)
        except Exception:
            log.exception("ws batch send failed for %s", peer)
            return
        self._clients.add(ws)
        try:
            async for _ in ws:
                pass  # we don't expect inbound messages
        except Exception:
            pass
        finally:
            self._clients.discard(ws)
            log.info(
                "ws client disconnected: %s (total=%d)", peer, len(self._clients)
            )

    async def _send_batch(self, ws) -> None:
        from .store import Store

        try:
            store = Store()
            mentions = store.recent(BATCH_LIMIT)
        except Exception:
            log.exception("ws batch: store query failed")
            return
        msg = json.dumps(
            {
                "v": 1,
                "type": "mentions_batch",
                "payload": {"list": [_build_payload(m) for m in mentions]},
            },
            ensure_ascii=False,
        )
        await ws.send(msg)
        log.info("ws batch sent %d mentions: %s", len(mentions), msg)

    async def _broadcast(self, mention) -> None:
        msg = json.dumps(
            {"v": 1, "type": "mention", "payload": _build_payload(mention)},
            ensure_ascii=False,
        )
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)
        log.info(
            "ws broadcast mention to %d clients: %s", len(self._clients), msg
        )

    async def _close_server(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()

    async def _shutdown(self) -> None:
        await self._close_server()

    async def _sleep_interruptible(self, total: float) -> None:
        step = 0.2
        elapsed = 0.0
        while elapsed < total and not self._stop.is_set():
            await asyncio.sleep(min(step, total - elapsed))
            elapsed += step
