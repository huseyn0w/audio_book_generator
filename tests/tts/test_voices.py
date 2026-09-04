"""Пол голоса. UI даёт выбрать язык и пол, движок обязан это знать."""

import pytest

from book2audio.tts.base import DEFAULTS, Voice, pick_default
from book2audio.tts.fake import FakeEngine
from book2audio.tts.kokoro import KokoroEngine
from book2audio.tts.silero import SileroEngine


def test_voice_is_hashable_and_carries_gender():
    v = Voice(id="xenia", gender="female")
    assert v.gender == "female"
    assert {v}


def test_voice_rejects_unknown_gender():
    with pytest.raises(ValueError, match="неизвестный пол"):
        Voice(id="x", gender="robot")


def test_silero_reports_gender_for_native_voices():
    by_id = {v.id: v.gender for v in SileroEngine().voices()}
    assert by_id == {
        "aidar": "male",
        "baya": "female",
        "kseniya": "female",
        "eugene": "male",
        "xenia": "female",
    }


def test_silero_marks_cis_voices_unknown():
    """Дикторы СНГ в UI не идут, пол по имени не угадываем."""
    genders = {v.gender for v in SileroEngine(model_id="v5_cis_base").voices()}
    assert genders == {"unknown"}


def test_kokoro_derives_gender_from_voice_id():
    by_id = {v.id: v.gender for v in KokoroEngine().voices()}
    assert by_id["af_nova"] == "female"
    assert by_id["am_michael"] == "male"
    assert by_id["bf_emma"] == "female"
    assert by_id["bm_george"] == "male"
    assert "unknown" not in by_id.values()


def test_fake_engine_reports_voices_too():
    assert [v.id for v in FakeEngine().voices()] == ["fake_a", "fake_b"]


def test_defaults_match_the_phase_zero_choice():
    assert DEFAULTS == {
        ("ru", "female"): "xenia",
        ("ru", "male"): "eugene",
        ("en", "female"): "af_nova",
        ("en", "male"): "am_michael",
    }


def test_pick_default_returns_voice_id():
    assert pick_default("ru", "male") == "eugene"
    assert pick_default("en", "female") == "af_nova"


def test_pick_default_rejects_unsupported_combination():
    with pytest.raises(KeyError):
        pick_default("de", "female")
