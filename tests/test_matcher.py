from tg_monitor.matcher import EntityMention, MatchInput, match


def _inp(**kw):
    defaults = dict(
        is_private=False,
        text="",
        entities=[],
        is_reply=False,
        reply_sender_id=None,
        me_id=100,
        me_username="mybot",
        keywords=[],
    )
    defaults.update(kw)
    return MatchInput(**defaults)


def test_dm():
    r = match(_inp(is_private=True))
    assert r is not None and r.kind == "dm"


def test_at_mention_by_username():
    r = match(_inp(entities=[EntityMention(username="mybot")]))
    assert r is not None and r.kind == "mention"


def test_at_mention_case_insensitive():
    r = match(_inp(entities=[EntityMention(username="MyBot")]))
    assert r is not None and r.kind == "mention"


def test_inline_mention_by_user_id():
    r = match(_inp(entities=[EntityMention(user_id=100)]))
    assert r is not None and r.kind == "mention"


def test_reply_to_me():
    r = match(_inp(is_reply=True, reply_sender_id=100))
    assert r is not None and r.kind == "reply"


def test_reply_to_other_no_match():
    r = match(_inp(is_reply=True, reply_sender_id=999))
    assert r is None


def test_broadcast_all():
    r = match(_inp(text="hey @all please check"))
    assert r is not None and r.kind == "broadcast"


def test_broadcast_channel():
    r = match(_inp(text="@channel reminder"))
    assert r is not None and r.kind == "broadcast"


def test_keyword_match():
    r = match(_inp(text="deploy prod server", keywords=["prod"]))
    assert r is not None and r.kind == "keyword"
    assert r.matched_keyword == "prod"


def test_keyword_case_insensitive():
    r = match(_inp(text="Deploy PROD server", keywords=["prod"]))
    assert r is not None and r.kind == "keyword"


def test_no_match():
    r = match(_inp(text="just a normal message"))
    assert r is None


def test_dm_takes_priority_over_keyword():
    r = match(_inp(is_private=True, text="urgent alert", keywords=["urgent"]))
    assert r is not None and r.kind == "dm"
