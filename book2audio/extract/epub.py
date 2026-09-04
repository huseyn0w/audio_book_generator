"""Извлечение EPUB.

Главы берутся из оглавления, а не из заголовков h1-h3: в реальных книгах
их часто нет вовсе, а spine разбит на сотни файлов по несколько абзацев.
Оглавление ссылается на якорь внутри файла, поэтому резать надо по якорю.
"""

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from book2audio.clean.speech import normalize_for_speech
from book2audio.clean.text import clean_text
from book2audio.models import Block, Chapter, Document, Selection

TEXT_TAGS = ("p", "h1", "h2", "h3", "h4", "blockquote")

SKIPPED_TAGS = ("table", "figure", "figcaption", "sup", "script", "style")

# Конвертеры fb2 в epub раскладывают сноски отдельными файлами, каждый
# начинается с голого номера, и в оглавление они не попадают. У Кристенсена
# это 202 файла и 162 тысячи символов: три часа обрывков в конце книги.
BARE_NUMBER = re.compile(r"\d{1,4}")


def looks_like_endnote(paragraphs: list[str], in_toc: bool) -> bool:
    """Документ spine это концевая сноска, а не глава.

    Оба условия обязательны. Документ вне оглавления может быть эпилогом,
    а абзац из одного числа может встретиться и в обычной главе.
    """
    if in_toc or not paragraphs:
        return False
    return bool(BARE_NUMBER.fullmatch(paragraphs[0].strip()))


@dataclass(frozen=True)
class Piece:
    """Абзац вместе с якорями, встреченными до него. Нужен, чтобы резать главы."""

    text: str
    document: str
    anchors: frozenset[str]
    is_heading: bool


def flatten_toc(entries) -> list[tuple[str, str, str]]:
    """Разворачивает вложенное оглавление в плоский список в порядке чтения."""
    flat: list[tuple[str, str, str]] = []

    def walk(items) -> None:
        for item in items:
            link, children = item if isinstance(item, tuple) else (item, [])
            href = getattr(link, "href", "") or ""
            document, _, anchor = href.partition("#")
            title = (getattr(link, "title", "") or "").strip()
            if title:
                flat.append((title, document, anchor))
            walk(children)

    walk(entries)
    return flat


def _pieces_of(item, name: str) -> list[Piece]:
    """Разбирает один документ spine в абзацы, помня встреченные якоря."""
    soup = BeautifulSoup(item.get_content(), "xml")
    for tag in soup.find_all(SKIPPED_TAGS):
        tag.decompose()

    pieces: list[Piece] = []
    pending: set[str] = set()
    for element in soup.find_all(True):
        identifier = element.get("id")
        if identifier:
            pending.add(identifier)
        if element.name not in TEXT_TAGS:
            continue
        text = " ".join(element.get_text(" ").split())
        if not text:
            continue
        pieces.append(
            Piece(
                text=text,
                document=name,
                anchors=frozenset(pending),
                is_heading=element.name.startswith("h"),
            )
        )
        pending = set()
    return pieces


def _cut_into_chapters(pieces: list[Piece], toc: list[tuple[str, str, str]]) -> list[Chapter]:
    """Режет поток абзацев по точкам оглавления."""
    marks: list[tuple[int, str]] = []
    search_from = 0
    for title, document, anchor in toc:
        found = None
        for index in range(search_from, len(pieces)):
            piece = pieces[index]
            if piece.document != document:
                continue
            if not anchor or anchor in piece.anchors:
                found = index
                break
        if found is None:
            continue
        marks.append((found, title))
        search_from = found + 1

    if not marks:
        return (
            [
                Chapter(
                    title="Начало",
                    blocks=[Block(kind="paragraph", text=p.text) for p in pieces],
                )
            ]
            if pieces
            else []
        )

    chapters: list[Chapter] = []
    head = pieces[: marks[0][0]]
    if head:
        chapters.append(
            Chapter(
                title="Начало",
                blocks=[Block(kind="paragraph", text=p.text) for p in head],
            )
        )

    for position, (start, title) in enumerate(marks):
        stop = marks[position + 1][0] if position + 1 < len(marks) else len(pieces)
        inside = pieces[start:stop]
        if not inside:
            continue
        blocks = [Block(kind="heading", text=title)]
        blocks += [
            Block(kind="paragraph", text=p.text) for p in inside if p.text.strip() != title.strip()
        ]
        chapters.append(Chapter(title=title, blocks=blocks))
    return chapters


def _cover(book) -> bytes | None:
    """Обложка EPUB. Три способа пометить её, в порядке надёжности.

    EPUB 2 кладёт <meta name="cover" content="id"> в OPF, EPUB 3 помечает
    сам файл свойством cover-image. Последний вариант это догадка по имени:
    так делают конвертеры, которые не соблюдают ни одну из спецификаций.
    """
    by_id = {item.get_id(): item for item in book.get_items()}

    for _, attributes in book.get_metadata("OPF", "cover") or []:
        item = by_id.get(attributes.get("content", ""))
        if item is not None:
            return item.get_content()

    for item in book.get_items():
        if "cover-image" in (getattr(item, "properties", None) or []):
            return item.get_content()

    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        if "cover" in item.get_name().lower():
            return item.get_content()
    return None


class EpubExtractor:
    def __init__(self, clean: bool = True) -> None:
        self.clean = clean
        self.report = None

    def extract(self, path: Path, selection: Selection | None = None) -> Document:
        if not zipfile.is_zipfile(path):
            raise ValueError(f"файл не похож на EPUB: {path.name}")
        book = epub.read_epub(str(path))

        by_id = {item.get_id(): item for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)}
        toc = flatten_toc(book.toc)
        toc_documents = {document for _, document, _ in toc}

        pieces: list[Piece] = []
        for item_id, _ in book.spine:
            item = by_id.get(item_id)
            if item is None:
                continue
            name = item.get_name()
            found = _pieces_of(item, name)
            if looks_like_endnote([p.text for p in found], in_toc=name in toc_documents):
                continue
            pieces.extend(found)

        chapters = _cut_into_chapters(pieces, toc)
        if selection and selection.chapters:
            wanted = [i for i in selection.chapters if 0 <= i < len(chapters)]
            chapters = [chapters[i] for i in wanted]

        def first(key: str) -> str:
            values = book.get_metadata("DC", key)
            return values[0][0] if values else ""

        language = (first("language") or "ru").lower()[:2]
        if language not in {"ru", "en"}:
            language = "ru"

        if self.clean:
            for chapter in chapters:
                chapter.title = normalize_for_speech(clean_text(chapter.title), language)
                chapter.blocks = [
                    Block(kind=b.kind, text=normalize_for_speech(clean_text(b.text), language))
                    for b in chapter.blocks
                    if clean_text(b.text)
                ]

        return Document(
            title=first("title") or path.stem,
            author=first("creator") or None,
            language=language,
            chapters=chapters,
            cover=_cover(book),
        )
