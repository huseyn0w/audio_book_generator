"""Русский синтез через Silero v5.

Модель v5_5_ru сама расставляет ударения и разбирает омографы,
поэтому стадия чистки этим не занимается.
"""

from pathlib import Path

import torch

from book2audio.audio import write_wav_mono16
from book2audio.net import ensure_ssl_certs

VOICES: dict[str, list[str]] = {
    "v5_5_ru": ["aidar", "baya", "kseniya", "xenia", "eugene"],
    "v5_ru": ["aidar", "baya", "kseniya", "xenia", "eugene"],
    "v5_cis_base": ["ru_aidar", "ru_baya", "ru_kseniya", "ru_xenia", "ru_eugene"],
}

ALLOWED_SAMPLE_RATES = (8000, 24000, 48000)


class SileroEngine:
    name = "silero"

    def __init__(self, sample_rate: int = 24000, model_id: str = "v5_5_ru") -> None:
        if model_id not in VOICES:
            raise ValueError(f"неизвестная модель: {model_id}")
        if sample_rate not in ALLOWED_SAMPLE_RATES:
            raise ValueError(f"Silero не умеет частоту {sample_rate}")
        self.sample_rate = sample_rate
        self.model_id = model_id
        self._model = None

    def voices(self) -> list[str]:
        return list(VOICES[self.model_id])

    def _load(self):
        if self._model is None:
            ensure_ssl_certs()
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-models",
                model="silero_tts",
                language="ru",
                speaker=self.model_id,
                trust_repo=True,
            )
            model.to(torch.device("cpu"))
            self._model = model
        return self._model

    def synth(self, text: str, voice: str, out_path: Path) -> None:
        if voice not in self.voices():
            raise ValueError(f"неизвестный голос: {voice}")
        if not text.strip():
            raise ValueError("пустой текст")
        audio = self._load().apply_tts(text=text, speaker=voice, sample_rate=self.sample_rate)
        write_wav_mono16(out_path, audio.numpy(), self.sample_rate)
