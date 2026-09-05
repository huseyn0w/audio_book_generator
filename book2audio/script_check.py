"""Совпадает ли выбранный язык с письменностью книги.

Смешанные языки внутри одной книги за рамками проекта: читаться она будет
голосом выбранного языка. Но перепутанный язык это частая ошибка на два
клика, и узнавать о ней надо до синтеза, а не из готового файла.
"""

CYRILLIC = ("Ѐ", "ӿ")
LATIN = frozenset("abcdefghijklmnopqrstuvwxyz")

# Доля чужого письма, выше которой это уже другая книга, а не заимствования.
# Замер на шести фикстурах: русские дают 0-1.8% латиницы, английская 12.2%
# кириллицы (это её же цифры, нормализованные до правки языка). Между
# измеренными группами широкий зазор, граница поставлена в его начале.
FOREIGN_LIMIT = 0.25


def _is_cyrillic(char: str) -> bool:
    return CYRILLIC[0] <= char <= CYRILLIC[1]


def foreign_share(text: str, language: str) -> float:
    """Доля букв чужой письменности. Цифры и знаки не в счёт."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    if language == "ru":
        foreign = sum(1 for c in letters if c.lower() in LATIN)
    else:
        foreign = sum(1 for c in letters if _is_cyrillic(c))
    return foreign / len(letters)


def language_warning(text: str, language: str) -> dict | None:
    """Данные для предупреждения или None, если язык похож на правду.

    Возвращаем числа и коды языков, а не готовую фразу: интерфейс собирает
    её на своём языке, а он не обязан совпадать с языком книги.
    """
    share = foreign_share(text, language)
    if share <= FOREIGN_LIMIT:
        return None
    return {
        "expected": language,
        "found": "en" if language == "ru" else "ru",
        "share": round(share, 2),
    }
