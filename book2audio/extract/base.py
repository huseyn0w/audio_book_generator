"""The extraction protocol. Every book format implements it its own way."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from book2audio.models import Document, Selection


class NoTextLayer(Exception):
    """The PDF is made of images. That needs OCR, which is out of scope here."""


@runtime_checkable
class Extractor(Protocol):
    def extract(self, path: Path, selection: Selection | None = None) -> Document:
        """Reads the book and returns a Document. Selection narrows what is read."""
        ...
