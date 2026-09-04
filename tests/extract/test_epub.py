from pathlib import Path

import pytest

from book2audio.extract.base import Extractor
from book2audio.extract.epub import EpubExtractor, flatten_toc
from book2audio.models import Selection

FIXTURES = Path(__file__).parent.parent / "fixtures"
BOOK = FIXTURES / "book_ru.epub"


def test_epub_extractor_satisfies_the_protocol():
    assert isinstance(EpubExtractor(), Extractor)


def test_epub_reads_metadata():
    doc = EpubExtractor().extract(BOOK)
    assert "инноваций" in doc.title
    assert doc.author and "Кристенсен" in doc.author
    assert doc.language == "ru"


def test_epub_produces_chapters_with_text():
    doc = EpubExtractor().extract(BOOK)
    assert len(doc.chapters) >= 2
    assert doc.char_count() > 2000


def test_epub_takes_chapters_from_the_toc_not_from_headings():
    """В книге нет ни одного h1-h3, главы существуют только в оглавлении."""
    doc = EpubExtractor().extract(BOOK)
    titles = [c.title for c in doc.chapters]
    assert any("Предисловие" in t or "благодарность" in t.lower() for t in titles)


def test_epub_splits_at_anchors_inside_a_file():
    """Оглавление ссылается на ch1-5.xhtml#id4, то есть на середину файла."""
    doc = EpubExtractor().extract(BOOK)
    pairs = [(c.title, c.char_count()) for c in doc.chapters]
    assert len(pairs) >= 3
    assert all(count > 0 for _, count in pairs)


def test_epub_follows_spine_order():
    doc = EpubExtractor().extract(BOOK)
    text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    assert text.strip()


def test_epub_blocks_have_no_page_numbers():
    doc = EpubExtractor().extract(BOOK)
    assert all(b.page is None for c in doc.chapters for b in c.blocks)


def test_epub_selection_by_chapters():
    subset = EpubExtractor().extract(BOOK, Selection(chapters=(0,)))
    assert len(subset.chapters) == 1


def test_epub_text_is_normalized_for_speech():
    doc = EpubExtractor().extract(BOOK)
    text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    assert "\xa0" not in text
    assert "  " not in text


def test_epub_can_skip_normalization():
    doc = EpubExtractor(clean=False).extract(BOOK)
    assert doc.char_count() > 0


def test_epub_rejects_a_file_that_is_not_epub(tmp_path):
    fake = tmp_path / "x.epub"
    fake.write_text("не архив", encoding="utf-8")
    with pytest.raises(ValueError, match="не похож на EPUB"):
        EpubExtractor().extract(fake)


def test_flatten_toc_walks_nested_entries_in_order():
    class Link:
        def __init__(self, title, href):
            self.title = title
            self.href = href

    toc = [
        Link("Раз", "a.xhtml#id1"),
        (Link("Два", "a.xhtml#id2"), [Link("Два-раз", "b.xhtml#id3")]),
        Link("Три", "c.xhtml"),
    ]
    assert flatten_toc(toc) == [
        ("Раз", "a.xhtml", "id1"),
        ("Два", "a.xhtml", "id2"),
        ("Два-раз", "b.xhtml", "id3"),
        ("Три", "c.xhtml", ""),
    ]


# --- концевые сноски ---


def test_endnote_documents_are_skipped():
    """Конвертеры fb2 в epub кладут сноски отдельными файлами вне оглавления.

    У Кристенсена это 202 файла и 162 тысячи символов, то есть три часа
    обрывочного текста в конце тринадцатичасовой книги.
    """
    from book2audio.extract.epub import looks_like_endnote

    assert looks_like_endnote(["168", "Там же, с. 40."], in_toc=False)
    assert not looks_like_endnote(["168", "Там же, с. 40."], in_toc=True)
    assert not looks_like_endnote(["Обычный абзац книги."], in_toc=False)
    assert not looks_like_endnote([], in_toc=False)


def test_endnote_first_paragraph_must_be_only_a_number():
    from book2audio.extract.epub import looks_like_endnote

    assert not looks_like_endnote(["Глава 168", "текст"], in_toc=False)
    assert not looks_like_endnote(["1998 год был непростым"], in_toc=False)


def test_real_book_drops_endnotes_and_matches_the_fb2_edition():
    """FB2 и EPUB это одна книга, объёмы обязаны сойтись."""
    doc = EpubExtractor().extract(BOOK)
    text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    assert "Там же" not in text
