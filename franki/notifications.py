"""
notifications.py — task-completion alerts for auto-accept mode.

Fires when the agent loop finishes a multi-step task while auto_accept is on
(i.e. the user handed control over and may have walked away).

Attempt order:
  1. Terminal bell          — always fires; wakes the terminal emulator
  2. Desktop notification   — notify-send (Linux) / osascript (macOS)
  3. Sound                  — canberra-gtk-play → ffplay (OGA) → aplay (WAV)

Every step is fire-and-forget. Missing tools or permissions are silently ignored.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from franki.ui.theme import GOLD, TEXT_DIM, BORDER

# OGA sound candidates, tried in order (prefer desktop-themed sounds)
_OGA_SOUNDS = [
    "/usr/share/sounds/Yaru/stereo/complete.oga",
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga",
]

# WAV fallbacks for aplay (always available on Ubuntu/Debian)
_WAV_SOUNDS = [
    "/usr/share/sounds/sound-icons/glass-water-1.wav",
    "/usr/share/sounds/sound-icons/pipe.wav",
    "/usr/share/sounds/alsa/Rear_Center.wav",
]


# ── Public API ────────────────────────────────────────────────────────────────

def notify_done(
    console: Console,
    steps: int = 0,
    files_written: int = 0,
    elapsed_s: float = 0.0,
    skill: str = "",
) -> None:
    """
    Print a completion banner, ring the terminal bell, send a desktop
    notification, and try to play a sound.
    """
    _banner(console, steps, files_written, elapsed_s)
    _bell()

    body_parts = []
    if steps:
        body_parts.append(f"{steps} step{'s' if steps != 1 else ''}")
    if files_written:
        body_parts.append(f"{files_written} file{'s' if files_written != 1 else ''} written")
    if elapsed_s:
        body_parts.append(f"{elapsed_s:.1f}s")

    body = " · ".join(body_parts) if body_parts else "Task complete"
    title = f"Franki — done{f'  [{skill}]' if skill else ''}"

    _desktop(title, body)
    _sound()


# ── Terminal banner ───────────────────────────────────────────────────────────

def _banner(
    console: Console,
    steps: int,
    files_written: int,
    elapsed_s: float,
) -> None:
    parts = ["  ✓  done"]
    if steps:
        parts.append(f"{steps} step{'s' if steps != 1 else ''}")
    if files_written:
        parts.append(f"{files_written} file{'s' if files_written != 1 else ''} written")
    if elapsed_s >= 1.0:
        parts.append(f"{elapsed_s:.1f}s")

    line = Text()
    line.append("  ✓ ", style=f"bold {GOLD}")
    line.append("done", style=f"bold {GOLD}")
    if steps or files_written or elapsed_s >= 1.0:
        line.append("  ·  ", style=TEXT_DIM)
        details = "  ·  ".join(parts[1:])
        line.append(details, style=TEXT_DIM)

    console.print()
    console.print(Rule(style=BORDER))
    console.print(line)
    console.print(Rule(style=BORDER))
    console.print()


# ── Bell ──────────────────────────────────────────────────────────────────────

def _bell() -> None:
    sys.stdout.write("\a")
    sys.stdout.flush()


# ── Desktop notification ──────────────────────────────────────────────────────

def _desktop(title: str, body: str) -> None:
    try:
        if sys.platform.startswith("linux"):
            subprocess.Popen(
                [
                    "notify-send",
                    "--app-name=franki",
                    "--expire-time=8000",
                    "--icon=dialog-information",
                    title,
                    body,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            script = f'display notification "{body}" with title "{title}"'
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


# ── Sound ─────────────────────────────────────────────────────────────────────

def _sound() -> None:
    # 1. canberra-gtk-play uses the current desktop theme — most seamless
    if _try_canberra():
        return
    # 2. ffplay handles OGA (Ogg Vorbis) files
    for path in _OGA_SOUNDS:
        if Path(path).is_file() and _try_ffplay(path):
            return
    # 3. aplay handles WAV — ships with almost every Linux distro
    for path in _WAV_SOUNDS:
        if Path(path).is_file() and _try_aplay(path):
            return


def _try_canberra() -> bool:
    try:
        subprocess.Popen(
            ["canberra-gtk-play", "--id=complete"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, Exception):
        return False


def _try_ffplay(path: str) -> bool:
    try:
        subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, Exception):
        return False


def _try_aplay(path: str) -> bool:
    try:
        subprocess.Popen(
            ["aplay", "-q", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, Exception):
        return False
