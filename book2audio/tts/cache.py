"""Кэш синтезированных чанков.

Прогон книги идёт десятки минут и будет падать. Без кэша каждое падение
стоит всего прогона заново.
"""

import hashlib
from pathlib import Path

from book2audio.tts.base import TTSEngine


class SynthCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

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
