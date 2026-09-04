"""Обложка. m4b без картинки выглядит в плеере безымянной серой плиткой."""

import base64
import zipfile
from pathlib import Path

import pytest

from book2audio.extract.epub import EpubExtractor
from book2audio.extract.fb2 import Fb2Extractor

# Самый маленький валидный JPEG-заголовок. Содержимое неважно, важен факт.
PIXEL = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)

FB2_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"
             xmlns:l="http://www.w3.org/1999/xlink">
  <description><title-info>
    <book-title>Книга</book-title><lang>ru</lang>
    {coverpage}
  </title-info></description>
  <body><section><title><p>Глава</p></title><p>Текст главы для проверки.</p></section></body>
  {binary}
</FictionBook>"""


def write_fb2(path: Path, with_cover: bool) -> Path:
    encoded = base64.b64encode(PIXEL).decode("ascii")
    path.write_text(
        FB2_TEMPLATE.format(
            coverpage='<coverpage><image l:href="#cover.jpg"/></coverpage>' if with_cover else "",
            binary=(
                f'<binary id="cover.jpg" content-type="image/jpeg">{encoded}</binary>'
                if with_cover
                else ""
            ),
        ),
        encoding="utf-8",
    )
    return path


def write_epub(path: Path, with_cover: bool) -> Path:
    """Минимальный EPUB 2: обложка помечена через <meta name="cover">."""
    meta = '<meta name="cover" content="cover-image"/>' if with_cover else ""
    manifest = (
        '<item id="cover-image" href="cover.jpg" media-type="image/jpeg"/>' if with_cover else ""
    )
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">book-1</dc:identifier>
    <dc:title>Книга</dc:title><dc:language>ru</dc:language>
    {meta}
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    {manifest}
  </manifest>
  <spine toc="ncx"><itemref idref="ch1"/></spine>
</package>"""
    ncx = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head/><docTitle><text>Книга</text></docTitle>
  <navMap><navPoint id="n1" playOrder="1">
    <navLabel><text>Глава</text></navLabel><content src="ch1.xhtml"/>
  </navPoint></navMap>
</ncx>"""
    chapter = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>Глава</h1><p>Текст главы для проверки.</p></body></html>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr("content.opf", opf)
        archive.writestr("toc.ncx", ncx)
        archive.writestr("ch1.xhtml", chapter)
        if with_cover:
            archive.writestr("cover.jpg", PIXEL)
    return path


def test_fb2_extracts_cover(tmp_path):
    document = Fb2Extractor().extract(write_fb2(tmp_path / "b.fb2", with_cover=True))
    assert document.cover == PIXEL


def test_fb2_without_coverpage_has_no_cover(tmp_path):
    document = Fb2Extractor().extract(write_fb2(tmp_path / "b.fb2", with_cover=False))
    assert document.cover is None


def test_epub_extracts_cover(tmp_path):
    document = EpubExtractor().extract(write_epub(tmp_path / "b.epub", with_cover=True))
    assert document.cover == PIXEL


def test_epub_without_cover_has_none(tmp_path):
    document = EpubExtractor().extract(write_epub(tmp_path / "b.epub", with_cover=False))
    assert document.cover is None


def test_pdf_document_has_no_cover_field_set(tmp_path):
    from book2audio.extract.pdf import PdfExtractor

    fixtures = Path(__file__).parent.parent / "fixtures"
    document = PdfExtractor().extract(fixtures / "toc_ru.pdf")
    assert document.cover is None


@pytest.mark.parametrize("name", ["book_ru.fb2", "book_ru.epub"])
def test_real_fixtures_still_extract(tmp_path, name):
    """Обложки в вырезках может не быть, но извлечение не должно ломаться."""
    fixtures = Path(__file__).parent.parent / "fixtures"
    extractor = Fb2Extractor() if name.endswith(".fb2") else EpubExtractor()
    document = extractor.extract(fixtures / name)
    assert document.chapters
    assert document.cover is None or isinstance(document.cover, bytes)


def _has_cover_stream(path: Path) -> bool:
    import subprocess

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=nw=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return "codec_name=" in probe.stdout


def test_cover_reaches_the_m4b(tmp_path):
    from book2audio.pipeline import convert
    from book2audio.tts.fake import FakeEngine

    book = write_fb2(tmp_path / "b.fb2", with_cover=True)
    out = convert(
        book,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path / "out",
        engine=FakeEngine(),
        work_dir=tmp_path / "work",
    )
    assert _has_cover_stream(out)


def test_book_without_cover_still_builds(tmp_path):
    from book2audio.pipeline import convert
    from book2audio.tts.fake import FakeEngine

    book = write_fb2(tmp_path / "b.fb2", with_cover=False)
    out = convert(
        book,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path / "out",
        engine=FakeEngine(),
        work_dir=tmp_path / "work",
    )
    assert out.exists()
    assert not _has_cover_stream(out)
