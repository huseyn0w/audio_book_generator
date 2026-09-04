"""Извлечение PDF через PyMuPDF.

Берём get_text("dict"), а не голый текст: словарь отдаёт размер шрифта,
начертание и координаты каждого спана. Фаза 2 без этих данных не отличит
колонтитул от абзаца, поэтому терять их нельзя.
"""

from pathlib import Path

import pymupdf

from book2audio.extract.base import NoTextLayer
from book2audio.extract.layout import RawBlock, RawPage, median_font_size
from book2audio.models import Block, Chapter, Document, Selection

# Ниже этого числа символов на страницу считаем, что текстового слоя нет.
MIN_CHARS_PER_PAGE = 100

# Во сколько раз шрифт заголовка крупнее медианного.
HEADING_FONT_RATIO = 1.15

# Заголовок это короткая строка. Длинный текст крупным шрифтом это врезка.
HEADING_MAX_CHARS = 120

MONOSPACED_FLAG = 8


def _block_text(raw: dict) -> str:
    """Склеивает спаны блока и убирает рваные пробелы.

    Часть PDF отдаёт текст с пробелом между каждой парой букв. Это артефакт
    извлечения, а не содержание, поэтому чиним здесь, а не в фазе 2.
    """
    parts = [span["text"] for line in raw.get("lines", []) for span in line["spans"]]
    return " ".join("".join(parts).split())


def _block_font_size(raw: dict) -> float:
    sizes = [span["size"] for line in raw.get("lines", []) for span in line["spans"]]
    return max(sizes) if sizes else 0.0


def _block_is_mono(raw: dict) -> bool:
    flags = [span["flags"] for line in raw.get("lines", []) for span in line["spans"]]
    return bool(flags) and all(f & MONOSPACED_FLAG for f in flags)


def read_pages(path: Path, selection: Selection | None = None) -> list[RawPage]:
    """Читает страницы PDF в сырую раскладку. Страницы вне диапазона не открываются."""
    doc = pymupdf.open(path)
    try:
        wanted = selection.page_indexes() if selection else list(range(doc.page_count))
        if not wanted:
            wanted = list(range(doc.page_count))
        if wanted[-1] >= doc.page_count:
            raise ValueError(
                f"страница {wanted[-1] + 1} за пределами документа, в документе {doc.page_count}"
            )

        pages: list[RawPage] = []
        for index in wanted:
            page = doc[index]
            blocks: list[RawBlock] = []
            for raw in page.get_text("dict", sort=True)["blocks"]:
                text = _block_text(raw)
                if not text:
                    continue
                blocks.append(
                    RawBlock(
                        text=text,
                        font_size=_block_font_size(raw),
                        bbox=tuple(raw["bbox"]),
                        page=index + 1,
                        is_mono=_block_is_mono(raw),
                    )
                )
            pages.append(
                RawPage(
                    number=index + 1,
                    width=page.rect.width,
                    height=page.rect.height,
                    blocks=blocks,
                )
            )
        return pages
    finally:
        doc.close()


def _is_heading(block: RawBlock, median: float) -> bool:
    return block.font_size >= median * HEADING_FONT_RATIO and len(block.text) <= HEADING_MAX_CHARS


def split_into_chapters(blocks: list[RawBlock], median: float) -> list[Chapter]:
    """Режет поток блоков на главы по крупному шрифту. Запасной путь без закладок."""
    chapters: list[Chapter] = []
    current = Chapter(title="Без названия", blocks=[])

    for raw in blocks:
        if _is_heading(raw, median):
            if current.blocks:
                chapters.append(current)
            current = Chapter(
                title=raw.text,
                blocks=[Block(kind="heading", text=raw.text, page=raw.page)],
            )
        else:
            current.blocks.append(Block(kind="paragraph", text=raw.text, page=raw.page))

    if current.blocks:
        chapters.append(current)
    return chapters


def _chapters_from_toc(toc: list[list], blocks: list[RawBlock], first_page: int) -> list[Chapter]:
    """Режет блоки по страницам, на которых начинаются закладки."""
    starts = [(page, title) for _level, title, page in toc if page >= first_page]
    if not starts:
        return []

    chapters: list[Chapter] = []
    for position, (page, title) in enumerate(starts):
        next_page = starts[position + 1][0] if position + 1 < len(starts) else None
        inside = [b for b in blocks if b.page >= page and (next_page is None or b.page < next_page)]
        if not inside:
            continue
        chapters.append(
            Chapter(
                title=title,
                blocks=[Block(kind="paragraph", text=b.text, page=b.page) for b in inside],
            )
        )
    return chapters


class PdfExtractor:
    def extract(self, path: Path, selection: Selection | None = None) -> Document:
        pages = read_pages(path, selection)
        blocks = [b for p in pages for b in p.blocks]

        chars_per_page = sum(len(b.text) for b in blocks) / max(1, len(pages))
        if chars_per_page < MIN_CHARS_PER_PAGE:
            raise NoTextLayer(
                f"в PDF нет текстового слоя ({chars_per_page:.0f} символов на страницу). "
                "Похоже, это скан. Нужен OCR, а он за рамками проекта."
            )

        doc = pymupdf.open(path)
        try:
            toc = doc.get_toc()
            meta = dict(doc.metadata or {})
        finally:
            doc.close()

        chapters = _chapters_from_toc(toc, blocks, pages[0].number) if toc else []
        if not chapters:
            chapters = split_into_chapters(blocks, median_font_size(blocks))

        return Document(
            title=meta.get("title") or path.stem,
            author=meta.get("author") or None,
            language="ru",
            chapters=chapters,
        )
