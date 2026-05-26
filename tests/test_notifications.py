"""Tests for franki/notifications.py."""
import sys
from io import StringIO
from unittest.mock import patch, MagicMock, call

import pytest
from rich.console import Console


def _console() -> Console:
    return Console(file=StringIO(), highlight=False, width=80)


# ── notify_done ───────────────────────────────────────────────────────────────

class TestNotifyDone:
    def test_calls_bell(self):
        from franki.notifications import notify_done
        with patch("franki.notifications._bell") as mock_bell, \
             patch("franki.notifications._desktop"), \
             patch("franki.notifications._sound"):
            notify_done(_console())
        mock_bell.assert_called_once()

    def test_calls_desktop(self):
        from franki.notifications import notify_done
        with patch("franki.notifications._bell"), \
             patch("franki.notifications._desktop") as mock_desk, \
             patch("franki.notifications._sound"):
            notify_done(_console(), steps=3, skill="pentest")
        assert mock_desk.called
        title_arg = mock_desk.call_args[0][0]
        assert "pentest" in title_arg

    def test_calls_sound(self):
        from franki.notifications import notify_done
        with patch("franki.notifications._bell"), \
             patch("franki.notifications._desktop"), \
             patch("franki.notifications._sound") as mock_sound:
            notify_done(_console())
        mock_sound.assert_called_once()

    def test_no_skill_title_has_no_bracket(self):
        from franki.notifications import notify_done
        captured_title = []
        def _capture(title, body):
            captured_title.append(title)
        with patch("franki.notifications._bell"), \
             patch("franki.notifications._desktop", side_effect=_capture), \
             patch("franki.notifications._sound"):
            notify_done(_console())
        assert "[" not in captured_title[0]

    def test_body_includes_steps_and_files(self):
        from franki.notifications import notify_done
        captured_body = []
        def _capture(title, body):
            captured_body.append(body)
        with patch("franki.notifications._bell"), \
             patch("franki.notifications._desktop", side_effect=_capture), \
             patch("franki.notifications._sound"):
            notify_done(_console(), steps=4, files_written=2, elapsed_s=7.3)
        body = captured_body[0]
        assert "4" in body
        assert "2" in body

    def test_empty_body_falls_back_to_task_complete(self):
        from franki.notifications import notify_done
        captured_body = []
        def _capture(title, body):
            captured_body.append(body)
        with patch("franki.notifications._bell"), \
             patch("franki.notifications._desktop", side_effect=_capture), \
             patch("franki.notifications._sound"):
            notify_done(_console())
        assert captured_body[0] == "Task complete"


# ── _bell ─────────────────────────────────────────────────────────────────────

class TestBell:
    def test_writes_bell_char(self):
        from franki.notifications import _bell
        with patch("franki.notifications.sys.stdout") as mock_stdout:
            _bell()
        mock_stdout.write.assert_called_once_with("\a")
        mock_stdout.flush.assert_called_once()


# ── _banner ───────────────────────────────────────────────────────────────────

class TestBanner:
    def test_prints_without_crashing(self):
        from franki.notifications import _banner
        c = _console()
        _banner(c, steps=2, files_written=1, elapsed_s=5.0)
        output = c.file.getvalue()
        assert "done" in output

    def test_steps_shown(self):
        from franki.notifications import _banner
        c = _console()
        _banner(c, steps=3, files_written=0, elapsed_s=0.0)
        assert "3" in c.file.getvalue()

    def test_files_written_shown(self):
        from franki.notifications import _banner
        c = _console()
        _banner(c, steps=0, files_written=5, elapsed_s=0.0)
        assert "5" in c.file.getvalue()

    def test_elapsed_shown_when_above_1s(self):
        from franki.notifications import _banner
        c = _console()
        _banner(c, steps=0, files_written=0, elapsed_s=2.5)
        assert "2.5" in c.file.getvalue()

    def test_elapsed_hidden_when_below_1s(self):
        from franki.notifications import _banner
        c = _console()
        _banner(c, steps=0, files_written=0, elapsed_s=0.4)
        assert "0.4" not in c.file.getvalue()


