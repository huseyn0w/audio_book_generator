"""Text fixes that need no knowledge of the typesetting.

It suits any format, so phase 3 reuses it for EPUB and FB2 as it is.
"""

import re

# Letter, hyphen, spaces, lowercase letter: that is a line break hyphen, drop it.
HYPHENATED = re.compile(r"(\w)-\s+([a-zа-яё])")

# The same, but an uppercase letter after the hyphen: a compound word broken
# across lines. We remove only the space and keep the hyphen.
HYPHENATED_COMPOUND = re.compile(r"(\w)-\s+([A-ZА-ЯЁ])")

# Quotes of every kind become guillemets: the engines read them the same way,
# and the mixture gets in the way of comparing texts and catching duplicates.
OPENING_QUOTES = ('"', "“", "„", "‟", "«")
CLOSING_QUOTES = ('"', "”", "‘", "”", "»")

APOSTROPHES = ("’", "‛", "ʼ", "`")

WHITESPACE = re.compile(r"[ \t   \r\n]+")


def join_hyphenated(text: str) -> str:
    """Rejoins a word broken by a hyphen at a line boundary."""
    previous = None
    while previous != text:
        previous = text
        text = HYPHENATED.sub(r"\1\2", text)
        text = HYPHENATED_COMPOUND.sub(r"\1-\2", text)
    return text


def normalize_quotes(text: str) -> str:
    """Brings quotes to guillemets and apostrophes to the straight one."""
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
    """Collapses whitespace runs and trims the edges."""
    return WHITESPACE.sub(" ", text).strip()


# A zero right against a bracket, then a possible typesetting space, then a
# Latin letter or digit. A space BEFORE the bracket means a real zero, left alone.
BIG_O = re.compile(r"0\(\s*([A-Za-z0-9])")


def restore_big_o(text: str) -> str:
    """Puts the letter O back into complexity bounds where extraction gave a zero.

    In technical books the font sometimes maps O onto the zero glyph, and read
    aloud that becomes "zero of n". The condition is narrow: a zero, then a
    bracket, then a Latin letter or digit. Measured on six fixtures: 15 hits in
    the English technical book, no false positives in the other five.
    """
    return BIG_O.sub(r"O(\1", text)


def clean_text(text: str) -> str:
    """The full fix for a line. Applying it again changes nothing."""
    return squeeze_spaces(normalize_quotes(join_hyphenated(restore_big_o(text))))
