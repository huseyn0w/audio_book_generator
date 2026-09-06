"""The normalization language has to match the voice language.

Английский PDF, нормализованный русскими правилами, читается вслух так:
«Chapter четырнадцать», «ноль( s log s)». Тесты держат это закрытым.
"""

from pathlib import Path

import pytest

from book2audio.extract.epub import EpubExtractor
from book2audio.extract.fb2 import Fb2Extractor
from book2audio.extract.pdf import PdfExtractor
from book2audio.pipeline import pick_extractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def all_text(document) -> str:
    return " ".join(b.text for c in document.chapters for b in c.blocks)


def cyrillic_share(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ") / len(letters)


def test_english_pdf_is_not_normalized_in_russian():
    document = PdfExtractor(language="en").extract(FIXTURES / "typeset_en.pdf")
    assert cyrillic_share(all_text(document)) < 0.01


def test_english_pdf_reports_english():
    document = PdfExtractor(language="en").extract(FIXTURES / "typeset_en.pdf")
    assert document.language == "en"


def test_russian_pdf_still_normalized_in_russian():
    document = PdfExtractor(language="ru").extract(FIXTURES / "typeset_ru.pdf")
    assert cyrillic_share(all_text(document)) > 0.9


def test_pdf_defaults_to_russian_when_language_is_not_given():
    document = PdfExtractor().extract(FIXTURES / "typeset_ru.pdf")
    assert document.language == "ru"


def test_english_numbers_become_english_words():
    document = PdfExtractor(language="en").extract(FIXTURES / "typeset_en.pdf")
    text = all_text(document)
    assert "четырнадцать" not in text
    assert "ноль" not in text


@pytest.mark.parametrize("suffix", [".pdf", ".epub", ".fb2"])
def test_pick_extractor_passes_the_language_through(suffix):
    extractor = pick_extractor(Path(f"book{suffix}"), clean=True, language="en")
    assert extractor.language == "en"


def test_user_language_wins_over_epub_metadata():
    """The user picks the voice, and the text has to be normalized for it."""
    document = EpubExtractor(language="en").extract(FIXTURES / "book_ru.epub")
    assert document.language == "en"


def test_fb2_falls_back_to_metadata_without_an_explicit_language():
    document = Fb2Extractor().extract(FIXTURES / "book_ru.fb2")
    assert document.language == "ru"
