"""Tests for standalone functions in main.py."""
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock

from franki.config import FrankiConfig
from franki.session import Session


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
                "capabilities": ["coding", "speed"],
            }
        },
    }
    base.update(kwargs)
    return FrankiConfig(**base)


# ── _count_tokens_approx ──────────────────────────────────────────────────────

class TestCountTokensApprox:
    def test_empty_string(self):
        from franki.main import _count_tokens_approx
        assert _count_tokens_approx("") == 1  # max(1, 0) = 1

    def test_short_text(self):
        from franki.main import _count_tokens_approx
        result = _count_tokens_approx("hello world")
        assert result > 0

    def test_400_chars_is_100_tokens(self):
        from franki.main import _count_tokens_approx
        result = _count_tokens_approx("a" * 400)
        assert result == 100


# ── _auto_search_query ────────────────────────────────────────────────────────

class TestAutoSearchQuery:
    def test_no_triggers_returns_none(self):
        from franki.main import _auto_search_query
        assert _auto_search_query("how do I reverse a list in python?") is None

    def test_latest_triggers(self):
        from franki.main import _auto_search_query
        result = _auto_search_query("what is the latest version of nmap?")
        assert result is not None

    def test_cve_detected(self):
        from franki.main import _auto_search_query
        result = _auto_search_query("tell me about CVE-2024-12345")
        assert result == "CVE-2024-12345"

    def test_today_triggers(self):
        from franki.main import _auto_search_query
        result = _auto_search_query("what happened today in cybersecurity?")
        assert result is not None

    def test_news_triggers(self):
        from franki.main import _auto_search_query
        result = _auto_search_query("any news about the Log4j vulnerability?")
        assert result is not None

    def test_current_triggers(self):
        from franki.main import _auto_search_query
        result = _auto_search_query("what is the current CVE score for this exploit?")
        assert result is not None


# ── _print_fallback_notice ────────────────────────────────────────────────────

class TestPrintFallbackNotice:
    def test_no_crash_with_reason(self):
        from franki.main import _print_fallback_notice
        _print_fallback_notice("groq/llama", "gemini/flash", "rate limit")

    def test_no_crash_without_reason(self):
        from franki.main import _print_fallback_notice
        _print_fallback_notice("groq/llama", "gemini/flash")

    def test_trivial_reason_not_shown(self):
        from franki.main import _print_fallback_notice
        # Should not crash for "rate-limited" or "priority order" reasons
        _print_fallback_notice("p1", "p2", "rate-limited")
        _print_fallback_notice("p1", "p2", "priority order")


# ── _confirm_shell_command ────────────────────────────────────────────────────

class TestConfirmShellCommand:
    def test_auto_accept_returns_true(self):
        from franki.main import _confirm_shell_command
        cfg = _cfg(auto_accept=True)
        assert _confirm_shell_command("ls -la", cfg) is True

    def test_user_accepts(self):
        from franki.main import _confirm_shell_command
        cfg = _cfg(auto_accept=False)
        with patch("builtins.input", return_value="y"):
            assert _confirm_shell_command("ls", cfg) is True

    def test_user_declines(self):
        from franki.main import _confirm_shell_command
        cfg = _cfg(auto_accept=False)
        with patch("builtins.input", return_value="n"):
            assert _confirm_shell_command("rm -rf /", cfg) is False

    def test_empty_input_declines(self):
        from franki.main import _confirm_shell_command
        cfg = _cfg(auto_accept=False)
        with patch("builtins.input", return_value=""):
            assert _confirm_shell_command("cmd", cfg) is False

    def test_eof_declines(self):
        from franki.main import _confirm_shell_command
        cfg = _cfg(auto_accept=False)
        with patch("builtins.input", side_effect=EOFError):
            assert _confirm_shell_command("cmd", cfg) is False

    def test_yes_word_accepted(self):
        from franki.main import _confirm_shell_command
        cfg = _cfg(auto_accept=False)
        with patch("builtins.input", return_value="yes"):
            assert _confirm_shell_command("cmd", cfg) is True


# ── _check_providers ──────────────────────────────────────────────────────────

