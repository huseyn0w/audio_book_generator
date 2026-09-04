"""Порядок применения правил чистки и отчёт о том, что выброшено.

Порядок важен. Сначала выбрасываем служебные блоки, пока у них ещё есть
координаты и шрифт. Потом расставляем порядок чтения. Только после этого
склеиваем обрывки: склейка стирает границы блоков, и колонтитул,
приклеенный к абзацу, уже не выкинуть.
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


@dataclass
class CleanReport:
    """Что и каким правилом выброшено. Пишется в clean_report.json."""

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
        }

    def summary(self) -> str:
        if not self.chars_before:
            return "чистить нечего"
        loss = 1 - self.chars_after / self.chars_before
        parts = ", ".join(f"{name} {count}" for name, count in self.dropped.items() if count)
        tail = f": {parts}" if parts else ""
        return f"чистка убрала {loss:.1%} символов{tail}"


def _count(pages: list[RawPage]) -> int:
    return sum(len(p.blocks) for p in pages)


def clean_pages(pages: list[RawPage]) -> tuple[list[RawBlock], CleanReport]:
    """Прогоняет страницы через все правила и отдаёт плоский список блоков."""
    report = CleanReport()
    if not pages:
        return [], report

    report.chars_before = sum(p.char_count() for p in pages)
    median = median_font_size([b for p in pages for b in p.blocks] or [])

    rules = [
        ("колонтитулы", drop_running_heads),
        ("колонцифры", drop_page_numbers),
        ("подписи к рисункам", drop_figure_captions),
        ("листинги и таблицы", drop_non_prose),
        ("числовые подписи", lambda pgs: drop_numeric_captions(pgs, median)),
        ("сноски", lambda pgs: drop_footnotes(pgs, median)),
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
