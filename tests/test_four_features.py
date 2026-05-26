"""Tests for @url, @dir, /test, and custom tools."""
import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from rich.console import Console

from franki.config import FrankiConfig
from franki.session import Session


def _console() -> Console:
    return Console(file=StringIO(), highlight=False, width=80)


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


# ── @url injection ────────────────────────────────────────────────────────────

class TestUrlInjection:
    def test_url_token_fetches_and_injects(self):
        from franki.utils.files import resolve_content
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><p>Hello from the web</p></body></html>"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_resp):
            result, errors = resolve_content("check this @https://example.com please")
        assert errors == []
        assert isinstance(result, str)
        assert "https://example.com" in result
        assert "Hello from the web" in result

    def test_url_strips_html_tags(self):
        from franki.utils.files import resolve_content
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><head><title>Ignore</title></head><body><h1>Keep</h1><p>This too</p></body></html>"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_resp):
            result, errors = resolve_content("@https://example.com")
        assert "<html>" not in result
        assert "Keep" in result
        assert "This too" in result

    def test_url_strips_script_and_style(self):
        from franki.utils.files import _strip_html
        html = "<html><script>alert('x')</script><style>.a{}</style><p>Content</p></html>"
        text = _strip_html(html)
        assert "alert" not in text
        assert ".a{}" not in text
        assert "Content" in text

    def test_url_fetch_error_returns_error(self):
        from franki.utils.files import resolve_content
        with patch("httpx.get", side_effect=Exception("connection refused")):
            result, errors = resolve_content("see @https://fail.example.com")
        assert len(errors) == 1
        assert "fail.example.com" in errors[0]

    def test_url_truncated_when_too_long(self):
        from franki.utils.files import _fetch_url, _URL_MAX_CHARS
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "x" * (_URL_MAX_CHARS + 5000)
        mock_resp.headers = {"content-type": "text/plain"}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_resp):
            block, err = _fetch_url("https://big.example.com")
        assert err == ""
        assert "truncated" in block

    def test_plain_text_url_no_html_strip(self):
        from franki.utils.files import resolve_content
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "raw text content\nline two"
        mock_resp.headers = {"content-type": "text/plain"}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_resp):
            result, errors = resolve_content("@https://raw.example.com/data.txt")
        assert "raw text content" in result

    def test_non_url_unchanged(self, tmp_path):
        from franki.utils.files import resolve_content
        f = tmp_path / "test.py"
        f.write_text("print('hi')")
        result, errors = resolve_content(f"@{f}")
        assert errors == []
        assert "print" in result


# ── @dir injection ────────────────────────────────────────────────────────────

class TestDirInjection:
    def test_injects_directory_tree(self, tmp_path):
        from franki.utils.files import resolve_content
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def add(a,b): return a+b")
        result, errors = resolve_content(f"@{tmp_path}/")
        assert errors == []
        assert "main.py" in result
        assert "utils.py" in result

    def test_injects_file_contents(self, tmp_path):
        from franki.utils.files import resolve_content
        f = tmp_path / "app.py"
        f.write_text("# my app\napp = Flask(__name__)")
        result, errors = resolve_content(f"@{tmp_path}")
        assert "app = Flask" in result

    def test_skips_pycache(self, tmp_path):
        from franki.utils.files import resolve_content
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "mod.pyc").write_bytes(b"\x00")
        (tmp_path / "real.py").write_text("# real")
        result, errors = resolve_content(f"@{tmp_path}")
        assert "__pycache__" not in result
        assert "real.py" in result

    def test_skips_node_modules(self, tmp_path):
        from franki.utils.files import resolve_content
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "pkg.js").write_text("module.exports = {}")
        (tmp_path / "index.js").write_text("const x = 1")
        result, errors = resolve_content(f"@{tmp_path}")
        assert "pkg.js" not in result
        assert "index.js" in result

    def test_large_file_truncated(self, tmp_path):
        from franki.utils.files import resolve_content, _DIR_FILE_MAXSIZE
        big = tmp_path / "big.py"
        big.write_text("x = 1\n" * (_DIR_FILE_MAXSIZE + 500))
        result, errors = resolve_content(f"@{tmp_path}")
        assert "truncated" in result


