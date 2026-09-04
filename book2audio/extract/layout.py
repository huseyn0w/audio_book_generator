"""Сырая раскладка страницы: текст вместе с размером шрифта и координатами.

Промежуточный слой между PyMuPDF и Document. Эвристики чистки в фазе 2
работают именно с ним: без размера шрифта и bbox колонтитул от абзаца
не отличить.
"""

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class RawBlock:
    text: str
    font_size: float
    bbox: tuple[float, float, float, float]
    page: int
    is_mono: bool = False

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("пустой текст блока")

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]


@dataclass(frozen=True)
class RawPage:
    number: int
    width: float
    height: float
    blocks: list[RawBlock]

    def char_count(self) -> int:
        return sum(len(b.text) for b in self.blocks)


def median_font_size(blocks: list[RawBlock]) -> float:
    """Медианный размер шрифта, взвешенный по длине текста.

    Взвешивание нужно, чтобы редкие крупные заголовки не сдвигали опорную
    величину: от неё зависят все эвристики фазы 2.
    """
    if not blocks:
        raise ValueError("нет блоков для расчёта медианы")
    weighted = [b.font_size for b in blocks for _ in range(len(b.text))]
    return statistics.median(weighted)
