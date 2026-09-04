"""Кэш синтезированных чанков.

Прогон книги идёт десятки минут и будет падать. Без кэша каждое падение
стоит всего прогона заново.
"""

import hashlib
from pathlib import Path

from book2audio.audio import silence
from book2audio.tts.base import TTSEngine

# Сколько раз пробуем один чанк. Движок иногда срывается на нехватке памяти
# или на одном кривом символе, и повтор чаще всего проходит.
ATTEMPTS = 3

# Скорость прозы. По ней считается длина тишины вместо сорвавшегося чанка:
# книга не должна съезжать по таймингу из-за одной дыры.
CHARS_PER_SECOND = 15.0

# Сколько символов чанка попадает в отчёт. Достаточно, чтобы найти место
# в книге, и не настолько много, чтобы отчёт стал вторым текстом книги.
REPORT_CHARS = 200


class SynthCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0
        self.failures: list[str] = []

    def key(self, text: str, voice: str, engine: TTSEngine) -> str:
        """Версия движка входит в ключ: смена модели обязана инвалидировать кэш."""
        # Нулевой байт как разделитель: поля не могут склеиться неоднозначно.
        material = f"{text}\x00{voice}\x00{engine.name}\x00{engine.version}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def path(self, text: str, voice: str, engine: TTSEngine) -> Path:
        return self.root / f"{self.key(text, voice, engine)}.wav"

    def synth(self, engine: TTSEngine, text: str, voice: str) -> Path:
        """Отдаёт wav из кэша или синтезирует и кладёт туда."""
        target = self.path(text, voice, engine)
        if target.exists():
            self.hits += 1
            return target

        # Пишем во временный файл и переименовываем: оборванный wav в кэше
        # хуже отсутствующего, он молча попадёт в книгу.
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
        """Как synth, но сорвавшийся чанк не роняет книгу, а становится тишиной.

        Голос и пустоту проверяем сами, до движка: от них повтор не спасёт,
        а тихая подмена превратила бы в тишину всю книгу. Всё остальное, чем
        бы движок ни упал, считается сбоем этого куска. Silero, например,
        кидает голый ValueError на куске, который не смог разобрать.
        """
        if voice not in {v.id for v in engine.voices()}:
            raise ValueError(f"неизвестный голос: {voice}")
        if not text.strip():
            raise ValueError("пустой текст")

        for attempt in range(ATTEMPTS):
            try:
                return self.synth(engine, text, voice)
            except Exception:  # noqa: BLE001 — движок волен упасть чем угодно
                if attempt == ATTEMPTS - 1:
                    break

        self.failures.append(text)
        # Тишина лежит вне кэша чанков: иначе после починки движка книга
        # молча пересобралась бы с теми же дырами.
        gaps = self.root / "failed"
        gaps.mkdir(exist_ok=True)
        gap = gaps / f"{self.key(text, voice, engine)}.wav"
        silence(gap, len(text) / CHARS_PER_SECOND, engine.sample_rate)
        return gap

    def report(self) -> dict:
        """Что не синтезировалось. Пишется рядом с отчётом о чистке."""
        return {
            "failed": len(self.failures),
            "chunks": [text[:REPORT_CHARS] for text in self.failures],
        }
