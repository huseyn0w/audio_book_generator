"""Latin into Cyrillic for Russian synthesis.

В таблице символов русской модели Silero латинских букв нет. Одна буква
из «E*Trade Bank» роняет apply_tts с KeyError, а в мягком пути движок
просто выбрасывает слово, и «специалисты Sony Bank» читается как
«специалисты банк».

Замер на книге Кристенсена: латиница в 27% кусков, 1463 уникальных
названия. Для деловой книги это имена компаний, то есть содержание.
"""

import re

# English letter names in Russian letters: that is how abbreviations get read out.
LETTER_NAMES = {
    "a": "эй",
    "b": "би",
    "c": "си",
    "d": "ди",
    "e": "и",
    "f": "эф",
    "g": "джи",
    "h": "эйч",
    "i": "ай",
    "j": "джей",
    "k": "кей",
    "l": "эл",
    "m": "эм",
    "n": "эн",
    "o": "оу",
    "p": "пи",
    "q": "кью",
    "r": "ар",
    "s": "эс",
    "t": "ти",
    "u": "ю",
    "v": "ви",
    "w": "дабл-ю",
    "x": "экс",
    "y": "уай",
    "z": "зед",
}

# Combinations are matched before single letters, and the order inside matters.
DIGRAPHS = [
    ("sch", "ш"),
    ("tch", "ч"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("th", "т"),
    ("ph", "ф"),
    ("ck", "к"),
    ("qu", "кв"),
    ("ee", "и"),
    ("ea", "и"),
    ("oo", "у"),
    ("ou", "ау"),
    ("ay", "эй"),
    ("ey", "эй"),
    ("ai", "эй"),
    ("oy", "ой"),
    ("ya", "я"),
    ("yu", "ю"),
    ("ye", "е"),
    ("yo", "ё"),
]

SINGLES = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "дж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "й",
    "z": "з",
}

# Long vowels for the "magic e": chase, nike, coke.
LONG = {"a": "эй", "e": "и", "i": "ай", "o": "оу", "u": "ю"}

CONSONANT = "bcdfghjklmnpqrstvwxz"

# A vowel, one consonant, a silent e at the end: the vowel is read long.
MAGIC_E = re.compile(rf"^(.*?)([aeiou])([{CONSONANT}])e$")

# Just a silent e after a consonant: google, apple.
SILENT_E = re.compile(rf"^(.{{3,}}[{CONSONANT}])e$")

# A word in all caps and at least two letters long is an abbreviation.
# One capital is an initial, read as a letter, but from the same table.
ACRONYM = re.compile(r"^[A-Z]{2,6}$")

# A word together with its apostrophes and inner hyphens.
WORD = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")


def _spell(word: str) -> str:
    return "-".join(LETTER_NAMES[c] for c in word.lower())


def _translit_word(word: str) -> str:
    """Approximate. A letter by letter transfer knows no English phonetics, but a
    recognizable name read aloud beats a word the engine throws away."""
    rest = word.lower()
    magic = MAGIC_E.match(rest)
    if magic:
        rest = magic.group(1) + LONG[magic.group(2)] + magic.group(3)
    else:
        silent = SILENT_E.match(rest)
        if silent:
            rest = silent.group(1)

    out: list[str] = []
    while rest:
        for source, target in DIGRAPHS:
            if rest.startswith(source):
                out.append(target)
                rest = rest[len(source) :]
                break
        else:
            char = rest[0]
            # "Sony" ends as «сони», not «сонй».
            if char == "y" and len(rest) == 1 and out:
                out.append("и")
            else:
                # Cyrillic from the "magic e", hyphens and apostrophes pass through.
                out.append(SINGLES.get(char, char))
            rest = rest[1:]
    return "".join(out)


def _replace(match: re.Match) -> str:
    word = match.group(0)
    letters = word.replace("-", "").replace("'", "").replace("’", "")
    if ACRONYM.match(letters):
        return _spell(letters)
    if len(letters) == 1:
        return LETTER_NAMES[letters.lower()]
    return _translit_word(word)


def latin_to_cyrillic(text: str) -> str:
    """Turns Latin words into Cyrillic. Cyrillic and digits are left alone."""
    if not any("a" <= c.lower() <= "z" for c in text):
        return text
    # An ampersand in a name is "and": AT&T is read «эй-ти энд ти».
    text = re.sub(r"\s*&\s*", " энд ", text)
    return WORD.sub(_replace, text)
