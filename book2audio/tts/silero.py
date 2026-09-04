"""Русский синтез через Silero v5.

Модель v5_5_ru сама расставляет ударения и разбирает омографы,
поэтому стадия чистки этим не занимается.
"""

from pathlib import Path

import torch

from book2audio.audio import write_wav_mono16
from book2audio.net import ensure_ssl_certs
from book2audio.tts.base import Voice

# Порядок совпадает с model.speakers. Медленный тест это сторожит.
VOICES: dict[str, list[str]] = {
    "v5_5_ru": ["aidar", "baya", "kseniya", "eugene", "xenia"],
    "v5_ru": ["aidar", "baya", "kseniya", "eugene", "xenia"],
    # Дикторы стран СНГ, читающие по-русски. Часть из них с акцентом,
    # поэтому в сравнении голосов они идут после родных v5_5_ru.
    "v5_cis_base": [
        "ru_aigul",
        "ru_albina",
        "ru_alexandr",
        "ru_alfia",
        "ru_alfia2",
        "ru_bogdan",
        "ru_dmitriy",
        "ru_ekaterina",
        "ru_vika",
        "ru_gamat",
        "ru_igor",
        "ru_karina",
        "ru_kejilgan",
        "ru_kermen",
        "ru_marat",
        "ru_miyau",
        "ru_nurgul",
        "ru_oksana",
        "ru_onaoy",
        "ru_ramilia",
        "ru_roman",
        "ru_safarhuja",
        "ru_saida",
        "ru_sibday",
        "ru_zara",
        "ru_zhadyra",
        "ru_zhazira",
        "ru_zinaida",
        "ru_eduard",
    ],
}

# Пол родных голосов известен точно. У дикторов СНГ его не угадываем:
# в UI эта модель не идёт, она нужна только скрипту сравнения.
GENDER: dict[str, str] = {
    "aidar": "male",
    "baya": "female",
    "kseniya": "female",
    "eugene": "male",
    "xenia": "female",
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
        self.version = model_id
        self._model = None

    def voices(self) -> list[Voice]:
        return [Voice(id=v, gender=GENDER.get(v, "unknown")) for v in VOICES[self.model_id]]

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
        if voice not in VOICES[self.model_id]:
            raise ValueError(f"неизвестный голос: {voice}")
        if not text.strip():
            raise ValueError("пустой текст")
        audio = self._load().apply_tts(text=text, speaker=voice, sample_rate=self.sample_rate)
        write_wav_mono16(out_path, audio.numpy(), self.sample_rate)
