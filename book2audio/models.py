"""The book model. Everything upstream builds a Document, everything downstream reads it."""

from dataclasses import dataclass, field
from typing import Literal

Language = Literal["ru", "en"]
BlockKind = Literal["heading", "paragraph"]

LANGUAGES: tuple[str, ...] = ("ru", "en")

# Fallback chapter titles follow the book, not the interface. The opening title is
# read aloud, so an English word in a Russian book would be heard; the chapter
# label sits in the player next to the book's own chapter names.
OPENING_TITLE = {"ru": "Начало", "en": "Beginning"}
CHAPTER_LABEL = {"ru": "Глава", "en": "Chapter"}
UNTITLED = {"ru": "Без названия", "en": "Untitled"}
BLOCK_KINDS: tuple[str, ...] = ("heading", "paragraph")


@dataclass(frozen=True)
class Block:
    """A piece of text with a known role. Only PDF has a page number."""

    kind: BlockKind
    text: str
    page: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in BLOCK_KINDS:
            raise ValueError(f"unknown block kind: {self.kind}")
        if not self.text.strip():
            raise ValueError("empty block text")


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
    # The image bytes, not a path: extraction need not know about the work folder.
    cover: bytes | None = None

    def __post_init__(self) -> None:
        if self.language not in LANGUAGES:
            raise ValueError(f"unsupported language: {self.language}")

    def char_count(self) -> int:
        return sum(c.char_count() for c in self.chapters)


@dataclass(frozen=True)
class Selection:
    """What exactly we are reading out.

    For PDF it is a page range, for EPUB and FB2 chapter numbers. You cannot set
    both: EPUB has no pages, and pretending it does is harmful.
    """

    pages: tuple[int, int] | None = None
    chapters: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.pages is not None and self.chapters is not None:
            raise ValueError("choose either pages or chapters, not both at once")
        if self.pages is not None:
            first, last = self.pages
            if first < 1:
                raise ValueError("pages are numbered from one")
            if first > last:
                raise ValueError("the range starts after it ends")

    def page_indexes(self) -> list[int]:
        """Page numbers from zero, the way PyMuPDF expects them."""
        if self.pages is None:
            return []
        first, last = self.pages
        return list(range(first - 1, last))


def parse_page_spec(value: str | None) -> Selection | None:
    """Parses "10-20" or "7". Empty means the whole book.

    It lives next to Selection rather than in the CLI: the web form needs the same
    parsing, and duplicating the rules in two places means diverging in a third.
    """
    if not value or not value.strip():
        return None
    parts = value.replace(" ", "").split("-")
    if len(parts) > 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"a page range looks like 10-20 or 7, not {value!r}")
    first = int(parts[0])
    last = int(parts[-1])
    if first < 1 or first > last:
        raise ValueError(f"bad page range: {value!r}")
    return Selection(pages=(first, last))
