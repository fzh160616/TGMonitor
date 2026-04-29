import json
from dataclasses import asdict, dataclass, field
from typing import List

from .paths import CONFIG_PATH, ensure_dirs


@dataclass
class Config:
    api_id: int = 0
    api_hash: str = ""
    keywords: List[str] = field(default_factory=list)
    excluded_senders: List[str] = field(default_factory=list)
    backfill_minutes: int = 5
    notification_sound: bool = True
    launch_at_login: bool = True
    ws_port: int = 0           # 0 = local WS server disabled
    ws_host: str = "0.0.0.0"   # 0.0.0.0 = LAN reachable; 127.0.0.1 = local only


def load() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return Config(
        api_id=int(raw.get("api_id", 0)),
        api_hash=str(raw.get("api_hash", "")),
        keywords=list(raw.get("keywords", [])),
        excluded_senders=list(raw.get("excluded_senders", [])),
        backfill_minutes=int(raw.get("backfill_minutes", 5)),
        notification_sound=bool(raw.get("notification_sound", True)),
        launch_at_login=bool(raw.get("launch_at_login", True)),
        ws_port=int(raw.get("ws_port", 0)),
        ws_host=str(raw.get("ws_host", "0.0.0.0")),
    )


def save(cfg: Config) -> None:
    ensure_dirs()
    CONFIG_PATH.write_text(
        json.dumps(asdict(cfg), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
