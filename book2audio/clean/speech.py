"""Приведение текста к виду, который движок прочитает правильно.

Работает со строками, поэтому годится для любого формата книги.
Ударения не наша забота: Silero v5 расставляет их сам.
"""

import re

from num2words import num2words

# Сокращения раскрываем до постановки чисел: «стр. 45» должно стать
# «страница сорок пять», а не «страница 45».
ABBREVIATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "т.е.": "то есть",
        "т.д.": "так далее",
        "т.п.": "тому подобное",
        "т.к.": "так как",
        "стр.": "страница",
        "см.": "смотри",
        "др.": "другие",
        "гг.": "годы",
        "вв.": "века",
    },
    "en": {
        "e.g.": "for example",
        "i.e.": "that is",
        "Fig.": "Figure",
        "fig.": "figure",
        "etc.": "et cetera",
        "vs.": "versus",
    },
}

URL = re.compile(r"\b(?:https?://|www\.)\S+|\b[\w.+-]+@[\w-]+\.[\w.]+\b")

# Число, не приклеенное к букве: «A4» и «COVID19» читать по частям нельзя.
NUMBER = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![\w])")

PERCENT = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*%")

# Год с предлогом: «в 1861 году», «до 1917 года», «к 1980 году».
YEAR_CONTEXT = re.compile(r"\b(в|к|с|до|от|после|за|на)\s+(\d{4})\s+(год\w*)", re.IGNORECASE)

# Русский порядковый числительный надо просклонять, иначе выходит
# «в тысяча восемьсот шестьдесят первый году». На слух это режет сразу.
# Ключ это предлог плюс форма слова «год», значение это окончания
# для основ на -ый/-ой и на -ий.
ORDINAL_ENDINGS: dict[str, tuple[str, str]] = {
    "предложный": ("ом", "ьем"),
    "дательный": ("ому", "ьему"),
    "родительный": ("ого", "ьего"),
    "творительный": ("ым", "ьим"),
    "именительный": ("ый", "ий"),
}

GENITIVE_PREPOSITIONS = {"с", "до", "от", "после"}

# Римская цифра как отдельное слово. Одиночная I слишком часто это местоимение
# или инициал, поэтому требуем минимум два знака.
ROMAN = re.compile(r"\b(?=[MDCLXVI]{2,})(M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3}))\b")

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

PERCENT_WORD = {"ru": "процентов", "en": "percent"}
LINK_WORD = {"ru": "ссылка", "en": "link"}


def strip_urls(text: str, language: str) -> str:
    """Ссылки и почта вслух бесполезны, заменяем одним словом."""
    return URL.sub(LINK_WORD.get(language, "link"), text)


def expand_abbreviations(text: str, language: str) -> str:
    """Раскрывает сокращения. Точка в них иначе ломает разбивку на предложения."""
    for short, full in ABBREVIATIONS.get(language, {}).items():
        text = re.sub(rf"(?<!\w){re.escape(short)}", full, text)
    return text


def _roman_value(numeral: str) -> int:
    total = 0
    previous = 0
    for char in reversed(numeral):
        value = ROMAN_VALUES[char]
        total += value if value >= previous else -value
        previous = max(previous, value)
    return total


def roman_to_words(text: str, language: str) -> str:
    """Переводит римские цифры в арабские. Числами займётся numbers_to_words."""

    def replace(match: re.Match[str]) -> str:
        numeral = match.group(0)
        if not numeral:
            return numeral
        return str(_roman_value(numeral))

    return ROMAN.sub(replace, text)


def _year_case(preposition: str, year_word: str) -> str:
    """Определяет падеж порядкового числительного по предлогу и форме слова «год»."""
    word = year_word.lower()
    preposition = preposition.lower()
    if word.startswith("годом"):
        return "творительный"
    if word.startswith(("года", "годов")):
        return "родительный"
    if preposition in GENITIVE_PREPOSITIONS:
        return "родительный"
    if preposition == "к":
        return "дательный"
    if preposition in {"в", "на"} and word.startswith("году"):
        return "предложный"
    return "именительный"


def _decline_ordinal(spoken: str, case: str) -> str:
    """Меняет окончание последнего слова порядкового числительного."""
    if case == "именительный":
        return spoken
    soft_stem, hard_stem = ORDINAL_ENDINGS[case][1], ORDINAL_ENDINGS[case][0]
    head, _, last = spoken.rpartition(" ")
    if last.endswith("ий"):
        last = last[:-2] + soft_stem
    elif last.endswith(("ый", "ой")):
        last = last[:-2] + hard_stem
    return f"{head} {last}".strip()


def _say(number: str, language: str, ordinal: bool = False) -> str:
    normalized = number.replace(",", ".")
    value = float(normalized) if "." in normalized else int(normalized)
    return num2words(value, lang=language, to="ordinal" if ordinal else "cardinal")


def numbers_to_words(text: str, language: str) -> str:
    """Числа прописью. Годы читаются порядковым числительным."""

    def say_year(match: re.Match[str]) -> str:
        preposition, year, word = match.groups()
        try:
            spoken = _say(year, language, ordinal=True)
        except (NotImplementedError, ValueError):
            return f"{preposition} {_say(year, language)} {word}"
        if language == "ru":
            spoken = _decline_ordinal(spoken, _year_case(preposition, word))
        return f"{preposition} {spoken} {word}"

    def say_percent(match: re.Match[str]) -> str:
        return f"{_say(match.group(1), language)} {PERCENT_WORD.get(language, 'percent')}"

    def say_number(match: re.Match[str]) -> str:
        try:
            return _say(match.group(1), language)
        except (NotImplementedError, ValueError):
            return match.group(1)

    text = YEAR_CONTEXT.sub(say_year, text)
    text = PERCENT.sub(say_percent, text)
    return NUMBER.sub(say_number, text)


def normalize_for_speech(text: str, language: str) -> str:
    """Полная подготовка строки к синтезу. Повторный вызов ничего не меняет."""
    text = strip_urls(text, language)
    text = expand_abbreviations(text, language)
    text = roman_to_words(text, language)
    return numbers_to_words(text, language)
