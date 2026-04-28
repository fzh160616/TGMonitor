import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

BROADCAST_RE = re.compile(r"@(all|channel|everyone|here)\b", re.IGNORECASE)


@dataclass
class EntityMention:
    """Subset of Telethon's mention entities that matter to us.

    For @username mentions, ``username`` is set; for inline name mentions
    (created by tapping a user without @-handle), ``user_id`` is set.
    """
    username: Optional[str] = None
    user_id: Optional[int] = None


@dataclass
class MatchInput:
    is_private: bool
    text: str
    entities: Sequence[EntityMention]
    is_reply: bool
    reply_sender_id: Optional[int]
    me_id: int
    me_username: Optional[str]
    keywords: Sequence[str]


@dataclass
class MatchResult:
    kind: str  # dm | mention | reply | broadcast | keyword
    matched_keyword: Optional[str] = None


def match(inp: MatchInput) -> Optional[MatchResult]:
    if inp.is_private:
        return MatchResult(kind="dm")

    if _is_at_mention(inp.entities, inp.me_id, inp.me_username):
        return MatchResult(kind="mention")

    if inp.is_reply and inp.reply_sender_id == inp.me_id:
        return MatchResult(kind="reply")

    if BROADCAST_RE.search(inp.text or ""):
        return MatchResult(kind="broadcast")

    hit = _keyword_hit(inp.text or "", inp.keywords)
    if hit is not None:
        return MatchResult(kind="keyword", matched_keyword=hit)

    return None


def _is_at_mention(
    entities: Iterable[EntityMention],
    me_id: int,
    me_username: Optional[str],
) -> bool:
    me_handle = (me_username or "").lower()
    for e in entities:
        if e.user_id is not None and e.user_id == me_id:
            return True
        if e.username and me_handle and e.username.lower() == me_handle:
            return True
    return False


def _keyword_hit(text: str, keywords: Sequence[str]) -> Optional[str]:
    lo = text.lower()
    for kw in keywords:
        if kw and kw.lower() in lo:
            return kw
    return None
