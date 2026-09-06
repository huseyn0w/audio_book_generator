"""PDF extraction through PyMuPDF.

We take get_text("dict") rather than bare text: the dictionary gives the font
size, the style and the coordinates of every span. Without that data phase 2
cannot tell a running head from a paragraph, so it must not be lost.
"""

from dataclasses import replace
from pathlib import Path

import pymupdf

from book2audio.clean.pipeline import CleanReport, clean_pages
from book2audio.clean.speech import normalize_for_speech
from book2audio.extract.base import NoTextLayer
from book2audio.extract.layout import RawBlock, RawPage, median_font_size
from book2audio.models import OPENING_TITLE, UNTITLED, Block, Chapter, Document, Selection

# Below this many characters per page we treat the text layer as absent.
MIN_CHARS_PER_PAGE = 100

# How many times larger a heading font is than the median one.
HEADING_FONT_RATIO = 1.15

# A heading is a short line. Long text in a large font is a pull quote.
HEADING_MAX_CHARS = 120

MONOSPACED_FLAG = 8


def _block_text(raw: dict) -> str:
    """Joins a block's spans into a line.

    Spans inside a line sit flush: a span break is a font change, often mid-word.
    Lines are joined to each other with a space, otherwise the last and the first
    word stick together at the line break.

    Some PDFs give text with a space between every pair of letters. That is an
    extraction artifact rather than content, so we collapse it here, not in phase 2.
    """
    lines = ["".join(span["text"] for span in line["spans"]) for line in raw.get("lines", [])]
    return " ".join(" ".join(lines).split())


def _block_font_size(raw: dict) -> float:
    sizes = [span["size"] for line in raw.get("lines", []) for span in line["spans"]]
    return max(sizes) if sizes else 0.0


def _block_is_mono(raw: dict) -> bool:
    flags = [span["flags"] for line in raw.get("lines", []) for span in line["spans"]]
    return bool(flags) and all(f & MONOSPACED_FLAG for f in flags)


def read_pages(path: Path, selection: Selection | None = None) -> list[RawPage]:
    """Reads PDF pages into the raw layout. Pages outside the range are never opened."""
    doc = pymupdf.open(path)
    try:
        wanted = selection.page_indexes() if selection else list(range(doc.page_count))
        if not wanted:
            wanted = list(range(doc.page_count))
        if wanted[-1] >= doc.page_count:
            raise ValueError(
                f"page {wanted[-1] + 1} is past the end, the document has {doc.page_count}"
            )

        pages: list[RawPage] = []
        for index in wanted:
            page = doc[index]
            blocks: list[RawBlock] = []
            for raw in page.get_text("dict", sort=True)["blocks"]:
                text = _block_text(raw)
                if not text:
                    continue
                blocks.append(
                    RawBlock(
                        text=text,
                        font_size=_block_font_size(raw),
                        bbox=tuple(raw["bbox"]),
                        page=index + 1,
                        is_mono=_block_is_mono(raw),
                    )
                )
            pages.append(
                RawPage(
                    number=index + 1,
                    width=page.rect.width,
                    height=page.rect.height,
                    blocks=blocks,
                )
            )
        return pages
    finally:
        doc.close()


def _is_heading(block: RawBlock, median: float) -> bool:
    return block.font_size >= median * HEADING_FONT_RATIO and len(block.text) <= HEADING_MAX_CHARS


def split_into_chapters(
    blocks: list[RawBlock], median: float, language: str = "ru"
) -> list[Chapter]:
    """Cuts the block stream into chapters by font size. The fallback without bookmarks."""
    chapters: list[Chapter] = []
    current = Chapter(title=UNTITLED[language], blocks=[])

    for raw in blocks:
        if _is_heading(raw, median):
            if current.blocks:
                chapters.append(current)
            current = Chapter(
                title=raw.text,
                blocks=[Block(kind="heading", text=raw.text, page=raw.page)],
            )
        else:
            current.blocks.append(Block(kind="paragraph", text=raw.text, page=raw.page))

    if current.blocks:
        chapters.append(current)
    return chapters


