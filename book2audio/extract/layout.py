"""The raw page layout: text together with font size and coordinates.

An intermediate layer between PyMuPDF and Document. The phase 2 cleaning
heuristics work on this: without font size and bbox you cannot tell a
running head from a paragraph.
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
            raise ValueError("empty block text")

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
    """Median font size, weighted by text length.

    The weighting keeps rare large headings from moving the baseline that
    every phase 2 heuristic depends on.
    """
    if not blocks:
        raise ValueError("no blocks to take a median from")
    weighted = [b.font_size for b in blocks for _ in range(len(b.text))]
    return statistics.median(weighted)
