from dataclasses import FrozenInstanceError

import pytest

from book2audio.models import Block, Chapter, Document, Selection, parse_page_spec


def make_chapter(title="Глава 1", texts=("абзац раз", "абзац два")):
    return Chapter(title=title, blocks=[Block(kind="paragraph", text=t) for t in texts])


def test_block_rejects_unknown_kind():
    with pytest.raises(ValueError, match="неизвестный вид блока"):
        Block(kind="footnote", text="что-то")


def test_block_rejects_empty_text():
    with pytest.raises(ValueError, match="пустой текст"):
        Block(kind="paragraph", text="   ")


def test_block_is_frozen():
    block = Block(kind="paragraph", text="текст")
    with pytest.raises(FrozenInstanceError):
        block.text = "другой"


def test_chapter_counts_characters_of_its_blocks():
    assert make_chapter(texts=("абв", "гдеё")).char_count() == 7


def test_document_counts_characters_across_chapters():
    doc = Document(
        title="Книга",
        author="Автор",
        language="ru",
        chapters=[make_chapter(texts=("абв",)), make_chapter(texts=("гдеё",))],
    )
    assert doc.char_count() == 7


def test_document_rejects_unsupported_language():
    with pytest.raises(ValueError, match="неподдерживаемый язык"):
        Document(title="Buch", author=None, language="de", chapters=[])


def test_selection_defaults_to_whole_document():
    sel = Selection()
    assert sel.pages is None
    assert sel.chapters is None


def test_selection_rejects_pages_and_chapters_together():
    with pytest.raises(ValueError, match="или страницы, или главы"):
        Selection(pages=(1, 5), chapters=(0, 1))


def test_selection_rejects_reversed_page_range():
    with pytest.raises(ValueError, match="начало диапазона"):
        Selection(pages=(9, 3))


def test_selection_rejects_page_below_one():
    with pytest.raises(ValueError, match="страницы нумеруются с единицы"):
        Selection(pages=(0, 5))


def test_selection_page_range_is_inclusive():
    assert Selection(pages=(3, 5)).page_indexes() == [2, 3, 4]


def test_selection_page_indexes_is_empty_without_range():
    assert Selection().page_indexes() == []


# --- разбор диапазона страниц ---


def test_page_spec_reads_a_range():
    assert parse_page_spec("10-20").pages == (10, 20)


def test_page_spec_reads_a_single_page():
    assert parse_page_spec("7").pages == (7, 7)


def test_page_spec_ignores_spaces():
    assert parse_page_spec(" 10 - 20 ").pages == (10, 20)


def test_empty_page_spec_means_the_whole_book():
    assert parse_page_spec("") is None
    assert parse_page_spec(None) is None


@pytest.mark.parametrize("bad", ["abc", "10-", "-20", "20-10", "0-5", "1-2-3"])
def test_bad_page_spec_is_rejected(bad):
    with pytest.raises(ValueError):
        parse_page_spec(bad)
