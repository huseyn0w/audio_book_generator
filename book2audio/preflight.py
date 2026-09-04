"""Проверки до запуска.

Про отсутствие ffmpeg надо узнавать на старте, а не на сборке m4b, когда
синтез уже отработал полчаса.
"""

import shutil
from pathlib import Path

# Инструмент и команда, которой он ставится.
INSTALL = {"ffmpeg": "brew install ffmpeg", "espeak-ng": "brew install espeak-ng"}

# ffmpeg нужен всегда: им склеивается и кодируется всё. espeak-ng фонемизирует
# незнакомые слова для Kokoro, то есть нужен только английскому. Silero
# обходится своими средствами.
TOOLS_BY_LANGUAGE = {"ru": ("ffmpeg",), "en": ("ffmpeg", "espeak-ng")}

# wav 24000 Гц, 16 бит, моно это 48 килобайт на секунду речи.
BYTES_PER_SECOND = 48_000

# Скорость прозы, замер на реальных книгах.
CHARS_PER_SECOND = 15.0

# Кэш чанков и склеенные главы лежат на диске одновременно, плюс запас
# на итоговый m4b и временные файлы ffmpeg.
COPIES = 2.5


class MissingTool(Exception):
    """Нет системной программы. В тексте лежит команда, которой её поставить."""


class NotEnoughSpace(Exception):
    """Промежуточные wav не поместятся."""


def missing_tools(language: str | None = None) -> list[str]:
    """Чего не хватает. Без языка проверяет всё, что вообще может понадобиться."""
    if language is None:
        wanted: tuple[str, ...] = tuple(INSTALL)
    else:
        wanted = TOOLS_BY_LANGUAGE.get(language, tuple(INSTALL))
    return [tool for tool in wanted if shutil.which(tool) is None]


def check_tools(language: str | None = None) -> None:
    missing = missing_tools(language)
    if not missing:
        return
    commands = "; ".join(INSTALL[tool] for tool in missing)
    raise MissingTool(f"не хватает: {', '.join(missing)}. Поставить: {commands}")


def estimate_bytes(chars: int) -> int:
    """Сколько места займёт работа над книгой такого объёма."""
    return int(chars / CHARS_PER_SECOND * BYTES_PER_SECOND * COPIES)


def free_bytes(path: Path) -> int:
    """Свободное место там, где будет работа. Папки может ещё не быть."""
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def check_space(path: Path, chars: int) -> None:
    needed = estimate_bytes(chars)
    free = free_bytes(path)
    if free >= needed:
        return
    raise NotEnoughSpace(
        f"мало места: нужно примерно {needed / 1e9:.1f} ГБ, свободно {free / 1e9:.1f} ГБ"
    )
