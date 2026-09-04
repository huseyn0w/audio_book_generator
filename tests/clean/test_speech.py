import pytest

from book2audio.clean.speech import (
    expand_abbreviations,
    normalize_for_speech,
    numbers_to_words,
    roman_to_words,
    strip_urls,
)

# --- числа ---


def test_plain_number_becomes_words_in_russian():
    assert numbers_to_words("было 23 человека", "ru") == "было двадцать три человека"


def test_plain_number_becomes_words_in_english():
    assert numbers_to_words("there were 23 people", "en") == "there were twenty-three people"


def test_year_is_read_as_a_year():
    assert "тысяча восемьсот шестьдесят первом" in numbers_to_words("в 1861 году", "ru")


def test_percent_is_read_as_a_word():
    assert numbers_to_words("рост 45%", "ru") == "рост сорок пять процентов"


def test_large_number_is_expanded():
    assert numbers_to_words("1000000 рублей", "ru").startswith("один миллион")


def test_decimal_number_is_expanded():
    assert "целых" in numbers_to_words("3,5 килограмма", "ru")


def test_number_glued_to_letters_is_left_alone():
    """A4 и COVID19 читать по частям бессмысленно."""
    assert numbers_to_words("формат A4", "ru") == "формат A4"


# --- римские цифры ---


def test_roman_numeral_in_a_heading_becomes_a_number():
    assert roman_to_words("Глава XIV", "ru") == "Глава 14"


def test_roman_century_is_converted():
    assert roman_to_words("в IV в. нашей эры", "ru") == "в 4 в. нашей эры"


def test_english_pronoun_i_is_not_a_roman_numeral():
    assert roman_to_words("I went home", "en") == "I went home"


def test_word_in_capitals_is_not_a_roman_numeral():
    assert roman_to_words("МВД и ЦИК", "ru") == "МВД и ЦИК"


# --- сокращения ---


@pytest.mark.parametrize(
    ("short", "full"),
    [
        ("т.е.", "то есть"),
        ("т.д.", "так далее"),
        ("т.п.", "тому подобное"),
        ("стр.", "страница"),
        ("см.", "смотри"),
        ("др.", "другие"),
    ],
)
def test_russian_abbreviations_are_expanded(short, full):
    assert expand_abbreviations(f"текст {short} дальше", "ru") == f"текст {full} дальше"


@pytest.mark.parametrize(
    ("short", "full"),
    [("e.g.", "for example"), ("i.e.", "that is"), ("Fig.", "Figure")],
)
def test_english_abbreviations_are_expanded(short, full):
    assert expand_abbreviations(f"text {short} more", "en") == f"text {full} more"


def test_abbreviation_inside_a_word_is_not_touched():
    assert expand_abbreviations("АЛГОРИТМ", "ru") == "АЛГОРИТМ"


# --- ссылки ---


def test_url_becomes_a_word():
    assert strip_urls("см. https://example.com/page тут", "ru") == "см. ссылка тут"


def test_email_becomes_a_word():
    assert strip_urls("пишите на a@b.com сюда", "ru") == "пишите на ссылка сюда"


def test_plain_text_is_untouched_by_url_rule():
    assert strip_urls("обычный текст", "ru") == "обычный текст"


# --- всё вместе ---


def test_full_normalization_applies_every_rule():
    result = normalize_for_speech("Глава XIV, стр. 45, т.е. https://a.b", "ru")
    assert "четырнадцать" in result
    assert "страница" in result
    assert "то есть" in result
    assert "ссылка" in result
    assert "XIV" not in result


def test_normalization_is_idempotent():
    once = normalize_for_speech("В 1861 году, т.е. давно", "ru")
    assert normalize_for_speech(once, "ru") == once


def test_normalization_keeps_ordinary_prose_intact():
    text = "Она вышла на улицу и долго смотрела вслед."
    assert normalize_for_speech(text, "ru") == text


# --- падежи года ---


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("в 1861 году", "в тысяча восемьсот шестьдесят первом году"),
        ("к 1980 году", "к тысяча девятьсот восьмидесятому году"),
        ("до 1917 года", "до тысяча девятьсот семнадцатого года"),
        ("с 1991 года", "с тысяча девятьсот девяносто первого года"),
        ("в 2003 году", "в две тысячи третьем году"),
    ],
)
def test_year_agrees_with_the_preposition(phrase, expected):
    """Без склонения выходит «в тысяча восемьсот первый году», это режет слух."""
    assert numbers_to_words(phrase, "ru") == expected
