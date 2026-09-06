"""Checking that the chosen language matches the script of the book.

Порог взят из замера на шести фикстурах: русские книги дают 98.2-100%
кириллицы, английская 87.8% латиницы. Между 12% и 88% пустое место,
поэтому граница в 25% чужого письма ни одну из них не задевает.
"""

import pytest

from book2audio.script_check import FOREIGN_LIMIT, foreign_share, language_warning


def test_pure_russian_has_no_foreign_letters():
    assert foreign_share("Обычный русский текст без латиницы.", "ru") == 0.0


def test_pure_english_has_no_foreign_letters():
    assert foreign_share("Plain English text with no Cyrillic.", "en") == 0.0


def test_foreign_share_counts_only_letters():
    """Digits and marks are not a script, they are the same in both languages."""
    assert foreign_share("2026 год, 15% — это много!", "ru") == 0.0


def test_english_inside_russian_is_measured():
    """Exactly ten letters: «Слово» five, «и» one, "word" four."""
    assert foreign_share("Слово и word", "ru") == pytest.approx(0.4, rel=0.01)


def test_empty_text_is_not_a_problem():
    assert foreign_share("", "ru") == 0.0
    assert language_warning("", "ru") is None


def test_no_warning_for_a_few_borrowed_words():
    """1.8% Latin is normal for Russian nonfiction, measured on the fixtures."""
    text = "Русский текст " * 100 + "startup"
    assert language_warning(text, "ru") is None


def test_warning_when_the_book_is_in_the_other_language():
    """We hand back data, not a phrase: the interface may be in a third language."""
    warning = language_warning("This book is written in English " * 20, "ru")
    assert warning == {"expected": "ru", "found": "en", "share": 1.0}


def test_warning_the_other_way_round():
    warning = language_warning("Эта книга написана по-русски " * 20, "en")
    assert warning["expected"] == "en"
    assert warning["found"] == "ru"
    assert warning["share"] > 0.9


def test_limit_sits_between_the_measured_groups():
    assert 0.13 < FOREIGN_LIMIT < 0.87


@pytest.mark.parametrize(
    "name,language",
    [
        ("book_ru.fb2", "ru"),
        ("book_ru.epub", "ru"),
        ("toc_ru.pdf", "ru"),
        ("typeset_ru.pdf", "ru"),
        ("typeset_en.pdf", "en"),
    ],
)
def test_real_fixtures_raise_no_false_alarm(name, language):
    from pathlib import Path

    from book2audio.pipeline import pick_extractor

    path = Path(__file__).parent / "fixtures" / name
    document = pick_extractor(path, clean=True, language=language).extract(path)
    text = " ".join(b.text for c in document.chapters for b in c.blocks)
    assert language_warning(text, language) is None
