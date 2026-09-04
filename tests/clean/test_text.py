import pytest

from book2audio.clean.text import (
    clean_text,
    join_hyphenated,
    normalize_quotes,
    restore_big_o,
    squeeze_spaces,
)

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


# --- О-большое, потерянное при извлечении ---


def test_big_o_restored_before_letter():
    """В шрифтах технических книг буква O иногда приходит нулём.

    Замер на фикстурах: 15 попаданий в английской технической книге,
    ноль ложных срабатываний в пяти остальных.
    """
    assert restore_big_o("which is just 0(N2 log N).") == "which is just O(N2 log N)."


def test_big_o_restored_before_digit():
    assert restore_big_o("runs in 0(1) time") == "runs in O(1) time"


def test_big_o_survives_a_space_from_typesetting():
    """В реальной книге вёрстка вставляет пробел: '0( s log s)'."""
    assert restore_big_o("is 0( s log s).") == "is O(s log s)."


def test_cyrillic_after_the_paren_is_not_big_o():
    assert restore_big_o("0(ноль) баллов") == "0(ноль) баллов"


def test_plain_zero_in_parentheses_is_left_alone():
    assert restore_big_o("оценка 0 (ноль) баллов") == "оценка 0 (ноль) баллов"
    assert restore_big_o("значение 0(-1) не трогаем") == "значение 0(-1) не трогаем"


def test_zero_not_touched_outside_parentheses():
    assert restore_big_o("ровно 0 попыток") == "ровно 0 попыток"
    assert restore_big_o("в 2010 году") == "в 2010 году"


def test_clean_text_applies_the_repair():
    assert "O(n" in clean_text("sorting is 0(n log n) overall")
