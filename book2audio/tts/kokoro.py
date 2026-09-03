"""Английский синтез через Kokoro-82M на MLX.

Работает на Apple GPU. Языковой код берётся из префикса голоса:
a это американский английский, b это британский.
"""

from pathlib import Path

import numpy as np

from book2audio.audio import write_wav_mono16
from book2audio.net import ensure_ssl_certs

VOICES: list[str] = [
    "af_heart",
    "af_bella",
    "af_nova",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_michael",
    "bf_alice",
    "bf_emma",
    "bm_daniel",
    "bm_george",
]

LANG_BY_PREFIX = {"a": "a", "b": "b"}


class KokoroEngine:
    name = "kokoro"
    sample_rate = 24000

    def __init__(self, model_repo: str = "mlx-community/Kokoro-82M-bf16") -> None:
        self.model_repo = model_repo
        self._model = None

    def voices(self) -> list[str]:
        return list(VOICES)

    def _lang_code(self, voice: str) -> str:
        prefix = voice[0]
        if prefix not in LANG_BY_PREFIX:
            raise ValueError(f"не понял язык голоса: {voice}")
        return LANG_BY_PREFIX[prefix]

    def _load(self):
        if self._model is None:
            ensure_ssl_certs()
            from mlx_audio.tts.utils import load_model

            self._model = load_model(self.model_repo)
        return self._model

    def synth(self, text: str, voice: str, out_path: Path) -> None:
        if voice not in VOICES:
            raise ValueError(f"неизвестный голос: {voice}")
        if not text.strip():
            raise ValueError("пустой текст")
        chunks = [
            np.asarray(result.audio, dtype=np.float32)
            for result in self._load().generate(
                text=text, voice=voice, speed=1.0, lang_code=self._lang_code(voice)
            )
        ]
        if not chunks:
            raise RuntimeError(f"Kokoro ничего не выдал на текст: {text[:60]!r}")
        write_wav_mono16(out_path, np.concatenate(chunks), self.sample_rate)
