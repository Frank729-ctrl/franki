from __future__ import annotations
import json
import os
from pathlib import Path
from pydantic import BaseModel


CONFIG_DIR = Path.home() / ".config" / "franki"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Known provider presets — used by setup wizard as starting points.
# Users can add any custom OpenAI-compatible provider.
KNOWN_PROVIDERS: dict[str, dict] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "suggested_models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "deepseek-r1-distill-llama-70b",
        ],
        "key_url": "console.groq.com/keys",
        "key_required": True,
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "suggested_models": [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
        ],
        "key_url": "aistudio.google.com/apikey",
        "key_required": True,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "suggested_models": [
            "meta-llama/llama-3.3-70b:free",
            "deepseek/deepseek-coder:free",
            "google/gemini-2.5-flash:free",
        ],
        "key_url": "openrouter.ai/keys",
        "key_required": True,
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "suggested_models": ["llama3", "mistral", "codellama", "qwen2.5-coder"],
        "key_url": None,
        "key_required": False,
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "suggested_models": ["meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo"],
        "key_url": "api.together.ai/settings/api-keys",
        "key_required": True,
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "suggested_models": ["llama-3.3-70b"],
        "key_url": "cloud.cerebras.ai",
        "key_required": True,
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "suggested_models": ["mistral-small-latest", "mistral-large-latest"],
        "key_url": "console.mistral.ai/api-keys",
        "key_required": True,
    },
}


class FrankiConfig(BaseModel):
    # Provider that is currently active
    active_provider: str = ""

    # Providers: name → {api_key, base_url, model, priority}
    providers: dict[str, dict] = {}

    # Skill
    active_skill: str = "coding"
    auto_skill: bool = True

    # Streaming
    stream: bool = True

    # Export / notes
    export_path: str = "~/Documents/franki-sessions"

    # Shell execution auto-accept
    auto_accept: bool = False

    # Web search (Tavily direct)
    tavily_api_key: str = ""

    # MCP server configs: name → {command, args, env, enabled}
    mcp: dict[str, dict] = {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_provider_key(self, provider: str) -> str:
        # Env var takes precedence (e.g. GROQ_API_KEY)
        env_key = f"{provider.upper()}_API_KEY"
        env_val = os.environ.get(env_key, "")
        if env_val:
            return env_val
        pdata = self.providers.get(provider, {})
        return pdata.get("api_key", "") if isinstance(pdata, dict) else ""

    def get_active_model(self) -> str:
        pdata = self.providers.get(self.active_provider, {})
        return pdata.get("model", "") if isinstance(pdata, dict) else ""

    def get_active_base_url(self) -> str:
        pdata = self.providers.get(self.active_provider, {})
        return pdata.get("base_url", "") if isinstance(pdata, dict) else ""

    def provider_list_by_priority(self) -> list[tuple[str, dict]]:
        """
        Return all configured (key + model + base_url) providers ordered so the
        active provider comes first, then others by ascending priority number.
        """
        entries: list[tuple[int, str, dict]] = []
        for name, pdata in self.providers.items():
            if not isinstance(pdata, dict):
                continue
            if not pdata.get("model") or not pdata.get("base_url"):
                continue
            if not self.get_provider_key(name) and pdata.get("key_required", True):
                continue
            priority = 0 if name == self.active_provider else pdata.get("priority", 99)
            entries.append((priority, name, pdata))
        entries.sort(key=lambda x: x[0])
        return [(name, pdata) for _, name, pdata in entries]

    def first_configured_provider(self) -> str | None:
        """Return name of the first usable provider."""
        for name, pdata in self.providers.items():
            if not isinstance(pdata, dict):
                continue
            if pdata.get("model") and pdata.get("base_url"):
                if self.get_provider_key(name) or not pdata.get("key_required", True):
                    return name
        return None


def load_config() -> FrankiConfig:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        return FrankiConfig()
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return FrankiConfig(**raw)
    except Exception:
        return FrankiConfig()


def save_config(cfg: FrankiConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
