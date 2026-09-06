"""The order the cleaning rules are applied in, and the report on what was dropped.

The order matters. First we drop the service blocks, while they still have
coordinates and a font. Then we set the reading order. Only after that do we
join the fragments: joining erases block boundaries, and a running head glued
to a paragraph can no longer be removed.
"""

from dataclasses import dataclass, field, replace

from book2audio.clean.pdf_layout import (
    drop_figure_captions,
    drop_footnotes,
    drop_non_prose,
    drop_numeric_captions,
    drop_page_numbers,
    drop_running_heads,
    merge_continuations,
    sort_reading_order,
)
from book2audio.clean.text import clean_text
from book2audio.extract.layout import RawBlock, RawPage, median_font_size

RULE_NAMES = {
    "running_heads": "running heads",
    "page_numbers": "page numbers",
    "figure_captions": "figure captions",
    "listings": "listings and tables",
    "numeric_captions": "numeric captions",
    "footnotes": "footnotes",
}


@dataclass
class CleanReport:
    """What was dropped and by which rule. Written into clean_report.json."""

    dropped: dict[str, int] = field(default_factory=dict)
    kept: int = 0
    chars_before: int = 0
    chars_after: int = 0

    def as_dict(self) -> dict:
        return {
            "kept": self.kept,
            "dropped": dict(self.dropped),
            "chars_before": self.chars_before,
            "chars_after": self.chars_after,
            "summary": self.summary(),
        }

    def summary(self) -> str:
        """A line for the CLI. The interface builds its own out of dropped."""
        if not self.chars_before:
            return "nothing to clean"
        loss = 1 - self.chars_after / self.chars_before
        parts = ", ".join(
            f"{RULE_NAMES.get(name, name)} {count}" for name, count in self.dropped.items() if count
        )
        tail = f": {parts}" if parts else ""
        return f"cleaning removed {loss:.1%} of the characters{tail}"


def _count(pages: list[RawPage]) -> int:
    return sum(len(p.blocks) for p in pages)


def clean_pages(pages: list[RawPage]) -> tuple[list[RawBlock], CleanReport]:
    """Runs the pages through every rule and returns a flat list of blocks."""
    report = CleanReport()
    if not pages:
        return [], report

    report.chars_before = sum(p.char_count() for p in pages)
    median = median_font_size([b for p in pages for b in p.blocks] or [])

    # Keys, not labels: the report is read both by the CLI and by the interface
    # in the chosen language. Whoever shows it picks the label.
    rules = [
        ("running_heads", drop_running_heads),
        ("page_numbers", drop_page_numbers),
        ("figure_captions", drop_figure_captions),
        ("listings", drop_non_prose),
        ("numeric_captions", lambda pgs: drop_numeric_captions(pgs, median)),
        ("footnotes", lambda pgs: drop_footnotes(pgs, median)),
    ]
    for name, rule in rules:
        before = _count(pages)
        pages = rule(pages)
        report.dropped[name] = before - _count(pages)

    pages = [sort_reading_order(p) for p in pages]

    blocks = merge_continuations([b for p in pages for b in p.blocks])
    blocks = [replace(b, text=clean_text(b.text)) for b in blocks if clean_text(b.text)]

    report.kept = len(blocks)
    report.chars_after = sum(len(b.text) for b in blocks)
    return blocks, report
