"""Модель книги. Всё выше по потоку строит Document, всё ниже его читает."""

from dataclasses import dataclass, field
from typing import Literal

Language = Literal["ru", "en"]
BlockKind = Literal["heading", "paragraph"]

LANGUAGES: tuple[str, ...] = ("ru", "en")
BLOCK_KINDS: tuple[str, ...] = ("heading", "paragraph")


@dataclass(frozen=True)
class Block:
    """Кусок текста с известной ролью. Номер страницы есть только у PDF."""

    kind: BlockKind
    text: str
    page: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in BLOCK_KINDS:
            raise ValueError(f"неизвестный вид блока: {self.kind}")
        if not self.text.strip():
            raise ValueError("пустой текст блока")


@dataclass
class Chapter:
    title: str
    blocks: list[Block] = field(default_factory=list)

    def char_count(self) -> int:
        return sum(len(b.text) for b in self.blocks)


@dataclass
class Document:
    title: str
    author: str | None
    language: Language
    chapters: list[Chapter] = field(default_factory=list)
    # Байты картинки, а не путь: извлечению не нужно знать про рабочую папку.
    cover: bytes | None = None

    def __post_init__(self) -> None:
        if self.language not in LANGUAGES:
            raise ValueError(f"неподдерживаемый язык: {self.language}")

    def char_count(self) -> int:
        return sum(c.char_count() for c in self.chapters)


@dataclass(frozen=True)
class Selection:
    """Что именно озвучиваем.

    У PDF это диапазон страниц, у EPUB и FB2 номера глав. Одновременно
    задать оба нельзя: в EPUB страниц нет, а притворяться, что есть, вредно.
    """

    pages: tuple[int, int] | None = None
    chapters: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.pages is not None and self.chapters is not None:
            raise ValueError("выбирается или страницы, или главы, не оба сразу")
        if self.pages is not None:
            first, last = self.pages
            if first < 1:
                raise ValueError("страницы нумеруются с единицы")
            if first > last:
                raise ValueError("начало диапазона больше конца")

    def page_indexes(self) -> list[int]:
        """Номера страниц с нуля, как их ждёт PyMuPDF."""
        if self.pages is None:
            return []
        first, last = self.pages
        return list(range(first - 1, last))
