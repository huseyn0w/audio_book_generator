"""Латиница для русского Silero.

В таблице символов русской модели латинских букв нет: одна буква «e»
из «E*Trade Bank» роняет синтез с KeyError. Замер на книге Кристенсена:
латиница в 27% кусков, 1463 уникальных названия. Выбрасывать их значит
читать «специалисты банк», поэтому переводим в кириллицу.
"""

import pytest

from book2audio.tts.translit import latin_to_cyrillic


def has_latin(text: str) -> bool:
    return any("a" <= c.lower() <= "z" for c in text)


# --- главное свойство: латиницы не остаётся ---


@pytest.mark.parametrize(
    "text",
    [
        "Специалисты E*Trade Bank и Sony Bank",
        "AT&T-Mediaone",
        "Abercrombie&Fitch",
        "IBM, AOL и ATM",
        "Wingspan",
        "Annotation",
        "x86 и Windows 3.11",
        "e-mail",
    ],
)
def test_no_latin_survives(text):
    assert not has_latin(latin_to_cyrillic(text))


# --- аббревиатуры читаются по буквам ---


def test_uppercase_acronym_is_spelled_out():
    assert latin_to_cyrillic("IBM") == "ай-би-эм"


def test_two_letter_acronym_is_spelled_out():
    assert latin_to_cyrillic("AI") == "эй-ай"


def test_ampersand_becomes_and():
    assert latin_to_cyrillic("AT&T") == "эй-ти энд ти"


# --- обычные слова транслитерируются ---


def test_ordinary_word():
    assert latin_to_cyrillic("Sony") == "сони"


def test_digraphs_are_handled():
    assert latin_to_cyrillic("Shell") == "шелл"
    assert latin_to_cyrillic("Microsoft") == "микрософт"


@pytest.mark.parametrize(
    "word,expected",
    [
        ("Sony", "сони"),
        ("Google", "гугл"),
        ("Nike", "найк"),
        ("Coke", "коук"),
        ("Intel", "интел"),
        ("Xerox", "ксерокс"),
        ("Toyota", "тойота"),
    ],
)
def test_common_names_are_recognizable(word, expected):
    """Перевод приблизительный: английской фонетики побуквенно не будет.
    Планка такая: имя должно быть узнаваемо на слух."""
    assert latin_to_cyrillic(word) == expected


def test_silent_e_is_not_pronounced():
    """«гугле» и «аппле» звучат нелепо, немая e на конце убирается."""
    assert latin_to_cyrillic("Google") == "гугл"
    assert latin_to_cyrillic("Apple") == "аппл"


def test_single_capital_letter_is_a_word_not_an_acronym():
    """Инициал «A.» не должен превращаться в «эй-...»."""
    assert latin_to_cyrillic("A.") == "эй."


# --- что трогать нельзя ---


def test_cyrillic_is_untouched():
    assert latin_to_cyrillic("Обычный русский текст") == "Обычный русский текст"


def test_digits_and_punctuation_survive():
    assert latin_to_cyrillic("в 2003 году, 15%") == "в 2003 году, 15%"


def test_mixed_sentence_keeps_russian_words():
    result = latin_to_cyrillic("Компания Intel выпустила процессор.")
    assert "Компания" in result
    assert "выпустила процессор." in result


def test_repeat_application_changes_nothing():
    once = latin_to_cyrillic("Sony Bank")
    assert latin_to_cyrillic(once) == once