# ── _desktop ──────────────────────────────────────────────────────────────────

class TestDesktop:
    def test_linux_calls_notify_send(self):
        from franki.notifications import _desktop
        with patch("franki.notifications.sys") as mock_sys, \
             patch("franki.notifications.subprocess.Popen") as mock_popen:
            mock_sys.platform = "linux"
            _desktop("Title", "Body")
        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "notify-send"
        assert "Title" in cmd
        assert "Body" in cmd

    def test_macos_calls_osascript(self):
        from franki.notifications import _desktop
        with patch("franki.notifications.sys") as mock_sys, \
             patch("franki.notifications.subprocess.Popen") as mock_popen:
            mock_sys.platform = "darwin"
            _desktop("Title", "Body")
        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "osascript"

    def test_popen_error_does_not_raise(self):
        from franki.notifications import _desktop
        with patch("franki.notifications.sys") as mock_sys, \
             patch("franki.notifications.subprocess.Popen", side_effect=FileNotFoundError):
            mock_sys.platform = "linux"
            _desktop("T", "B")  # must not raise

    def test_unknown_platform_does_nothing(self):
        from franki.notifications import _desktop
        with patch("franki.notifications.sys") as mock_sys, \
             patch("franki.notifications.subprocess.Popen") as mock_popen:
            mock_sys.platform = "win32"
            _desktop("T", "B")
        assert not mock_popen.called


# ── _sound helpers ────────────────────────────────────────────────────────────

class TestSoundHelpers:
    def test_try_canberra_returns_true_on_success(self):
        from franki.notifications import _try_canberra
        with patch("franki.notifications.subprocess.Popen"):
            assert _try_canberra() is True

    def test_try_canberra_returns_false_on_file_not_found(self):
        from franki.notifications import _try_canberra
        with patch("franki.notifications.subprocess.Popen", side_effect=FileNotFoundError):
            assert _try_canberra() is False

    def test_try_ffplay_returns_true_on_success(self):
        from franki.notifications import _try_ffplay
        with patch("franki.notifications.subprocess.Popen"):
            assert _try_ffplay("/some/sound.oga") is True

    def test_try_ffplay_returns_false_on_file_not_found(self):
        from franki.notifications import _try_ffplay
        with patch("franki.notifications.subprocess.Popen", side_effect=FileNotFoundError):
            assert _try_ffplay("/some/sound.oga") is False

    def test_try_aplay_returns_true_on_success(self):
        from franki.notifications import _try_aplay
        with patch("franki.notifications.subprocess.Popen"):
            assert _try_aplay("/some/sound.wav") is True

    def test_try_aplay_returns_false_on_error(self):
        from franki.notifications import _try_aplay
        with patch("franki.notifications.subprocess.Popen", side_effect=Exception("no aplay")):
            assert _try_aplay("/some/sound.wav") is False


class TestSoundDispatch:
    def test_canberra_used_first_when_available(self):
        from franki.notifications import _sound
        with patch("franki.notifications._try_canberra", return_value=True) as mock_can, \
             patch("franki.notifications._try_ffplay") as mock_ff, \
             patch("franki.notifications._try_aplay") as mock_ap:
            _sound()
        mock_can.assert_called_once()
        mock_ff.assert_not_called()
        mock_ap.assert_not_called()

    def test_falls_back_to_ffplay_when_canberra_missing(self):
        from franki.notifications import _sound
        with patch("franki.notifications._try_canberra", return_value=False), \
             patch("franki.notifications.Path") as mock_path, \
             patch("franki.notifications._try_ffplay", return_value=True) as mock_ff, \
             patch("franki.notifications._try_aplay") as mock_ap:
            mock_path.return_value.is_file.return_value = True
            _sound()
        assert mock_ff.called
        mock_ap.assert_not_called()

    def test_falls_back_to_aplay_when_no_oga_files(self):
        from franki.notifications import _sound
        with patch("franki.notifications._try_canberra", return_value=False), \
             patch("franki.notifications.Path") as mock_path, \
             patch("franki.notifications._try_ffplay") as mock_ff, \
             patch("franki.notifications._try_aplay", return_value=True) as mock_ap:
            # First call group (OGA) → file not found; second group (WAV) → exists
            mock_path.return_value.is_file.side_effect = (
                [False, False, False]  # all OGA files absent
                + [True]               # first WAV file present
            )
            _sound()
        mock_ff.assert_not_called()
        assert mock_ap.called


