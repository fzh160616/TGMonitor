import logging

import rumps

log = logging.getLogger(__name__)

KIND_LABEL = {
    "dm": "私聊",
    "mention": "@提及",
    "reply": "回复",
    "broadcast": "群播",
    "keyword": "关键词",
}

PREVIEW_LIMIT = 120


def post(
    *,
    chat_title: str,
    sender_name: str,
    text: str,
    kind: str,
    matched_keyword: str | None,
    sound: bool,
    mention_id: int,
) -> None:
    label = KIND_LABEL.get(kind, kind)
    if kind == "keyword" and matched_keyword:
        label = f"关键词: {matched_keyword}"

    if kind == "dm":
        title = sender_name
        subtitle = label
    else:
        title = chat_title
        subtitle = f"{sender_name} · {label}"

    body = (text or "").strip().replace("\n", " ")
    if len(body) > PREVIEW_LIMIT:
        body = body[:PREVIEW_LIMIT] + "…"

    try:
        rumps.notification(
            title=title,
            subtitle=subtitle,
            message=body or "(无文本)",
            sound=sound,
            data={"mention_id": mention_id},
        )
    except Exception:
        log.exception("post notification failed")
