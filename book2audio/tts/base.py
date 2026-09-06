"""The one synthesis interface. Everything downstream consumes wav."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

Language = Literal["ru", "en"]
Gender = Literal["male", "female", "unknown"]

GENDERS: tuple[str, ...] = ("male", "female", "unknown")

# Picked by a blind comparison, see docs/superpowers/specs/voice-choice.md.
# The Russian female voice was revisited 2026-09-05 on a real book paragraph.
DEFAULTS: dict[tuple[str, str], str] = {
    ("ru", "female"): "kseniya",
    ("ru", "male"): "eugene",
    ("en", "female"): "af_nova",
    ("en", "male"): "am_michael",
}


@dataclass(frozen=True)
class Voice:
    """An engine voice. The UI needs the gender to offer a choice before a narrator is picked."""

    id: str
    gender: Gender

    def __post_init__(self) -> None:
        if self.gender not in GENDERS:
            raise ValueError(f"unknown gender: {self.gender}")


def pick_default(language: str, gender: str) -> str:
    """The default voice for a language plus gender pair."""
    return DEFAULTS[(language, gender)]


@runtime_checkable
class TTSEngine(Protocol):
    name: str
    # The model version is part of the cache key: a new model invalidates old wavs.
    version: str
    sample_rate: int
    # How many times faster than real time synthesis runs. Needed to say up
    # front how long the wait is: Silero and Kokoro differ by six times.
    realtime: float
    # How many characters the engine takes at once. Silero models differ in
    # this limit, and one shared constant would break the smaller one.
    max_chars: int

    def voices(self) -> list[Voice]:
        """The engine voices together with their gender."""
        ...

    def synth(self, text: str, voice: str, out_path: Path) -> None:
        """Synthesizes the text into a mono wav at x1 speed."""
        ...
