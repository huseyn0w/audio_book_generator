import json

import pytest

from book2audio.tts.fake import FakeEngine
from scripts.voice_bakeoff import EN_TEXT, ENGINE_SETS, RU_TEXT, build_engines, run_bakeoff


def test_bakeoff_writes_x1_and_x2_for_each_voice(tmp_path):
    run_bakeoff([(FakeEngine(), "ru")], tmp_path)
    names = sorted(p.name for p in tmp_path.glob("*.wav"))
    assert names == ["ru_01.wav", "ru_01_x2.wav", "ru_02.wav", "ru_02_x2.wav"]


def test_bakeoff_hides_voice_names_from_filenames(tmp_path):
    run_bakeoff([(FakeEngine(), "ru")], tmp_path)
    for path in tmp_path.glob("*.wav"):
        assert "fake" not in path.name


def test_bakeoff_writes_key_mapping(tmp_path):
    mapping = run_bakeoff([(FakeEngine(), "ru")], tmp_path)
    saved = json.loads((tmp_path / "key" / "mapping.json").read_text(encoding="utf-8"))
    assert saved == mapping
    assert saved["ru_01"] == "fake/fake_a"
    assert saved["ru_02"] == "fake/fake_b"


def test_bakeoff_numbers_languages_independently(tmp_path):
    mapping = run_bakeoff([(FakeEngine(), "ru"), (FakeEngine(), "en")], tmp_path)
    assert set(mapping) == {"ru_01", "ru_02", "en_01", "en_02"}


def test_bakeoff_keeps_numbering_across_engines_of_same_language(tmp_path):
    mapping = run_bakeoff([(FakeEngine(), "ru"), (FakeEngine(), "ru")], tmp_path)
    assert sorted(mapping) == ["ru_01", "ru_02", "ru_03", "ru_04"]


def test_test_texts_contain_homographs_and_direct_speech():
    assert "замок" in RU_TEXT.lower()
    assert "?" in RU_TEXT
    assert "?" in EN_TEXT


def test_engine_sets_put_native_russian_first():
    assert ENGINE_SETS["all"][0] == "silero:v5_5_ru"
    assert "silero:v5_cis_base" not in ENGINE_SETS["native"]


def test_build_engines_maps_names_to_languages():
    built = build_engines(ENGINE_SETS["native"])
    assert [lang for _, lang in built] == ["ru", "en"]
    assert built[0][0].model_id == "v5_5_ru"
    assert built[1][0].name == "kokoro"


def test_build_engines_rejects_unknown_name():
    with pytest.raises(ValueError, match="неизвестный движок"):
        build_engines(["whisper"])


def test_bakeoff_writes_player_page(tmp_path):
    run_bakeoff([(FakeEngine(), "ru")], tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "ru_01.wav" in html
    assert "ru_01_x2.wav" in html


def test_player_page_hides_voice_names_from_visible_text(tmp_path):
    """Сравнение слепое: имя голоса живёт в data-атрибуте, а не в тексте страницы."""
    run_bakeoff([(FakeEngine(), "ru")], tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'data-voice="fake/fake_a"' in html
    assert ">fake/fake_a<" not in html
