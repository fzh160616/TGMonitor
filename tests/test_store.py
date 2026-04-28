import time

import pytest

from tg_monitor.paths import DB_PATH, ensure_dirs
from tg_monitor.store import Store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect DB_PATH to a temp file so each test runs against a clean DB."""
    db = tmp_path / "test.db"
    monkeypatch.setattr("tg_monitor.store.DB_PATH", db)
    monkeypatch.setattr("tg_monitor.paths.DB_PATH", db)
    # ensure_dirs uses DATA_DIR; redirect it too
    monkeypatch.setattr("tg_monitor.paths.DATA_DIR", tmp_path)
    yield


def _make_store() -> Store:
    return Store()


def _insert(store, *, tg_message_id=1, chat_id=10, **kw):
    defaults = dict(
        chat_title="Test Chat",
        sender_id=50,
        sender_name="Alice",
        text="hello",
        kind="mention",
        matched_keyword=None,
    )
    defaults.update(kw)
    return store.insert(
        tg_message_id=tg_message_id,
        chat_id=chat_id,
        **defaults,
    )


def test_insert_returns_id():
    s = _make_store()
    mid = _insert(s)
    assert mid is not None and mid > 0


def test_dedup_returns_none():
    s = _make_store()
    _insert(s, tg_message_id=1, chat_id=10)
    mid2 = _insert(s, tg_message_id=1, chat_id=10)
    assert mid2 is None


def test_dedup_different_chat_allowed():
    s = _make_store()
    mid1 = _insert(s, tg_message_id=1, chat_id=10)
    mid2 = _insert(s, tg_message_id=1, chat_id=20)
    assert mid1 is not None and mid2 is not None
    assert mid1 != mid2


def test_recent_order(monkeypatch):
    timestamps = iter([100, 200])
    monkeypatch.setattr("tg_monitor.store.time.time", lambda: next(timestamps))
    s = _make_store()
    _insert(s, tg_message_id=1)   # received_at=100
    _insert(s, tg_message_id=2)   # received_at=200
    recent = s.recent(10)
    assert recent[0].tg_message_id == 2  # newest first


def test_get_returns_mention():
    s = _make_store()
    mid = _insert(s, text="ping")
    m = s.get(mid)
    assert m is not None
    assert m.text == "ping"
    assert m.seen_at is None


def test_mark_seen():
    s = _make_store()
    mid = _insert(s)
    s.mark_seen(mid)
    m = s.get(mid)
    assert m.seen_at is not None


def test_mark_seen_idempotent():
    s = _make_store()
    mid = _insert(s)
    s.mark_seen(mid)
    t1 = s.get(mid).seen_at
    time.sleep(0.01)
    s.mark_seen(mid)
    t2 = s.get(mid).seen_at
    assert t1 == t2  # timestamp should not change on second mark


def test_mark_all_seen():
    s = _make_store()
    _insert(s, tg_message_id=1)
    _insert(s, tg_message_id=2)
    assert s.unseen_count() == 2
    s.mark_all_seen()
    assert s.unseen_count() == 0


def test_unseen_count():
    s = _make_store()
    _insert(s, tg_message_id=1)
    _insert(s, tg_message_id=2)
    _insert(s, tg_message_id=3)
    s.mark_seen(_insert(s, tg_message_id=4))  # mark one immediately
    # 3 unseen (1,2,3) + 1 seen (4) → unseen = 3
    assert s.unseen_count() == 3
