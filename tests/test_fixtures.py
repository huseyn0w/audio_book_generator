"""Фикстуры это вырезки из реальных книг. Пересобираются scripts/make_fixtures.py."""

from pathlib import Path

import pymupdf
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def test_toc_fixture_has_bookmarks_and_metadata():
    doc = pymupdf.open(FIXTURES / "toc_ru.pdf")
    assert doc.page_count >= 3
    assert len(doc.get_toc()) >= 1
    assert doc.metadata["title"]


def test_no_toc_fixture_has_text_but_no_bookmarks():
    doc = pymupdf.open(FIXTURES / "no_toc_ru.pdf")
    assert doc.get_toc() == []
    assert len(doc[0].get_text().strip()) > 200


def test_scanned_fixture_has_no_text_layer():
    doc = pymupdf.open(FIXTURES / "scanned_ru.pdf")
    assert all(len(doc[i].get_text().strip()) < 20 for i in range(doc.page_count))


@pytest.mark.parametrize("name", ["toc_ru.pdf", "no_toc_ru.pdf", "scanned_ru.pdf"])
def test_fixtures_stay_small_enough_to_commit(name):
    assert (FIXTURES / name).stat().st_size < 3_000_000


def test_typeset_ru_fixture_has_two_columns_and_small_font():
    from book2audio.extract.layout import median_font_size
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "typeset_ru.pdf")
    blocks = [b for p in pages for b in p.blocks]
    median = median_font_size(blocks)
    small = [b for b in blocks if b.font_size < median * 0.92]
    lefts = sorted(b.bbox[0] for b in blocks)
    width = pages[0].width

    assert len(small) > 20, "нужны сноски мелким шрифтом"
    assert any(x > width * 0.5 for x in lefts), "нужна вторая колонка"


def test_typeset_ru_fixture_has_hyphenated_line_breaks():
    import re

    from book2audio.extract.pdf import read_pages

    blocks = [b for p in read_pages(FIXTURES / "typeset_ru.pdf") for b in p.blocks]
    hyphens = sum(len(re.findall(r"\w-\s+[а-яё]", b.text)) for b in blocks)
    assert hyphens > 10


def test_typeset_en_fixture_has_repeated_running_headers():
    import re
    from collections import Counter

    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "typeset_en.pdf")
    edges = Counter()
    for page in pages:
        if page.blocks:
            for block in (page.blocks[0], page.blocks[-1]):
                edges[re.sub(r"\d+", "#", block.text).strip()[:40]] += 1
    assert max(edges.values()) >= len(pages) * 0.5


@pytest.mark.parametrize("name", ["typeset_ru.pdf", "typeset_en.pdf"])
def test_typeset_fixtures_stay_small_enough_to_commit(name):
    assert (FIXTURES / name).stat().st_size < 3_000_000
