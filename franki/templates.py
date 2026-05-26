"""Named prompt templates — save and reuse common prompts."""
from __future__ import annotations
import json
import re
from pathlib import Path

TEMPLATES_FILE = Path.home() / ".config" / "franki" / "templates.json"


def _load() -> dict[str, str]:
    if not TEMPLATES_FILE.exists():
        return {}
    try:
        return json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, str]) -> None:
    TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _valid_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", name))


def save_template(name: str, prompt: str) -> None:
    data = _load()
    data[name] = prompt
    _save(data)


def get_template(name: str) -> str | None:
    return _load().get(name)


def delete_template(name: str) -> bool:
    data = _load()
    if name not in data:
        return False
    del data[name]
    _save(data)
    return True


def list_templates() -> dict[str, str]:
    return _load()


def valid_name(name: str) -> bool:
    return _valid_name(name)
