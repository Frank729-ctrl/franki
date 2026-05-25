import subprocess


_TIMEOUT = 60


def run_command(cmd: str) -> tuple[str, str, int]:
    """
    Run a shell command. Returns (stdout, stderr, returncode).
    Timeout is 60 seconds.
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"command timed out after {_TIMEOUT}s", 1
    except Exception as exc:
        return "", str(exc), 1


def build_ai_prompt(cmd: str, stdout: str, stderr: str, returncode: int) -> str:
    """Build the message sent to the AI after running a shell command."""
    parts = [f"I ran the following command:\n`{cmd}`\n\nHere is the output:"]

    if stdout.strip():
        parts.append(f"```\n{stdout.rstrip()}\n```")
    if stderr.strip():
        parts.append(f"Stderr:\n```\n{stderr.rstrip()}\n```")
    if returncode != 0:
        parts.append(f"Exit code: {returncode}")

    parts.append("Please analyse this output.")
    return "\n\n".join(parts)
