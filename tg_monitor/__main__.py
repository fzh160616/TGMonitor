import logging
from logging.handlers import RotatingFileHandler

from .app import TGMonitorApp
from .paths import LOG_PATH, ensure_dirs


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
    _setup_logging()
    logging.getLogger(__name__).info("starting tg-monitor")
    TGMonitorApp().run()


if __name__ == "__main__":
    main()
