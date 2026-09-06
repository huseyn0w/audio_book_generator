from pathlib import Path

from book2audio.clean.pdf_layout import (
    RUNNING_SHARE,
    drop_page_numbers,
    drop_running_heads,
    normalize_for_matching,
)
from book2audio.extract.layout import RawBlock, RawPage

PAGE_HEIGHT = 800.0
FIXTURES = Path(__file__).parent.parent / "fixtures"


def blk(text, top, page=1):
    return RawBlock(text=text, font_size=13.0, bbox=(50.0, top, 500.0, top + 12), page=page)


def make_page(number, blocks):
    return RawPage(number=number, width=600.0, height=PAGE_HEIGHT, blocks=blocks)


def texts(pages):
    return [b.text for p in pages for b in p.blocks]


# --- page numbers ---


def test_bare_number_at_the_bottom_is_dropped():
    pages = [make_page(1, [blk("Текст главы.", 400), blk("42", 770)])]
    assert texts(drop_page_numbers(pages)) == ["Текст главы."]


def test_bare_number_at_the_top_is_dropped():
    pages = [make_page(1, [blk("7", 20), blk("Текст главы.", 400)])]
    assert texts(drop_page_numbers(pages)) == ["Текст главы."]


def test_roman_numeral_at_the_edge_is_dropped():
    pages = [make_page(1, [blk("xiv", 770), blk("Текст.", 400)])]
    assert texts(drop_page_numbers(pages)) == ["Текст."]


def test_number_in_the_middle_of_the_page_survives():
    """This may be a year or a list number rather than a page number."""
    pages = [make_page(1, [blk("1861", 400)])]
    assert texts(drop_page_numbers(pages)) == ["1861"]


def test_number_with_words_survives():
    pages = [make_page(1, [blk("Глава 42", 770)])]
    assert texts(drop_page_numbers(pages)) == ["Глава 42"]


# --- running heads ---


def test_normalize_replaces_digits_for_matching():
    assert normalize_for_matching("Глава 12, стр. 345") == "глава #, стр. #"


def test_head_repeated_on_most_pages_is_dropped():
    pages = [
        make_page(n, [blk(f"Клейтон Кристенсен · {n}", 20), blk(f"Текст {n}.", 400)])
        for n in range(1, 11)
    ]
    assert texts(drop_running_heads(pages)) == [f"Текст {n}." for n in range(1, 11)]


def test_head_on_few_pages_survives():
    pages = [
        make_page(n, [blk("Повтор" if n < 3 else f"Уникум {n}", 20), blk(f"Текст {n}.", 400)])
        for n in range(1, 11)
    ]
    assert "Повтор" in texts(drop_running_heads(pages))


def test_only_edge_blocks_are_considered_running_heads():
    """The same phrase in the middle of a page is not a running head."""
    pages = [
        make_page(n, [blk(f"Верх {n}", 20), blk("Повторяющаяся фраза", 400), blk(f"Низ {n}", 770)])
        for n in range(1, 11)
    ]
    assert texts(drop_running_heads(pages)).count("Повторяющаяся фраза") == 10


def test_running_share_threshold_is_documented():
    assert 0.0 < RUNNING_SHARE < 1.0


# --- the safety catch ---


def test_rule_backs_off_when_it_would_eat_most_of_a_page():
    """Better to read a running head than to lose a page of text."""
    pages = [make_page(n, [blk("Повтор", 20), blk("Повтор", 770)]) for n in range(1, 11)]
    assert len(texts(drop_running_heads(pages))) == 20


# --- real data ---


def test_running_heads_are_found_in_the_typeset_fixture():
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "typeset_en.pdf")
    before = sum(len(p.blocks) for p in pages)
    after = sum(len(p.blocks) for p in drop_running_heads(pages))
    assert after < before


def test_page_numbers_are_found_in_a_real_book():
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "no_toc_ru.pdf")
    before = texts(pages)
    after = texts(drop_page_numbers(pages))
    assert "3" in before
    assert "3" not in after


def test_dates_in_the_page_body_are_never_dropped():
    """The history textbook has 311 numeric blocks, and they are dates, not page numbers.

    Требование края страницы это единственное, что отделяет одно от другого.
    """
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "typeset_ru.pdf")
    assert texts(drop_page_numbers(pages)) == texts(pages)
