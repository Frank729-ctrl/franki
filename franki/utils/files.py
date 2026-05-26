from __future__ import annotations
import base64
import mimetypes
import re
from pathlib import Path

_REF_PATTERN = re.compile(r'@(\S+)')
_URL_RE      = re.compile(r'^https?://')

_IMAGE_EXTS  = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# Limits for @dir and @url injection
_DIR_MAX_FILES    = 40
_DIR_MAX_CHARS    = 20_000
_DIR_FILE_MAXSIZE = 6_000   # chars per file
_URL_MAX_CHARS    = 12_000


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_files(text: str) -> tuple[str, list[str]]:
    """
    Find all @filename refs in text, read them as text, prepend their content.
    Returns (enriched_message, [error_strings]).
    """
    refs = _REF_PATTERN.findall(text)
    if not refs:
        return text, []

    errors: list[str] = []
    file_sections: list[str] = []
    clean = text

    for ref in refs:
        path = Path(ref).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / ref
        clean = re.sub(r'@' + re.escape(ref), '', clean, count=1)
        if not path.exists():
            errors.append(f"@{ref}: file not found")
            continue
        if not path.is_file():
            errors.append(f"@{ref}: not a file")
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            lang = path.suffix.lstrip(".") or "text"
            file_sections.append(f"**File: `{ref}`**\n```{lang}\n{content}\n```")
        except Exception as exc:
            errors.append(f"@{ref}: {exc}")

    clean = clean.strip()
    if file_sections:
        prefix = "\n\n".join(file_sections)
        message = f"{prefix}\n\n{clean}" if clean else prefix
    else:
        message = clean
    return message, errors


def resolve_content(raw: str) -> tuple[str | list, list[str]]:
    """
    Parse @token refs in *raw*:

    - ``@https://...``          — fetch the URL and inject as text
    - ``@path/to/dir/``         — inject directory tree + file contents
    - ``@image.png``            — base64-encode for vision (multimodal)
    - ``@file.py``              — inject as a fenced code block

    Returns (content, errors) where content is str or a multimodal list.
    """
    errors: list[str] = []
    if "@" not in raw:
        return raw, errors

    text_parts:  list[str]  = []
    image_parts: list[dict] = []
    remaining = raw

    for token in re.findall(r'@(\S+)', raw):
        # ── Clipboard injection ───────────────────────────────────────────────
        if token.lower() == "clipboard":
            block, err = _inject_clipboard()
            if err:
                errors.append(err)
            else:
                text_parts.append(block)
            remaining = remaining.replace(f"@{token}", "").strip()
            continue

        # ── Git context injection ─────────────────────────────────────────────
        if token.lower() == "git":
            block, err = _inject_git()
            if err:
                errors.append(err)
            else:
                text_parts.append(block)
            remaining = remaining.replace(f"@{token}", "").strip()
            continue

        # ── URL injection ─────────────────────────────────────────────────────
        if _URL_RE.match(token):
            block, err = _fetch_url(token)
            if err:
                errors.append(err)
            else:
                text_parts.append(block)
            remaining = remaining.replace(f"@{token}", "").strip()
            continue

        p = Path(token).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / token

        if not p.exists():
            errors.append(f"file not found: {token}")
            continue

        # ── Directory injection ───────────────────────────────────────────────
        if p.is_dir():
            block, err = _inject_dir(p, token)
            if err:
                errors.append(err)
            else:
                text_parts.append(block)
            remaining = remaining.replace(f"@{token}", "").strip()
            continue

        # ── Image (vision) ────────────────────────────────────────────────────
        if p.suffix.lower() in _IMAGE_EXTS:
            try:
                data = base64.b64encode(p.read_bytes()).decode()
                mime = mimetypes.guess_type(str(p))[0] or "image/png"
                image_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{data}"},
                })
                remaining = remaining.replace(f"@{token}", "").strip()
            except OSError as exc:
                errors.append(str(exc))
            continue

        # ── Text file ─────────────────────────────────────────────────────────
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            lang = p.suffix.lstrip(".") or "text"
            text_parts.append(f"[{token}]\n```{lang}\n{content}\n```")
            remaining = remaining.replace(f"@{token}", "").strip()
        except OSError as exc:
            errors.append(str(exc))

    if not image_parts:
        combined = "\n\n".join(text_parts + ([remaining] if remaining else []))
        return combined, errors

    # Multimodal response
    parts: list[dict] = []
    all_text = "\n\n".join(text_parts + ([remaining] if remaining else []))
    if all_text:
        parts.append({"type": "text", "text": all_text})
    parts.extend(image_parts)
    return parts, errors


# ── Clipboard injector ───────────────────────────────────────────────────────

_CLIPBOARD_MAX = 10_000


def _inject_clipboard() -> tuple[str, str]:
    try:
        import pyperclip
        text = pyperclip.paste()
    except ImportError:
        return "", "@clipboard: pyperclip not installed"
    except Exception as exc:
        return "", f"@clipboard: {exc}"

    if not text or not text.strip():
        return "", "@clipboard: clipboard is empty"

    text = text.strip()
    if len(text) > _CLIPBOARD_MAX:
        text = text[:_CLIPBOARD_MAX] + f"\n... (truncated — {len(text) - _CLIPBOARD_MAX} chars omitted)"

    return f"[clipboard]\n```\n{text}\n```", ""


# ── Git context injector ─────────────────────────────────────────────────────

