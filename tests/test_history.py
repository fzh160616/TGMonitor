from tg_monitor.history import _render_html
from tg_monitor.store import Mention


def _mention(id=1, kind="mention", chat_title="Test", sender_name="Alice",
             text="hello", received_at=1700000000, seen_at=None, **kw):
    return Mention(
        id=id, tg_message_id=id, chat_id=10,
        chat_title=chat_title, chat_username=kw.get("chat_username"),
        sender_id=50, sender_name=sender_name,
        sender_username=kw.get("sender_username"),
        text=text, kind=kind, matched_keyword=kw.get("matched_keyword"),
        received_at=received_at, seen_at=seen_at,
    )


def test_render_html_contains_sender():
    html = _render_html([_mention(sender_name="Bob")])
    assert "Bob" in html


def test_render_html_contains_text():
    html = _render_html([_mention(text="urgent deploy")])
    assert "urgent deploy" in html


def test_render_html_escapes_html():
    html = _render_html([_mention(text="<script>alert(1)</script>")])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_empty():
    html = _render_html([])
    assert "暂无记录" in html
