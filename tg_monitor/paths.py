from pathlib import Path

APP_NAME = "TGMonitor"
LAUNCH_AGENT_LABEL = "com.tgmonitor.agent"

HOME = Path.home()
DATA_DIR = HOME / "Library" / "Application Support" / APP_NAME
LOG_DIR = HOME / "Library" / "Logs" / APP_NAME
LAUNCH_AGENTS_DIR = HOME / "Library" / "LaunchAgents"

CONFIG_PATH = DATA_DIR / "config.json"
SESSION_PATH = DATA_DIR / "tg.session"
DB_PATH = DATA_DIR / "data.db"
VENV_DIR = DATA_DIR / ".venv"

LOG_PATH = LOG_DIR / "tg-monitor.log"
LAUNCH_AGENT_PLIST = LAUNCH_AGENTS_DIR / f"{LAUNCH_AGENT_LABEL}.plist"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
