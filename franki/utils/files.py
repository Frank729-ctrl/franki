import re
from pathlib import Path


_REF_PATTERN = re.compile(r'@(\S+)')


def resolve_files(text: str) -> tuple[str, list[str]]:
    """
    Find all @filename refs in text, read them, prepend their content.
    Returns (enriched_message, [error_strings]).
    The @ref tokens are stripped from the user-visible message text.
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
            file_sections.append(
                f"**File: `{ref}`**\n```{lang}\n{content}\n```"
            )
        except Exception as exc:
            errors.append(f"@{ref}: {exc}")

    clean = clean.strip()

    if file_sections:
        prefix = "\n\n".join(file_sections)
        message = f"{prefix}\n\n{clean}" if clean else prefix
    else:
        message = clean

    return message, errors
