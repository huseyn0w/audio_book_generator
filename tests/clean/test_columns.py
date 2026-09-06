from pathlib import Path

from book2audio.clean.pdf_layout import column_count, sort_reading_order
from book2audio.extract.layout import RawBlock, RawPage

WIDTH = 600.0
FIXTURES = Path(__file__).parent.parent / "fixtures"


def blk(text, left, top, width=250.0):
    return RawBlock(text=text, font_size=13.0, bbox=(left, top, left + width, top + 12), page=1)


def page(blocks):
    return RawPage(number=1, width=WIDTH, height=800.0, blocks=blocks)


def texts(p):
    return [b.text for b in p.blocks]


# --- detecting the columns ---


def test_single_column_page_is_detected():
    p = page([blk(f"Абзац {i}", 50, 100 + i * 40, width=500) for i in range(6)])
    assert column_count(p) == 1


def test_two_column_page_is_detected():
    left = [blk(f"Л{i}", 40, 100 + i * 40) for i in range(5)]
    right = [blk(f"П{i}", 320, 100 + i * 40) for i in range(5)]
    assert column_count(page(left + right)) == 2


def test_page_with_too_few_blocks_stays_single_column():
    """With two blocks you cannot tell columns from coincidence."""
    assert column_count(page([blk("Л", 40, 100), blk("П", 320, 100)])) == 1


def test_full_width_blocks_do_not_create_columns():
    p = page([blk(f"Широкий {i}", 40, 100 + i * 40, width=520) for i in range(8)])
    assert column_count(p) == 1


# --- reading order ---


def test_single_column_is_sorted_top_to_bottom():
    p = page(
        [blk("третий", 50, 300, 500), blk("первый", 50, 100, 500), blk("второй", 50, 200, 500)]
    )
    assert texts(sort_reading_order(p)) == ["первый", "второй", "третий"]


def test_two_columns_are_read_left_first_then_right():
    """Without this the text reads interleaved and the meaning is lost."""
    blocks = [
        blk("Л1", 40, 100),
        blk("П1", 320, 90),
        blk("Л2", 40, 200),
        blk("П2", 320, 190),
        blk("Л3", 40, 300),
        blk("П3", 320, 290),
    ]
    assert texts(sort_reading_order(page(blocks))) == ["Л1", "Л2", "Л3", "П1", "П2", "П3"]


def test_full_width_heading_stays_ahead_of_both_columns():
    blocks = [
        blk("П1", 320, 200),
        blk("Л1", 40, 200),
        blk("Заголовок на всю ширину", 40, 50, width=520),
    ]
    assert texts(sort_reading_order(page(blocks)))[0] == "Заголовок на всю ширину"


def test_sorting_never_loses_a_block():
    blocks = [blk(f"б{i}", 40 if i % 2 else 320, 100 + i * 30) for i in range(10)]
    assert len(sort_reading_order(page(blocks)).blocks) == 10


# --- real data ---


def test_history_textbook_is_two_column():
    from book2audio.clean.pdf_layout import drop_figure_captions
    from book2audio.extract.pdf import read_pages

    pages = drop_figure_captions(read_pages(FIXTURES / "typeset_ru.pdf"))
    two = sum(1 for p in pages if column_count(p) == 2)
    assert two >= 3


def test_clean_book_stays_single_column():
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "toc_ru.pdf")
    assert all(column_count(p) == 1 for p in pages)
