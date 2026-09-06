"""Bringing the text to a form the engine will read correctly.

Работает со строками, поэтому годится для любого формата книги.
Ударения не наша забота: Silero v5 расставляет их сам.
"""

import re

from num2words import num2words

# Abbreviations expand before the numbers are spelled out: «стр. 45» has to become
# «страница сорок пять», not «страница 45».
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

# A number not glued to a letter: «A4» and «COVID19» must not be read in pieces.
NUMBER = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![\w])")

PERCENT = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*%")

# A year with a preposition: «в 1861 году», «до 1917 года», «к 1980 году».
YEAR_CONTEXT = re.compile(r"\b(в|к|с|до|от|после|за|на)\s+(\d{4})\s+(год\w*)", re.IGNORECASE)

# A Russian ordinal has to be declined, otherwise you get «в тысяча восемьсот
# шестьдесят первый году», which grates the moment you hear it. The key is the
# preposition plus the form of «год», the value is the endings for stems in
# -ый/-ой and in -ий.
ORDINAL_ENDINGS: dict[str, tuple[str, str]] = {
    "предложный": ("ом", "ьем"),
    "дательный": ("ому", "ьему"),
    "родительный": ("ого", "ьего"),
    "творительный": ("ым", "ьим"),
    "именительный": ("ый", "ий"),
}

GENITIVE_PREPOSITIONS = {"с", "до", "от", "после"}

# «Глава 1» has to be read «Глава первая», not «Глава один». You hear it at every
# chapter boundary, so it is a rule of its own. The gender comes from the word.
HEADING_WORDS_FEMININE = ("глава", "часть", "книга")
HEADING_WORDS_MASCULINE = ("раздел", "том")
HEADING_ORDINAL = re.compile(r"\b(Глава|Часть|Книга|Раздел|Том)\s+(\d{1,3})\b", re.IGNORECASE)

# A Roman numeral as a separate word. A lone I is far too often a pronoun or an
# initial, so we require at least two characters.
ROMAN = re.compile(r"\b(?=[MDCLXVI]{2,})(M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3}))\b")

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

# A century in Roman numerals. «III в.» as «три век» turns it into a count, so the
# century is handled before the general Roman numeral rule.
ROMAN_PART = r"(?=[MDCLXVI]{1,7}\b)M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
CENTURY = re.compile(
    rf"(?:\b(в|к|с|до|от|после|на)\s+)?({ROMAN_PART})(?:\s*[—–-]\s*({ROMAN_PART}))?"
    r"\s+(вв?\.|век[аеовх]*)",
    re.IGNORECASE,
)

PERCENT_WORD = {"ru": "процентов", "en": "percent"}
LINK_WORD = {"ru": "ссылка", "en": "link"}


def strip_urls(text: str, language: str) -> str:
    """Links and email are useless read aloud, so one word replaces them."""
    return URL.sub(LINK_WORD.get(language, "link"), text)


def expand_abbreviations(text: str, language: str) -> str:
    """Expands abbreviations. Their period otherwise breaks sentence splitting."""
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
    """Turns Roman numerals into Arabic. numbers_to_words deals with the numbers."""

    def replace(match: re.Match[str]) -> str:
        numeral = match.group(0)
        if not numeral:
            return numeral
        return str(_roman_value(numeral))

    return ROMAN.sub(replace, text)


def _year_case(preposition: str, year_word: str) -> str:
    """Works out the case of the ordinal from the preposition and the form of «год»."""
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
    """Changes the ending of the last word of the ordinal."""
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


def _feminize_ordinal(spoken: str) -> str:
    """первый -> первая, третий -> третья."""
    head, _, last = spoken.rpartition(" ")
    if last.endswith("ий"):
        last = last[:-2] + "ья"
    elif last.endswith(("ый", "ой")):
        last = last[:-2] + "ая"
    return f"{head} {last}".strip()


def headings_to_ordinals(text: str, language: str) -> str:
    """A chapter number is read as an ordinal in the right gender."""
    if language != "ru":
        return text

    def replace_heading(match: re.Match[str]) -> str:
        word, number = match.groups()
        try:
            spoken = _say(number, "ru", ordinal=True)
        except (NotImplementedError, ValueError):
            return match.group(0)
        if word.lower() in HEADING_WORDS_FEMININE:
            spoken = _feminize_ordinal(spoken)
        return f"{word} {spoken}"

    return HEADING_ORDINAL.sub(replace_heading, text)


def centuries_to_words(text: str, language: str) -> str:
    """«IV в.» is read «четвёртом веке», not «четыре век»."""
    if language != "ru":
        return text

    def replace_century(match: re.Match[str]) -> str:
        # The original form of «век» is not needed: the case comes from the preposition.
        preposition, first, second, _ = match.groups()
        head = f"{preposition} " if preposition else ""

        if second:
            case, century = "родительный", "веков"
        elif preposition and preposition.lower() in {"в", "на"}:
            case, century = "предложный", "веке"
        elif preposition and preposition.lower() in GENITIVE_PREPOSITIONS:
            case, century = "родительный", "века"
        else:
            case, century = "именительный", "век"

        numerals = [first] + ([second] if second else [])
        spoken = [
            _decline_ordinal(_say(str(_roman_value(n.upper())), "ru", ordinal=True), case)
            for n in numerals
        ]
        joined = "—".join(spoken)
        return f"{head}{joined} {century}"

    return CENTURY.sub(replace_century, text)


def numbers_to_words(text: str, language: str) -> str:
    """Numbers spelled out. Years are read as ordinals."""

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
    """The full preparation of a line for synthesis. Calling it again changes nothing."""
    text = strip_urls(text, language)
    text = expand_abbreviations(text, language)
    text = centuries_to_words(text, language)
    text = roman_to_words(text, language)
    text = headings_to_ordinals(text, language)
    return numbers_to_words(text, language)
