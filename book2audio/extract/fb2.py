"""FB2 extraction. The simplest of the three formats: the markup already said it all.

The heavy phase 2 heuristics are not needed here, FB2 has no fonts and no
coordinates. We run only the text fixes and the normalization for speech.
"""

import base64
import binascii
from pathlib import Path

from lxml import etree

from book2audio.clean.speech import normalize_for_speech
from book2audio.clean.text import clean_text
from book2audio.models import OPENING_TITLE, Block, Chapter, Document, Selection

# Tags that never reach the audio. Tables make no sense read aloud, the annotation
# is a publisher's insert, and text-author is the attribution under a quote.
SKIPPED_TAGS = frozenset({"table", "annotation", "image", "text-author"})

# Wrappers we have to step inside. Comparing the FB2 and EPUB sizes of one book
# showed that <cite> holds chapter summaries of 400-1400 characters, that is real
# content rather than a service insert.
CONTAINER_TAGS = frozenset({"cite", "epigraph", "poem", "stanza"})

TEXT_TAGS = frozenset({"p", "subtitle", "v"})


def _local(element) -> str:
    return etree.QName(element).localname


def _text_of(element) -> str:
    """Collects an element's text, dropping the footnote links."""
    parts: list[str] = []
    for node in element.iter():
        if node is not element and _local(node) == "a" and node.get("type") == "note":
            continue
        if node.text:
            parts.append(node.text)
        if node is not element and node.tail:
            parts.append(node.tail)
    return " ".join("".join(parts).split())


def _section_title(section) -> str:
    for child in section:
        if _local(child) == "title":
            return _text_of(child)
    return ""


def _own_blocks(section) -> list[Block]:
    """The paragraphs of the section itself, without the nested sections."""
    blocks: list[Block] = []

    def collect(element) -> None:
        for child in element:
            tag = _local(child)
            if tag in {"title", "section"} or tag in SKIPPED_TAGS:
                continue
            if tag in CONTAINER_TAGS:
                collect(child)
                continue
            if tag in TEXT_TAGS:
                text = _text_of(child)
                if text:
                    blocks.append(Block(kind="paragraph", text=text))

    collect(section)
    return blocks


def flatten_sections(root, language: str = "ru") -> list[Chapter]:
    """Flattens the section tree into a list of chapters in document order.

    FB2 nesting can be arbitrarily deep, while a listener needs a linear list of
    chapters. Every section with a heading becomes a chapter.
    """
    body = None
    for element in root:
        if _local(element) == "body" and element.get("name") is None:
            body = element
            break
    if body is None:
        return []

    chapters: list[Chapter] = []

    def walk(section) -> None:
        title = _section_title(section)
        blocks = _own_blocks(section)
        if title:
            blocks.insert(0, Block(kind="heading", text=title))
        if blocks:
            chapters.append(Chapter(title=title or OPENING_TITLE[language], blocks=blocks))
        for child in section:
            if _local(child) == "section":
                walk(child)

    for child in body:
        if _local(child) == "section":
            walk(child)
    return chapters


def _metadata(root) -> tuple[str, str | None, str]:
    title, author, language = "", None, "ru"
    for description in root:
        if _local(description) != "description":
            continue
        for info in description:
            if _local(info) != "title-info":
                continue
            for field in info:
                tag = _local(field)
                if tag == "book-title":
                    title = _text_of(field)
                elif tag == "author" and author is None:
                    names = [
                        _text_of(part)
                        for part in field
                        if _local(part) in {"first-name", "middle-name", "last-name"}
                    ]
                    author = " ".join(n for n in names if n) or None
                elif tag == "lang":
                    language = (_text_of(field) or "ru").lower()[:2]
    return title, author, language


def _cover(root) -> bytes | None:
    """The cover: <coverpage> points at a <binary> by id, the body is base64."""
    href = ""
    for element in root.iter():
        if _local(element) != "coverpage":
            continue
        for child in element:
            if _local(child) == "image":
                # The attribute lives in the xlink space, and books differ in the namespace.
                for name, value in child.attrib.items():
                    if name.endswith("href"):
                        href = value
                        break
        break
    if not href.startswith("#"):
        return None

    wanted = href[1:]
    for element in root.iter():
        if _local(element) == "binary" and element.get("id") == wanted:
            try:
                return base64.b64decode(element.text or "")
            except (ValueError, binascii.Error):
                return None
    return None


class Fb2Extractor:
    def __init__(self, clean: bool = True, language: str | None = None) -> None:
        self.clean = clean
        # See EpubExtractor: the chosen voice wins over the book metadata.
        self.language = language
        self.report = None

    def extract(self, path: Path, selection: Selection | None = None) -> Document:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        root = etree.parse(str(path), parser).getroot()
        if root is None or _local(root) != "FictionBook":
            raise ValueError(f"this file does not look like FB2: {path.name}")

        title, author, language = _metadata(root)
        language = self.language or language
        if language not in {"ru", "en"}:
            language = "ru"

        chapters = flatten_sections(root, language)
        if selection and selection.chapters:
            wanted = [i for i in selection.chapters if 0 <= i < len(chapters)]
            chapters = [chapters[i] for i in wanted]

        if self.clean:
            for chapter in chapters:
                chapter.title = normalize_for_speech(clean_text(chapter.title), language)
                chapter.blocks = [
                    Block(
                        kind=b.kind,
                        text=normalize_for_speech(clean_text(b.text), language),
                    )
                    for b in chapter.blocks
                    if clean_text(b.text)
                ]

        return Document(
            title=title or path.stem,
            author=author,
            language=language,
            chapters=chapters,
            cover=_cover(root),
        )
