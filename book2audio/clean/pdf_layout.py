"""Эвристики чистки, которым нужны шрифт и координаты.

Работают с RawBlock до сборки Document. Порядок применения важен: сначала
склейка обрывков, потом выбрасывание служебных блоков.
"""

from dataclasses import replace

from book2audio.extract.layout import RawBlock

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
