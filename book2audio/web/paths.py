"""Папка сохранения, пришедшая из браузера.

Флаг --copy-to задаёт папку на весь запуск сервера. Здесь то же самое,
но для одной книги: художественное на телефон, рабочее на диск.
"""

from pathlib import Path

# Папки, которые предлагаются в интерфейсе. Полный путь набирать руками
# неудобно, а этих трёх хватает почти всегда.
# Ключ, а не подпись: подпись выбирает интерфейс на своём языке.
SUGGESTED = (
    ("desktop", "Desktop/Audiobooks"),
    ("downloads", "Downloads/Audiobooks"),
    ("documents", "Documents/Audiobooks"),
)


class BadDestination(ValueError):
    """Путь не годится: относительный, или там лежит файл."""


def suggestions() -> list[dict]:
    """Готовые варианты папок с полными путями."""
    home = Path.home()
    return [{"key": key, "path": str(home / tail)} for key, tail in SUGGESTED]


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
