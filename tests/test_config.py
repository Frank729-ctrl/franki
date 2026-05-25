"""Tests for config.py — provider model, priority ordering, key resolution."""
import os
import pytest
from franki.config import FrankiConfig, KNOWN_PROVIDERS


def _make_cfg(**kwargs) -> FrankiConfig:
    return FrankiConfig(**kwargs)


def _provider(model="llama", base_url="https://api.groq.com/openai/v1",
              api_key="sk-test", priority=1, key_required=True):
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "priority": priority,
        "key_required": key_required,
    }


class TestFrankiConfigBasics:
    def test_defaults(self):
        cfg = FrankiConfig()
        assert cfg.active_provider == ""
        assert cfg.active_skill == "coding"
        assert cfg.auto_skill is True
        assert cfg.auto_accept is False
        assert cfg.stream is True

    def test_get_active_model_no_provider(self):
        cfg = FrankiConfig()
        assert cfg.get_active_model() == ""

    def test_get_active_model(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={"groq": _provider(model="llama-3.3-70b")},
        )
        assert cfg.get_active_model() == "llama-3.3-70b"

    def test_get_active_base_url(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={"groq": _provider(base_url="https://api.groq.com/openai/v1")},
        )
        assert cfg.get_active_base_url() == "https://api.groq.com/openai/v1"

    def test_get_provider_key_from_config(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={"groq": _provider(api_key="sk-abc123")},
        )
        assert cfg.get_provider_key("groq") == "sk-abc123"

    def test_get_provider_key_from_env(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "env-key-xyz")
        cfg = FrankiConfig(
            active_provider="groq",
            providers={"groq": _provider(api_key="config-key")},
        )
        # env var overrides config
        assert cfg.get_provider_key("groq") == "env-key-xyz"

    def test_get_provider_key_missing(self):
        cfg = FrankiConfig()
        assert cfg.get_provider_key("nonexistent") == ""


class TestProviderPriorityOrdering:
    def test_active_provider_comes_first(self):
        cfg = FrankiConfig(
            active_provider="b",
            providers={
                "a": _provider(priority=1, model="m-a"),
                "b": _provider(priority=2, model="m-b"),
                "c": _provider(priority=3, model="m-c"),
            },
        )
        ordered = [name for name, _ in cfg.provider_list_by_priority()]
        assert ordered[0] == "b"

    def test_remaining_sorted_by_priority(self):
        cfg = FrankiConfig(
            active_provider="a",
            providers={
                "a": _provider(priority=1, model="m-a"),
                "c": _provider(priority=3, model="m-c"),
                "b": _provider(priority=2, model="m-b"),
            },
        )
        ordered = [name for name, _ in cfg.provider_list_by_priority()]
        # after 'a' (active), should be b then c
        assert ordered[1:] == ["b", "c"]

    def test_provider_without_model_excluded(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={
                "groq": _provider(model="llama"),
                "empty": {"api_key": "x", "base_url": "http://x", "model": "", "priority": 1},
            },
        )
        names = [name for name, _ in cfg.provider_list_by_priority()]
        assert "empty" not in names

    def test_provider_without_key_excluded_when_required(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={
                "groq": _provider(model="llama"),
                "nokey": {"api_key": "", "base_url": "http://x", "model": "m", "priority": 2, "key_required": True},
            },
        )
        names = [name for name, _ in cfg.provider_list_by_priority()]
        assert "nokey" not in names

    def test_provider_without_key_included_when_not_required(self):
        cfg = FrankiConfig(
            active_provider="ollama",
            providers={
                "ollama": {
                    "api_key": "ollama",
                    "base_url": "http://localhost:11434/v1",
                    "model": "llama3",
                    "priority": 1,
                    "key_required": False,
                },
            },
        )
        names = [name for name, _ in cfg.provider_list_by_priority()]
        assert "ollama" in names

    def test_first_configured_provider(self):
        cfg = FrankiConfig(
            providers={"groq": _provider(model="llama")},
        )
        assert cfg.first_configured_provider() == "groq"

    def test_first_configured_provider_none_when_empty(self):
        cfg = FrankiConfig()
        assert cfg.first_configured_provider() is None


class TestKnownProviders:
    def test_known_providers_have_required_fields(self):
        for name, preset in KNOWN_PROVIDERS.items():
            assert "base_url" in preset, f"{name} missing base_url"
            assert "suggested_models" in preset, f"{name} missing suggested_models"
            assert isinstance(preset["suggested_models"], list), f"{name} suggested_models not list"
            assert len(preset["suggested_models"]) > 0, f"{name} has no suggested models"
