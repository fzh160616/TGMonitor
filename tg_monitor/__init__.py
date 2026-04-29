try:
    from importlib.metadata import version as _version
    __version__ = _version("tg-monitor")
except Exception:
    __version__ = "0.1.0"
