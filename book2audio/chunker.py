"""Cutting text into synthesis chunks and placing the pauses.

The engine synthesizes pieces, not a whole book. We never break a sentence:
a broken one is audible at once, the intonation stops mid-word.
"""

from dataclasses import dataclass

import pysbd

from book2audio.models import Document

CHUNK_LIMIT = 800

PAUSE_IN_PARAGRAPH = 0.25
PAUSE_BETWEEN_PARAGRAPHS = 0.7
PAUSE_BETWEEN_CHAPTERS = 1.5


@dataclass(frozen=True)
class Chunk:
    text: str
    pause_after: float

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("empty chunk text")
        if self.pause_after < 0:
            raise ValueError(f"a pause cannot be negative: {self.pause_after}")


def split_long_sentence(sentence: str, limit: int) -> list[str]:
    """Cuts a sentence that is itself longer than the limit.

    Order of preference: semicolon, comma, space, then as it is.
    A crooked pause inside a sentence beats synthesis that fell over.
    """
    if len(sentence) <= limit:
        return [sentence]

    for separator in ("; ", ", "):
        if separator in sentence:
            pieces = sentence.split(separator)
            joined = [p + separator.strip() for p in pieces[:-1]] + [pieces[-1]]
            return _pack(joined, limit, glue=" ")

    if " " in sentence:
        return _pack(sentence.split(" "), limit, glue=" ")

    return [sentence[i : i + limit] for i in range(0, len(sentence), limit)]


def _pack(pieces: list[str], limit: int, glue: str) -> list[str]:
    """Packs the pieces into lines no longer than the limit."""
    out: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{glue}{piece}" if current else piece
        if current and len(candidate) > limit:
            out.append(current)
            current = piece
        else:
            current = candidate
    if current:
        out.append(current)
    return [part for chunk in out for part in split_long_sentence(chunk, limit)]


def _sentences(text: str, language: str) -> list[str]:
    segmenter = pysbd.Segmenter(language=language, clean=False)
    return [s.strip() for s in segmenter.segment(text) if s.strip()]


def _pack_paragraph(text: str, language: str, limit: int) -> list[str]:
    """Packs a paragraph's sentences into chunks without breaking a sentence."""
    parts: list[str] = []
    for sentence in _sentences(text, language):
        parts.extend(split_long_sentence(sentence, limit))
    return _pack(parts, limit, glue=" ")


def is_speakable(text: str) -> bool:
    """Whether the piece has anything to pronounce.

    "* * *" is a scene break: no letters or digits, and Silero fails on it with
    a bare ValueError. The pause between paragraphs marks the scene break anyway.
    """
    return any(c.isalnum() for c in text)


def chunk_document(doc: Document, language: str, limit: int = CHUNK_LIMIT) -> list[Chunk]:
    """Splits the document into chunks with pauses at paragraph and chapter borders."""
    chunks: list[Chunk] = []

    for chapter in doc.chapters:
        blocks = list(chapter.blocks)
        announced = blocks and blocks[0].kind == "heading" and blocks[0].text == chapter.title
        texts = [b.text for b in blocks]
        if not announced and chapter.title:
            texts.insert(0, chapter.title)

        texts = [t for t in texts if is_speakable(t)]

        for position, text in enumerate(texts):
            last_in_chapter = position == len(texts) - 1
            pieces = _pack_paragraph(text, language, limit)
            for index, piece in enumerate(pieces):
                if index < len(pieces) - 1:
                    pause = PAUSE_IN_PARAGRAPH
                elif last_in_chapter:
                    pause = PAUSE_BETWEEN_CHAPTERS
                else:
                    pause = PAUSE_BETWEEN_PARAGRAPHS
                if is_speakable(piece):
                    chunks.append(Chunk(text=piece, pause_after=pause))

    return chunks
