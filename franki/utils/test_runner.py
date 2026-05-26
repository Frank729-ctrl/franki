"""Detect and run the project's test suite."""
from __future__ import annotations
import subprocess
from pathlib import Path

_MAX_OUTPUT_LINES = 200


def detect_test_cmd(cwd: Path | None = None) -> str | None:
    """Return a sensible test command for the project at *cwd*, or None."""
    d = (cwd or Path.cwd()).resolve()

    # Python — pytest
    if (d / "pytest.ini").exists() or (d / "setup.cfg").exists():
        return "python3 -m pytest --tb=short -q"
    if (d / "pyproject.toml").exists():
        try:
            body = (d / "pyproject.toml").read_text(encoding="utf-8")
            if "pytest" in body or "[tool.pytest" in body:
                return "python3 -m pytest --tb=short -q"
        except OSError:
            pass

    # Node / npm
    if (d / "package.json").exists():
        return "npm test"

    # Go
    if list(d.glob("*.go")):
        return "go test ./..."

    # Rust / Cargo
    if (d / "Cargo.toml").exists():
        return "cargo test"

    # Makefile with a 'test' target
    if (d / "Makefile").exists():
        try:
            content = (d / "Makefile").read_text(encoding="utf-8")
            if "test:" in content or "test :" in content:
                return "make test"
        except OSError:
            pass

    return None


def run_tests(command: str, timeout: int = 120) -> tuple[str, int]:
    """
    Run *command* and return *(combined_output, returncode)*.
    Output is capped at _MAX_OUTPUT_LINES lines.
    """
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"tests timed out after {timeout}s", 1
    except Exception as exc:
        return f"error running tests: {exc}", 1

    combined = result.stdout
    if result.stderr:
        combined += "\n" + result.stderr
    combined = combined.strip()

    lines = combined.splitlines()
    if len(lines) > _MAX_OUTPUT_LINES:
        kept = "\n".join(lines[:_MAX_OUTPUT_LINES])
        combined = kept + f"\n... ({len(lines) - _MAX_OUTPUT_LINES} more lines)"

    return combined or "(no output)", result.returncode
