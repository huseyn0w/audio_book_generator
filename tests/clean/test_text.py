import pytest

from book2audio.clean.text import clean_text, join_hyphenated, normalize_quotes, squeeze_spaces

# --- переносы ---


def test_hyphen_at_line_break_joins_the_word():
    assert join_hyphenated("госу- дарство") == "государство"


def test_hyphen_before_capital_is_kept():
    """Красно-Белый это составное слово, а не перенос."""
    assert join_hyphenated("Красно- Белый") == "Красно-Белый"


def test_hyphen_between_words_is_kept():
    assert join_hyphenated("что-то важное") == "что-то важное"


def test_english_hyphenation_joins_too():
    assert join_hyphenated("govern- ment") == "government"


def test_multiple_hyphenations_in_one_paragraph():
    assert join_hyphenated("рас- сказ и по- весть") == "рассказ и повесть"


def test_hyphen_at_the_very_end_survives():
    assert join_hyphenated("оборванный пере-") == "оборванный пере-"


def test_double_hyphen_is_not_a_line_break():
    assert join_hyphenated("текст -- ещё текст") == "текст -- ещё текст"


# --- кавычки и пробелы ---


@pytest.mark.parametrize("quoted", ['"слово"', "«слово»", "“слово”", "„слово“"])
def test_quotes_are_normalized_to_one_form(quoted):
    assert normalize_quotes(quoted) == "«слово»"


def test_apostrophes_are_normalized():
    assert normalize_quotes("don’t") == "don't"


def test_squeeze_collapses_runs_of_spaces():
    assert squeeze_spaces("много     пробелов") == "много пробелов"


def test_squeeze_replaces_non_breaking_space():
    assert squeeze_spaces("нераз рывный") == "нераз рывный"


def test_squeeze_turns_single_newline_into_space():
    assert squeeze_spaces("строка\nдругая") == "строка другая"


def test_squeeze_strips_edges():
    assert squeeze_spaces("  край  ") == "край"


# --- всё вместе ---


def test_clean_text_applies_every_rule():
    dirty = 'госу- дарство   и  "порядок"\nдальше'
    assert clean_text(dirty) == "государство и «порядок» дальше"


def test_clean_text_is_idempotent():
    once = clean_text('госу- дарство  "тут"')
    assert clean_text(once) == once


def test_clean_text_keeps_meaningful_dashes():
    assert clean_text("Москва — столица.") == "Москва — столица."
