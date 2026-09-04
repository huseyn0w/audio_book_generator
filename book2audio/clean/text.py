"""Правка текста, не требующая знания вёрстки.

Годится для любого формата, поэтому в фазе 3 переиспользуется
для EPUB и FB2 как есть.
"""

import re

# Буква, дефис, пробелы, строчная буква: это перенос, дефис убираем.
HYPHENATED = re.compile(r"(\w)-\s+([a-zа-яё])")

# То же, но после дефиса заглавная: это составное слово вроде «Красно-Белый»,
# разорванное переносом. Убираем только пробел, дефис оставляем.
HYPHENATED_COMPOUND = re.compile(r"(\w)-\s+([A-ZА-ЯЁ])")

# Кавычки всех видов приводим к ёлочкам: движки читают их одинаково,
# а разнобой мешает сравнивать тексты и ловить дубли.
OPENING_QUOTES = ('"', "“", "„", "‟", "«")
CLOSING_QUOTES = ('"', "”", "‘", "”", "»")

APOSTROPHES = ("’", "‛", "ʼ", "`")

WHITESPACE = re.compile(r"[ \t   \r\n]+")


def join_hyphenated(text: str) -> str:
    """Склеивает слово, разорванное переносом на границе строки."""
    previous = None
    while previous != text:
        previous = text
        text = HYPHENATED.sub(r"\1\2", text)
        text = HYPHENATED_COMPOUND.sub(r"\1-\2", text)
    return text


def normalize_quotes(text: str) -> str:
    """Сводит кавычки к ёлочкам, апострофы к прямому."""
    for mark in APOSTROPHES:
        text = text.replace(mark, "'")
    result: list[str] = []
    inside = False
    for char in text:
        if char in OPENING_QUOTES or char in CLOSING_QUOTES:
            result.append("»" if inside else "«")
            inside = not inside
        else:
            result.append(char)
    return "".join(result)


def squeeze_spaces(text: str) -> str:
    """Схлопывает пробельные последовательности и убирает края."""
    return WHITESPACE.sub(" ", text).strip()


def clean_text(text: str) -> str:
    """Полная правка строки. Повторное применение ничего не меняет."""
    return squeeze_spaces(normalize_quotes(join_hyphenated(text)))
