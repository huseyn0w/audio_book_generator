"""The cache of synthesized chunks.

A book run takes tens of minutes and will fail. Without a cache every failure
costs the whole run again.
"""

import hashlib
from pathlib import Path

from book2audio.audio import silence
from book2audio.tts.base import TTSEngine

# How many times we try one chunk. The engine sometimes trips on memory pressure
# or on one crooked character, and a retry usually gets through.
ATTEMPTS = 3

# Prose speed. It sets the length of the silence that replaces a failed chunk:
# the book must not drift out of time because of one hole.
CHARS_PER_SECOND = 15.0

# How many chunk characters go into the report. Enough to find the place in the
# book, and not so many that the report becomes a second copy of the text.
REPORT_CHARS = 200


class SynthCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0
        self.failures: list[str] = []

    def key(self, text: str, voice: str, engine: TTSEngine) -> str:
        """The engine version is part of the key: a new model must invalidate the cache."""
        # A zero byte as separator: the fields cannot merge ambiguously.
        material = f"{text}\x00{voice}\x00{engine.name}\x00{engine.version}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def path(self, text: str, voice: str, engine: TTSEngine) -> Path:
        return self.root / f"{self.key(text, voice, engine)}.wav"

    def synth(self, engine: TTSEngine, text: str, voice: str) -> Path:
        """Returns a wav from the cache, or synthesizes it and puts it there."""
        target = self.path(text, voice, engine)
        if target.exists():
            self.hits += 1
            return target

        # Write to a temporary file and rename: a truncated wav in the cache is
        # worse than a missing one, it would slip into the book unnoticed.
        staging = target.with_suffix(".part")
        try:
            engine.synth(text, voice, staging)
            staging.replace(target)
        except BaseException:
            staging.unlink(missing_ok=True)
            raise

        self.misses += 1
        return target

    def synth_or_silence(self, engine: TTSEngine, text: str, voice: str) -> Path:
        """Like synth, but a failed chunk turns into silence instead of killing the book.

        We check the voice and the empty text ourselves, before the engine: a retry
        will not save those, and a quiet substitution would turn the whole book into
        silence. Everything else, whatever the engine fails with, counts as a failure
        of this piece. Silero, for one, throws a bare ValueError on a piece it could
        not parse.
        """
        if voice not in {v.id for v in engine.voices()}:
            raise ValueError(f"unknown voice: {voice}")
        if not text.strip():
            raise ValueError("empty text")

        for attempt in range(ATTEMPTS):
            try:
                return self.synth(engine, text, voice)
            except Exception:  # noqa: BLE001 - the engine may fail with anything
                if attempt == ATTEMPTS - 1:
                    break

        self.failures.append(text)
        # The silence lives outside the chunk cache: otherwise, once the engine was
        # fixed, the book would quietly rebuild with the same holes.
        gaps = self.root / "failed"
        gaps.mkdir(exist_ok=True)
        gap = gaps / f"{self.key(text, voice, engine)}.wav"
        silence(gap, len(text) / CHARS_PER_SECOND, engine.sample_rate)
        return gap

    def report(self) -> dict:
        """What did not synthesize. Written next to the cleaning report."""
        return {
            "failed": len(self.failures),
            "chunks": [text[:REPORT_CHARS] for text in self.failures],
        }
