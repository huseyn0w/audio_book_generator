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


def parse_page_spec(value: str | None) -> Selection | None:
    """Разбирает «10-20» или «7». Пусто значит вся книга.

    Живёт рядом с Selection, а не в CLI: тот же разбор нужен веб-форме,
    а дублировать правила в двух местах значит разойтись в третьем.
    """
    if not value or not value.strip():
        return None
    parts = value.replace(" ", "").split("-")
    if len(parts) > 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"диапазон страниц должен быть вида 10-20 или 7, а не {value!r}")
    first = int(parts[0])
    last = int(parts[-1])
    if first < 1 or first > last:
        raise ValueError(f"неверный диапазон страниц: {value!r}")
    return Selection(pages=(first, last))
