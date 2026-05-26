"""Tests for setup_wizard.py helper functions and wizard flow."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

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
    }
    base.update(kwargs)
    return FrankiConfig(**base)


# ── _validate_key ─────────────────────────────────────────────────────────────

class TestValidateKey:
    def test_success_returns_true(self):
        from franki.setup_wizard import _validate_key
        with patch("franki.providers.generic.chat_once", new_callable=AsyncMock, return_value="reply"):
            ok, err = asyncio.run(_validate_key("sk-test", "https://api.groq.com/v1", "llama"))
        assert ok is True
        assert err == ""

    def test_provider_error_returns_false(self):
        from franki.setup_wizard import _validate_key
        from franki.providers.generic import ProviderError
        with patch(
            "franki.providers.generic.chat_once",
            new_callable=AsyncMock,
            side_effect=ProviderError("401 unauthorized"),
        ):
            ok, err = asyncio.run(_validate_key("bad", "url", "model"))
        assert ok is False
        assert "401" in err

    def test_rate_limit_error_returns_false(self):
        from franki.setup_wizard import _validate_key
        from franki.providers.generic import ProviderRateLimitError
        with patch(
            "franki.providers.generic.chat_once",
            new_callable=AsyncMock,
            side_effect=ProviderRateLimitError("rate limit"),
        ):
            ok, err = asyncio.run(_validate_key("key", "url", "model"))
        assert ok is False

    def test_generic_exception_returns_false(self):
        from franki.setup_wizard import _validate_key
        with patch(
            "franki.providers.generic.chat_once",
            new_callable=AsyncMock,
            side_effect=Exception("network error"),
        ):
            ok, err = asyncio.run(_validate_key("key", "url", "model"))
        assert ok is False
        assert "network" in err


# ── _ask ──────────────────────────────────────────────────────────────────────

class TestWizardAsk:
    def test_returns_input(self):
        from franki.setup_wizard import _ask
        with patch("builtins.input", return_value="myvalue"):
            assert _ask("Enter something") == "myvalue"

    def test_empty_returns_default(self):
        from franki.setup_wizard import _ask
        with patch("builtins.input", return_value=""):
            assert _ask("Prompt", default="mydefault") == "mydefault"

    def test_eof_raises(self):
        from franki.setup_wizard import _ask
        with patch("builtins.input", side_effect=EOFError):
            with pytest.raises(EOFError):
                _ask("Prompt", "default")

    def test_keyboard_interrupt_raises(self):
        from franki.setup_wizard import _ask
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                _ask("Prompt")

    def test_no_default_no_suffix(self):
        from franki.setup_wizard import _ask
        with patch("builtins.input", return_value="val"):
            assert _ask("No default prompt") == "val"


# ── _ask_key ──────────────────────────────────────────────────────────────────

class TestWizardAskKey:
    def test_returns_key(self):
        from franki.setup_wizard import _ask_key
        with patch("getpass.getpass", return_value="sk-secret"):
            assert _ask_key("API key") == "sk-secret"

    def test_eof_raises(self):
        from franki.setup_wizard import _ask_key
        with patch("getpass.getpass", side_effect=EOFError):
            with pytest.raises(EOFError):
                _ask_key("API key")

    def test_keyboard_interrupt_raises(self):
        from franki.setup_wizard import _ask_key
        with patch("getpass.getpass", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                _ask_key("API key")


# ── _yn ───────────────────────────────────────────────────────────────────────

class TestWizardYn:
    def test_y_returns_true(self):
        from franki.setup_wizard import _yn
        with patch("builtins.input", return_value="y"):
            assert _yn("Enable?") is True

    def test_n_returns_false(self):
        from franki.setup_wizard import _yn
        with patch("builtins.input", return_value="n"):
            assert _yn("Enable?") is False

    def test_empty_returns_default_false(self):
        from franki.setup_wizard import _yn
        with patch("builtins.input", return_value=""):
            assert _yn("Enable?", default=False) is False

    def test_empty_returns_default_true(self):
        from franki.setup_wizard import _yn
        with patch("builtins.input", return_value=""):
            assert _yn("Enable?", default=True) is True

    def test_eof_returns_default(self):
        from franki.setup_wizard import _yn
        with patch("builtins.input", side_effect=EOFError):
            assert _yn("Enable?", default=True) is True

    def test_keyboard_interrupt_returns_default(self):
        from franki.setup_wizard import _yn
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            assert _yn("Enable?", default=False) is False

    def test_yes_word_returns_true(self):
        from franki.setup_wizard import _yn
        with patch("builtins.input", return_value="yes"):
            assert _yn("Enable?") is True


# ── _add_provider ─────────────────────────────────────────────────────────────

def _make_counter(responses):
    """Return a fake_input that yields responses then "" forever."""
    call_count = [0]

    def fake_input(p=""):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(responses):
            return responses[idx]
        return ""

    return fake_input


class TestAddProvider:
    def test_eof_on_choice_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        with patch("builtins.input", side_effect=EOFError):
            assert _add_provider(cfg, is_first=True) is False

    def test_keyboard_interrupt_on_choice_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            assert _add_provider(cfg, is_first=True) is False

    def test_invalid_high_index_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        with patch("builtins.input", side_effect=_make_counter(["99"])):
            assert _add_provider(cfg, is_first=True) is False

    def test_non_digit_choice_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        with patch("builtins.input", side_effect=_make_counter(["abc"])):
            assert _add_provider(cfg, is_first=True) is False

    def test_zero_index_out_of_range_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        with patch("builtins.input", side_effect=_make_counter(["0"])):
            assert _add_provider(cfg, is_first=True) is False

    def test_key_required_empty_key_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        # groq is choice 1 — key_required=True
        with patch("builtins.input", side_effect=_make_counter(["1"])):
            with patch("getpass.getpass", return_value=""):
                assert _add_provider(cfg, is_first=True) is False

    def test_eof_on_api_key_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        with patch("builtins.input", side_effect=_make_counter(["1"])):
            with patch("getpass.getpass", side_effect=EOFError):
                assert _add_provider(cfg, is_first=True) is False

    def test_validation_passes_adds_provider(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        # choice=1 (groq), then model name
        with patch("builtins.input", side_effect=_make_counter(["1", "llama"])):
            with patch("getpass.getpass", return_value="sk-key"):
                with patch(
                    "franki.setup_wizard._validate_key",
                    new_callable=AsyncMock,
                    return_value=(True, ""),
                ):
                    result = _add_provider(cfg, is_first=True)
        assert result is True
        assert "groq" in cfg.providers

    def test_validation_fails_user_adds_anyway(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        # choice, model, add-anyway?=y
        with patch("builtins.input", side_effect=_make_counter(["1", "llama", "y"])):
            with patch("getpass.getpass", return_value="sk-key"):
                with patch(
                    "franki.setup_wizard._validate_key",
                    new_callable=AsyncMock,
                    return_value=(False, "auth error"),
                ):
                    result = _add_provider(cfg, is_first=True)
        assert result is True
        assert "groq" in cfg.providers

    def test_validation_fails_user_skips(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        # choice, model, add-anyway?=n
        with patch("builtins.input", side_effect=_make_counter(["1", "llama", "n"])):
            with patch("getpass.getpass", return_value="sk-key"):
                with patch(
                    "franki.setup_wizard._validate_key",
                    new_callable=AsyncMock,
                    return_value=(False, "auth error"),
                ):
                    result = _add_provider(cfg, is_first=True)
        assert result is False
        assert "groq" not in cfg.providers

    def test_eof_on_model_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        call_count = [0]

        def fake_input(p=""):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return "1"  # groq
            raise EOFError  # model input

        with patch("builtins.input", side_effect=fake_input):
            with patch("getpass.getpass", return_value="sk-key"):
                result = _add_provider(cfg, is_first=True)
        assert result is False

    def test_custom_provider_adds_successfully(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        # choice=8 (custom), name, base_url, model
        with patch(
            "builtins.input",
            side_effect=_make_counter(["8", "myprovider", "https://api.example.com/v1", "mymodel"]),
        ):
            with patch("getpass.getpass", return_value="sk-custom"):
                with patch(
                    "franki.setup_wizard._validate_key",
                    new_callable=AsyncMock,
                    return_value=(True, ""),
                ):
                    result = _add_provider(cfg, is_first=True)
        assert result is True
        assert "myprovider" in cfg.providers

    def test_custom_provider_empty_name_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        with patch("builtins.input", side_effect=_make_counter(["8", ""])):
            result = _add_provider(cfg, is_first=True)
        assert result is False

    def test_custom_provider_empty_url_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        with patch("builtins.input", side_effect=_make_counter(["8", "myname", ""])):
            result = _add_provider(cfg, is_first=True)
        assert result is False

    def test_custom_provider_eof_on_name_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        call_count = [0]

        def fake_input(p=""):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return "8"  # custom
            raise EOFError  # name prompt

        with patch("builtins.input", side_effect=fake_input):
            result = _add_provider(cfg, is_first=True)
        assert result is False

    def test_empty_model_custom_returns_false(self):
        from franki.setup_wizard import _add_provider
        cfg = FrankiConfig()
        # custom: name ok, url ok, key ok, model="" → return False
        with patch(
            "builtins.input",
            side_effect=_make_counter(["8", "myprovider", "https://api.example.com/v1", ""]),
        ):
            with patch("getpass.getpass", return_value="sk-custom"):
                result = _add_provider(cfg, is_first=True)
        assert result is False

    def test_ollama_no_key_required(self):
        from franki.setup_wizard import _add_provider, _PRESET_DISPLAY
        ollama_idx = next(
            i + 1 for i, (k, _) in enumerate(_PRESET_DISPLAY) if k == "ollama"
        )
        cfg = FrankiConfig()
        with patch("builtins.input", side_effect=_make_counter([str(ollama_idx), "llama2"])):
            with patch(
                "franki.setup_wizard._validate_key",
                new_callable=AsyncMock,
                return_value=(True, ""),
            ):
                result = _add_provider(cfg, is_first=True)
        assert result is True
        assert "ollama" in cfg.providers

    def test_second_provider_priority_incremented(self):
        from franki.setup_wizard import _add_provider
        cfg = _cfg()  # already has groq at priority 1
        with patch("builtins.input", side_effect=_make_counter(["1", "llama2"])):
            with patch("getpass.getpass", return_value="sk-key2"):
                with patch(
                    "franki.setup_wizard._validate_key",
                    new_callable=AsyncMock,
                    return_value=(True, ""),
                ):
                    _add_provider(cfg, is_first=False)
        # New groq overwrites, priority should be max(1) + 1 = 2
        assert cfg.providers["groq"]["priority"] == 2


# ── run_wizard ────────────────────────────────────────────────────────────────

def _fake_add_success(name="groq"):
    """Return a side_effect function that adds one provider and returns True."""
    called = [False]

    def side_effect(cfg, is_first):
        if not called[0]:
            called[0] = True
            cfg.providers[name] = {
                "api_key": "sk",
                "base_url": "x",
                "model": "m",
                "priority": 1,
                "key_required": True,
            }
            return True
        raise KeyboardInterrupt  # cancel if called again unexpectedly

    return side_effect


class TestRunWizard:
    def test_ki_in_add_provider_saves_empty_cfg(self):
        from franki.setup_wizard import run_wizard
        # _add_provider raises KI → wizard breaks → no providers
        with patch("franki.setup_wizard._add_provider", side_effect=KeyboardInterrupt):
            with patch("franki.setup_wizard.save_config") as mock_save:
                cfg = run_wizard()
        assert mock_save.called
        assert not cfg.providers

    def test_eof_in_add_provider_saves_empty_cfg(self):
        from franki.setup_wizard import run_wizard
        with patch("franki.setup_wizard._add_provider", side_effect=EOFError):
            with patch("franki.setup_wizard.save_config") as mock_save:
                cfg = run_wizard()
        assert mock_save.called
        assert not cfg.providers

    def test_failed_add_then_cancelled(self):
        from franki.setup_wizard import run_wizard
        # First call returns False (user skipped key), second call raises KI
        call_count = [0]

        def fake_add(cfg, is_first):
            call_count[0] += 1
            if call_count[0] == 1:
                return False
            raise KeyboardInterrupt

        with patch("franki.setup_wizard._add_provider", side_effect=fake_add):
            with patch("franki.setup_wizard.save_config"):
                cfg = run_wizard()
        assert not cfg.providers
        assert call_count[0] == 2

    def test_one_provider_added_sets_active(self):
        from franki.setup_wizard import run_wizard
        # add_provider adds groq, user says no-more, auto-skill yes, export default
        # _yn("Add another?")="n", _yn("auto-skill")="y", _ask("export")=""
        with patch("franki.setup_wizard._add_provider", side_effect=_fake_add_success("groq")):
            with patch("builtins.input", side_effect=_make_counter(["n", "y", ""])):
                with patch("franki.setup_wizard.save_config") as mock_save:
                    with patch("pathlib.Path.mkdir"):
                        cfg = run_wizard()
        assert mock_save.called
        assert "groq" in cfg.providers
        assert cfg.active_provider == "groq"

    def test_existing_cfg_shows_add_panel(self):
        from franki.setup_wizard import run_wizard
        existing = _cfg()
        # Cancel immediately after showing the "add providers" panel
        # Still need inputs for auto-skill and export path
        with patch("franki.setup_wizard._add_provider", side_effect=KeyboardInterrupt):
            with patch("builtins.input", side_effect=_make_counter(["y", ""])):
                with patch("franki.setup_wizard.save_config"):
                    with patch("pathlib.Path.mkdir"):
                        cfg = run_wizard(existing_cfg=existing)
        assert "groq" in cfg.providers  # existing provider preserved

    def test_existing_cfg_with_providers_shows_different_panel(self):
        from franki.setup_wizard import run_wizard
        existing = _cfg()
        # add a second provider successfully
        add_count = [0]

        def fake_add(cfg, is_first):
            add_count[0] += 1
            if add_count[0] == 1:
                cfg.providers["gemini"] = {
                    "api_key": "sk",
                    "base_url": "x",
                    "model": "m",
                    "priority": 2,
                    "key_required": True,
                }
                return True
            raise KeyboardInterrupt

        # After adding gemini: add-another?="n", then default choice="1",
        # auto-skill="y", export=""
        with patch("franki.setup_wizard._add_provider", side_effect=fake_add):
            with patch("builtins.input", side_effect=_make_counter(["n", "1", "y", ""])):
                with patch("franki.setup_wizard.save_config"):
                    with patch("pathlib.Path.mkdir"):
                        cfg = run_wizard(existing_cfg=existing)
        assert "gemini" in cfg.providers

    def test_two_providers_choose_second_as_default(self):
        from franki.setup_wizard import run_wizard
        add_count = [0]

        def fake_add(cfg, is_first):
            name = "groq" if add_count[0] == 0 else "gemini"
            add_count[0] += 1
            cfg.providers[name] = {
                "api_key": "sk",
                "base_url": "x",
                "model": "m",
                "priority": add_count[0],
                "key_required": True,
            }
            return True

        # After groq: add-another?="y"
        # After gemini: add-another?="n"
        # Default choice="2" (gemini)
        # auto-skill="y", export=""
        with patch("franki.setup_wizard._add_provider", side_effect=fake_add):
            with patch("builtins.input", side_effect=_make_counter(["y", "n", "2", "y", ""])):
                with patch("franki.setup_wizard.save_config"):
                    with patch("pathlib.Path.mkdir"):
                        cfg = run_wizard()

        assert len(cfg.providers) == 2
        assert cfg.active_provider == "gemini"

    def test_default_provider_eof_uses_first(self):
        from franki.setup_wizard import run_wizard
        add_count = [0]

        def fake_add(cfg, is_first):
            name = "groq" if add_count[0] == 0 else "gemini"
            add_count[0] += 1
            cfg.providers[name] = {
                "api_key": "sk",
                "base_url": "x",
                "model": "m",
                "priority": add_count[0],
                "key_required": True,
            }
            return True

        # After groq: add-another?="y" → continue
        # After gemini: add-another? raises EOFError → _yn returns False → break
        # Default choice: raises EOFError → caught → uses first provider
        call_count = [0]

        def fake_input(p=""):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return "y"
            raise EOFError

        with patch("franki.setup_wizard._add_provider", side_effect=fake_add):
            with patch("builtins.input", side_effect=fake_input):
                with patch("franki.setup_wizard.save_config"):
                    with patch("pathlib.Path.mkdir"):
                        cfg = run_wizard()

        assert cfg.active_provider == "groq"

    def test_invalid_default_index_uses_first(self):
        from franki.setup_wizard import run_wizard
        add_count = [0]

        def fake_add(cfg, is_first):
            name = "groq" if add_count[0] == 0 else "gemini"
            add_count[0] += 1
            cfg.providers[name] = {
                "api_key": "sk",
                "base_url": "x",
                "model": "m",
                "priority": add_count[0],
                "key_required": True,
            }
            return True

        # add-another?="y", then "n", then default="99" (out of range), auto-skill="n", export=""
        with patch("franki.setup_wizard._add_provider", side_effect=fake_add):
            with patch("builtins.input", side_effect=_make_counter(["y", "n", "99", "n", ""])):
                with patch("franki.setup_wizard.save_config"):
                    with patch("pathlib.Path.mkdir"):
                        cfg = run_wizard()

        assert cfg.active_provider == "groq"

    def test_auto_skill_eof_defaults_true(self):
        from franki.setup_wizard import run_wizard
        with patch("franki.setup_wizard._add_provider", side_effect=_fake_add_success("groq")):
            # add-another?="n", then auto-skill raises EOFError → default=True
            call_count = [0]

            def fake_input(p=""):
                idx = call_count[0]
                call_count[0] += 1
                if idx == 0:
                    return "n"  # add-another?
                raise EOFError  # auto-skill and export

            with patch("builtins.input", side_effect=fake_input):
                with patch("franki.setup_wizard.save_config"):
                    with patch("pathlib.Path.mkdir"):
                        cfg = run_wizard()

        assert cfg.auto_skill is True

    def test_export_path_eof_uses_default(self):
        from franki.setup_wizard import run_wizard
        with patch("franki.setup_wizard._add_provider", side_effect=_fake_add_success("groq")):
            # add-another?="n", auto-skill="n", export raises EOFError → default path
            call_count = [0]

            def fake_input(p=""):
                idx = call_count[0]
                call_count[0] += 1
                if idx == 0:
                    return "n"  # add-another?
                if idx == 1:
                    return "n"  # auto-skill
                raise EOFError  # export path

            with patch("builtins.input", side_effect=fake_input):
                with patch("franki.setup_wizard.save_config"):
                    with patch("pathlib.Path.mkdir"):
                        cfg = run_wizard()

        assert "franki" in cfg.export_path or "Documents" in cfg.export_path

    def test_non_digit_default_uses_first(self):
        from franki.setup_wizard import run_wizard
        add_count = [0]

        def fake_add(cfg, is_first):
            name = "groq" if add_count[0] == 0 else "gemini"
            add_count[0] += 1
            cfg.providers[name] = {
                "api_key": "sk",
                "base_url": "x",
                "model": "m",
                "priority": add_count[0],
                "key_required": True,
            }
            return True

        # add-another?="y", "n", default="notadigit", auto-skill="y", export=""
        with patch("franki.setup_wizard._add_provider", side_effect=fake_add):
            with patch("builtins.input", side_effect=_make_counter(["y", "n", "notadigit", "y", ""])):
                with patch("franki.setup_wizard.save_config"):
                    with patch("pathlib.Path.mkdir"):
                        cfg = run_wizard()

        assert cfg.active_provider == "groq"  # non-digit → first provider