class TestCheckProviders:
    def test_no_providers_prints_notice(self, capsys):
        from franki.main import _check_providers
        cfg = FrankiConfig()  # no providers
        _check_providers(cfg)  # should not crash

    def test_active_provider_not_in_providers(self):
        from franki.main import _check_providers
        cfg = FrankiConfig(active_provider="missing", providers={})
        with patch("franki.main.save_config"):
            _check_providers(cfg)

    def test_no_key_prints_warning(self, monkeypatch):
        from franki.main import _check_providers
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        cfg = FrankiConfig(
            active_provider="groq",
            providers={"groq": {
                "api_key": "",  # no key
                "base_url": "https://api.groq.com/v1",
                "model": "llama",
                "priority": 1,
                "key_required": True,
            }},
        )
        _check_providers(cfg)  # should print warning, not crash

    def test_good_config_no_output(self):
        from franki.main import _check_providers
        cfg = _cfg()
        _check_providers(cfg)  # should not crash or print anything alarming

    def test_active_provider_missing_falls_back(self):
        from franki.main import _check_providers
        cfg = FrankiConfig(
            active_provider="old_provider",  # not in providers
            providers={"groq": {
                "api_key": "sk-test",
                "base_url": "https://api.groq.com/v1",
                "model": "llama",
                "priority": 1,
                "key_required": True,
            }},
        )
        with patch("franki.main.save_config"):
            _check_providers(cfg)
        assert cfg.active_provider == "groq"


# ── _maybe_auto_compact ───────────────────────────────────────────────────────

class TestMaybeAutoCompact:
    def test_disabled_returns_false(self):
        from franki.main import _maybe_auto_compact
        cfg = FrankiConfig(auto_compact=False)
        assert _maybe_auto_compact(cfg, Session()) is False

    def test_message_count_triggers(self):
        from franki.main import _maybe_auto_compact
        cfg = FrankiConfig(auto_compact=True, auto_compact_messages=3)
        s = Session()
        for _ in range(3):
            s.add_user("q")
            s.add_assistant("a")
        with patch("franki.ai_ops.ask_ai", return_value="summary"):
            result = _maybe_auto_compact(cfg, s)
        assert result is True

    def test_message_count_not_reached(self):
        from franki.main import _maybe_auto_compact
        cfg = FrankiConfig(auto_compact=True, auto_compact_messages=10)
        s = Session()
        s.add_user("q")
        assert _maybe_auto_compact(cfg, s) is False

    def test_token_threshold_not_reached(self):
        from franki.main import _maybe_auto_compact
        cfg = FrankiConfig(auto_compact=True, auto_compact_messages=0, auto_compact_threshold=0.99)
        s = Session()
        s.add_user("short message")
        assert _maybe_auto_compact(cfg, s) is False

    def test_message_count_zero_uses_token_check(self):
        from franki.main import _maybe_auto_compact
        cfg = FrankiConfig(
            auto_compact=True,
            auto_compact_messages=0,  # disabled message count
            auto_compact_threshold=0.99,  # very high — won't trigger
        )
        s = Session()
        # Should check token window, not message count
        result = _maybe_auto_compact(cfg, s)
        assert result is False  # threshold not reached


# ── _prompt_save_exit ─────────────────────────────────────────────────────────

class TestPromptSaveExit:
    def test_empty_session_prints_bye(self, capsys):
        from franki.main import _prompt_save_exit
        s = Session()
        _prompt_save_exit(s, _cfg())

    def test_user_saves(self, tmp_path):
        from franki.main import _prompt_save_exit
        s = Session()
        s.add_user("q")
        s.add_assistant("a")
        cfg = FrankiConfig(export_path=str(tmp_path))
        with patch("builtins.input", return_value="y"):
            _prompt_save_exit(s, cfg)

    def test_user_declines(self):
        from franki.main import _prompt_save_exit
        s = Session()
        s.add_user("q")
        s.add_assistant("a")
        with patch("builtins.input", return_value="n"):
            _prompt_save_exit(s, _cfg())

    def test_eof_no_save(self):
        from franki.main import _prompt_save_exit
        s = Session()
        s.add_user("q")
        with patch("builtins.input", side_effect=EOFError):
            _prompt_save_exit(s, _cfg())

    def test_export_error_handled(self, tmp_path):
        from franki.main import _prompt_save_exit
        s = Session()
        s.add_user("q")
        s.add_assistant("a")
        cfg = FrankiConfig(export_path=str(tmp_path))
        with patch("builtins.input", return_value="y"):
            with patch("franki.exporter.export_session", side_effect=Exception("disk full")):
                _prompt_save_exit(s, cfg)


# ── _render_splash ────────────────────────────────────────────────────────────

