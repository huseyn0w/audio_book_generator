"""Движок-пустышка. Пишет тишину длиной пропорционально тексту.

Нужен, чтобы тесты конвейера гонялись за секунды и не тянули веса моделей.
"""

from pathlib import Path

import numpy as np

from book2audio.audio import write_wav_mono16
from book2audio.tts.base import Voice


class FakeEngine:
    name = "fake"
    realtime = 60.0
    version = "1"
    sample_rate = 24000
    CHARS_PER_SECOND = 15.0

    VOICE_IDS = ("fake_a", "fake_b")

    def voices(self) -> list[Voice]:
        return [Voice(id="fake_a", gender="female"), Voice(id="fake_b", gender="male")]

    def synth(self, text: str, voice: str, out_path: Path) -> None:
        if voice not in self.VOICE_IDS:
            raise ValueError(f"неизвестный голос: {voice}")
        if not text.strip():
            raise ValueError("пустой текст")
        frames = int(self.sample_rate * len(text) / self.CHARS_PER_SECOND)
        write_wav_mono16(out_path, np.zeros(frames, dtype=np.float32), self.sample_rate)
