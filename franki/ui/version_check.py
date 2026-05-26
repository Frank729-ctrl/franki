"""
version_check.py — non-blocking PyPI version check on startup.

Runs in a daemon thread. If a newer version is found, calls on_update(current, latest)
on the main thread's console. Daemon flag ensures it never delays process exit.
"""
from __future__ import annotations
import threading


_PYPI_URL = "https://pypi.org/pypi/franki-cli/json"
_TIMEOUT  = 5.0


def start_version_check(current_version: str, on_update) -> None:
    """
    Spawn a daemon thread that queries PyPI. If a newer version exists,
    on_update(current_version, latest_version) is called from that thread.
    All exceptions are swallowed — this must never affect startup.
    """
    def _check() -> None:
        try:
            import httpx
            resp = httpx.get(_PYPI_URL, timeout=_TIMEOUT, follow_redirects=True)
            if resp.status_code != 200:
                return
            latest = resp.json()["info"]["version"]
            if _is_newer(latest, current_version):
                on_update(current_version, latest)
        except Exception:
            pass

    t = threading.Thread(target=_check, daemon=True, name="franki-version-check")
    t.start()


def _parse(ver: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in ver.strip().split(".")[:3])
    except ValueError:
        return (0,)


def _is_newer(candidate: str, current: str) -> bool:
    return _parse(candidate) > _parse(current)
