from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from pydantic import BaseModel


def _warn(msg: str) -> None:
    print(f"  franki: {msg}", file=sys.stderr)


CONFIG_DIR = Path.home() / ".config" / "franki"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Known provider presets — used by setup wizard as starting points.
# Users can add any custom OpenAI-compatible provider.
KNOWN_PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "api_type": "anthropic",
        "suggested_models": [
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ],
        "key_url": "console.anthropic.com/settings/api-keys",
        "key_required": True,
        "capabilities": ["coding", "reasoning", "long-context", "vision"],
        "cost_per_1m_input": 3.0,
        "cost_per_1m_output": 15.0,
        "local": False,
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "suggested_models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "deepseek-r1-distill-llama-70b",
        ],
        "key_url": "console.groq.com/keys",
        "key_required": True,
        "capabilities": ["speed", "coding"],
        "cost_per_1m_input": 0.05,
        "cost_per_1m_output": 0.08,
        "local": False,
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
        "capabilities": ["long-context", "vision", "reasoning"],
        "cost_per_1m_input": 0.15,
        "cost_per_1m_output": 0.60,
        "local": False,
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
        "capabilities": ["reasoning", "coding", "vision", "long-context"],
        "cost_per_1m_input": 0.0,
        "cost_per_1m_output": 0.0,
        "local": False,
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "suggested_models": ["llama3", "mistral", "codellama", "qwen2.5-coder"],
        "key_url": None,
        "key_required": False,
        "capabilities": ["local", "coding", "cheap"],
        "cost_per_1m_input": 0.0,
        "cost_per_1m_output": 0.0,
        "local": True,
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "suggested_models": ["meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo"],
        "key_url": "api.together.ai/settings/api-keys",
        "key_required": True,
        "capabilities": ["coding", "reasoning"],
        "cost_per_1m_input": 0.90,
        "cost_per_1m_output": 0.90,
        "local": False,
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "suggested_models": ["llama-3.3-70b"],
        "key_url": "cloud.cerebras.ai",
        "key_required": True,
        "capabilities": ["speed", "coding"],
        "cost_per_1m_input": 0.60,
        "cost_per_1m_output": 0.60,
        "local": False,
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "suggested_models": ["mistral-small-latest", "mistral-large-latest"],
        "key_url": "console.mistral.ai/api-keys",
        "key_required": True,
        "capabilities": ["coding", "reasoning", "json"],
        "cost_per_1m_input": 0.20,
        "cost_per_1m_output": 0.60,
        "local": False,
    },
    "cohere": {
        "base_url": "https://api.cohere.com",
        "api_type": "cohere",
        "suggested_models": [
            "command-r-plus-08-2024",
            "command-r-08-2024",
            "command-r7b-12-2024",
        ],
        "key_url": "dashboard.cohere.com/api-keys",
        "key_required": True,
        "capabilities": ["coding", "reasoning", "long-context"],
        "cost_per_1m_input": 2.50,
        "cost_per_1m_output": 10.0,
        "local": False,
    },
    "azure": {
        "base_url": "",
        "api_type": "azure",
        "suggested_models": ["gpt-4o", "gpt-4o-mini"],
        "key_url": "portal.azure.com",
        "key_required": True,
        "capabilities": ["coding", "reasoning", "vision"],
        "cost_per_1m_input": 2.50,
        "cost_per_1m_output": 10.0,
        "local": False,
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

    # Notify when a multi-step task finishes while auto_accept is on
    notify_on_done: bool = True

    # Auto-copy each AI response to clipboard
    auto_copy: bool = False

    # Auto-compact: summarise history when context window reaches threshold
    auto_compact: bool = True
    auto_compact_threshold: float = 0.70      # fraction of context window (was 0.85)
    auto_compact_messages: int = 0            # 0 = disabled; N = compact after N user messages
    auto_commit: bool = False

    # Token budget: trim large tool results before sending to reduce rate-limit pressure.
    # tool_result_max_chars: max chars kept per tool result in API calls (0 = unlimited).
    # max_history_turns: sliding window — only last N user turns sent (0 = unlimited).
    tool_result_max_chars: int = 2000
    max_history_turns: int = 0
    # per-tool overrides: tool_name → "always" | "ask" | "never"
    tool_permissions: dict[str, str] = {}

    # Routing
    local_first: bool = False                 # prefer local providers (Ollama, LM Studio)
    routing_strategy: str = "capability"      # "capability" | "speed" | "cost" | "priority"

    # Web search (Tavily direct)
    tavily_api_key: str = ""

    # MCP server configs: name → {command, args, env, enabled}
    mcp: dict[str, dict] = {}

    # Session counter — used to trigger periodic feedback prompts
    session_count: int = 0

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


def _is_legacy_config(raw: dict) -> bool:
    """Detect 0.1.0 config format: had active_model string or providers with models list."""
    if "active_model" in raw:
        return True
    for pdata in raw.get("providers", {}).values():
        if isinstance(pdata, dict) and "models" in pdata:
            return True
    return False


def needs_setup() -> bool:
    """True when no config exists, config is legacy format, or no providers are configured."""
    if not CONFIG_FILE.exists():
        return True
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if _is_legacy_config(raw):
            return True
        # No providers means setup was never completed (e.g. after a reinstall)
        if not raw.get("providers"):
            return True
        return False
    except (OSError, json.JSONDecodeError):
        return True
    except Exception:
        return True


def load_config() -> FrankiConfig:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        return FrankiConfig()

    try:
        text = CONFIG_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        _warn(f"could not read config: {exc} — using defaults")
        return FrankiConfig()

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        bak = CONFIG_FILE.with_suffix(".json.bak")
        try:
            bak.write_text(text, encoding="utf-8")
        except OSError:
            pass
        _warn(f"config is corrupt ({exc}) — using defaults. Original backed up to {bak}")
        return FrankiConfig()

    try:
        return FrankiConfig(**raw)
    except Exception as exc:
        _warn(f"config has incompatible fields ({exc}) — using defaults")
        return FrankiConfig()


def save_config(cfg: FrankiConfig) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    except OSError as exc:
        _warn(f"could not save config: {exc}")
