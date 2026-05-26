"""Varied multi-word spinner phrases for the thinking/working states."""
from __future__ import annotations
import random


_THINKING: list[str] = [
    "working on it",
    "let me think about this",
    "figuring this out",
    "reading through this",
    "on it, one sec",
    "thinking this through",
    "give me a moment",
    "digging into this",
    "working through it",
    "let me put this together",
    "got it, thinking",
    "pulling this together",
    "looking into this",
    "crunching through this",
    "hold on a moment",
    "putting my thoughts together",
    "making sense of this",
    "on the case",
]

_STILL_THINKING: list[str] = [
    "still at it, hang tight",
    "this one needs a moment",
    "working through the details",
    "almost there",
    "digging deeper into this",
    "taking a bit longer than usual",
    "complex one — stay with me",
    "still processing this",
    "giving this proper thought",
    "nearly there",
]

_LONG_RUNNING: list[str] = [
    "this is taking a while — complex task",
    "still running, don't close me",
    "working hard on this one",
    "deep in thought here",
    "long task — still going",
    "patience, almost done",
]


def pick_phrase() -> str:
    """Pick a random opening phrase for a new request."""
    return random.choice(_THINKING)


def phrase_for_elapsed(elapsed_s: float, opening: str) -> str:
    """Escalate the phrase text based on how long we've been waiting."""
    if elapsed_s < 8:
        return opening
    if elapsed_s < 20:
        return random.choice(_STILL_THINKING)
    return random.choice(_LONG_RUNNING)
