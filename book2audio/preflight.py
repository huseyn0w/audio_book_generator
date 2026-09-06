"""Checks before the run.

A missing ffmpeg has to surface at startup, not while assembling the m4b, when
synthesis has already run for half an hour.
"""

import shutil
from pathlib import Path

# The tool and the command that installs it.
INSTALL = {"ffmpeg": "brew install ffmpeg", "espeak-ng": "brew install espeak-ng"}

# ffmpeg is always needed: it joins and encodes everything. espeak-ng phonemizes
# unknown words for Kokoro, so only English needs it. Silero manages on its own.
TOOLS_BY_LANGUAGE = {"ru": ("ffmpeg",), "en": ("ffmpeg", "espeak-ng")}

# A wav at 24000 Hz, 16 bit, mono is 48 kilobytes per second of speech.
BYTES_PER_SECOND = 48_000

# Prose speed, measured on real books.
CHARS_PER_SECOND = 15.0

# The chunk cache and the joined chapters sit on disk at the same time, plus room
# for the final m4b and ffmpeg's temporary files.
COPIES = 2.5


class MissingTool(Exception):
    """A system program is missing. The message carries the command that installs it."""


class NotEnoughSpace(Exception):
    """The intermediate wavs will not fit."""


def missing_tools(language: str | None = None) -> list[str]:
    """What is missing. Without a language it checks everything that could be needed."""
    if language is None:
        wanted: tuple[str, ...] = tuple(INSTALL)
    else:
        wanted = TOOLS_BY_LANGUAGE.get(language, tuple(INSTALL))
    return [tool for tool in wanted if shutil.which(tool) is None]


def check_tools(language: str | None = None) -> None:
    missing = missing_tools(language)
    if not missing:
        return
    commands = "; ".join(INSTALL[tool] for tool in missing)
    raise MissingTool(f"missing: {', '.join(missing)}. Install with: {commands}")


def estimate_bytes(chars: int) -> int:
    """How much room a book of this size needs while it is being worked on."""
    return int(chars / CHARS_PER_SECOND * BYTES_PER_SECOND * COPIES)


def free_bytes(path: Path) -> int:
    """Free space where the work will happen. The folder may not exist yet."""
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def check_space(path: Path, chars: int) -> None:
    needed = estimate_bytes(chars)
    free = free_bytes(path)
    if free >= needed:
        return
    raise NotEnoughSpace(
        f"not enough space: about {needed / 1e9:.1f} GB needed, {free / 1e9:.1f} GB free"
    )
