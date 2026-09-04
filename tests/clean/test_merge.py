import pytest

from book2audio.clean.pdf_layout import MERGED_MAX_CHARS, merge_continuations
from book2audio.extract.layout import RawBlock


def blk(text, size=13.0, top=100.0, page=1):
    return RawBlock(text=text, font_size=size, bbox=(50.0, top, 500.0, top + 12), page=page)


def texts(blocks):
    return [b.text for b in blocks]


def test_block_without_terminal_punctuation_joins_the_next():
    merged = merge_continuations([blk("Начало фразы"), blk("и её конец.")])
    assert texts(merged) == ["Начало фразы и её конец."]


def test_block_ending_with_a_period_stays_alone():
    merged = merge_continuations([blk("Первый абзац."), blk("Второй абзац.")])
    assert texts(merged) == ["Первый абзац.", "Второй абзац."]


@pytest.mark.parametrize("ending", [".", "!", "?", "…", ":", ";", "»", '"'])
def test_all_terminal_marks_stop_the_merge(ending):
    merged = merge_continuations([blk(f"Конец{ending}"), blk("Дальше.")])
    assert len(merged) == 2


def test_three_fragments_join_into_one_paragraph():
    merged = merge_continuations([blk("Раз"), blk("два"), blk("три.")])
    assert texts(merged) == ["Раз два три."]


def test_merge_keeps_the_first_block_page_and_font():
    merged = merge_continuations([blk("Начало", page=7), blk("конец.", page=8)])
    assert merged[0].page == 7
    assert merged[0].font_size == 13.0


def test_merge_stops_at_a_font_size_change():
    """Смена кегля означает смену роли блока, склеивать нельзя."""
    merged = merge_continuations([blk("Обычный текст", size=13.0), blk("Заголовок", size=20.0)])
    assert len(merged) == 2


def test_merge_stops_before_exceeding_the_length_cap():
    """Сломанная вёрстка иначе склеит всю главу в один блок."""
    pieces = [blk("а" * 500) for _ in range(20)]
    merged = merge_continuations(pieces)
    assert all(len(b.text) <= MERGED_MAX_CHARS for b in merged)
    assert len(merged) > 1


def test_trailing_fragment_survives_without_a_successor():
    merged = merge_continuations([blk("Оборванный хвост")])
    assert texts(merged) == ["Оборванный хвост"]


def test_empty_input_gives_empty_output():
    assert merge_continuations([]) == []


def test_merge_reduces_fragmentation_on_the_real_fixture():
    from pathlib import Path

    from book2audio.extract.pdf import read_pages

    fixtures = Path(__file__).parent.parent / "fixtures"
    blocks = [b for p in read_pages(fixtures / "typeset_ru.pdf") for b in p.blocks]
    merged = merge_continuations(blocks)
    assert len(merged) < len(blocks) * 0.7
