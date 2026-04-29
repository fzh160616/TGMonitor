import fcntl
import logging
import sys
from logging.handlers import RotatingFileHandler

from .app import TGMonitorApp
from .paths import DATA_DIR, LOG_PATH, ensure_dirs

# File-descriptor kept open for the entire process lifetime; the OS releases
# the exclusive lock automatically when the process exits (even on crash).
_lock_fd = None


def _acquire_lock() -> bool:
    """Return True if this process is the only running instance, False otherwise."""
    global _lock_fd
    ensure_dirs()
    lock_path = DATA_DIR / "tg-monitor.lock"
    fd = open(lock_path, "w")  # noqa: SIM115
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fd.close()
        return False
    _lock_fd = fd  # keep alive until process exits
    return True


def _setup_logging() -> None:
    ensure_dirs()
    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def main() -> None:
    if not _acquire_lock():
        print("tg-monitor is already running. Exiting.", flush=True)
        sys.exit(0)
    _setup_logging()
    logging.getLogger(__name__).info("starting tg-monitor")
    TGMonitorApp().run()


if __name__ == "__main__":
    main()
