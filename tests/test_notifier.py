from unittest.mock import patch
from tg_monitor import notifier


def _call_kwargs(mock_notif):
    return mock_notif.call_args.kwargs


def test_post_calls_rumps_notification():
    with patch("tg_monitor.notifier.rumps.notification") as mock_notif:
        notifier.post(
            chat_title="Test Chat",
            sender_name="Alice",
            text="hello world",
            kind="mention",
            matched_keyword=None,
            sound=True,
            mention_id=1,
        )
    mock_notif.assert_called_once()
    kw = _call_kwargs(mock_notif)
    assert kw["title"] == "Test Chat"
    assert "Alice" in kw["subtitle"]
    assert kw["sound"] is True


def test_post_dm_uses_sender_as_title():
    with patch("tg_monitor.notifier.rumps.notification") as mock_notif:
        notifier.post(
            chat_title="irrelevant",
            sender_name="Bob",
            text="hey",
            kind="dm",
            matched_keyword=None,
            sound=False,
            mention_id=2,
        )
    assert _call_kwargs(mock_notif)["title"] == "Bob"


def test_post_keyword_label():
    with patch("tg_monitor.notifier.rumps.notification") as mock_notif:
        notifier.post(
            chat_title="Group",
            sender_name="Eve",
            text="deploy prod",
            kind="keyword",
            matched_keyword="prod",
            sound=True,
            mention_id=3,
        )
    assert "prod" in _call_kwargs(mock_notif)["subtitle"]


def test_post_truncates_long_text():
    long_text = "x" * 200
    with patch("tg_monitor.notifier.rumps.notification") as mock_notif:
        notifier.post(
            chat_title="G",
            sender_name="X",
            text=long_text,
            kind="mention",
            matched_keyword=None,
            sound=False,
            mention_id=4,
        )
    assert len(_call_kwargs(mock_notif)["message"]) <= notifier.PREVIEW_LIMIT + 1


def test_post_handles_rumps_exception():
    with patch("tg_monitor.notifier.rumps.notification", side_effect=Exception("oops")):
        notifier.post(
            chat_title="G", sender_name="X", text="hi",
            kind="mention", matched_keyword=None, sound=False, mention_id=5,
        )
    # should not raise
