"""Tests for mitre.py — JSON extraction logic (no AI calls)."""
import json
import pytest
from franki.mitre import _extract_json


class TestExtractJson:
    def _valid(self):
        return {
            "tactic": "Credential Access",
            "technique_id": "T1003",
            "technique_name": "OS Credential Dumping",
            "description": "Adversary dumps credentials from LSASS.",
            "detection": "Monitor lsass.exe access.",
            "mitigation": "Enable Credential Guard.",
        }

    def test_plain_json(self):
        raw = json.dumps(self._valid())
        result = _extract_json(raw)
        assert result is not None
        assert result["technique_id"] == "T1003"

    def test_json_with_markdown_fence(self):
        raw = "```json\n" + json.dumps(self._valid()) + "\n```"
        result = _extract_json(raw)
        assert result is not None
        assert result["tactic"] == "Credential Access"

    def test_json_with_plain_fence(self):
        raw = "```\n" + json.dumps(self._valid()) + "\n```"
        result = _extract_json(raw)
        assert result is not None

    def test_json_embedded_in_text(self):
        inner = json.dumps(self._valid())
        raw = f"Here is the result:\n{inner}\nDone."
        result = _extract_json(raw)
        assert result is not None
        assert result["technique_id"] == "T1003"

    def test_invalid_json_returns_none(self):
        assert _extract_json("not json at all") is None

    def test_empty_string_returns_none(self):
        assert _extract_json("") is None

    def test_partial_json_returns_none(self):
        assert _extract_json('{"tactic": "x"') is None

    def test_nested_object_extracted(self):
        # The regex extracts the outermost { } pair
        outer = {"outer": "val", "inner": {"a": 1}}
        result = _extract_json(json.dumps(outer))
        assert result is not None
        assert result["outer"] == "val"
