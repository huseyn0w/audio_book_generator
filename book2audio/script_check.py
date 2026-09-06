"""Whether the chosen language matches the script the book is written in.

Mixed languages inside one book are out of scope: it will be read in the voice
of the chosen language. But picking the wrong language is a common two-click
mistake, and you should hear about it before synthesis, not from the finished file.
"""

CYRILLIC = ("Ѐ", "ӿ")
LATIN = frozenset("abcdefghijklmnopqrstuvwxyz")

# The share of foreign script above which this is a different book, not borrowings.
# Measured on six fixtures: Russian ones give 0-1.8% Latin, the English one 12.2%
# Cyrillic (its own numbers, normalized before the language was fixed). The gap
# between the measured groups is wide, and the threshold sits at its start.
FOREIGN_LIMIT = 0.25


def _is_cyrillic(char: str) -> bool:
    return CYRILLIC[0] <= char <= CYRILLIC[1]


def foreign_share(text: str, language: str) -> float:
    """The share of letters in a foreign script. Digits and marks do not count."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    if language == "ru":
        foreign = sum(1 for c in letters if c.lower() in LATIN)
    else:
        foreign = sum(1 for c in letters if _is_cyrillic(c))
    return foreign / len(letters)


def language_warning(text: str, language: str) -> dict | None:
    """Data for the warning, or None if the language looks right.

    We return numbers and language codes rather than a finished phrase: the
    interface builds it in its own language, which need not match the book.
    """
    share = foreign_share(text, language)
    if share <= FOREIGN_LIMIT:
        return None
    return {
        "expected": language,
        "found": "en" if language == "ru" else "ru",
        "share": round(share, 2),
    }
