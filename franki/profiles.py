"""Named config profiles — save / load / list / delete FrankiConfig snapshots."""
from __future__ import annotations
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from franki.config import FrankiConfig

PROFILES_DIR = Path.home() / ".config" / "franki" / "profiles"

_NAME_RE = __import__("re").compile(r'^[a-zA-Z0-9_\-]{1,32}$')


def _valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name))


def save_profile(name: str, cfg: "FrankiConfig") -> Path:
    """Persist the current config as a named profile."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    p = PROFILES_DIR / f"{name}.json"
    p.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_profile(name: str) -> "FrankiConfig | None":
    """Load a named profile. Returns None if not found or corrupt."""
    from franki.config import FrankiConfig
    p = PROFILES_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return FrankiConfig(**raw)
    except Exception:
        return None


def list_profiles() -> list[str]:
    """Return sorted names of all saved profiles."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def delete_profile(name: str) -> bool:
    """Delete a named profile. Returns True if it existed and was deleted."""
    p = PROFILES_DIR / f"{name}.json"
    if p.exists():
        try:
            p.unlink()
            return True
        except OSError:
            pass
    return False
