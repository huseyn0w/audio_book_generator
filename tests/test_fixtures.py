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
