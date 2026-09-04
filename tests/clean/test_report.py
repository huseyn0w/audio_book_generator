from pathlib import Path

from book2audio.clean.pipeline import clean_pages
from book2audio.extract.layout import RawBlock, RawPage

FIXTURES = Path(__file__).parent.parent / "fixtures"


def blk(text, size=13.0, top=100.0, left=50.0, width=450.0, page=1):
    return RawBlock(text=text, font_size=size, bbox=(left, top, left + width, top + 12), page=page)


def page(number, blocks, height=800.0):
    return RawPage(number=number, width=600.0, height=height, blocks=blocks)


def test_report_counts_drops_per_rule():
    pages = [page(1, [blk("Обычный текст здесь."), blk("42", top=770.0, width=20.0)])]
    _, report = clean_pages(pages)
    assert report.dropped["колонцифры"] == 1


def test_report_knows_how_many_blocks_survived():
    pages = [page(1, [blk("Первый абзац."), blk("Второй абзац.")])]
    blocks, report = clean_pages(pages)
    assert report.kept == len(blocks) == 2


def test_report_serializes_to_json_friendly_dict():
    pages = [page(1, [blk("Текст.")])]
    _, report = clean_pages(pages)
    data = report.as_dict()
    assert set(data) == {"kept", "dropped", "chars_before", "chars_after"}
    assert isinstance(data["dropped"], dict)


def test_report_tracks_character_loss():
    pages = [page(1, [blk("Обычный текст здесь."), blk("42", top=770.0, width=20.0)])]
    _, report = clean_pages(pages)
    assert report.chars_before > report.chars_after


def test_clean_pages_returns_a_flat_block_list():
    pages = [page(1, [blk("Первый.")]), page(2, [blk("Второй.", page=2)])]
    blocks, _ = clean_pages(pages)
    assert [b.text for b in blocks] == ["Первый.", "Второй."]


def test_clean_pages_merges_fragments_across_the_whole_document():
    pages = [page(1, [blk("Начало фразы")]), page(2, [blk("и её конец.", page=2)])]
    blocks, _ = clean_pages(pages)
    assert [b.text for b in blocks] == ["Начало фразы и её конец."]


def test_clean_pages_applies_text_rules():
    pages = [page(1, [blk('госу- дарство и  "порядок".')])]
    blocks, _ = clean_pages(pages)
    assert blocks[0].text == "государство и «порядок»."


def test_clean_pages_survives_an_empty_document():
    blocks, report = clean_pages([])
    assert blocks == []
    assert report.kept == 0


# --- реальные данные ---


def test_clean_book_loses_almost_nothing():
    """На Кристенсене чистить нечего, потери должны быть в пределах шума."""
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "toc_ru.pdf")
    _, report = clean_pages(pages)
    loss = 1 - report.chars_after / report.chars_before
    assert loss < 0.03, f"потеряно {loss:.1%}"


def test_typeset_book_drops_real_noise():
    from book2audio.extract.pdf import read_pages

    pages = read_pages(FIXTURES / "typeset_ru.pdf")
    _, report = clean_pages(pages)
    assert report.dropped["подписи к рисункам"] >= 20


def test_no_rule_eats_more_than_half_of_a_real_book():
    from book2audio.extract.pdf import read_pages

    for name in ("toc_ru.pdf", "no_toc_ru.pdf", "typeset_ru.pdf", "typeset_en.pdf"):
        pages = read_pages(FIXTURES / name)
        _, report = clean_pages(pages)
        loss = 1 - report.chars_after / report.chars_before
        assert loss < 0.5, f"{name}: потеряно {loss:.1%}"
