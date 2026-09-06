"""Voice gender. The UI offers a language and a gender, and the engine has to know it."""

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
    with pytest.raises(ValueError, match="unknown gender"):
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
    """The CIS narrators never reach the UI, and we do not guess gender from a name."""
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
        ("ru", "female"): "kseniya",
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


def test_every_engine_reports_a_version_for_the_cache_key():
    assert FakeEngine().version
    assert SileroEngine(model_id="v5_5_ru").version == "v5_5_ru"
    assert KokoroEngine().version == "mlx-community/Kokoro-82M-bf16"


# --- the piece length limit ---


def test_engines_declare_a_chunk_limit():
    """Measured 2026-09-05: v5_5_ru takes ~1097 characters, v5_cis_base ~795.

    Общая константа в 800 символов ломала бы модель СНГ, поэтому предел
    объявляет сам движок.
    """
    from book2audio.tts.kokoro import KokoroEngine
    from book2audio.tts.silero import SileroEngine

    assert (
        SileroEngine(model_id="v5_5_ru").max_chars > SileroEngine(model_id="v5_cis_base").max_chars
    )
    assert SileroEngine(model_id="v5_cis_base").max_chars < 795
    assert SileroEngine(model_id="v5_5_ru").max_chars < 1097
    assert KokoroEngine().max_chars > 0


def test_fake_engine_has_a_limit_too():
    from book2audio.tts.fake import FakeEngine

    assert FakeEngine().max_chars > 0
