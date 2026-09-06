"""Dropping what is not prose: figure captions, footnotes, listings.

Самая опасная группа правил. Наивное «мелкий шрифт плюс низ страницы»
проверено на реальных книгах и отвергнуто: в Cracking the Coding Interview
мелким шрифтом внизу набран обычный текст, и такое правило его съело бы.
"""

from pathlib import Path

from book2audio.clean.pdf_layout import (
    NON_PROSE_RATIO,
    drop_figure_captions,
    drop_footnotes,
    drop_non_prose,
)
from book2audio.extract.layout import RawBlock, RawPage

FIXTURES = Path(__file__).parent.parent / "fixtures"


def blk(text, size=13.0, top=100.0):
    return RawBlock(text=text, font_size=size, bbox=(50.0, top, 500.0, top + 12), page=1)


def page(blocks):
    return RawPage(number=1, width=600.0, height=800.0, blocks=blocks)


def texts(pages):
    return [b.text for p in pages for b in p.blocks]


# --- figure captions ---


def test_caption_with_a_figure_marker_is_dropped():
    pages = [page([blk("\x02 Арка Константина. Рим", size=9.0), blk("Обычный текст.")])]
    assert texts(drop_figure_captions(pages)) == ["Обычный текст."]


def test_caption_rule_ignores_normal_text():
    pages = [page([blk("Обычный абзац с текстом.")])]
    assert texts(drop_figure_captions(pages)) == ["Обычный абзац с текстом."]


def test_caption_rule_only_looks_at_the_first_character():
    pages = [page([blk("Текст с \x02 маркером в середине.")])]
    assert len(texts(drop_figure_captions(pages))) == 1


# --- listings and tables ---


def test_code_listing_is_dropped():
    # A real block from Cracking the Coding Interview, non-letter share 0.32.
    code = (
        "1 void allFib(int n) { 2 for (int i= 0; i < n; i++) { "
        '3 System.out.println(i + ": "+ fib(i)); 4 } 5 } 6 7 int fib(int n) { '
        "8 if (n <= 0) return 0; 9 else if (n == 1) return 1; "
        "10 return fib(n - 1) + fib(n - 2); 11 }"
    )
    pages = [page([blk(code), blk("Обычный текст.")])]
    assert texts(drop_non_prose(pages)) == ["Обычный текст."]


def test_prose_just_below_the_threshold_survives():
    """The threshold keeps real prose with digits, not only clean text."""
    text = "К 1861 году в стране было 23 губернии, 45 уездов и 120 волостей всего."
    pages = [page([blk(text)])]
    assert texts(drop_non_prose(pages)) == [text]


def test_short_noisy_string_survives():
    """A short line with digits may be a date or a heading."""
    pages = [page([blk("1861 г.")])]
    assert texts(drop_non_prose(pages)) == ["1861 г."]


def test_normal_prose_with_a_few_numbers_survives():
    text = "В 1861 году отменили крепостное право, и через 20 лет всё изменилось полностью."
    pages = [page([blk(text)])]
    assert texts(drop_non_prose(pages)) == [text]


def test_non_prose_ratio_is_a_share():
    assert 0.0 < NON_PROSE_RATIO < 1.0


# --- footnotes ---


def test_numbered_small_block_at_the_bottom_is_dropped():
    pages = [
        page(
            [
                blk("Основной текст.", size=13.0, top=300.0),
                blk("1. Подробнее см. в приложении.", size=9.0, top=760.0),
            ]
        )
    ]
    assert texts(drop_footnotes(pages, median=13.0)) == ["Основной текст."]


def test_numbered_block_in_normal_font_survives():
    """A numbered list is content, not a footnote."""
    pages = [page([blk("1. Первый пункт списка.", size=13.0, top=760.0)])]
    assert texts(drop_footnotes(pages, median=13.0)) == ["1. Первый пункт списка."]


def test_small_block_at_the_top_survives():
    pages = [page([blk("1. Что-то мелкое сверху.", size=9.0, top=50.0)])]
    assert texts(drop_footnotes(pages, median=13.0)) == ["1. Что-то мелкое сверху."]


def test_small_bottom_block_without_a_number_survives():
    """In Cracking the Coding Interview ordinary text is set that way."""
    pages = [page([blk("There are several ways to compute this.", size=8.5, top=760.0)])]
    assert len(texts(drop_footnotes(pages, median=9.5))) == 1


# --- real data ---


def test_captions_are_removed_from_the_history_textbook():
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "typeset_ru.pdf")
    before = sum(len(p.blocks) for p in pages)
    after = sum(len(p.blocks) for p in drop_figure_captions(pages))
    assert before - after >= 20


def test_code_listings_are_removed_from_the_programming_book():
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "typeset_en.pdf")
    before = sum(len(p.blocks) for p in pages)
    after = sum(len(p.blocks) for p in drop_non_prose(pages))
    assert before - after >= 2


def test_clean_book_loses_nothing_to_these_rules():
    """On the Christensen book these rules must not fire at all."""
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "toc_ru.pdf")
    assert texts(drop_figure_captions(pages)) == texts(pages)
    assert texts(drop_non_prose(pages)) == texts(pages)


# --- numeric captions ---


def test_numeric_caption_in_small_font_is_dropped():
    """Date captions like «1160—1170 гг.» sound like random numbers read aloud."""
    from book2audio.clean.pdf_layout import drop_numeric_captions

    pages = [page([blk("Основной текст здесь.", size=13.0), blk("1160—1170 гг.", size=9.0)])]
    assert texts(drop_numeric_captions(pages, median=13.0)) == ["Основной текст здесь."]


def test_numeric_string_in_normal_font_survives():
    from book2audio.clean.pdf_layout import drop_numeric_captions

    pages = [page([blk("1861 г.", size=13.0)])]
    assert texts(drop_numeric_captions(pages, median=13.0)) == ["1861 г."]


def test_small_prose_survives_the_numeric_rule():
    from book2audio.clean.pdf_layout import drop_numeric_captions

    pages = [page([blk("Мелкий, но обычный текст без цифр.", size=9.0)])]
    assert len(texts(drop_numeric_captions(pages, median=13.0))) == 1


def test_numeric_caption_rule_does_not_touch_clean_books():
    from book2audio.clean.pdf_layout import drop_numeric_captions
    from book2audio.extract.layout import median_font_size
    from book2audio.extract.pdf import read_pages

    for name in ("toc_ru.pdf", "no_toc_ru.pdf"):
        pages = read_pages(FIXTURES / name)
        median = median_font_size([b for p in pages for b in p.blocks])
        assert texts(drop_numeric_captions(pages, median)) == texts(pages)