_GIT_DIFF_MAX = 8_000   # chars — diffs can be enormous


def _run_git(args: list[str]) -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _inject_git() -> tuple[str, str]:
    """
    Inject current git state: branch, status, diff (HEAD), recent log.
    Returns (block, error).
    """
    # Verify we're inside a git repo
    root = _run_git(["rev-parse", "--show-toplevel"])
    if not root:
        return "", "@git: not inside a git repository"

    branch  = _run_git(["branch", "--show-current"]) or "HEAD detached"
    status  = _run_git(["status", "--short"])
    diff    = _run_git(["diff", "HEAD"])
    log     = _run_git(["log", "--oneline", "-15"])

    sections: list[str] = [f"[git context — branch: {branch}]", ""]

    if status:
        sections += ["## Status", "```", status, "```", ""]
    else:
        sections += ["## Status", "nothing to commit, working tree clean", ""]

    if diff:
        if len(diff) > _GIT_DIFF_MAX:
            diff = diff[:_GIT_DIFF_MAX] + f"\n... (diff truncated — {len(diff) - _GIT_DIFF_MAX} chars omitted)"
        sections += ["## Diff (HEAD)", "```diff", diff, "```", ""]

    if log:
        sections += ["## Recent commits", "```", log, "```"]

    return "\n".join(sections).rstrip(), ""


# ── URL fetcher ───────────────────────────────────────────────────────────────

def _fetch_url(url: str) -> tuple[str, str]:
    """
    Fetch *url* and return (injected_block, error_message).
    Strips HTML tags, truncates to _URL_MAX_CHARS.
    """
    try:
        import httpx
    except ImportError:
        return "", "httpx not installed — cannot fetch URLs"

    try:
        resp = httpx.get(url, timeout=15.0, follow_redirects=True, headers={
            "User-Agent": "franki-cli/0.1 (context-fetcher)"
        })
        resp.raise_for_status()
    except Exception as exc:
        return "", f"@{url}: fetch failed — {exc}"

    ct = resp.headers.get("content-type", "")
    text = resp.text

    # Strip HTML
    if "html" in ct or text.lstrip().startswith("<"):
        text = _strip_html(text)

    text = text.strip()
    if len(text) > _URL_MAX_CHARS:
        text = text[:_URL_MAX_CHARS] + f"\n... (truncated — {len(text) - _URL_MAX_CHARS} chars omitted)"

    block = f"[{url}]\n```\n{text}\n```"
    return block, ""


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode entities using stdlib only."""
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        _SKIP = {"script", "style", "head", "nav", "footer", "aside"}

        def __init__(self):
            super().__init__()
            self._parts: list[str] = []
            self._skip_depth = 0

        def handle_starttag(self, tag, attrs):
            if tag.lower() in self._SKIP:
                self._skip_depth += 1

        def handle_endtag(self, tag):
            if tag.lower() in self._SKIP and self._skip_depth > 0:
                self._skip_depth -= 1

        def handle_data(self, data):
            if self._skip_depth == 0:
                stripped = data.strip()
                if stripped:
                    self._parts.append(stripped)

        def get_text(self) -> str:
            return "\n".join(self._parts)

    s = _Stripper()
    s.feed(html)
    return s.get_text()


# ── Directory injector ────────────────────────────────────────────────────────

_DIR_SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox",
             "dist", "build", ".next", ".nuxt", "coverage", ".mypy_cache"}
_TEXT_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".sh", ".bash",
    ".go", ".rs", ".c", ".cpp", ".h", ".java", ".kt", ".rb", ".php",
    ".sql", ".env", ".gitignore", ".dockerfile", "",
}


def _inject_dir(path: Path, token: str) -> tuple[str, str]:
    """
    Build a compact directory listing + file contents for *path*.
    Returns (block, error).
    """
    tree_lines:  list[str] = []
    file_blocks: list[str] = []
    total_chars  = 0
    file_count   = 0

    try:
        for item in sorted(path.rglob("*")):
            if file_count >= _DIR_MAX_FILES or total_chars >= _DIR_CHARS:
                tree_lines.append("  ... (truncated)")
                break

            # Skip hidden dirs/files and known noise
            parts = item.relative_to(path).parts
            if any(p in _DIR_SKIP or p.startswith(".") for p in parts):
                continue

            rel = item.relative_to(path)
            indent = "  " * (len(parts) - 1)

            if item.is_dir():
                tree_lines.append(f"{indent}{item.name}/")
            elif item.is_file():
                tree_lines.append(f"{indent}{item.name}")
                if item.suffix.lower() in _TEXT_EXTS or item.suffix == "":
                    try:
                        content = item.read_text(encoding="utf-8", errors="replace")
                        if len(content) > _DIR_FILE_MAXSIZE:
                            content = content[:_DIR_FILE_MAXSIZE] + "\n... (truncated)"
                        lang = item.suffix.lstrip(".") or "text"
                        block = f"[{rel}]\n```{lang}\n{content}\n```"
                        file_blocks.append(block)
                        total_chars += len(block)
                        file_count += 1
                    except OSError:
                        pass
    except Exception as exc:
        return "", f"@{token}: {exc}"

    header = f"[directory: {token}]\n" + "\n".join(tree_lines)
    body   = "\n\n".join(file_blocks)
    result = header + ("\n\n" + body if body else "")
    return result, ""


# Alias: fix typo in old internal reference
_DIR_CHARS = _DIR_MAX_CHARS
