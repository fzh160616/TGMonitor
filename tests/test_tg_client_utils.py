from tg_monitor.tg_client import (
    _backfill_limit,
    _display_name,
    _is_excluded,
    _raw_is_reply,
    _raw_reply_msg_id,
    _reconnect_delay,
)


def test_reconnect_delay_starts_at_5():
    assert _reconnect_delay(0) == 5


def test_reconnect_delay_doubles():
    assert _reconnect_delay(1) == 10
    assert _reconnect_delay(2) == 20


def test_reconnect_delay_caps_at_120():
    assert _reconnect_delay(10) == 120


def test_backfill_limit_default():
    assert _backfill_limit(5) == 100  # max(100, 5*20)=100


def test_backfill_limit_scales():
    assert _backfill_limit(10) == 200  # max(100, 10*20)=200


def test_backfill_limit_minimum():
    assert _backfill_limit(1) == 100  # max(100, 20)=100


class _FakeReplyTo:
    def __init__(self, msg_id):
        self.reply_to_msg_id = msg_id


class _FakeMsg:
    def __init__(self, reply_to=None):
        self.reply_to = reply_to


def test_raw_is_reply_no_reply():
    assert _raw_is_reply(_FakeMsg(reply_to=None)) is False


def test_raw_is_reply_with_reply():
    assert _raw_is_reply(_FakeMsg(reply_to=_FakeReplyTo(42))) is True


def test_raw_reply_msg_id():
    assert _raw_reply_msg_id(_FakeMsg(reply_to=_FakeReplyTo(99))) == 99


def test_raw_reply_msg_id_no_reply():
    assert _raw_reply_msg_id(_FakeMsg(reply_to=None)) is None


# --- _is_excluded ---

def test_is_excluded_by_numeric_id():
    assert _is_excluded(123, None, ["123"]) is True


def test_is_excluded_by_username():
    assert _is_excluded(0, "alice", ["@alice"]) is True


def test_is_excluded_username_case_insensitive():
    assert _is_excluded(0, "Alice", ["@alice"]) is True


def test_not_excluded_when_empty_list():
    assert _is_excluded(123, "alice", []) is False


def test_not_excluded_different_id():
    assert _is_excluded(999, None, ["123"]) is False


# --- _display_name ---

class _FakeUser:
    def __init__(self, first="", last="", username=None):
        self.first_name = first
        self.last_name = last
        self.username = username


def test_display_name_full_name():
    assert _display_name(_FakeUser(first="John", last="Doe")) == "John Doe"


def test_display_name_username_fallback():
    assert _display_name(_FakeUser(username="jdoe")) == "@jdoe"


def test_display_name_none():
    assert _display_name(None) == "(未知)"
