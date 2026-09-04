from pathlib import Path

import pytest

from book2audio.extract.base import NoTextLayer
from book2audio.extract.layout import RawBlock
from book2audio.extract.pdf import (
    PdfExtractor,
    chapters_from_toc,
    read_pages,
    split_into_chapters,
)
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
    doc = PdfExtractor(clean=False).extract(TOC_PDF)
    assert [c.title for c in doc.chapters] == [
        "Глава 1 Императив роста",
        "Инновации: «черный ящик»?",
    ]


def test_extract_normalizes_chapter_titles_for_speech():
    doc = PdfExtractor().extract(TOC_PDF)
    assert doc.chapters[0].title == "Глава первая Императив роста"


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


def test_read_pages_keeps_space_at_line_breaks():
    """Спаны внутри строки склеиваются вплотную, строки между собой через пробел."""
    blocks = [b for p in read_pages(TOC_PDF) for b in p.blocks]
    joined = " ".join(b.text for b in blocks)
    assert "жесткие требования" in joined
    assert "жесткиетребования" not in joined


def test_toc_chapter_marks_its_title_block_as_heading():
    doc = PdfExtractor().extract(TOC_PDF)
    first = doc.chapters[0]
    assert first.blocks[0].kind == "heading"
    assert first.blocks[0].text == first.title


def _raw(text, page, size=13.0):
    return RawBlock(text=text, font_size=size, bbox=(0, 0, 100, 10), page=page)


def test_toc_split_happens_at_the_heading_block_not_the_page_edge():
    """Подглава часто начинается посреди страницы, резать по странице нельзя."""
    blocks = [
        _raw("Хвост первой главы", 5),
        _raw("Ещё хвост первой главы", 5),
        _raw("Вторая глава", 5),
        _raw("Тело второй главы", 5),
    ]
    toc = [[1, "Первая глава", 4], [2, "Вторая глава", 5]]
    chapters = chapters_from_toc(toc, [_raw("Начало", 4), *blocks], first_page=4)

    assert [c.title for c in chapters] == ["Первая глава", "Вторая глава"]
    assert [b.text for b in chapters[0].blocks] == [
        "Начало",
        "Хвост первой главы",
        "Ещё хвост первой главы",
    ]
    assert chapters[1].blocks[0].kind == "heading"
    assert [b.text for b in chapters[1].blocks] == ["Вторая глава", "Тело второй главы"]


def test_toc_split_falls_back_to_page_start_when_title_not_found():
    """Заголовок в тексте может быть свёрстан иначе, чем в закладке."""
    blocks = [_raw("Текст четвёртой", 4), _raw("Текст пятой", 5)]
    toc = [[1, "Первая", 4], [1, "Совсем другое название", 5]]
    chapters = chapters_from_toc(toc, blocks, first_page=4)

    assert [b.text for b in chapters[1].blocks] == ["Текст пятой"]
    assert chapters[1].blocks[0].kind == "paragraph"


def test_no_chapter_title_is_read_twice_on_the_real_book():
    doc = PdfExtractor().extract(TOC_PDF)
    for chapter in doc.chapters:
        matching = [b for b in chapter.blocks if b.text.strip() == chapter.title.strip()]
        assert len(matching) <= 1
        if matching:
            assert matching[0] is chapter.blocks[0]
