"""EPUB extraction.

Chapters come from the table of contents rather than h1-h3 headings: real books
often have none at all, and the spine is split into hundreds of files of a few
paragraphs. The contents point at an anchor inside a file, so we cut on anchors.
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
from book2audio.models import OPENING_TITLE, Block, Chapter, Document, Selection

TEXT_TAGS = ("p", "h1", "h2", "h3", "h4", "blockquote")

SKIPPED_TAGS = ("table", "figure", "figcaption", "sup", "script", "style")

# fb2 to epub converters lay endnotes out as separate files, each starting with a
# bare number, and they never reach the contents. In the Christensen book that is
# 202 files and 162 thousand characters: three hours of scraps at the end.
BARE_NUMBER = re.compile(r"\d{1,4}")


def looks_like_endnote(paragraphs: list[str], in_toc: bool) -> bool:
    """This spine document is an endnote, not a chapter.

    Both conditions are required. A document outside the contents may be an
    epilogue, and a paragraph of one number can appear in an ordinary chapter.
    """
    if in_toc or not paragraphs:
        return False
    return bool(BARE_NUMBER.fullmatch(paragraphs[0].strip()))


@dataclass(frozen=True)
class Piece:
    """A paragraph with the anchors seen before it. Needed to cut the chapters."""

    text: str
    document: str
    anchors: frozenset[str]
    is_heading: bool


def flatten_toc(entries) -> list[tuple[str, str, str]]:
    """Flattens a nested table of contents into reading order."""
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
    """Parses one spine document into paragraphs, remembering the anchors seen."""
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


def _cut_into_chapters(
    pieces: list[Piece], toc: list[tuple[str, str, str]], language: str = "ru"
) -> list[Chapter]:
    """Cuts the paragraph stream at the table of contents entries."""
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
                    title=OPENING_TITLE[language],
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
                title=OPENING_TITLE[language],
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
    """The EPUB cover. Three ways to mark it, in order of reliability.

    EPUB 2 puts <meta name="cover" content="id"> in the OPF, EPUB 3 marks the file
    itself with the cover-image property. The last one is a guess from the name:
    that is what converters do when they follow neither specification.
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
    def __init__(self, clean: bool = True, language: str | None = None) -> None:
        self.clean = clean
        # An explicit language wins over the metadata: it also picks the voice, and
        # metadata in converted books lies regularly.
        self.language = language
        self.report = None

    def extract(self, path: Path, selection: Selection | None = None) -> Document:
        if not zipfile.is_zipfile(path):
            raise ValueError(f"this file does not look like EPUB: {path.name}")
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

        def first(key: str) -> str:
            values = book.get_metadata("DC", key)
            return values[0][0] if values else ""

        language = self.language or (first("language") or "ru").lower()[:2]
        if language not in {"ru", "en"}:
            language = "ru"

        chapters = _cut_into_chapters(pieces, toc, language)
        if selection and selection.chapters:
            wanted = [i for i in selection.chapters if 0 <= i < len(chapters)]
            chapters = [chapters[i] for i in wanted]

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
