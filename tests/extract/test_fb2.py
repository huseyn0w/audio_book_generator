from pathlib import Path

import pytest

from book2audio.extract.base import Extractor
from book2audio.extract.fb2 import Fb2Extractor, flatten_sections
from book2audio.models import Selection

FIXTURES = Path(__file__).parent.parent / "fixtures"
BOOK = FIXTURES / "book_ru.fb2"


def test_fb2_extractor_satisfies_the_protocol():
    assert isinstance(Fb2Extractor(), Extractor)


def test_fb2_reads_metadata():
    doc = Fb2Extractor().extract(BOOK)
    assert "инноваций" in doc.title
    assert doc.author and "Кристенсен" in doc.author
    assert doc.language == "ru"


def test_fb2_produces_chapters_with_text():
    doc = Fb2Extractor().extract(BOOK)
    assert len(doc.chapters) >= 3
    assert doc.char_count() > 2000


def test_fb2_skips_the_notes_body():
    """The 202 notes in the Christensen book must not be read aloud."""
    doc = Fb2Extractor().extract(BOOK)
    text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    assert "Черный ящик" not in text or doc.char_count() < 400_000
    assert len(doc.chapters) < 50


def test_fb2_uses_section_titles_as_chapter_titles():
    doc = Fb2Extractor().extract(BOOK)
    titles = [c.title for c in doc.chapters]
    assert any("Предисловие" in t for t in titles)


def test_fb2_marks_the_title_block_as_a_heading():
    doc = Fb2Extractor().extract(BOOK)
    titled = [c for c in doc.chapters if c.title != "Начало"]
    assert titled
    assert titled[0].blocks[0].kind == "heading"


def test_fb2_flattens_nested_sections_into_chapters():
    doc = Fb2Extractor().extract(BOOK)
    assert len(doc.chapters) > 5


def test_fb2_blocks_have_no_page_numbers():
    """FB2 has no pages, and pretending it does is harmful."""
    doc = Fb2Extractor().extract(BOOK)
    assert all(b.page is None for c in doc.chapters for b in c.blocks)


def test_fb2_selection_by_chapters():
    everything = Fb2Extractor().extract(BOOK)
    subset = Fb2Extractor().extract(BOOK, Selection(chapters=(0, 1)))
    assert len(subset.chapters) == 2
    assert subset.chapters[0].title == everything.chapters[0].title


def test_fb2_selection_ignores_out_of_range_indexes():
    doc = Fb2Extractor().extract(BOOK, Selection(chapters=(0, 999)))
    assert len(doc.chapters) == 1


def test_fb2_text_is_normalized_for_speech():
    doc = Fb2Extractor().extract(BOOK)
    text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    assert "\xa0" not in text
    assert "  " not in text


def test_fb2_can_skip_normalization():
    doc = Fb2Extractor(clean=False).extract(BOOK)
    assert doc.char_count() > 0


def test_fb2_recovers_from_broken_xml(tmp_path):
    broken = tmp_path / "broken.fb2"
    broken.write_bytes(BOOK.read_bytes()[: int(BOOK.stat().st_size * 0.6)])
    doc = Fb2Extractor().extract(broken)
    assert doc.char_count() > 0


def test_fb2_rejects_a_file_that_is_not_fb2(tmp_path):
    not_fb2 = tmp_path / "x.fb2"
    not_fb2.write_text("<html><body>привет</body></html>", encoding="utf-8")
    with pytest.raises(ValueError, match="does not look like FB2"):
        Fb2Extractor().extract(not_fb2)


def test_flatten_sections_keeps_document_order():
    from lxml import etree

    xml = """<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
      <body>
        <section><title><p>Раз</p></title><p>Текст раз.</p>
          <section><title><p>Раз-два</p></title><p>Текст раз-два.</p></section>
        </section>
        <section><title><p>Два</p></title><p>Текст два.</p></section>
      </body>
    </FictionBook>"""
    root = etree.fromstring(xml.encode("utf-8"))
    chapters = flatten_sections(root)
    assert [c.title for c in chapters] == ["Раз", "Раз-два", "Два"]


# --- quotes are content ---


def test_cite_blocks_are_read_as_content():
    """In the Christensen book <cite> holds chapter summaries of 400-1400 characters.

    Найдено сверкой объёмов между FB2 и EPUB одной книги.
    """
    from lxml import etree

    xml = """<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
      <body><section><title><p>Гл</p></title>
        <cite><p>Важная мысль главы целиком.</p></cite>
        <p>Обычный абзац.</p>
      </section></body>
    </FictionBook>"""
    chapters = flatten_sections(etree.fromstring(xml.encode("utf-8")))
    texts = [b.text for b in chapters[0].blocks]
    assert "Важная мысль главы целиком." in texts


def test_signature_lines_are_skipped():
    """<text-author> is the attribution under a quote, not the book text."""
    from lxml import etree

    xml = """<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
      <body><section><title><p>Гл</p></title>
        <cite><text-author>Клейтон Кристенсен</text-author>
              <text-author>Бостон</text-author></cite>
        <p>Обычный абзац.</p>
      </section></body>
    </FictionBook>"""
    chapters = flatten_sections(etree.fromstring(xml.encode("utf-8")))
    texts = [b.text for b in chapters[0].blocks]
    assert "Бостон" not in " ".join(texts)
    assert "Обычный абзац." in texts


def test_epigraph_is_read_as_content():
    from lxml import etree

    xml = """<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
      <body><section><title><p>Гл</p></title>
        <epigraph><p>Эпиграф главы.</p></epigraph>
        <p>Текст.</p>
      </section></body>
    </FictionBook>"""
    chapters = flatten_sections(etree.fromstring(xml.encode("utf-8")))
    assert "Эпиграф главы." in [b.text for b in chapters[0].blocks]