# ── test runner ───────────────────────────────────────────────────────────────

class TestDetectTestCmd:
    def test_detects_pytest_from_pyproject(self, tmp_path):
        from franki.utils.test_runner import detect_test_cmd
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        cmd = detect_test_cmd(tmp_path)
        assert cmd is not None
        assert "pytest" in cmd

    def test_detects_pytest_from_pytest_ini(self, tmp_path):
        from franki.utils.test_runner import detect_test_cmd
        (tmp_path / "pytest.ini").write_text("[pytest]\n")
        cmd = detect_test_cmd(tmp_path)
        assert "pytest" in cmd

    def test_detects_npm_test(self, tmp_path):
        from franki.utils.test_runner import detect_test_cmd
        (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
        cmd = detect_test_cmd(tmp_path)
        assert cmd == "npm test"

    def test_detects_cargo(self, tmp_path):
        from franki.utils.test_runner import detect_test_cmd
        (tmp_path / "Cargo.toml").write_text("[package]\nname = \"myapp\"\n")
        cmd = detect_test_cmd(tmp_path)
        assert cmd == "cargo test"

    def test_returns_none_when_no_runner(self, tmp_path):
        from franki.utils.test_runner import detect_test_cmd
        assert detect_test_cmd(tmp_path) is None


class TestRunTests:
    def test_returns_output_and_rc_zero(self):
        from franki.utils.test_runner import run_tests
        output, rc = run_tests("echo 'all good'")
        assert rc == 0
        assert "all good" in output

    def test_returns_nonzero_rc_on_failure(self):
        from franki.utils.test_runner import run_tests
        output, rc = run_tests("exit 1")
        assert rc != 0

    def test_truncates_long_output(self):
        from franki.utils.test_runner import run_tests, _MAX_OUTPUT_LINES
        cmd = f"python3 -c \"[print('line') for _ in range({_MAX_OUTPUT_LINES + 50})]\""
        output, rc = run_tests(cmd)
        lines = output.splitlines()
        assert len(lines) <= _MAX_OUTPUT_LINES + 5  # +5 for the truncation message

    def test_timeout_returns_error(self):
        from franki.utils.test_runner import run_tests
        output, rc = run_tests("sleep 10", timeout=1)
        assert rc != 0
        assert "timed out" in output.lower()


class TestCmdTest:
    def test_no_runner_detected_prints_usage(self, tmp_path):
        from franki.commands import _cmd_test
        session = Session()
        c = _console()
        with patch("os.getcwd", return_value=str(tmp_path)), \
             patch("franki.commands.console", c):
            _cmd_test(_cfg(), session, "")
        assert "no test runner" in c.file.getvalue().lower()

    def test_explicit_command_runs_it(self):
        from franki.commands import _cmd_test
        session = Session()
        with patch("franki.utils.test_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="1 passed", stderr="", returncode=0)
            with patch("franki.commands.console", _console()):
                _cmd_test(_cfg(), session, "echo test")
        assert len(session.history_display()) == 1

    def test_test_output_injected_into_session(self):
        from franki.commands import _cmd_test
        session = Session()
        with patch("franki.utils.test_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="FAILED test_foo.py::test_bar", stderr="", returncode=1
            )
            with patch("franki.commands.console", _console()):
                _cmd_test(_cfg(), session, "pytest -q")
        msgs = session.history_display()
        assert len(msgs) == 1
        assert "FAILED" in msgs[0]["content"]

    def test_passing_tests_says_passed(self):
        from franki.commands import _cmd_test
        session = Session()
        c = _console()
        with patch("franki.utils.test_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="5 passed", stderr="", returncode=0)
            with patch("franki.commands.console", c):
                _cmd_test(_cfg(), session, "pytest -q")
        assert "passed" in c.file.getvalue()


# ── custom tools ──────────────────────────────────────────────────────────────

class TestParseCustomTools:
    _CONTEXT = """
# My project

Some context here.

```franki-tools
[query_db]
description = Run a SQL query against the local dev database
command = psql -U dev mydb -c "{query}"
param.query = The SQL query to execute

[restart_server]
description = Restart the development server
command = systemctl restart myapp
```

More text.
"""

    def test_parses_two_tools(self):
        from franki.custom_tools import parse_custom_tools
        tools = parse_custom_tools(self._CONTEXT)
        assert len(tools) == 2

    def test_parses_name_description_command(self):
        from franki.custom_tools import parse_custom_tools
        tools = parse_custom_tools(self._CONTEXT)
        t = tools[0]
        assert t["name"] == "query_db"
        assert "SQL" in t["description"]
        assert "psql" in t["command"]

    def test_parses_params(self):
        from franki.custom_tools import parse_custom_tools
        tools = parse_custom_tools(self._CONTEXT)
        t = tools[0]
        assert "query" in t["params"]
        assert "SQL" in t["params"]["query"]

    def test_tool_without_command_excluded(self):
        from franki.custom_tools import parse_custom_tools
        ctx = "```franki-tools\n[no_cmd]\ndescription = Has no command\n```"
        tools = parse_custom_tools(ctx)
        assert tools == []

    def test_no_fence_returns_empty(self):
        from franki.custom_tools import parse_custom_tools
        assert parse_custom_tools("no tools here") == []

    def test_empty_context_returns_empty(self):
        from franki.custom_tools import parse_custom_tools
        assert parse_custom_tools("") == []

    def test_comment_lines_ignored(self):
        from franki.custom_tools import parse_custom_tools
        ctx = "```franki-tools\n# this is a comment\n[mytool]\ncommand = echo hi\n```"
        tools = parse_custom_tools(ctx)
        assert len(tools) == 1
        assert tools[0]["name"] == "mytool"


class TestCustomToolSchemas:
    def _register(self):
        from franki.custom_tools import parse_custom_tools
        from franki.agent.tools import register_custom_tools
        ctx = "```franki-tools\n[db_query]\ndescription=Query DB\ncommand=psql -c \"{sql}\"\nparam.sql=SQL statement\n```"
        register_custom_tools(parse_custom_tools(ctx))

    def teardown_method(self):
        from franki.agent.tools import register_custom_tools
        register_custom_tools([])

    def test_schemas_include_custom_tool(self):
        self._register()
        from franki.agent.tools import get_custom_tool_schemas
        schemas = get_custom_tool_schemas()
        names = [s["function"]["name"] for s in schemas]
        assert "db_query" in names

    def test_get_all_schemas_includes_builtin_and_custom(self):
        self._register()
        from franki.agent.tools import get_all_tool_schemas, TOOL_SCHEMAS
        all_schemas = get_all_tool_schemas()
        assert len(all_schemas) > len(TOOL_SCHEMAS)

    def test_custom_schema_has_param(self):
        self._register()
        from franki.agent.tools import get_custom_tool_schemas
        schemas = get_custom_tool_schemas()
        s = schemas[0]
        props = s["function"]["parameters"]["properties"]
        assert "sql" in props


class TestExecuteCustomTool:
    def setup_method(self):
        from franki.agent.tools import register_custom_tools
        register_custom_tools([{
            "name":    "echo_tool",
            "description": "Echo something",
            "command": "echo {message}",
            "params":  {"message": "Message to echo"},
        }])

    def teardown_method(self):
        from franki.agent.tools import register_custom_tools
        register_custom_tools([])

    def test_executes_with_param_substitution(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("echo_tool", {"message": "hello world"})
        assert "hello world" in result

    def test_unknown_tool_still_returns_error(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("nonexistent_custom_tool", {})
        assert "unknown tool" in result
