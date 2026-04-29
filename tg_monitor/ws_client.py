"""WebSocket cloud-sync worker.

Runs in its own thread + asyncio loop. Consumes Mention objects from a
thread-safe queue (populated on the main thread after each new mention),
and forwards them to a configurable WS endpoint.

Flow:
  1. On (re)connect, send the most recent N mentions as a `mentions_batch`
     so the server has fresh state.
  2. Then drain the incoming queue, sending each new Mention as a single
     `mention` message.

Reconnects with exponential backoff (1s → 60s).
"""

import asyncio
import json
import logging
import queue
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

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


class WsWorker:
    """Dedicated thread that maintains a WebSocket connection and syncs mentions."""

    def __init__(
        self,
        ws_queue: "queue.Queue",
        get_url: Callable[[], str],
    ) -> None:
        self._queue = ws_queue
        self._get_url = get_url  # callable so each reconnect picks up edits
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="ws-worker", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    # ---------- internals ----------

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception:
            log.exception("ws worker crashed")
        finally:
            loop.close()

    async def _main(self) -> None:
        try:
            import websockets  # lazy import; declared in pyproject.toml
        except ImportError:
            log.error("websockets package not installed; ws sync disabled")
            return

        backoff = 1
        while not self._stop.is_set():
            url = self._get_url()
            if not url:
                # Sleep in short chunks so stop() responds quickly.
                await self._sleep_interruptible(2)
                continue
            try:
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=10
                ) as ws:
                    log.info("ws connected: %s", url)
                    backoff = 1
                    await self._send_batch(ws)
                    await self._pump(ws)
            except Exception as e:
                log.warning("ws error (%s); retry in %ds", e, backoff)
                await self._sleep_interruptible(backoff)
                backoff = min(backoff * 2, 60)

    async def _sleep_interruptible(self, total: float) -> None:
        """Sleep up to `total` seconds but wake quickly when stop() is signalled."""
        step = 0.2
        elapsed = 0.0
        while elapsed < total and not self._stop.is_set():
            await asyncio.sleep(min(step, total - elapsed))
            elapsed += step

    async def _send_batch(self, ws) -> None:
        """Send the most recent N mentions on (re)connect for cloud bootstrapping."""
        from .store import Store

        try:
            store = Store()  # this thread's own SQLite connection
            mentions = store.recent(BATCH_LIMIT)
        except Exception:
            log.exception("ws batch: store query failed")
            return
        if not mentions:
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
        log.info("ws batch sent %d mentions", len(mentions))

    async def _pump(self, ws) -> None:
        """Drain the queue, forwarding each Mention as a single WS message."""
        while not self._stop.is_set():
            try:
                mention = self._queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            try:
                msg = json.dumps(
                    {
                        "v": 1,
                        "type": "mention",
                        "payload": _build_payload(mention),
                    },
                    ensure_ascii=False,
                )
                await ws.send(msg)
                log.debug("ws sent mention id=%s", getattr(mention, "id", "?"))
            except Exception:
                # On send failure, requeue this mention so the next reconnect
                # batch (or later pump) can pick it up, then bubble up to
                # trigger reconnect logic.
                try:
                    self._queue.put_nowait(mention)
                except Exception:
                    pass
                raise
