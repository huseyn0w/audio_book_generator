from pathlib import Path

import pytest

from book2audio.extract.base import NoTextLayer
from book2audio.extract.layout import RawBlock
from book2audio.extract.pdf import PdfExtractor, read_pages, split_into_chapters
from book2audio.models import Selection

FIXTURES = Path(__file__).parent.parent / "fixtures"
TOC_PDF = FIXTURES / "toc_ru.pdf"
NO_TOC_PDF = FIXTURES / "no_toc_ru.pdf"
SCANNED_PDF = FIXTURES / "scanned_ru.pdf"


# --- чтение страниц ---


def test_read_pages_returns_one_page_per_pdf_page():
    pages = read_pages(TOC_PDF)
    assert len(pages) == 9
    assert [p.number for p in pages] == list(range(1, 10))


def test_read_pages_keeps_font_size_and_bbox():
    blocks = [b for p in read_pages(TOC_PDF) for b in p.blocks]
    assert all(b.font_size > 0 for b in blocks)
    assert all(b.bbox[3] > b.bbox[1] for b in blocks)


def test_read_pages_collapses_broken_spacing():
    """У части PDF текст извлекается с рваными пробелами между словами."""
    blocks = [b for p in read_pages(NO_TOC_PDF) for b in p.blocks]
    assert not any("  " in b.text for b in blocks)


def test_read_pages_honours_page_range():
    pages = read_pages(TOC_PDF, Selection(pages=(2, 4)))
    assert [p.number for p in pages] == [2, 3, 4]


def test_read_pages_rejects_range_past_the_end():
    with pytest.raises(ValueError, match="в документе"):
        read_pages(TOC_PDF, Selection(pages=(50, 60)))


# --- текстовый слой ---


def test_extract_raises_on_scanned_pdf():
    with pytest.raises(NoTextLayer, match="OCR"):
        PdfExtractor().extract(SCANNED_PDF)


# --- главы ---


def test_extract_uses_pdf_bookmarks_when_present():
    doc = PdfExtractor().extract(TOC_PDF)
    assert [c.title for c in doc.chapters] == [
        "Глава 1 Императив роста",
        "Инновации: «черный ящик»?",
    ]


def test_extract_reads_metadata():
    doc = PdfExtractor().extract(TOC_PDF)
    assert "инноваций" in doc.title
    assert doc.author and "Кристенсен" in doc.author
    assert doc.language == "ru"


def test_extract_falls_back_to_font_size_without_bookmarks():
    doc = PdfExtractor().extract(NO_TOC_PDF)
    assert len(doc.chapters) >= 1
    assert doc.char_count() > 1000


def test_split_into_chapters_treats_large_font_as_heading():
    def blk(text, size, page=1):
        return RawBlock(text=text, font_size=size, bbox=(0, 0, 100, 10), page=page)

    blocks = [
        blk("Обычный абзац подлиннее, чтобы задать медиану", 13.0),
        blk("Глава вторая", 20.0),
        blk("Ещё один обычный абзац такой же длины примерно", 13.0),
    ]
    chapters = split_into_chapters(blocks, median=13.0)
    assert [c.title for c in chapters] == ["Без названия", "Глава вторая"]
    assert chapters[1].blocks[0].kind == "heading"


def test_split_into_chapters_ignores_long_lines_in_large_font():
    """Крупный шрифт на длинном тексте это не заголовок, а врезка."""

    def blk(text, size):
        return RawBlock(text=text, font_size=size, bbox=(0, 0, 100, 10), page=1)

    long_text = "слово " * 60
    chapters = split_into_chapters([blk(long_text, 20.0)], median=13.0)
    assert len(chapters) == 1
    assert chapters[0].blocks[0].kind == "paragraph"


# --- протокол ---


def test_pdf_extractor_produces_blocks_with_page_numbers():
    doc = PdfExtractor().extract(TOC_PDF, Selection(pages=(1, 3)))
    pages = {b.page for c in doc.chapters for b in c.blocks}
    assert pages <= {1, 2, 3}
