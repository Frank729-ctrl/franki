"""Tests for config_cmd.py — helper functions and interactive config."""
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock

from franki.config import FrankiConfig


def _cfg(**kwargs):
    base = {
        "active_provider": "groq",
        "active_skill": "coding",
        "providers": {
            "groq": {
                "api_key": "sk-test",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama-3.3-70b",
                "priority": 1,
                "key_required": True,
            }
        },
        "tavily_api_key": "tv-test",
        "auto_compact": True,
        "auto_compact_threshold": 0.85,
        "auto_compact_messages": 0,
    }
    base.update(kwargs)
    return FrankiConfig(**base)


def _noop(*args, **kwargs):
    pass


# ── _mask ─────────────────────────────────────────────────────────────────────

class TestMask:
    def test_empty_returns_not_set(self):
        from franki.config_cmd import _mask
        assert _mask("") == "(not set)"

    def test_short_value_all_stars(self):
        from franki.config_cmd import _mask
        assert _mask("abc") == "****"

    def test_long_value_partial(self):
        from franki.config_cmd import _mask
        result = _mask("sk-abcdefghijklmn")
        assert result.startswith("sk-a")
        assert result.endswith("lmn")
        assert "****" in result

    def test_exactly_8_chars_all_stars(self):
        from franki.config_cmd import _mask
        assert _mask("12345678") == "****"

    def test_9_chars_shows_partial(self):
        from franki.config_cmd import _mask
        result = _mask("123456789")
        assert "1234" in result
        assert "6789" in result


# ── _ask ──────────────────────────────────────────────────────────────────────

class TestAsk:
    def test_returns_input(self):
        from franki.config_cmd import _ask
        with patch("builtins.input", return_value="myvalue"):
            result = _ask("Enter name")
        assert result == "myvalue"

    def test_empty_input_returns_default(self):
        from franki.config_cmd import _ask
        with patch("builtins.input", return_value=""):
            result = _ask("Enter name", default="default_val")
        assert result == "default_val"

    def test_eof_returns_default(self):
        from franki.config_cmd import _ask
        with patch("builtins.input", side_effect=EOFError):
            result = _ask("Enter name", default="fallback")
        assert result == "fallback"

    def test_keyboard_interrupt_returns_default(self):
        from franki.config_cmd import _ask
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = _ask("Enter name", default="safe")
        assert result == "safe"

    def test_no_default_empty_returns_empty(self):
        from franki.config_cmd import _ask
        with patch("builtins.input", return_value=""):
            result = _ask("prompt")
        assert result == ""


# ── _yn ───────────────────────────────────────────────────────────────────────

class TestYn:
    def test_y_returns_true(self):
        from franki.config_cmd import _yn
        with patch("builtins.input", return_value="y"):
            assert _yn("Enable?", False) is True

    def test_n_returns_false(self):
        from franki.config_cmd import _yn
        with patch("builtins.input", return_value="n"):
            assert _yn("Enable?", True) is False

    def test_empty_returns_current_true(self):
        from franki.config_cmd import _yn
        with patch("builtins.input", return_value=""):
            assert _yn("Enable?", True) is True

    def test_empty_returns_current_false(self):
        from franki.config_cmd import _yn
        with patch("builtins.input", return_value=""):
            assert _yn("Enable?", False) is False

    def test_eof_returns_current(self):
        from franki.config_cmd import _yn
        with patch("builtins.input", side_effect=EOFError):
            assert _yn("Enable?", True) is True

    def test_yes_word_returns_true(self):
        from franki.config_cmd import _yn
        with patch("builtins.input", return_value="yes"):
            assert _yn("Enable?", False) is True


# ── _print_summary ────────────────────────────────────────────────────────────

class TestPrintSummary:
    def test_renders_without_crash(self):
        from franki.config_cmd import _print_summary
        _print_summary(_cfg())

    def test_no_providers(self):
        from franki.config_cmd import _print_summary
        _print_summary(FrankiConfig())

    def test_auto_compact_off(self):
        from franki.config_cmd import _print_summary
        cfg = _cfg(auto_compact=False)
        _print_summary(cfg)

    def test_auto_compact_with_message_count(self):
        from franki.config_cmd import _print_summary
        cfg = _cfg(auto_compact=True, auto_compact_messages=50)
        _print_summary(cfg)


# ── run_interactive_config ────────────────────────────────────────────────────

