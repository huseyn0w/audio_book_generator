"""Извлечение FB2. Самый простой из трёх форматов: разметка уже всё сказала.

Тяжёлые эвристики фазы 2 здесь не нужны, шрифтов и координат в FB2 нет.
Прогоняем только правку текста и нормализацию под речь.
"""

import base64
import binascii
from pathlib import Path

from lxml import etree

from book2audio.clean.speech import normalize_for_speech
from book2audio.clean.text import clean_text
from book2audio.models import Block, Chapter, Document, Selection

# Теги, которые в озвучку не идут. Таблицы вслух бессмысленны, аннотация
# это издательская врезка, text-author это подпись под цитатой.
SKIPPED_TAGS = frozenset({"table", "annotation", "image", "text-author"})

# Обёртки, внутрь которых надо зайти. Сверка объёмов FB2 и EPUB одной книги
# показала, что в <cite> лежат резюме глав по 400-1400 символов, то есть
# настоящее содержание, а не служебная врезка.
CONTAINER_TAGS = frozenset({"cite", "epigraph", "poem", "stanza"})

TEXT_TAGS = frozenset({"p", "subtitle", "v"})


def _local(element) -> str:
    return etree.QName(element).localname


def _text_of(element) -> str:
    """Собирает текст элемента, выбрасывая ссылки на примечания."""
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
    """Абзацы самой секции, без вложенных секций."""
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


def flatten_sections(root) -> list[Chapter]:
    """Разворачивает дерево секций в плоский список глав в порядке документа.

    Вложенность в FB2 бывает произвольной глубины, а слушателю нужен
    линейный список глав. Каждая секция с заголовком становится главой.
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
            chapters.append(Chapter(title=title or "Начало", blocks=blocks))
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
    """Обложка: <coverpage> ссылается на <binary> по id, тело в base64."""
    href = ""
    for element in root.iter():
        if _local(element) != "coverpage":
            continue
        for child in element:
            if _local(child) == "image":
                # Атрибут в пространстве xlink, а namespace в книгах разный.
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
        # См. EpubExtractor: выбранный голос главнее метаданных книги.
        self.language = language
        self.report = None

    def extract(self, path: Path, selection: Selection | None = None) -> Document:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        root = etree.parse(str(path), parser).getroot()
        if root is None or _local(root) != "FictionBook":
            raise ValueError(f"файл не похож на FB2: {path.name}")

        title, author, language = _metadata(root)
        language = self.language or language
        if language not in {"ru", "en"}:
            language = "ru"

        chapters = flatten_sections(root)
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