def _find_heading_index(
    blocks: list[RawBlock], title: str, page: int, search_from: int
) -> int | None:
    """Looks for the block holding the heading text on the bookmark page."""
    wanted = title.strip()
    for index in range(search_from, len(blocks)):
        if blocks[index].page > page:
            break
        if blocks[index].page == page and blocks[index].text.strip() == wanted:
            return index
    return None


def _find_page_start(blocks: list[RawBlock], page: int, search_from: int) -> int | None:
    for index in range(search_from, len(blocks)):
        if blocks[index].page >= page:
            return index
    return None


def chapters_from_toc(
    toc: list[list], blocks: list[RawBlock], first_page: int, language: str = "ru"
) -> list[Chapter]:
    """Cuts the blocks at the PDF bookmarks.

    A chapter boundary is the block with the heading text, not the page edge.
    Subchapters often start mid-page, and cutting on the page drags the tail of the
    previous chapter into the next one and makes the heading get read twice.
    """
    starts = [(page, title) for _level, title, page in toc if page >= first_page]
    if not starts:
        return []

    marks: list[tuple[int, str, bool]] = []
    search_from = 0
    for page, title in starts:
        index = _find_heading_index(blocks, title, page, search_from)
        is_heading = index is not None
        if index is None:
            index = _find_page_start(blocks, page, search_from)
        if index is None:
            continue
        marks.append((index, title, is_heading))
        search_from = index + 1

    if not marks:
        return []

    chapters: list[Chapter] = []
    for position, (index, title, is_heading) in enumerate(marks):
        stop = marks[position + 1][0] if position + 1 < len(marks) else len(blocks)
        inside = blocks[index:stop]
        if not inside:
            continue
        kinds = ["heading" if is_heading and i == 0 else "paragraph" for i in range(len(inside))]
        chapters.append(
            Chapter(
                title=title,
                blocks=[
                    Block(kind=kind, text=b.text, page=b.page)
                    for kind, b in zip(kinds, inside, strict=True)
                ],
            )
        )

    # The blocks before the first bookmark are the preface, and must not be lost.
    head = blocks[: marks[0][0]]
    if head:
        chapters.insert(
            0,
            Chapter(
                title=OPENING_TITLE[language],
                blocks=[Block(kind="paragraph", text=b.text, page=b.page) for b in head],
            ),
        )
    return chapters


class PdfExtractor:
    def __init__(self, clean: bool = True, language: str = "ru") -> None:
        self.clean = clean
        # A PDF carries no language in its metadata or its markup, so whoever picks
        # the voice names it. Normalization has to match the voice: Russian numerals
        # inside an English book read as garbage.
        self.language = language
        self.report: CleanReport | None = None

    def extract(self, path: Path, selection: Selection | None = None) -> Document:
        pages = read_pages(path, selection)
        blocks = [b for p in pages for b in p.blocks]

        chars_per_page = sum(len(b.text) for b in blocks) / max(1, len(pages))
        if chars_per_page < MIN_CHARS_PER_PAGE:
            raise NoTextLayer(
                f"the PDF has no text layer ({chars_per_page:.0f} characters per page). "
                "This looks like a scan. It needs OCR, which is out of scope here."
            )

        doc = pymupdf.open(path)
        try:
            toc = doc.get_toc()
            meta = dict(doc.metadata or {})
        finally:
            doc.close()

        if self.clean:
            blocks, self.report = clean_pages(pages)
            if not blocks:
                raise NoTextLayer("no text was left after cleaning")

        chapters = chapters_from_toc(toc, blocks, pages[0].number, self.language) if toc else []
        if not chapters:
            chapters = split_into_chapters(blocks, median_font_size(blocks), self.language)

        language = self.language
        if self.clean:
            for chapter in chapters:
                chapter.title = normalize_for_speech(chapter.title, language)
                chapter.blocks = [
                    replace(b, text=normalize_for_speech(b.text, language)) for b in chapter.blocks
                ]

        return Document(
            title=meta.get("title") or path.stem,
            author=meta.get("author") or None,
            language=language,
            chapters=chapters,
        )
