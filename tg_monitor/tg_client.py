import asyncio
import logging
import queue
import threading
from dataclasses import dataclass
from typing import Optional

from telethon import TelegramClient, events
from telethon.tl.types import (
    Channel,
    Chat,
    MessageEntityMention,
    MessageEntityMentionName,
    PeerUser,
    User,
)

from . import config as cfg
from .matcher import EntityMention, MatchInput, MatchResult, match
from .paths import SESSION_PATH

log = logging.getLogger(__name__)


@dataclass
class Hit:
    """Payload pushed to the main thread when a message matches."""
    tg_message_id: int
    chat_id: int
    chat_title: str
    sender_id: int
    sender_name: str
    text: str
    result: MatchResult
    chat_username: str = ""    # channel/group @handle
    sender_username: str = ""  # sender @handle


class TgWorker:
    def __init__(self, hits: "queue.Queue[Hit]", status: "queue.Queue[str]") -> None:
        self.hits = hits
        self.status = status
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional[TelegramClient] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._shutdown: threading.Event = threading.Event()
        self.me_id: int = 0
        self.me_username: Optional[str] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="tg-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._shutdown.set()
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        import time as _time
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        attempt = 0
        try:
            while not self._shutdown.is_set():
                # Create fresh stop event BEFORE entering _main so stop() always
                # signals the correct event even if it races with _main().
                self._stop_event = asyncio.Event()
                t_start = _time.monotonic()
                try:
                    loop.run_until_complete(self._main())
                except Exception:
                    log.exception("tg worker crashed (attempt %d)", attempt)
                if self._shutdown.is_set():
                    break
                # Reset backoff after a healthy connection (≥60s); else increment.
                if _time.monotonic() - t_start >= 60:
                    attempt = 0
                else:
                    attempt += 1
                delay = _reconnect_delay(attempt)
                log.info("reconnecting in %ds…", delay)
                self.status.put("disconnected")
                # Interruptible sleep — returns immediately if _shutdown is set.
                self._shutdown.wait(timeout=delay)
        finally:
            self.status.put("disconnected")
            loop.close()

    async def _main(self) -> None:
        c = cfg.load()
        if not c.api_id or not c.api_hash:
            log.error("missing api_id / api_hash in config; worker exiting")
            return

        client = TelegramClient(str(SESSION_PATH), c.api_id, c.api_hash)
        self._client = client

        await client.connect()
        if not await client.is_user_authorized():
            log.error("session not authorized; run login flow first")
            return

        me = await client.get_me()
        self.me_id = me.id
        self.me_username = getattr(me, "username", None)
        log.info("logged in as id=%s username=%s", self.me_id, self.me_username)

        @client.on(events.NewMessage())
        async def _on_msg(event: events.NewMessage.Event) -> None:
            if event.message.out:
                return
            try:
                await self._handle(event)
            except Exception:
                log.exception("handler failed for message")

        self.status.put("connected")
        log.info("listening for new messages…")

        c = cfg.load()
        if c.backfill_minutes > 0:
            asyncio.create_task(self._backfill(client, c.backfill_minutes))

        run_task = asyncio.create_task(client.run_until_disconnected())
        stop_task = asyncio.create_task(self._stop_event.wait())
        done, pending = await asyncio.wait(
            {run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
        if client.is_connected():
            await client.disconnect()

    async def _handle(self, event: events.NewMessage.Event) -> None:
        c = cfg.load()
        raw_sender_id = event.sender_id or 0

        # Early exclusion by numeric ID (no network call needed)
        if _is_excluded(raw_sender_id, None, c.excluded_senders):
            return

        text = event.message.message or ""
        entities = _extract_entities(event)
        reply_sender_id: Optional[int] = None
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                if reply is not None:
                    reply_sender_id = reply.sender_id
            except Exception:
                log.exception("get_reply_message failed")

        result = match(MatchInput(
            is_private=bool(event.is_private),
            text=text,
            entities=entities,
            is_reply=bool(event.is_reply),
            reply_sender_id=reply_sender_id,
            me_id=self.me_id,
            me_username=self.me_username,
            keywords=c.keywords,
        ))
        if result is None:
            return

        chat = await event.get_chat()
        sender = await event.get_sender()

        # Second exclusion pass now that we have the sender's username
        sender_username = getattr(sender, "username", None)
        if _is_excluded(raw_sender_id, sender_username, c.excluded_senders):
            return

        chat_username = getattr(chat, "username", None) or ""
        sender_handle = sender_username or ""

        hit = Hit(
            tg_message_id=event.message.id,
            chat_id=event.chat_id,
            chat_title=_chat_title(chat),
            sender_id=getattr(sender, "id", 0) or 0,
            sender_name=_display_name(sender),
            text=text,
            result=result,
            chat_username=chat_username,
            sender_username=sender_handle,
        )
        self.hits.put(hit)


    async def _backfill(self, client: TelegramClient, minutes: int) -> None:
        import time as _time
        c = cfg.load()  # load once for the entire backfill run
        cutoff = _time.time() - minutes * 60
        limit = _backfill_limit(minutes)
        log.info("backfill: scanning last %d min (limit=%d/dialog)…", minutes, limit)
        async for dialog in client.iter_dialogs():
            if self._shutdown.is_set():
                break
            try:
                async for msg in client.iter_messages(dialog.id, limit=limit):
                    if msg.date.timestamp() < cutoff:
                        break  # iter_messages is newest-first; stop when too old
                    await self._process_raw(client, msg, dialog, c)
            except Exception:
                log.exception("backfill: error in dialog %s", dialog.id)
        log.info("backfill: done")

    async def _process_raw(self, client: TelegramClient, msg, dialog, c: "cfg.Config") -> None:
        """Process a raw Message from backfill (shares match logic with _handle)."""
        if msg.out:
            return
        raw_sender_id = msg.sender_id or 0

        if _is_excluded(raw_sender_id, None, c.excluded_senders):
            return

        text = msg.message or ""
        entities: list[EntityMention] = []
        if msg.entities:
            for ent in msg.entities:
                if isinstance(ent, MessageEntityMentionName):
                    entities.append(EntityMention(user_id=ent.user_id))
                elif isinstance(ent, MessageEntityMention):
                    handle = text[ent.offset: ent.offset + ent.length].lstrip("@")
                    entities.append(EntityMention(username=handle))

        is_private = isinstance(getattr(msg, "peer_id", None), PeerUser)

        is_reply = _raw_is_reply(msg)
        reply_sender_id: Optional[int] = None
        if is_reply:
            reply_msg_id = _raw_reply_msg_id(msg)
            if reply_msg_id is not None:
                try:
                    replied = await client.get_messages(dialog.id, ids=reply_msg_id)
                    # Use getattr: replied may be MessageEmpty (truthy, no sender_id)
                    reply_sender_id = getattr(replied, "sender_id", None)
                except Exception:
                    log.debug("backfill: get reply msg failed msg_id=%s", reply_msg_id)

        result = match(MatchInput(
            is_private=is_private,
            text=text,
            entities=entities,
            is_reply=is_reply,
            reply_sender_id=reply_sender_id,
            me_id=self.me_id,
            me_username=self.me_username,
            keywords=c.keywords,
        ))
        if result is None:
            return

        chat = dialog.entity
        sender = None
        if raw_sender_id:
            try:
                sender = await client.get_entity(raw_sender_id)
            except Exception:
                log.debug("backfill: get_entity failed sender_id=%s", raw_sender_id)

        sender_username = getattr(sender, "username", None)
        if _is_excluded(raw_sender_id, sender_username, c.excluded_senders):
            return

        chat_username = getattr(chat, "username", None) or ""
        sender_handle = sender_username or ""

        self.hits.put(Hit(
            tg_message_id=msg.id,
            chat_id=dialog.id,
            chat_title=_chat_title(chat),
            sender_id=raw_sender_id,
            sender_name=_display_name(sender),
            text=text,
            result=result,
            chat_username=chat_username,
            sender_username=sender_handle,
        ))


def _is_excluded(sender_id: int, username: Optional[str], excluded: list[str]) -> bool:
    for entry in excluded:
        clean = entry.lstrip("@").strip()
        if clean.isdigit():
            if sender_id == int(clean):
                return True
        elif username and username.lower() == clean.lower():
            return True
    return False


def _extract_entities(event: events.NewMessage.Event) -> list[EntityMention]:
    out: list[EntityMention] = []
    msg = event.message
    if not msg.entities:
        return out
    raw_text = msg.message or ""
    for ent in msg.entities:
        if isinstance(ent, MessageEntityMentionName):
            out.append(EntityMention(user_id=ent.user_id))
        elif isinstance(ent, MessageEntityMention):
            handle = raw_text[ent.offset : ent.offset + ent.length].lstrip("@")
            out.append(EntityMention(username=handle))
    return out


def _chat_title(chat: object) -> str:
    if isinstance(chat, (Chat, Channel)):
        return getattr(chat, "title", None) or "(无标题)"
    if isinstance(chat, User):
        return _display_name(chat)
    return "(未知会话)"


def _display_name(obj: object) -> str:
    if obj is None:
        return "(未知)"
    first = getattr(obj, "first_name", "") or ""
    last = getattr(obj, "last_name", "") or ""
    full = (first + " " + last).strip()
    if full:
        return full
    username = getattr(obj, "username", None)
    if username:
        return f"@{username}"
    title = getattr(obj, "title", None)
    if title:
        return title
    return "(未知)"


def _reconnect_delay(attempt: int) -> int:
    return min(5 * (2 ** attempt), 120)


def _backfill_limit(backfill_minutes: int) -> int:
    return max(100, backfill_minutes * 20)


def _raw_is_reply(msg: object) -> bool:
    return getattr(msg, "reply_to", None) is not None


def _raw_reply_msg_id(msg: object) -> Optional[int]:
    rt = getattr(msg, "reply_to", None)
    if rt is None:
        return None
    return getattr(rt, "reply_to_msg_id", None)
