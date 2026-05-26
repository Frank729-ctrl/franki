try:
    from importlib.metadata import version
    __version__ = version("franki-cli")
except Exception:
    __version__ = "0.1.7"
