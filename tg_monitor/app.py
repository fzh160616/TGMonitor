import logging
import pathlib
import queue
import subprocess
import tempfile
import time
from datetime import datetime
from typing import Dict

import rumps

from . import config as cfg
from . import notifier
from .paths import (
    DATA_DIR,
    LAUNCH_AGENT_LABEL,
    LAUNCH_AGENT_PLIST,
    LOG_PATH,
)
from .store import Mention, Store
from .tg_client import Hit, TgWorker

log = logging.getLogger(__name__)

RECENT_LIMIT = 20
POLL_INTERVAL = 0.2

_RESOURCES = pathlib.Path(__file__).parent.parent / "resources"
_ICON_DEFAULT = str(_RESOURCES / "TGMonitor.png")
_BADGE_CACHE  = str(pathlib.Path(tempfile.gettempdir()) / "tgmonitor_badge.png")


def _icon_path() -> str | None:
    p = pathlib.Path(_ICON_DEFAULT)
    return str(p) if p.exists() else None


def _render_badge_icon(count: int) -> str:
    """Draw red circular badge with white count over the base icon. Returns temp PNG path."""
    from AppKit import (  # pyobjc-framework-Cocoa
        NSBitmapImageRep,
        NSBezierPath,
        NSColor,
        NSFont,
        NSFontAttributeName,
        NSForegroundColorAttributeName,
        NSImage,
        NSMakeRect,
        NSPNGFileType,
    )
    from Foundation import NSString

    base = NSImage.alloc().initWithContentsOfFile_(_ICON_DEFAULT)
    sz = base.size()

    img = NSImage.alloc().initWithSize_(sz)
    img.lockFocus()

    base.drawAtPoint_fromRect_operation_fraction_(
        (0.0, 0.0), ((0.0, 0.0), sz), 14, 1.0  # NSCompositingOperationSourceOver = 14
    )

    r = sz.height * 0.36        # ≈ 7.9 px for a 22 px icon
    cx = sz.width - r - 0.5
    cy = r + 0.5

    circle = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r, r * 2, r * 2))
    NSColor.redColor().setFill()
    circle.fill()
    NSColor.whiteColor().setStroke()
    circle.setLineWidth_(1.0)
    circle.stroke()

    label = str(count) if count < 100 else "99+"
    font_sz = r * 1.15 if len(label) == 1 else r * 0.85
    attrs = {
        NSFontAttributeName: NSFont.boldSystemFontOfSize_(font_sz),
        NSForegroundColorAttributeName: NSColor.whiteColor(),
    }
    ns_label = NSString.stringWithString_(label)
    text_sz = ns_label.sizeWithAttributes_(attrs)
    ns_label.drawAtPoint_withAttributes_(
        (cx - text_sz.width / 2, cy - text_sz.height / 2), attrs
    )

    img.unlockFocus()

    tiff = img.TIFFRepresentation()
    rep = NSBitmapImageRep.imageRepWithData_(tiff)
    png = rep.representationUsingType_properties_(NSPNGFileType, None)
    png.writeToFile_atomically_(_BADGE_CACHE, True)

    return _BADGE_CACHE


