try:
    from importlib.metadata import version
    __version__ = version("franki")
except Exception:
    __version__ = "0.2.0"