class TestRunInteractiveConfig:
    """
    Each test provides exactly the right sequence of inputs.
    The first input() call is for the main menu choice.
    Additional calls depend on the option chosen.
    Finally a "0" or "" quits the loop.
    """

    def test_quit_with_zero(self):
        from franki.config_cmd import run_interactive_config
        with patch("builtins.input", return_value="0"):
            run_interactive_config(_cfg())

    def test_quit_with_empty(self):
        from franki.config_cmd import run_interactive_config
        with patch("builtins.input", return_value=""):
            run_interactive_config(_cfg())

    def test_eof_quits(self):
        from franki.config_cmd import run_interactive_config
        with patch("builtins.input", side_effect=EOFError):
            run_interactive_config(_cfg())

    def test_keyboard_interrupt_quits(self):
        from franki.config_cmd import run_interactive_config
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            run_interactive_config(_cfg())

    def test_unknown_choice_continues_to_quit(self):
        from franki.config_cmd import run_interactive_config
        # "99" → unknown → loop back → "0" → quit
        inputs = iter(["99", "0"])
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(_cfg())

    def test_option_4_auto_skill_toggle(self):
        from franki.config_cmd import run_interactive_config
        # choice "4" → _yn("Enable auto-skill?") → "y" → back to menu → "0"
        cfg = _cfg(auto_skill=True)
        inputs = iter(["4", "n", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.auto_skill is False

    def test_option_5_auto_accept_toggle(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg(auto_accept=False)
        inputs = iter(["5", "y", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.auto_accept is True

    def test_option_8_local_first_toggle(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        cfg.local_first = False
        inputs = iter(["8", "y", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.local_first is True

    def test_option_9_export_path(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        # "9" → _ask("Export path") → "/new/path" → back → "0"
        inputs = iter(["9", "/new/path", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.export_path == "/new/path"

    def test_option_9_empty_path_no_change(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        original_path = cfg.export_path
        inputs = iter(["9", "", "0"])
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg)
        assert cfg.export_path == original_path

    def test_option_10_tavily_key(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        # "10" → getpass("") → "tv-newkey" → "0"
        inputs = iter(["10", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            with patch("getpass.getpass", return_value="tv-newkey"):
                run_interactive_config(cfg, save_fn)
        assert cfg.tavily_api_key == "tv-newkey"

    def test_option_10_eof_continues(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        inputs = iter(["10", "0"])
        with patch("builtins.input", side_effect=inputs):
            with patch("getpass.getpass", side_effect=EOFError):
                run_interactive_config(cfg)

    def test_option_1_set_active_provider(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        # "1" → shows providers → _ask → "groq" → back → "0"
        inputs = iter(["1", "groq", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.active_provider == "groq"

    def test_option_1_no_providers(self):
        from franki.config_cmd import run_interactive_config
        cfg = FrankiConfig()  # no providers
        # "1" → "no providers" message → loop → "0"
        inputs = iter(["1", "0"])
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg)

    def test_option_2_change_model(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        inputs = iter(["2", "llama-3.1-8b", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.providers["groq"]["model"] == "llama-3.1-8b"

    def test_option_3_change_skill(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg(active_skill="coding")
        inputs = iter(["3", "pentest", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.active_skill == "pentest"

    def test_option_3_invalid_skill(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg(active_skill="coding")
        inputs = iter(["3", "not_a_real_skill_xyz", "0"])
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg)
        assert cfg.active_skill == "coding"  # unchanged

    def test_option_7_routing_strategy(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        inputs = iter(["7", "speed", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.routing_strategy == "speed"

    def test_option_7_invalid_strategy(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        inputs = iter(["7", "invalid_strat", "0"])
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg)
        assert cfg.routing_strategy == "capability"  # unchanged

    def test_option_11_update_provider_key(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        # "11" → shows providers → _ask → "groq" → getpass → "sk-newkey" → "0"
        inputs = iter(["11", "groq", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            with patch("getpass.getpass", return_value="sk-newkey"):
                run_interactive_config(cfg, save_fn)
        assert cfg.providers["groq"]["api_key"] == "sk-newkey"

    def test_option_11_no_providers(self):
        from franki.config_cmd import run_interactive_config
        cfg = FrankiConfig()
        inputs = iter(["11", "0"])
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg)

    def test_option_11_provider_not_found(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        inputs = iter(["11", "nonexistent", "0"])
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg)

    def test_option_6_compact_off(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg(auto_compact=True)
        # "6" → _yn → "n" (turn off) → skip threshold → "0"
        inputs = iter(["6", "n", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.auto_compact is False

    def test_option_6_compact_on_with_threshold(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg(auto_compact=False)
        # "6" → _yn → "y" (turn on) → _ask threshold → "90" → "0"
        inputs = iter(["6", "y", "90", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.auto_compact is True
        assert abs(cfg.auto_compact_threshold - 0.90) < 0.01


# ── run_config_cli ────────────────────────────────────────────────────────────

class TestRunConfigCli:
    def test_list_action(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg):
            run_config_cli(["list"])

    def test_get_export_path(self, capsys):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg):
            run_config_cli(["get", "export_path"])
        out = capsys.readouterr().out
        assert "export_path" in out

    def test_get_provider_key_masked(self, capsys):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg):
            run_config_cli(["get", "groq.api_key"])
        out = capsys.readouterr().out
        # Key should be masked
        assert "sk-test" not in out

    def test_set_active_provider(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config") as mock_save:
            run_config_cli(["set", "active_skill", "pentest"])
        assert mock_save.called

    def test_set_auto_compact_true(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg(auto_compact=False)
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "auto_compact", "true"])
        assert cfg.auto_compact is True

    def test_set_auto_compact_threshold(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "auto_compact_threshold", "80%"])
        assert abs(cfg.auto_compact_threshold - 0.80) < 0.01

    def test_set_auto_compact_threshold_invalid(self, capsys):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "auto_compact_threshold", "notanumber"])
        out = capsys.readouterr().out
        assert "invalid" in out

    def test_set_auto_compact_messages(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "auto_compact_messages", "50"])
        assert cfg.auto_compact_messages == 50

    def test_set_local_first(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "local_first", "true"])
        assert cfg.local_first is True

    def test_set_routing_strategy(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "routing_strategy", "speed"])
        assert cfg.routing_strategy == "speed"

    def test_set_routing_strategy_invalid(self, capsys):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "routing_strategy", "invalid"])
        out = capsys.readouterr().out
        assert "unknown strategy" in out

    def test_set_provider_field(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "groq.model", "llama-3.1-8b"])
        assert cfg.providers["groq"]["model"] == "llama-3.1-8b"

    def test_set_unknown_provider_field(self, capsys):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "nonexistent.model", "m"])
        out = capsys.readouterr().out
        assert "not found" in out

    def test_set_unknown_key(self, capsys):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "unknown_key_xyz", "value"])
        out = capsys.readouterr().out
        assert "unknown key" in out

    def test_interactive_no_args(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg):
            with patch("builtins.input", return_value="0"):
                run_config_cli([])

    def test_usage_message_on_bad_args(self, capsys):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg):
            run_config_cli(["garbage"])
        out = capsys.readouterr().out
        assert "usage" in out.lower()

    def test_set_active_provider_key(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "active_provider", "groq"])
        assert cfg.active_provider == "groq"

    def test_set_export_path(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "export_path", "/tmp/exports"])
        assert cfg.export_path == "/tmp/exports"

    def test_set_auto_skill(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg(auto_skill=False)
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "auto_skill", "true"])
        assert cfg.auto_skill is True

    def test_set_auto_accept(self):
        from franki.config_cmd import run_config_cli
        cfg = _cfg(auto_accept=False)
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "auto_accept", "yes"])
        assert cfg.auto_accept is True

    def test_set_auto_compact_messages_invalid(self, capsys):
        from franki.config_cmd import run_config_cli
        cfg = _cfg()
        with patch("franki.config_cmd.load_config", return_value=cfg), \
             patch("franki.config_cmd.save_config"):
            run_config_cli(["set", "auto_compact_messages", "notanumber"])
        out = capsys.readouterr().out
        assert "invalid" in out


# ── Additional interactive config tests (index-based selection) ───────────────

class TestRunInteractiveConfigIndexSelection:
    def test_option_1_by_digit_index(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        # "1" → show providers → sel="1" (digit) → idx=0 → names[0]="groq" → set → "0"
        inputs = iter(["1", "1", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.active_provider == "groq"
        assert save_fn.called

    def test_option_1_provider_not_found_by_name(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        inputs = iter(["1", "does_not_exist", "0"])
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg)
        assert cfg.active_provider == "groq"  # unchanged

    def test_option_3_by_digit_index(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg(active_skill="coding")
        # "3" → show skills → sel="1" (digit) → first skill → "0"
        inputs = iter(["3", "1", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert save_fn.called  # a valid skill was selected

    def test_option_6_invalid_threshold_no_crash(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg(auto_compact=False)
        # "6" → "y" → threshold="notanumber" → ValueError ignored → "0"
        inputs = iter(["6", "y", "notanumber", "0"])
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg)
        assert cfg.auto_compact is True  # still turned on

    def test_option_7_by_digit_index(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        # "7" → show strategies → "1" → "capability" → "0"
        inputs = iter(["7", "1", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            run_interactive_config(cfg, save_fn)
        assert cfg.routing_strategy == "capability"
        assert save_fn.called

    def test_option_11_by_digit_index(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        # "11" → show providers → "1" (digit) → sel="groq" → getpass → "newkey" → "0"
        inputs = iter(["11", "1", "0"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            with patch("getpass.getpass", return_value="newkey"):
                run_interactive_config(cfg, save_fn)
        assert cfg.providers["groq"]["api_key"] == "newkey"
        assert save_fn.called

    def test_option_11_getpass_eof_continues(self):
        from franki.config_cmd import run_interactive_config
        cfg = _cfg()
        original_key = cfg.providers["groq"]["api_key"]
        # "11" → "groq" → getpass raises EOFError → continue → "0"
        inputs = iter(["11", "groq", "0"])
        with patch("builtins.input", side_effect=inputs):
            with patch("getpass.getpass", side_effect=EOFError):
                run_interactive_config(cfg)
        assert cfg.providers["groq"]["api_key"] == original_key  # unchanged
