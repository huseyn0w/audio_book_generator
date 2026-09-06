"""Russian synthesis through Silero v5.

The v5_5_ru model places stress marks and resolves homographs on its own,
so the cleaning stage does not deal with that.
"""

from pathlib import Path

import torch

from book2audio.audio import write_wav_mono16
from book2audio.net import ensure_ssl_certs
from book2audio.tts.base import Voice
from book2audio.tts.translit import latin_to_cyrillic

# The order matches model.speakers. A slow test guards that.
VOICES: dict[str, list[str]] = {
    "v5_5_ru": ["aidar", "baya", "kseniya", "eugene", "xenia"],
    "v5_ru": ["aidar", "baya", "kseniya", "eugene", "xenia"],
    # CIS narrators reading in Russian. Some of them have an accent, so in the
    # voice comparison they come after the native v5_5_ru ones.
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

# The gender of the native voices is known exactly. We do not guess it for the
# CIS narrators: that model never reaches the UI, only the comparison script.
GENDER: dict[str, str] = {
    "aidar": "male",
    "baya": "female",
    "kseniya": "female",
    "eugene": "male",
    "xenia": "female",
}

ALLOWED_SAMPLE_RATES = (8000, 24000, 48000)

# The piece length limit. Measured by bisection on 2026-09-05 on a real
# paragraph: v5_5_ru took 1097 characters, v5_cis_base 795. We leave room:
# the limit depends on the text, not on the character count alone.
MAX_CHARS = {"v5_5_ru": 900, "v5_ru": 900, "v5_cis_base": 700}


class SileroEngine:
    name = "silero"
    # How many times faster than real time synthesis runs. The M series measured
    # x32-x46, and we take the lower bound: promising less beats promising more.
    realtime = 32.0

    def __init__(self, sample_rate: int = 24000, model_id: str = "v5_5_ru") -> None:
        if model_id not in VOICES:
            raise ValueError(f"unknown model: {model_id}")
        if sample_rate not in ALLOWED_SAMPLE_RATES:
            raise ValueError(f"Silero does not do the {sample_rate} sample rate")
        self.sample_rate = sample_rate
        self.model_id = model_id
        self.max_chars = MAX_CHARS[model_id]
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

    def prepare(self, text: str) -> str:
        """Prepares the text for the model's character table.

        It holds no Latin letters: one letter out of "E*Trade Bank" makes
        apply_tts fail with KeyError, and on the lenient path the engine just
        drops the word, so the company name disappears from the sentence.
        """
        return latin_to_cyrillic(text)

    def synth(self, text: str, voice: str, out_path: Path) -> None:
        if voice not in VOICES[self.model_id]:
            raise ValueError(f"unknown voice: {voice}")
        if not text.strip():
            raise ValueError("empty text")
        audio = self._load().apply_tts(
            text=self.prepare(text), speaker=voice, sample_rate=self.sample_rate
        )
        write_wav_mono16(out_path, audio.numpy(), self.sample_rate)