class TestRenderSplash:
    def test_renders_without_crash(self):
        from franki.main import _render_splash
        cfg = _cfg()
        _render_splash(cfg)

    def test_renders_with_no_provider(self):
        from franki.main import _render_splash
        cfg = FrankiConfig()
        _render_splash(cfg)


# ── _print_skill_bar ─────────────────────────────────────────────────────────

class TestPrintSkillBar:
    def test_renders_without_crash(self):
        from franki.main import _print_skill_bar
        _print_skill_bar(_cfg())

    def test_renders_with_scope(self):
        from franki.main import _print_skill_bar
        _print_skill_bar(_cfg(), scope="10.0.0.1")

    def test_renders_with_token_warning(self):
        from franki.main import _print_skill_bar
        _print_skill_bar(_cfg(), token_warn="context 85% full")

    def test_pentest_skill_with_scope_shows_report_hint(self):
        from franki.main import _print_skill_bar
        cfg = FrankiConfig(
            active_skill="pentest",
            active_provider="groq",
            providers={"groq": {
                "api_key": "k", "base_url": "https://x",
                "model": "m", "priority": 1,
            }},
        )
        _print_skill_bar(cfg, scope="10.0.0.1")  # pentest + scope → "report when done" hint

    def test_pentest_skill_no_scope_shows_scope_hint(self):
        from franki.main import _print_skill_bar
        cfg = FrankiConfig(
            active_skill="pentest",
            active_provider="groq",
            providers={"groq": {
                "api_key": "k", "base_url": "https://x",
                "model": "m", "priority": 1,
            }},
        )
        _print_skill_bar(cfg)  # pentest, no scope → "/scope to set target hosts" hint

    def test_long_model_name_truncated(self):
        from franki.main import _print_skill_bar
        cfg = FrankiConfig(
            active_provider="groq",
            providers={"groq": {
                "api_key": "k",
                "base_url": "https://x",
                "model": "a" * 35,  # very long model name
                "priority": 1,
            }},
        )
        _print_skill_bar(cfg)


# ── _maybe_auto_switch_skill ──────────────────────────────────────────────────

class TestMaybeAutoSwitchSkill:
    def test_auto_skill_off_does_nothing(self):
        from franki.main import _maybe_auto_switch_skill
        cfg = _cfg(auto_skill=False)
        s = Session(skill="coding")
        _maybe_auto_switch_skill("nmap scan ports", cfg, s, lambda c: None, lambda: None)
        assert s.skill == "coding"

    def test_auto_skill_switches_when_different(self):
        from franki.main import _maybe_auto_switch_skill
        cfg = _cfg(auto_skill=True, active_skill="coding")
        s = Session(skill="coding")
        with patch("franki.skills.detect_skill", return_value="pentest"):
            with patch("franki.main.save_config"):
                _maybe_auto_switch_skill("scan the network", cfg, s, lambda c: None, lambda: None)
        assert s.skill == "pentest"

    def test_auto_skill_same_skill_no_switch(self):
        from franki.main import _maybe_auto_switch_skill
        cfg = _cfg(auto_skill=True, active_skill="coding")
        s = Session(skill="coding")
        with patch("franki.skills.detect_skill", return_value="coding"):
            _maybe_auto_switch_skill("write python code", cfg, s, lambda c: None, lambda: None)
        assert s.skill == "coding"

    def test_auto_skill_none_returned_no_switch(self):
        from franki.main import _maybe_auto_switch_skill
        cfg = _cfg(auto_skill=True)
        s = Session(skill="coding")
        with patch("franki.skills.detect_skill", return_value=None):
            _maybe_auto_switch_skill("ambiguous message", cfg, s, lambda c: None, lambda: None)
        assert s.skill == "coding"


# ── _run_auto_search ──────────────────────────────────────────────────────────

class TestRunAutoSearch:
    def test_successful_search_adds_to_session(self):
        from franki.main import _run_auto_search
        from franki.utils.search import SearchResult
        sr = SearchResult(query="nmap", answer="scanner", results=[])
        with patch("franki.utils.search.web_search", return_value=sr):
            s = Session()
            _run_auto_search(_cfg(), s, "nmap")
        assert len(s.history_display()) == 1

    def test_search_error_silently_ignored(self):
        from franki.main import _run_auto_search
        from franki.utils.search import SearchError
        with patch("franki.utils.search.web_search", side_effect=SearchError("no key")):
            s = Session()
            _run_auto_search(_cfg(), s, "query")
        # No exception, no message added
        assert len(s.history_display()) == 0
