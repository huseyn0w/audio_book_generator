"""Cleaning heuristics that need the font and the coordinates.

They work on RawBlock before the Document is built. The order matters: first the
fragments are joined, then the service blocks are dropped.
"""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import replace

from book2audio.extract.layout import RawBlock, RawPage

# The marks a paragraph really ends on.
TERMINALS = (".", "!", "?", "…", ":", ";", "»", '"', "”", "’")

# The joining limit. Broken typesetting would otherwise pull a whole chapter into
# one block, and such a block can neither be synthesized nor shown in the preview.
MERGED_MAX_CHARS = 5000

# How far the font size may differ for two blocks to count as the same role.
FONT_TOLERANCE = 0.6


def _is_open(text: str) -> bool:
    """A paragraph is cut off when it does not end on a terminal mark."""
    return not text.rstrip().endswith(TERMINALS)


def _same_role(left: RawBlock, right: RawBlock) -> bool:
    return abs(left.font_size - right.font_size) <= FONT_TOLERANCE


def merge_continuations(blocks: list[RawBlock]) -> list[RawBlock]:
    """Joins fragment blocks into paragraphs.

    In some PDFs a block is a line rather than a paragraph: up to 60% of blocks do
    not end on punctuation. Without joining, the chunker cuts on fragments and
    synthesis stumbles on every line.
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


# --- the service blocks of a page ---

# The band at the top and the bottom where we look for page numbers and running heads.
EDGE_BAND = 0.12

# On what share of pages a line must appear to count as a running head.
RUNNING_SHARE = 0.3

# A safety catch: a rule that eats more than this share of a page is not applied
# to it. Better to read a running head than to lose a paragraph.
MAX_DROP_SHARE = 0.6

PAGE_NUMBER = re.compile(r"^[\divxlcdmIVXLCDM.\s\-–—]+$")

DIGITS = re.compile(r"\d+")


def _in_edge_band(block: RawBlock, page: RawPage) -> bool:
    band = page.height * EDGE_BAND
    return block.top < band or block.top > page.height - band


def normalize_for_matching(text: str) -> str:
    """The form used to compare running heads: digits to a hash, case down."""
    return DIGITS.sub("#", text).strip().lower()


def _apply_with_guard(
    pages: list[RawPage], should_drop: Callable[[RawBlock, RawPage], bool]
) -> list[RawPage]:
    """Applies a rule page by page, backing off when it eats the page."""
    result: list[RawPage] = []
    for page in pages:
        kept = [b for b in page.blocks if not should_drop(b, page)]
        if page.blocks and len(kept) < len(page.blocks) * (1 - MAX_DROP_SHARE):
            kept = list(page.blocks)
        result.append(replace(page, blocks=kept))
    return result


def drop_page_numbers(pages: list[RawPage]) -> list[RawPage]:
    """Drops page numbers: bare numbers at the top or the bottom edge."""

    def rule(block: RawBlock, page: RawPage) -> bool:
        return _in_edge_band(block, page) and bool(PAGE_NUMBER.fullmatch(block.text.strip()))

    return _apply_with_guard(pages, rule)


def drop_running_heads(pages: list[RawPage]) -> list[RawPage]:
    """Drops running heads: edge lines that repeat throughout the book."""
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


# --- not prose ---

# The typesetting puts a service glyph before a figure caption. In the extracted
# text it arrives as a control character. The signal is very precise: 48 hits in
# the history textbook and none in the two other books.
FIGURE_MARKER = re.compile(r"^[\x00-\x1f]")

# The share of characters that are neither letters nor spaces. Above this line a
# block counts as a listing or a table.
NON_PROSE_RATIO = 0.30
NON_PROSE_MIN_CHARS = 40

# A footnote starts with a number.
FOOTNOTE_START = re.compile(r"^\d{1,3}[\s.)]")

# The band at the bottom of the page where we look for footnotes.
FOOTNOTE_BAND = 0.75

# How much smaller than the median a footnote font has to be.
SMALL_FONT_RATIO = 0.92


def _non_alpha_share(text: str) -> float:
    if not text:
        return 0.0
    noise = sum(1 for char in text if not char.isalpha() and not char.isspace())
    return noise / len(text)


def drop_figure_captions(pages: list[RawPage]) -> list[RawPage]:
    """Drops figure captions.

    Reading «Бюст Диоклетиана» in the middle of a paragraph makes no sense, and
    textbooks carry dozens of such captions per spread.
    """

    def rule(block: RawBlock, page: RawPage) -> bool:
        return bool(FIGURE_MARKER.match(block.text))

    return _apply_with_guard(pages, rule)


def drop_non_prose(pages: list[RawPage]) -> list[RawPage]:
    """Drops code listings and tables. They are useless read aloud."""

    def rule(block: RawBlock, page: RawPage) -> bool:
        return (
            len(block.text) >= NON_PROSE_MIN_CHARS
            and _non_alpha_share(block.text) > NON_PROSE_RATIO
        )

    return _apply_with_guard(pages, rule)


def drop_footnotes(pages: list[RawPage], median: float) -> list[RawPage]:
    """Drops footnotes: a small font, the bottom of the page and a leading number.

    All three conditions are required. A small font at the bottom is not enough on
    its own: in Cracking the Coding Interview ordinary text is set that way.
    """

    def rule(block: RawBlock, page: RawPage) -> bool:
        return (
            block.font_size < median * SMALL_FONT_RATIO
            and block.top > page.height * FOOTNOTE_BAND
            and bool(FOOTNOTE_START.match(block.text))
        )

    return _apply_with_guard(pages, rule)


# --- columns and reading order ---

# The tolerance around the page middle: a block may cross it a little.
COLUMN_TOLERANCE = 0.04

# How many blocks each column needs before we believe in two columns.
MIN_BLOCKS_PER_COLUMN = 3

# The share of the page width from which a block counts as spanning.
FULL_WIDTH_SHARE = 0.7


def _column_of(block: RawBlock, page: RawPage) -> int:
    """0 is the left column and the spanning blocks, 1 is the right one."""
    middle = page.width / 2
    tolerance = page.width * COLUMN_TOLERANCE
    if (block.bbox[2] - block.bbox[0]) >= page.width * FULL_WIDTH_SHARE:
        return 0
    return 1 if block.bbox[0] >= middle - tolerance else 0


def column_count(page: RawPage) -> int:
    """Two columns or one. A mistake here costs the most: the text interleaves."""
    middle = page.width / 2
    tolerance = page.width * COLUMN_TOLERANCE

    left = right = 0
    for block in page.blocks:
        if (block.bbox[2] - block.bbox[0]) >= page.width * FULL_WIDTH_SHARE:
            continue
        if block.bbox[2] <= middle + tolerance:
            left += 1
        elif block.bbox[0] >= middle - tolerance:
            right += 1

    if left >= MIN_BLOCKS_PER_COLUMN and right >= MIN_BLOCKS_PER_COLUMN:
        return 2
    return 1


def sort_reading_order(page: RawPage) -> RawPage:
    """Puts the blocks into reading order.

    With one column, top to bottom. With two, the whole left column first and then
    the whole right one: PyMuPDF sorts by y and on two columns hands back the lines
    interleaved.
    """
    if column_count(page) == 1:
        ordered = sorted(page.blocks, key=lambda b: (round(b.top, 1), b.bbox[0]))
    else:
        ordered = sorted(
            page.blocks, key=lambda b: (_column_of(b, page), round(b.top, 1), b.bbox[0])
        )
    return replace(page, blocks=ordered)


# The share of non-letters at which a small block counts as a date caption.
NUMERIC_CAPTION_RATIO = 0.6


def drop_numeric_captions(pages: list[RawPage], median: float) -> list[RawPage]:
    """Drops small blocks made almost entirely of digits.

    In atlases and textbooks the dates under illustrations are set that way. Read
    aloud they sound like a random run of numbers in the middle of a paragraph. The
    small font requirement is essential: «1861 г.» in the body text is content.
    """

    def rule(block: RawBlock, page: RawPage) -> bool:
        return (
            block.font_size < median * SMALL_FONT_RATIO
            and _non_alpha_share(block.text) > NUMERIC_CAPTION_RATIO
        )

    return _apply_with_guard(pages, rule)
