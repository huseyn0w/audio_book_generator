"""Cutting test fixtures out of real books.

Whole books never go into the repository, only clippings of a few pages. The
sources live in ~/Downloads and may be missing on another machine, so this script
is run by hand rather than by the tests.

Usage:
    uv run python scripts/make_fixtures.py
"""

from pathlib import Path

import pymupdf

SOURCES = Path.home() / "Downloads"
FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"

# fixture name -> (source file, first page, last page, what it is for)
RECIPES: dict[str, tuple[str, int, int, str]] = {
    "toc_ru.pdf": ("430741.pdf", 22, 30, "has bookmarks and metadata"),
    "no_toc_ru.pdf": (
        "Нил Штраус Правда Неудобная книга об отношениях.pdf",
        30,
        36,
        "no bookmarks, chapters are found by font size",
    ),
    "scanned_ru.pdf": (
        "Glavnoe_v_istorii_iskusstv.pdf",
        10,
        12,
        "no text layer, we expect a readable error",
    ),
    "typeset_ru.pdf": (
        "7-hist-05.pdf",
        44,
        51,
        "two columns, running heads, footnotes in a small font, line break hyphens",
    ),
    "typeset_en.pdf": (
        "Cracking the Coding Interview 189 Programming Questions and Solutions.pdf",
        60,
        66,
        "running heads, page numbers, code listings",
    ),
}


def cut(source: Path, first: int, last: int, target: Path) -> None:
    """Cuts pages first through last inclusive, numbered from one."""
    src = pymupdf.open(source)
    out = pymupdf.open()
    out.insert_pdf(src, from_page=first - 1, to_page=last - 1)
    out.set_metadata(src.metadata)
    # Bookmarks point at the original pages, and a clipping numbers its own.
    kept = [
        [level, title, page - first + 1]
        for level, title, page in src.get_toc()
        if first <= page <= last
    ]
    if kept:
        out.set_toc(kept)
    out.save(target, garbage=4, deflate=True)
    out.close()
    src.close()


def cut_fb2(source: Path, keep_sections: int, target: Path) -> None:
    """Keeps the first sections of the first body and trims the notes.

    The second body with name="notes" is kept on purpose: the fixture exists to
    check that the notes never reach the audio.
    """
    from lxml import etree

    tree = etree.parse(str(source), etree.XMLParser(recover=True))
    root = tree.getroot()
    ns = {"fb": root.nsmap.get(None, "")}

    bodies = root.findall("fb:body", ns)
    for index, body in enumerate(bodies):
        sections = body.findall("fb:section", ns)
        limit = keep_sections if index == 0 else 3
        for section in sections[limit:]:
            body.remove(section)

    # The images weigh more than the text itself and the tests do not need them.
    for binary in root.findall("fb:binary", ns)[1:]:
        root.remove(binary)

    target.write_bytes(etree.tostring(tree, xml_declaration=True, encoding="utf-8"))


def cut_epub(source: Path, keep_docs: int, target: Path) -> None:
    """Keeps the first spine documents together with their part of the contents."""
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(str(source))
    kept_ids = [item_id for item_id, _ in book.spine[:keep_docs]]
    kept_names = set()

    trimmed = epub.EpubBook()
    trimmed.set_identifier("fixture")
    for key in ("title", "creator", "language"):
        values = book.get_metadata("DC", key)
        if values:
            setter = {
                "title": trimmed.set_title,
                "creator": trimmed.add_author,
                "language": trimmed.set_language,
            }[key]
            setter(values[0][0])

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        if item.get_id() in kept_ids:
            trimmed.add_item(item)
            kept_names.add(item.get_name())

    def keep_entry(entry):
        link = entry[0] if isinstance(entry, tuple) else entry
        return getattr(link, "href", "").split("#")[0] in kept_names

    trimmed.toc = [
        (e[0], [k for k in e[1] if keep_entry(k)]) if isinstance(e, tuple) else e
        for e in book.toc
        if keep_entry(e)
    ]
    trimmed.spine = [item_id for item_id in kept_ids]
    trimmed.add_item(epub.EpubNcx())
    trimmed.add_item(epub.EpubNav())
    epub.write_epub(str(target), trimmed)


EBOOK_RECIPES: dict[str, tuple[str, int, str]] = {
    "book_ru.fb2": ("430741.fb2", 5, "sections, nesting, a separate notes body"),
    "book_ru.epub": (
        (
            "Kristensen_Reshenie-problemy-innovaciy-v-biznese-Kak-sozdat-rastushchiy-biznes-"
            "i-uspeshno-podderzhivat-ego-rost.430741.fb2.epub"
        ),
        12,
        "nested contents with anchors, no h1-h3 headings",
    ),
}


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, (source_name, first, last, why) in RECIPES.items():
        source = SOURCES / source_name
        if not source.exists():
            print(f"skipped {name}: no source {source}")
            continue
        target = FIXTURES / name
        cut(source, first, last, target)
        size_kb = target.stat().st_size // 1024
        print(f"{name:16} {size_kb:5} KB  pages {first}-{last}  {why}")

    for name, (source_name, keep, why) in EBOOK_RECIPES.items():
        source = SOURCES / source_name
        if not source.exists():
            print(f"skipped {name}: no source {source}")
            continue
        target = FIXTURES / name
        if name.endswith(".fb2"):
            cut_fb2(source, keep, target)
        else:
            cut_epub(source, keep, target)
        print(f"{name:16} {target.stat().st_size // 1024:5} KB  {why}")


if __name__ == "__main__":
    main()
