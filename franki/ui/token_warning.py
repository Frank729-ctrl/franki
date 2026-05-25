"""
token_warning.py — context-window thresholds and token usage percentage.
"""
from __future__ import annotations

# Known context windows in tokens
_CONTEXT_WINDOWS: dict[str, int] = {
    # Groq
    "llama-3.3-70b-versatile":        128_000,
    "llama-3.1-8b-instant":           128_000,
    "deepseek-r1-distill-llama-70b":  128_000,
    # Gemini
    "gemini-2.5-flash":             1_000_000,
    "gemini-2.5-flash-lite":        1_000_000,
    # DelkaAI
    "auto":                           128_000,
}

_OPENROUTER_DEFAULT = 32_000
_WARN_THRESHOLD     = 0.80          # 80%


def context_window(model_name: str) -> int:
    """Return the context-window size for a model name. OpenRouter models default to 32k."""
    return _CONTEXT_WINDOWS.get(model_name, _OPENROUTER_DEFAULT)


def token_usage_pct(approx_tokens: int, model_name: str) -> float:
    """Return fraction (0.0–1.0) of the context window consumed."""
    window = context_window(model_name)
    return approx_tokens / window


def warning_text(approx_tokens: int, model_name: str) -> str | None:
    """
    Return a warning string if usage exceeds the threshold, else None.
    e.g. "⚠ context 82% full — /compact to reduce"
    """
    pct = token_usage_pct(approx_tokens, model_name)
    if pct >= _WARN_THRESHOLD:
        return f"⚠ context {pct:.0%} full — /compact to reduce"
    return None
