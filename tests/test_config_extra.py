"""Extra tests for config.py — needs_setup, load_config, save_config, legacy detection."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from franki.config import (
    FrankiConfig,
    _is_legacy_config,
    needs_setup,
    load_config,
    save_config,
)


# ── _is_legacy_config ─────────────────────────────────────────────────────────

class TestIsLegacyConfig:
    def test_active_model_key_is_legacy(self):
        raw = {"active_model": "llama", "providers": {}}
        assert _is_legacy_config(raw) is True

    def test_provider_with_models_list_is_legacy(self):
        raw = {
            "providers": {
                "groq": {"models": ["llama-3", "llama-2"], "api_key": "sk"}
            }
        }
        assert _is_legacy_config(raw) is True

    def test_modern_config_is_not_legacy(self):
        raw = {
            "active_provider": "groq",
            "providers": {
                "groq": {"model": "llama-3", "api_key": "sk", "base_url": "https://x"}
            },
        }
        assert _is_legacy_config(raw) is False

    def test_empty_dict_is_not_legacy(self):
        assert _is_legacy_config({}) is False

    def test_no_providers_key_is_not_legacy(self):
        assert _is_legacy_config({"active_provider": "groq"}) is False

    def test_non_dict_provider_value_ignored(self):
        raw = {"providers": {"groq": "string_value"}}
        assert _is_legacy_config(raw) is False


# ── needs_setup ───────────────────────────────────────────────────────────────

class TestNeedsSetup:
    def test_no_config_file_returns_true(self, tmp_path):
        fake_file = tmp_path / "config.json"
        with patch("franki.config.CONFIG_FILE", fake_file):
            assert needs_setup() is True

    def test_modern_config_returns_false(self, tmp_path):
        fake_file = tmp_path / "config.json"
        modern = {
            "active_provider": "groq",
            "providers": {"groq": {"model": "llama", "base_url": "https://x", "api_key": "k"}},
        }
        fake_file.write_text(json.dumps(modern))
        with patch("franki.config.CONFIG_FILE", fake_file):
            assert needs_setup() is False

    def test_legacy_config_returns_true(self, tmp_path):
        fake_file = tmp_path / "config.json"
        legacy = {"active_model": "llama", "providers": {}}
        fake_file.write_text(json.dumps(legacy))
        with patch("franki.config.CONFIG_FILE", fake_file):
            assert needs_setup() is True

    def test_corrupt_file_returns_true(self, tmp_path):
        fake_file = tmp_path / "config.json"
        fake_file.write_text("not valid json {{{")
        with patch("franki.config.CONFIG_FILE", fake_file):
            assert needs_setup() is True


# ── load_config ───────────────────────────────────────────────────────────────

class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, tmp_path):
        fake_file = tmp_path / "config.json"
        fake_dir = tmp_path
        with patch("franki.config.CONFIG_FILE", fake_file), \
             patch("franki.config.CONFIG_DIR", fake_dir):
            cfg = load_config()
        assert isinstance(cfg, FrankiConfig)
        assert cfg.active_provider == ""

    def test_loads_stored_values(self, tmp_path):
        fake_file = tmp_path / "config.json"
        fake_dir = tmp_path
        data = {"active_provider": "gemini", "active_skill": "soc"}
        fake_file.write_text(json.dumps(data))
        with patch("franki.config.CONFIG_FILE", fake_file), \
             patch("franki.config.CONFIG_DIR", fake_dir):
            cfg = load_config()
        assert cfg.active_provider == "gemini"
        assert cfg.active_skill == "soc"

    def test_corrupt_file_returns_defaults(self, tmp_path):
        fake_file = tmp_path / "config.json"
        fake_dir = tmp_path
        fake_file.write_text("{corrupt}")
        with patch("franki.config.CONFIG_FILE", fake_file), \
             patch("franki.config.CONFIG_DIR", fake_dir):
            cfg = load_config()
        assert isinstance(cfg, FrankiConfig)


# ── save_config ───────────────────────────────────────────────────────────────

class TestSaveConfig:
    def test_writes_json_file(self, tmp_path):
        fake_file = tmp_path / "config.json"
        fake_dir = tmp_path
        cfg = FrankiConfig(active_provider="groq", active_skill="pentest")
        with patch("franki.config.CONFIG_FILE", fake_file), \
             patch("franki.config.CONFIG_DIR", fake_dir):
            save_config(cfg)
        assert fake_file.exists()
        data = json.loads(fake_file.read_text())
        assert data["active_provider"] == "groq"
        assert data["active_skill"] == "pentest"

    def test_creates_dir_if_missing(self, tmp_path):
        new_dir = tmp_path / "nested" / "dir"
        fake_file = new_dir / "config.json"
        cfg = FrankiConfig()
        with patch("franki.config.CONFIG_FILE", fake_file), \
             patch("franki.config.CONFIG_DIR", new_dir):
            save_config(cfg)
        assert fake_file.exists()

    def test_roundtrip_preserves_values(self, tmp_path):
        fake_file = tmp_path / "config.json"
        fake_dir = tmp_path
        cfg = FrankiConfig(
            tavily_api_key="tv-key-123",
            local_first=True,
            auto_compact_messages=50,
        )
        with patch("franki.config.CONFIG_FILE", fake_file), \
             patch("franki.config.CONFIG_DIR", fake_dir):
            save_config(cfg)
            loaded = load_config()
        assert loaded.tavily_api_key == "tv-key-123"
        assert loaded.local_first is True
        assert loaded.auto_compact_messages == 50


# ── FrankiConfig helpers ──────────────────────────────────────────────────────

class TestFrankiConfigHelpers:
    def test_get_active_base_url_empty_when_no_provider(self):
        cfg = FrankiConfig()
        assert cfg.get_active_base_url() == ""

    def test_get_provider_key_missing_provider(self):
        cfg = FrankiConfig(active_provider="groq", providers={})
        key = cfg.get_provider_key("groq")
        assert key == ""

    def test_provider_list_skips_missing_model(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={"groq": {"api_key": "k", "base_url": "https://x", "model": "", "priority": 1}},
        )
        result = cfg.provider_list_by_priority()
        assert result == []

    def test_first_configured_provider_skips_no_model(self):
        cfg = FrankiConfig(
            providers={
                "empty": {"api_key": "x", "base_url": "http://x", "model": "", "priority": 1},
                "real": {"api_key": "k", "base_url": "http://real", "model": "m", "priority": 2},
            }
        )
        result = cfg.first_configured_provider()
        assert result == "real"

    def test_first_configured_provider_skips_no_key_required(self):
        cfg = FrankiConfig(
            providers={
                "nokey": {
                    "api_key": "",
                    "base_url": "http://x",
                    "model": "m",
                    "priority": 1,
                    "key_required": True,
                }
            }
        )
        result = cfg.first_configured_provider()
        assert result is None

    def test_routing_config_defaults(self):
        cfg = FrankiConfig()
        assert cfg.local_first is False
        assert cfg.routing_strategy == "capability"
        assert cfg.auto_compact is True
        assert cfg.auto_compact_threshold == pytest.approx(0.85)
        assert cfg.auto_compact_messages == 0
