import html as _html
import subprocess
import tempfile
from datetime import datetime
from typing import List

from .store import Mention, Store

_KIND_LABEL = {
    "dm": "私聊",
    "mention": "@提及",
    "reply": "回复",
    "broadcast": "群播",
    "keyword": "关键词",
    "error": "错误",
}

_CSS = """
body{font-family:-apple-system,sans-serif;max-width:860px;margin:2em auto;color:#1d1d1f}
h1{font-size:1.2em;color:#444}
table{border-collapse:collapse;width:100%}
th{background:#f5f5f7;text-align:left;padding:8px 10px;font-weight:600;font-size:.85em}
td{padding:8px 10px;border-bottom:1px solid #e0e0e0;font-size:.9em;vertical-align:top}
tr:hover td{background:#fafafa}
.kind{display:inline-block;padding:1px 6px;border-radius:4px;font-size:.8em;background:#e8f4fd;color:#1a6fa8}
.unseen{background:#fff8e6}
.text{max-width:400px;word-break:break-word;white-space:pre-wrap}
"""


def _render_html(mentions: List[Mention]) -> str:
    if not mentions:
        return "<html><body><p>暂无记录</p></body></html>"

    rows = []
    for m in mentions:
        ts = datetime.fromtimestamp(m.received_at).strftime("%Y-%m-%d %H:%M")
        kind_label = _KIND_LABEL.get(m.kind, m.kind)
        if m.kind == "keyword" and m.matched_keyword:
            kind_label = f"关键词:{m.matched_keyword}"
        unseen_class = "" if m.seen_at else ' class="unseen"'
        text_esc = _html.escape(m.text or "")
        rows.append(
            f"<tr{unseen_class}>"
            f"<td>{ts}</td>"
            f'<td><span class="kind">{_html.escape(kind_label)}</span></td>'
            f"<td>{_html.escape(m.chat_title)}</td>"
            f"<td>{_html.escape(m.sender_name)}</td>"
            f'<td class="text">{text_esc}</td>'
            f"</tr>"
        )

    body = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>TG Monitor 历史</title>
<style>{_CSS}</style></head>
<body>
<h1>TG Monitor 历史记录 ({len(mentions)} 条)</h1>
<table>
<tr><th>时间</th><th>类型</th><th>会话</th><th>发言人</th><th>内容</th></tr>
{body}
</table>
</body></html>"""


def open_history(store: Store, limit: int = 500) -> None:
    mentions = store.recent(limit)
    html = _render_html(mentions)
    fd, tmp_path = tempfile.mkstemp(suffix=".html", prefix="tgmonitor_history_")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(html)
    subprocess.Popen(["open", tmp_path])
