"""The interface in two languages.

English by default. Russian strings must not arrive from the server: the client
picks the labels, the server hands back data and stable keys.
"""

import json
import re
from pathlib import Path

import pytest

STATIC = Path("book2audio/web/static")


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def dictionaries() -> dict:
    """Pulls the dictionaries out of i18n.js without starting a browser."""
    source = read("i18n.js")
    match = re.search(r"const STRINGS = (\{.*?\n\});", source, re.DOTALL)
    assert match, "STRINGS not found in i18n.js"
    return json.loads(match.group(1))


# --- the dictionaries ---


def test_both_languages_exist():
    assert set(dictionaries()) == {"en", "ru"}


def test_no_key_is_missing_in_either_language():
    data = dictionaries()
    assert set(data["en"]) == set(data["ru"])


def test_no_value_is_empty():
    for lang, table in dictionaries().items():
        for key, value in table.items():
            assert value.strip(), f"{lang}.{key} is empty"


def test_english_has_no_cyrillic():
    for key, value in dictionaries()["en"].items():
        assert not re.search(r"[А-Яа-яЁё]", value), f"cyrillic in en.{key}: {value}"


def test_russian_is_actually_russian():
    """Half the dictionary in Latin would mean an unfinished translation."""
    table = dictionaries()["ru"]
    cyrillic = sum(1 for v in table.values() if re.search(r"[А-Яа-яЁё]", v))
    assert cyrillic > len(table) * 0.7


# --- the markup ---


def test_markup_has_no_hardcoded_russian():
    html = read("index.html")
    body = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    leftovers = re.findall(r"[А-Яа-яЁё][А-Яа-яЁё ,.:—«»()!?-]{3,}", body)
    assert not leftovers, f"russian text in the markup: {leftovers[:5]}"


def test_page_starts_in_english():
    assert '<html lang="en">' in read("index.html")


def test_every_translatable_node_is_marked():
    html = read("index.html")
    assert 'data-i18n="upload.title"' in html
    assert "data-i18n-placeholder" in html
    assert "data-i18n-aria" in html


def test_header_has_a_language_switch():
    html = read("index.html")
    assert 'id="ui-language"' in html
    assert "<header" in html.split('id="ui-language"')[0].rsplit("</header>", 1)[0]


# --- the script ---


def test_script_has_no_hardcoded_russian():
    js = read("app.js")
    code = re.sub(r"//.*", "", js)
    # All three kinds of quotes: Russian text slipped through template strings.
    leftovers = re.findall(r'"[^"\n]*[А-Яа-яЁё][^"\n]*"', code)
    leftovers += re.findall(r"'[^'\n]*[А-Яа-яЁё][^'\n]*'", code)
    leftovers += re.findall(r"`[^`]*[А-Яа-яЁё][^`]*`", code)
    assert not leftovers, f"russian strings in app.js: {leftovers[:5]}"


def test_choice_is_remembered():
    assert "localStorage" in read("i18n.js")


def test_default_language_is_english():
    js = read("i18n.js")
    assert re.search(r'DEFAULT_LANGUAGE\s*=\s*"en"', js)


@pytest.mark.parametrize("key", ["upload.title", "review.title", "progress.title", "done.title"])
def test_screen_titles_are_translated(key):
    assert key in dictionaries()["en"]


def test_language_name_and_letter_form_are_separate():
    """«88% букв английский» is a calque. Letters need a form of their own."""
    ru = dictionaries()["ru"]
    assert ru["review.languageEn"] == "английский"
    assert ru["review.lettersEn"] == "английские"
    js = read("app.js")
    assert 'expected: t(expected === "ru" ? "review.languageRu"' in js
    assert 'found: t(found === "ru" ? "review.lettersRu"' in js


def test_the_start_button_names_the_action():
    """ "Read it aloud" never said that pressing it starts the conversion."""
    assert "start" in dictionaries()["en"]["review.synthesize"].lower()
