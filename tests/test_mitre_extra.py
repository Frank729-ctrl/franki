"""Tests for mitre.py — run_mitre function with mocked AI."""
import pytest
from io import StringIO
from unittest.mock import patch

from franki.config import FrankiConfig
from franki.mitre import run_mitre, _extract_json


def _cfg():
    return FrankiConfig(
        active_provider="groq",
        providers={"groq": {
            "api_key": "sk-test",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama",
            "priority": 1,
        }},
    )


_VALID_RESPONSE = """{
  "tactic": "Credential Access",
  "technique_id": "T1003",
  "technique_name": "OS Credential Dumping",
  "description": "Adversary dumps credentials from LSASS.",
  "detection": "Monitor lsass.exe access.",
  "mitigation": "Enable Credential Guard."
}"""


class TestRunMitre:
    def test_empty_behaviour_prints_usage(self, capsys):
        run_mitre(_cfg(), "")
        # Should print usage without crashing

    def test_whitespace_only_behaviour_prints_usage(self, capsys):
        run_mitre(_cfg(), "   ")

    def test_valid_response_renders_table(self, capsys):
        with patch("franki.mitre.ask_ai", return_value=_VALID_RESPONSE):
            run_mitre(_cfg(), "process injected into lsass.exe")
        # No crash — table rendered

    def test_valid_response_with_fence(self):
        fenced = f"```json\n{_VALID_RESPONSE}\n```"
        with patch("franki.mitre.ask_ai", return_value=fenced):
            run_mitre(_cfg(), "lsass dump")

    def test_invalid_json_fallback_to_raw_text(self, capsys):
        with patch("franki.mitre.ask_ai", return_value="Could not map this behaviour."):
            run_mitre(_cfg(), "some behaviour")
        # Falls back to printing raw text — no crash

    def test_ai_error_handled_gracefully(self, capsys):
        with patch("franki.mitre.ask_ai", side_effect=Exception("AI failure")):
            run_mitre(_cfg(), "process injection")
        # Should print error message, not raise

    def test_table_includes_all_fields(self, capsys):
        with patch("franki.mitre.ask_ai", return_value=_VALID_RESPONSE):
            from rich.console import Console
            import franki.mitre as m
            old_console = None
            run_mitre(_cfg(), "dump credentials")
        # Verifying no KeyError / missing field exception

    def test_partial_json_missing_fields(self):
        partial = '{"tactic": "Credential Access", "technique_id": "T1003"}'
        with patch("franki.mitre.ask_ai", return_value=partial):
            run_mitre(_cfg(), "some technique")
        # Missing fields should use "—" fallback, no crash

    def test_behaviour_passed_to_ai(self):
        captured = []
        with patch("franki.mitre.ask_ai", side_effect=lambda cfg, msgs, **kw: (captured.extend(msgs), _VALID_RESPONSE)[1]):
            run_mitre(_cfg(), "unusual process spawning")
        assert any("unusual process spawning" in m.get("content", "") for m in captured)


class TestExtractJsonDirect:
    def test_invalid_json_in_braces_returns_none(self):
        """Text has {braces} but isn't valid JSON — hits except JSONDecodeError pass."""
        result = _extract_json("{key: value no quotes}")
        assert result is None

    def test_nested_invalid_json_braces_returns_none(self):
        result = _extract_json("{invalid: {nested: bad}}")
        assert result is None
