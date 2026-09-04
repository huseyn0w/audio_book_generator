"""Единственный интерфейс синтеза. Всё, что ниже по потоку, потребляет wav."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

Language = Literal["ru", "en"]
Gender = Literal["male", "female", "unknown"]

GENDERS: tuple[str, ...] = ("male", "female", "unknown")

# Выбраны слепым сравнением в фазе 0, см. docs/superpowers/specs/voice-choice.md
DEFAULTS: dict[tuple[str, str], str] = {
    ("ru", "female"): "xenia",
    ("ru", "male"): "eugene",
    ("en", "female"): "af_nova",
    ("en", "male"): "am_michael",
}


@dataclass(frozen=True)
class Voice:
    """Голос движка. Пол нужен UI, чтобы дать выбор до выбора конкретного диктора."""

    id: str
    gender: Gender

    def __post_init__(self) -> None:
        if self.gender not in GENDERS:
            raise ValueError(f"неизвестный пол: {self.gender}")


def pick_default(language: str, gender: str) -> str:
    """Голос по умолчанию для пары язык плюс пол."""
    return DEFAULTS[(language, gender)]


@runtime_checkable
class TTSEngine(Protocol):
    name: str
    sample_rate: int

    def voices(self) -> list[Voice]:
        """Голоса движка вместе с полом."""
        ...

    def synth(self, text: str, voice: str, out_path: Path) -> None:
        """Синтезирует текст в моно-wav на скорости x1."""
        ...
