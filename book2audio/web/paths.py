"""Папка сохранения, пришедшая из браузера.

Флаг --copy-to задаёт папку на весь запуск сервера. Здесь то же самое,
но для одной книги: художественное на телефон, рабочее на диск.
"""

from pathlib import Path

# Папки, которые предлагаются в интерфейсе. Полный путь набирать руками
# неудобно, а этих трёх хватает почти всегда.
SUGGESTED = (
    ("Рабочий стол", "Desktop/Audiobooks"),
    ("Загрузки", "Downloads/Audiobooks"),
    ("Документы", "Documents/Audiobooks"),
)


class BadDestination(ValueError):
    """Путь не годится: относительный, или там лежит файл."""


def suggestions() -> list[dict]:
    """Готовые варианты папок с полными путями."""
    home = Path.home()
    items = [{"label": label, "path": str(home / tail)} for label, tail in SUGGESTED]
    from book2audio.pipeline import ICLOUD_AUDIOBOOKS

    items.insert(0, {"label": "iCloud Drive", "path": str(ICLOUD_AUDIOBOOKS)})
    return items


def resolve_destination(value: str | None) -> Path | None:
    """Путь из формы в проверенную папку. Пусто значит папку сервера."""
    if not value or not value.strip():
        return None

    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise BadDestination(
            f"нужен полный путь, например ~/Desktop/Audiobooks, а не {value.strip()!r}"
        )
    if path.exists() and not path.is_dir():
        raise BadDestination(f"это не папка, а файл: {path}")
    return path
