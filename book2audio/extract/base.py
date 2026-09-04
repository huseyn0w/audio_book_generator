"""Протокол извлечения. Каждый формат книги реализует его по-своему."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from book2audio.models import Document, Selection


class NoTextLayer(Exception):
    """PDF состоит из картинок. Нужен OCR, а он за рамками проекта."""


@runtime_checkable
class Extractor(Protocol):
    def extract(self, path: Path, selection: Selection | None = None) -> Document:
        """Читает книгу и отдаёт Document. Selection ограничивает объём."""
        ...