class TGMonitorApp(rumps.App):
    def __init__(self) -> None:
        icon = _icon_path()
        # If icon file exists use it (no title text); fall back to emoji
        super().__init__("" if icon else "🔔", icon=icon, quit_button=None)
        self.config = cfg.load()
        self.store = Store()
        self.hits: "queue.Queue[Hit]" = queue.Queue()
        self.worker = TgWorker(self.hits)

        # MenuItems for individual mentions, keyed by mention id, so we can
        # rebuild without losing references.
        self._mention_items: Dict[int, rumps.MenuItem] = {}

        self._build_menu()
        self._refresh_mentions()
        self._update_title()

        self.worker.start()

        rumps.Timer(self._drain_hits, POLL_INTERVAL).start()

    # ------- menu construction -------

    def _build_menu(self) -> None:
        self._mentions_section = rumps.MenuItem("最近提醒")
        mark_all_item = rumps.MenuItem("全部已读", callback=self._mark_all_read)
        self._mentions_section.add(mark_all_item)
        self._mentions_section.add(rumps.separator)

        settings = rumps.MenuItem("设置")
        settings.add(rumps.MenuItem("编辑关键词…", callback=self._edit_keywords))
        settings.add(rumps.MenuItem("排除账号…", callback=self._edit_excluded))
        self._launch_item = rumps.MenuItem(
            "开机自启", callback=self._toggle_launch_at_login
        )
        self._launch_item.state = self.config.launch_at_login
        settings.add(self._launch_item)
        self._sound_item = rumps.MenuItem(
            "通知声音", callback=self._toggle_sound
        )
        self._sound_item.state = self.config.notification_sound
        settings.add(self._sound_item)
        settings.add(rumps.MenuItem("打开数据目录", callback=self._open_data_dir))
        settings.add(rumps.MenuItem("查看日志", callback=self._open_log))

        self.menu = [
            self._mentions_section,
            None,  # separator
            settings,
            rumps.MenuItem("关于 TG Monitor", callback=self._about),
            None,
            rumps.MenuItem("退出", callback=self._quit),
        ]

    def _refresh_mentions(self) -> None:
        # Wipe old items (keep the "全部已读" header)
        for key in list(self._mention_items.keys()):
            try:
                del self.menu["最近提醒"][str(key)]
            except KeyError:
                pass
        self._mention_items.clear()

        recent = self.store.recent(RECENT_LIMIT)
        if not recent:
            placeholder = rumps.MenuItem("(暂无)")
            placeholder.set_callback(None)
            self.menu["最近提醒"]["empty"] = placeholder
            self._mention_items[-1] = placeholder
            return
        # Remove placeholder if present
        try:
            del self.menu["最近提醒"]["empty"]
        except KeyError:
            pass

        for m in recent:
            item = rumps.MenuItem(
                _label(m),
                callback=self._make_toggle_callback(m.id),
            )
            # ✓ checkmark = unread (needs action); no mark = already seen
            item.state = 1 if m.seen_at is None else 0
            self.menu["最近提醒"][str(m.id)] = item
            self._mention_items[m.id] = item

    def _update_title(self) -> None:
        n = self.store.unseen_count()
        self.title = ""
        if n == 0:
            self.icon = _icon_path()
            self.template = True
        else:
            try:
                self.icon = _render_badge_icon(n)
                self.template = False
            except Exception:
                log.exception("badge render failed; falling back to text")
                self.title = f" {n}" if _icon_path() else f"🔔 {n}"
                self.icon = _icon_path()
                self.template = True

    # ------- queue draining (main thread) -------

    def _drain_hits(self, _sender) -> None:
        drained = False
        while True:
            try:
                hit = self.hits.get_nowait()
            except queue.Empty:
                break
            try:
                self._absorb(hit)
            except Exception:
                log.exception("_absorb failed for hit chat_id=%s msg_id=%s", hit.chat_id, hit.tg_message_id)
                try:
                    self.store.insert(
                        tg_message_id=hit.tg_message_id, chat_id=hit.chat_id,
                        chat_title=hit.chat_title, sender_id=hit.sender_id,
                        sender_name=hit.sender_name, text=hit.text,
                        kind="error", matched_keyword=None,
                    )
                except Exception:
                    log.exception("fallback insert also failed")
            drained = True
        if drained:
            self._refresh_mentions()
            self._update_title()

    def _absorb(self, hit: Hit) -> None:
        mid = self.store.insert(
            tg_message_id=hit.tg_message_id,
            chat_id=hit.chat_id,
            chat_title=hit.chat_title,
            sender_id=hit.sender_id,
            sender_name=hit.sender_name,
            text=hit.text,
            kind=hit.result.kind,
            matched_keyword=hit.result.matched_keyword,
        )
        if mid is None:
            return  # dedup hit
        notifier.post(
            chat_title=hit.chat_title,
            sender_name=hit.sender_name,
            text=hit.text,
            kind=hit.result.kind,
            matched_keyword=hit.result.matched_keyword,
            sound=self.config.notification_sound,
            mention_id=mid,
        )

    # ------- menu callbacks -------

    def _make_toggle_callback(self, mention_id: int):
        """Click once to mark seen (removes ✓); click again to show full text."""
        def _cb(sender) -> None:
            m = self.store.get(mention_id)
            if m is None:
                return
            if m.seen_at is None:
                # First click: mark as read, remove checkmark
                self.store.mark_seen(mention_id)
                sender.state = 0
                self._update_title()
            else:
                # Already read: show full detail
                ts = datetime.fromtimestamp(m.received_at).strftime("%Y-%m-%d %H:%M:%S")
                label = notifier.KIND_LABEL.get(m.kind, m.kind)
                if m.kind == "keyword" and m.matched_keyword:
                    label = f"关键词: {m.matched_keyword}"
                body = (
                    f"{label}\n"
                    f"群组: {m.chat_title}\n"
                    f"发言人: {m.sender_name}\n"
                    f"时间: {ts}\n\n"
                    f"{m.text or '(无文本)'}"
                )
                rumps.alert(title=m.chat_title, message=body, ok="关闭")
        return _cb

    def _mark_all_read(self, _sender) -> None:
        self.store.mark_all_seen()
        self._refresh_mentions()
        self._update_title()

    def _edit_keywords(self, _sender) -> None:
        w = rumps.Window(
            message="每行一个关键词（大小写不敏感）：",
            title="编辑关键词",
            default_text="\n".join(self.config.keywords),
            ok="保存", cancel="取消",
            dimensions=(300, 200),
        )
        resp = w.run()
        if resp.clicked:
            self.config.keywords = [k.strip() for k in resp.text.splitlines() if k.strip()]
            cfg.save(self.config)

    def _edit_excluded(self, _sender) -> None:
        w = rumps.Window(
            message="每行填一个账号（@username 或纯数字 user_id）：",
            title="排除发言人",
            default_text="\n".join(self.config.excluded_senders),
            ok="保存", cancel="取消",
            dimensions=(300, 180),
        )
        resp = w.run()
        if resp.clicked:
            entries = [e.strip() for e in resp.text.splitlines() if e.strip()]
            self.config.excluded_senders = entries
            cfg.save(self.config)

    def _toggle_launch_at_login(self, sender) -> None:
        sender.state = not sender.state
        self.config.launch_at_login = bool(sender.state)
        cfg.save(self.config)
        if sender.state:
            _launchctl_load()
        else:
            _launchctl_unload()

    def _toggle_sound(self, sender) -> None:
        sender.state = not sender.state
        self.config.notification_sound = bool(sender.state)
        cfg.save(self.config)

    def _open_data_dir(self, _sender) -> None:
        subprocess.Popen(["open", str(DATA_DIR)])

    def _open_log(self, _sender) -> None:
        if not LOG_PATH.exists():
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            LOG_PATH.touch()
        subprocess.Popen(["open", str(LOG_PATH)])

    def _about(self, _sender) -> None:
        from . import __version__
        rumps.alert(
            title="TG Monitor",
            message=(
                f"版本 {__version__}\n"
                "macOS 菜单栏 Telegram @ 提醒。\n"
                "数据仅存本地。"
            ),
            ok="关闭",
        )

    def _quit(self, _sender) -> None:
        try:
            self.worker.stop()
        finally:
            rumps.quit_application()


_KIND_BADGE = {"dm": "💬", "mention": "@", "reply": "↩", "broadcast": "📢", "keyword": "🔑", "error": "⚠️"}


def _label(m: Mention) -> str:
    badge = _KIND_BADGE.get(m.kind, "?")
    ts = datetime.fromtimestamp(m.received_at).strftime("%H:%M")
    snippet = (m.text or "").replace("\n", " ").strip()
    if len(snippet) > 28:
        snippet = snippet[:28] + "…"
    return f"{badge} {ts}  {m.chat_title} · {m.sender_name}  {snippet}"


def _launchctl_load() -> None:
    if not LAUNCH_AGENT_PLIST.exists():
        log.warning("LaunchAgent plist missing: %s", LAUNCH_AGENT_PLIST)
        return
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{_uid()}", str(LAUNCH_AGENT_PLIST)],
        check=False,
    )


def _launchctl_unload() -> None:
    if not LAUNCH_AGENT_PLIST.exists():
        return
    subprocess.run(
        ["launchctl", "bootout", f"gui/{_uid()}/{LAUNCH_AGENT_LABEL}"],
        check=False,
    )


def _uid() -> int:
    import os
    return os.getuid()
