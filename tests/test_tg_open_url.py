from tg_monitor.app import _tg_message_url


def test_tg_message_url():
    url = _tg_message_url(chat_id=-1001234567890, tg_message_id=42)
    assert url == "tg://openmessage?chat_id=-1001234567890&message_id=42"


def test_tg_message_url_positive_chat():
    url = _tg_message_url(chat_id=123, tg_message_id=1)
    assert url == "tg://openmessage?chat_id=123&message_id=1"