# ── Integration: agent loop fires notify_done ─────────────────────────────────

class TestAgentLoopNotification:
    """Verify run_agent calls notify_done when auto_accept=True and tools ran."""

    def _make_cfg(self):
        from franki.config import FrankiConfig
        return FrankiConfig(
            active_provider="groq",
            providers={"groq": {
                "api_key": "sk-test",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama",
                "priority": 1,
            }},
            auto_accept=True,
            notify_on_done=True,
        )

    def test_notify_fires_after_tool_use(self):
        import asyncio
        from franki.agent.loop import run_agent
        from franki.session import Session

        cfg = self._make_cfg()
        session = Session(skill="coding")
        console = _console()

        tool_response = {
            "content": "",
            "tool_calls": [{
                "id": "c1",
                "function": {"name": "read_file", "arguments": '{"path": "/tmp/x"}'},
            }],
        }
        final_response = {"content": "All done.", "tool_calls": []}

        call_count = 0

        async def _fake(cfg, msgs, skill, tracker=None, console=None, cost_tracker=None):
            nonlocal call_count
            call_count += 1
            return tool_response if call_count == 1 else final_response

        with patch("franki.agent.loop._call_with_tools", side_effect=_fake):
            with patch("franki.agent.tools.execute_tool", return_value="file contents"):
                with patch("franki.notifications.notify_done") as mock_notify:
                    asyncio.run(run_agent(cfg, session, console, "read something"))

        assert mock_notify.called
        kwargs = mock_notify.call_args[1]
        assert kwargs["steps"] >= 1

    def test_no_notify_when_auto_accept_off(self):
        import asyncio
        from franki.agent.loop import run_agent
        from franki.session import Session

        cfg = self._make_cfg()
        cfg.auto_accept = False
        session = Session(skill="coding")
        console = _console()

        final_response = {"content": "Done.", "tool_calls": []}

        async def _fake(cfg, msgs, skill, tracker=None, console=None, cost_tracker=None):
            return final_response

        with patch("franki.agent.loop._call_with_tools", side_effect=_fake):
            with patch("franki.notifications.notify_done") as mock_notify:
                asyncio.run(run_agent(cfg, session, console, "hello"))

        mock_notify.assert_not_called()

    def test_no_notify_when_notify_on_done_off(self):
        import asyncio
        from franki.agent.loop import run_agent
        from franki.session import Session

        cfg = self._make_cfg()
        cfg.notify_on_done = False
        session = Session(skill="coding")
        console = _console()

        tool_response = {
            "content": "",
            "tool_calls": [{
                "id": "c1",
                "function": {"name": "read_file", "arguments": '{"path": "/tmp/x"}'},
            }],
        }
        final_response = {"content": "Done.", "tool_calls": []}

        call_count = 0

        async def _fake(cfg, msgs, skill, tracker=None, console=None, cost_tracker=None):
            nonlocal call_count
            call_count += 1
            return tool_response if call_count == 1 else final_response

        with patch("franki.agent.loop._call_with_tools", side_effect=_fake):
            with patch("franki.agent.tools.execute_tool", return_value="contents"):
                with patch("franki.notifications.notify_done") as mock_notify:
                    asyncio.run(run_agent(cfg, session, console, "read x"))

        mock_notify.assert_not_called()
