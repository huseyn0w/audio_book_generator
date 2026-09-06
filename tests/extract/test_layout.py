"""The raw PDF layout. Phase 2 cleans this, so fonts and bboxes must not be lost."""

import pytest

from book2audio.extract.layout import RawBlock, RawPage, median_font_size


def block(text="текст", size=14.0, top=100.0, page=1, mono=False):
    return RawBlock(
        text=text, font_size=size, bbox=(50.0, top, 500.0, top + 12), page=page, is_mono=mono
    )


def test_raw_block_keeps_font_size_and_bbox():
    b = block(size=24.7, top=72.1)
    assert b.font_size == 24.7
    assert b.bbox[1] == 72.1


def test_raw_block_rejects_empty_text():
    with pytest.raises(ValueError, match="empty block text"):
        block(text="   ")


def test_raw_block_exposes_top_and_height():
    b = block(top=200.0)
    assert b.top == 200.0
    assert b.height == 12.0


def test_median_font_size_weights_by_text_length():
    """One huge heading must not move the median of the body text."""
    blocks = [block(text="а" * 500, size=14.0), block(text="Заголовок", size=30.0)]
    assert median_font_size(blocks) == 14.0


def test_median_font_size_raises_on_empty_input():
    with pytest.raises(ValueError, match="no blocks"):
        median_font_size([])


def test_raw_page_counts_characters():
    page = RawPage(number=1, width=595, height=842, blocks=[block("абв"), block("гдеё")])
    assert page.char_count() == 7
