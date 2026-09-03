"""Единственный интерфейс синтеза. Всё, что ниже по потоку, потребляет wav."""

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class TTSEngine(Protocol):
    name: str
    sample_rate: int

    def voices(self) -> list[str]:
        """Список доступных голосов движка."""
        ...

    def synth(self, text: str, voice: str, out_path: Path) -> None:
        """Синтезирует текст в моно-wav на скорости x1."""
        ...
