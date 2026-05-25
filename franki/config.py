import json
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, field_validator


CONFIG_DIR = Path.home() / ".config" / "franki"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "mode": "direct",
    "active_skill": "coding",
    "active_model": "groq/llama-3.3-70b-versatile",
    "stream": True,
    "providers": {
        "groq": {
            "api_key": "",
            "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b"],
            "priority": 1,
        },
        "gemini": {
            "api_key": "",
            "models": ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
            "priority": 2,
        },
        "openrouter": {
            "api_key": "",
            "models": ["deepseek/deepseek-coder:free", "meta-llama/llama-3.3-70b:free"],
            "priority": 3,
        },
        "delkaai": {
            "enabled": False,
            "url": "https://api.delkaai.com",
            "api_key": "",
            "priority": 0,
        },
    },
    "fallback": {
        "enabled": True,
        "on_errors": ["429", "rate_limit", "quota_exceeded", "overloaded", "503"],
    },
    "export_path": "~/Documents/Obsidian Vault/Home Obsi/franki-sessions/",
    "theme": "dark",
}


class ProviderConfig(BaseModel):
    api_key: str = ""
    models: list[str] = []
    priority: int = 99
    enabled: bool = True
    url: str = ""

    @field_validator("api_key")
    @classmethod
    def api_key_from_env(cls, v: str) -> str:
        return v


class DelkaAIConfig(BaseModel):
    enabled: bool = False
    url: str = "https://api.delkaai.com"
    api_key: str = ""
    priority: int = 0


class FallbackConfig(BaseModel):
    enabled: bool = True
    on_errors: list[str] = ["429", "rate_limit", "quota_exceeded", "overloaded", "503"]


class FrankiConfig(BaseModel):
    mode: str = "direct"
    active_skill: str = "coding"
    active_model: str = "groq/llama-3.3-70b-versatile"
    stream: bool = True
    providers: dict = {}
    fallback: FallbackConfig = FallbackConfig()
    export_path: str = "~/Documents/Obsidian Vault/Home Obsi/franki-sessions/"
    theme: str = "dark"

    def get_provider_key(self, provider: str) -> str:
        env_map = {
            "groq": "GROQ_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "delkaai": "DELKAAI_API_KEY",
        }
        env_var = env_map.get(provider)
        if env_var:
            env_val = os.environ.get(env_var, "")
            if env_val:
                return env_val
        prov = self.providers.get(provider, {})
        return prov.get("api_key", "") if isinstance(prov, dict) else ""

    def get_active_provider(self) -> str:
        return self.active_model.split("/")[0] if "/" in self.active_model else "groq"

    def get_active_model_name(self) -> str:
        parts = self.active_model.split("/", 1)
        return parts[1] if len(parts) == 2 else self.active_model


def load_config() -> FrankiConfig:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    raw = json.loads(CONFIG_FILE.read_text())
    return FrankiConfig(**raw)


def save_config(cfg: FrankiConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(cfg.model_dump_json(indent=2))
