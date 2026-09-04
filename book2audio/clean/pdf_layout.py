"""Эвристики чистки, которым нужны шрифт и координаты.

Работают с RawBlock до сборки Document. Порядок применения важен: сначала
склейка обрывков, потом выбрасывание служебных блоков.
"""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import replace

from book2audio.extract.layout import RawBlock, RawPage

# Знаки, на которых абзац действительно кончается.
TERMINALS = (".", "!", "?", "…", ":", ";", "»", '"', "”", "’")

# Предел склейки. Сломанная вёрстка иначе собирает всю главу в один блок,
# а такой блок нельзя ни озвучить куском, ни показать в предпросмотре.
MERGED_MAX_CHARS = 5000

# Насколько может отличаться кегль, чтобы блоки считались одной ролью.
FONT_TOLERANCE = 0.6


def _is_open(text: str) -> bool:
    """Абзац оборван, если не кончается терминальным знаком."""
    return not text.rstrip().endswith(TERMINALS)


def _same_role(left: RawBlock, right: RawBlock) -> bool:
    return abs(left.font_size - right.font_size) <= FONT_TOLERANCE


def merge_continuations(blocks: list[RawBlock]) -> list[RawBlock]:
    """Склеивает блоки-обрывки в абзацы.

    У части PDF блок это строка, а не абзац: до 60% блоков не кончаются
    знаком препинания. Без склейки чанкер режет по обрывкам и синтез
    спотыкается на каждой строке.
    """
    merged: list[RawBlock] = []
    for block in blocks:
        if not merged:
            merged.append(block)
            continue

        previous = merged[-1]
        joined_length = len(previous.text) + 1 + len(block.text)
        if (
            _is_open(previous.text)
            and _same_role(previous, block)
            and joined_length <= MERGED_MAX_CHARS
        ):
            merged[-1] = replace(previous, text=f"{previous.text} {block.text}")
        else:
            merged.append(block)
    return merged


# --- служебные блоки страницы ---

# Полоса сверху и снизу, в которой ищем колонцифры и колонтитулы.
EDGE_BAND = 0.12

# На какой доле страниц должна встретиться строка, чтобы считаться колонтитулом.
RUNNING_SHARE = 0.3

# Предохранитель: правило, съедающее больше этой доли страницы, на ней не
# применяется. Лучше прочитать колонтитул, чем потерять абзац.
MAX_DROP_SHARE = 0.6

PAGE_NUMBER = re.compile(r"^[\divxlcdmIVXLCDM.\s\-–—]+$")

DIGITS = re.compile(r"\d+")


def _in_edge_band(block: RawBlock, page: RawPage) -> bool:
    band = page.height * EDGE_BAND
    return block.top < band or block.top > page.height - band


def normalize_for_matching(text: str) -> str:
    """Форма для сравнения колонтитулов: цифры в решётку, регистр вниз."""
    return DIGITS.sub("#", text).strip().lower()


def _apply_with_guard(
    pages: list[RawPage], should_drop: Callable[[RawBlock, RawPage], bool]
) -> list[RawPage]:
    """Применяет правило постранично, отступая, если оно съедает страницу."""
    result: list[RawPage] = []
    for page in pages:
        kept = [b for b in page.blocks if not should_drop(b, page)]
        if page.blocks and len(kept) < len(page.blocks) * (1 - MAX_DROP_SHARE):
            kept = list(page.blocks)
        result.append(replace(page, blocks=kept))
    return result


def drop_page_numbers(pages: list[RawPage]) -> list[RawPage]:
    """Выбрасывает колонцифры: голые числа у верхнего или нижнего края."""

    def rule(block: RawBlock, page: RawPage) -> bool:
        return _in_edge_band(block, page) and bool(PAGE_NUMBER.fullmatch(block.text.strip()))

    return _apply_with_guard(pages, rule)


def drop_running_heads(pages: list[RawPage]) -> list[RawPage]:
    """Выбрасывает колонтитулы: краевые строки, повторяющиеся по всей книге."""
    seen: Counter[str] = Counter()
    for page in pages:
        edges = {normalize_for_matching(b.text) for b in page.blocks if _in_edge_band(b, page)}
        seen.update(edges)

    threshold = max(2, len(pages) * RUNNING_SHARE)
    running = {form for form, count in seen.items() if count >= threshold}
    if not running:
        return list(pages)

    def rule(block: RawBlock, page: RawPage) -> bool:
        return _in_edge_band(block, page) and normalize_for_matching(block.text) in running

    return _apply_with_guard(pages, rule)


# --- не-проза ---

# Вёрстка ставит перед подписью к рисунку служебный глиф. В извлечённом
# тексте он приходит управляющим символом. Сигнал очень точный: 48 попаданий
# в учебнике истории и ноль в двух других книгах.
FIGURE_MARKER = re.compile(r"^[\x00-\x1f]")

# Доля символов, которые не буквы и не пробелы. Выше этой границы блок
# считается листингом или таблицей.
NON_PROSE_RATIO = 0.30
NON_PROSE_MIN_CHARS = 40

# Сноска начинается с номера.
FOOTNOTE_START = re.compile(r"^\d{1,3}[\s.)]")

# Полоса внизу страницы, в которой ищем сноски.
FOOTNOTE_BAND = 0.75

# Насколько мельче медианы должен быть шрифт сноски.
SMALL_FONT_RATIO = 0.92


def _non_alpha_share(text: str) -> float:
    if not text:
        return 0.0
    noise = sum(1 for char in text if not char.isalpha() and not char.isspace())
    return noise / len(text)


def drop_figure_captions(pages: list[RawPage]) -> list[RawPage]:
    """Выбрасывает подписи к рисункам.

    Читать «Бюст Диоклетиана» посреди абзаца бессмысленно, а в учебниках
    таких подписей десятки на разворот.
    """

    def rule(block: RawBlock, page: RawPage) -> bool:
        return bool(FIGURE_MARKER.match(block.text))

    return _apply_with_guard(pages, rule)


def drop_non_prose(pages: list[RawPage]) -> list[RawPage]:
    """Выбрасывает листинги кода и таблицы. Вслух они бесполезны."""

    def rule(block: RawBlock, page: RawPage) -> bool:
        return (
            len(block.text) >= NON_PROSE_MIN_CHARS
            and _non_alpha_share(block.text) > NON_PROSE_RATIO
        )

    return _apply_with_guard(pages, rule)


def drop_footnotes(pages: list[RawPage], median: float) -> list[RawPage]:
    """Выбрасывает сноски: мелкий шрифт, низ страницы и номер в начале.

    Все три условия обязательны. Одного мелкого шрифта внизу мало: в
    Cracking the Coding Interview так набран обычный текст.
    """

    def rule(block: RawBlock, page: RawPage) -> bool:
        return (
            block.font_size < median * SMALL_FONT_RATIO
            and block.top > page.height * FOOTNOTE_BAND
            and bool(FOOTNOTE_START.match(block.text))
        )

    return _apply_with_guard(pages, rule)
