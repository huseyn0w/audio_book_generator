"""The save folder that came from the browser.

The --copy-to flag sets a folder for the whole server run. This is the same
thing for a single book: fiction to the phone, work books to the disk.
"""

from pathlib import Path

# The folders offered in the interface. Typing a full path by hand is
# awkward, and these three cover almost every case.
# A key, not a label: the interface picks the label in its own language.
SUGGESTED = (
    ("desktop", "Desktop/Audiobooks"),
    ("downloads", "Downloads/Audiobooks"),
    ("documents", "Documents/Audiobooks"),
)


class BadDestination(ValueError):
    """The path will not do: it is relative, or a file sits there."""


def suggestions() -> list[dict]:
    """The ready-made folder options with full paths."""
    home = Path.home()
    return [{"key": key, "path": str(home / tail)} for key, tail in SUGGESTED]


def resolve_destination(value: str | None) -> Path | None:
    """Turns the path from the form into a checked folder. Empty means the server folder."""
    if not value or not value.strip():
        return None

    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise BadDestination(
            f"a full path is needed, for example ~/Desktop/Audiobooks, not {value.strip()!r}"
        )
    if path.exists() and not path.is_dir():
        raise BadDestination(f"that is a file, not a folder: {path}")
    return path
