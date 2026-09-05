"""Интерфейс на двух языках.

По умолчанию английский. Русские строки не должны приезжать с сервера:
подписи выбирает клиент, сервер отдаёт данные и устойчивые ключи.
"""

import json
import re
from pathlib import Path

import pytest

STATIC = Path("book2audio/web/static")


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def dictionaries() -> dict:
    """Достаёт словари из i18n.js без запуска браузера."""
    source = read("i18n.js")
    match = re.search(r"const STRINGS = (\{.*?\n\});", source, re.DOTALL)
    assert match, "не нашёл STRINGS в i18n.js"
    return json.loads(match.group(1))


# --- словари ---


def test_both_languages_exist():
    assert set(dictionaries()) == {"en", "ru"}


def test_no_key_is_missing_in_either_language():
    data = dictionaries()
    assert set(data["en"]) == set(data["ru"])


def test_no_value_is_empty():
    for lang, table in dictionaries().items():
        for key, value in table.items():
            assert value.strip(), f"{lang}.{key} пустой"


def test_english_has_no_cyrillic():
    for key, value in dictionaries()["en"].items():
        assert not re.search(r"[А-Яа-яЁё]", value), f"кириллица в en.{key}: {value}"


def test_russian_is_actually_russian():
    """Половина словаря латиницей значила бы незаконченный перевод."""
    table = dictionaries()["ru"]
    cyrillic = sum(1 for v in table.values() if re.search(r"[А-Яа-яЁё]", v))
    assert cyrillic > len(table) * 0.7


# --- разметка ---


def test_markup_has_no_hardcoded_russian():
    html = read("index.html")
    body = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    leftovers = re.findall(r"[А-Яа-яЁё][А-Яа-яЁё ,.:—«»()!?-]{3,}", body)
    assert not leftovers, f"русский текст в разметке: {leftovers[:5]}"


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


# --- скрипт ---


def test_script_has_no_hardcoded_russian():
    js = read("app.js")
    code = re.sub(r"//.*", "", js)
    # Все три вида кавычек: русский текст пролезал через шаблонные строки.
    leftovers = re.findall(r'"[^"\n]*[А-Яа-яЁё][^"\n]*"', code)
    leftovers += re.findall(r"'[^'\n]*[А-Яа-яЁё][^'\n]*'", code)
    leftovers += re.findall(r"`[^`]*[А-Яа-яЁё][^`]*`", code)
    assert not leftovers, f"русские строки в app.js: {leftovers[:5]}"


def test_choice_is_remembered():
    assert "localStorage" in read("i18n.js")


def test_default_language_is_english():
    js = read("i18n.js")
    assert re.search(r'DEFAULT_LANGUAGE\s*=\s*"en"', js)


@pytest.mark.parametrize("key", ["upload.title", "review.title", "progress.title", "done.title"])
def test_screen_titles_are_translated(key):
    assert key in dictionaries()["en"]


def test_language_name_and_letter_form_are_separate():
    """«88% букв английский» это калька. Для букв нужна своя форма."""
    ru = dictionaries()["ru"]
    assert ru["review.languageEn"] == "английский"
    assert ru["review.lettersEn"] == "английские"
    js = read("app.js")
    assert 'expected: t(expected === "ru" ? "review.languageRu"' in js
    assert 'found: t(found === "ru" ? "review.lettersRu"' in js
