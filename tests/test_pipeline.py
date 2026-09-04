import wave
from pathlib import Path

import pytest

from book2audio.models import Selection
from book2audio.pipeline import Progress, convert
from book2audio.tts.fake import FakeEngine

FIXTURES = Path(__file__).parent / "fixtures"
TOC_PDF = FIXTURES / "toc_ru.pdf"
SCANNED_PDF = FIXTURES / "scanned_ru.pdf"


def test_convert_produces_a_playable_wav(tmp_path):
    out = convert(
        TOC_PDF,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path,
        selection=Selection(pages=(1, 2)),
        engine=FakeEngine(),
    )
    assert out.exists()
    with wave.open(str(out)) as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 24000
        assert w.getnframes() > 24000


def test_convert_names_the_file_after_the_book(tmp_path):
    out = convert(
        TOC_PDF,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path,
        selection=Selection(pages=(1, 2)),
        engine=FakeEngine(),
    )
    assert "инноваци" in out.stem.lower()
    assert out.suffix == ".wav"


def test_convert_reports_progress_for_every_stage(tmp_path):
    seen: list[Progress] = []
    convert(
        TOC_PDF,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path,
        selection=Selection(pages=(1, 2)),
        engine=FakeEngine(),
        on_progress=seen.append,
    )
    stages = [p.stage for p in seen]
    assert stages[0] == "extract"
    assert "chunk" in stages
    assert "synth" in stages
    assert stages[-1] == "assemble"


def test_synth_progress_counts_up_to_total(tmp_path):
    seen: list[Progress] = []
    convert(
        TOC_PDF,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path,
        selection=Selection(pages=(1, 2)),
        engine=FakeEngine(),
        on_progress=seen.append,
    )
    synth = [p for p in seen if p.stage == "synth"]
    assert synth[-1].done == synth[-1].total
    assert [p.done for p in synth] == list(range(1, len(synth) + 1))


def test_convert_reuses_the_cache_on_a_second_run(tmp_path):
    calls = 0

    class Counting(FakeEngine):
        def synth(self, text, voice, out_path):
            nonlocal calls
            calls += 1
            super().synth(text, voice, out_path)

    args = {
        "language": "ru",
        "voice": "fake_a",
        "out_dir": tmp_path,
        "selection": Selection(pages=(1, 2)),
        "engine": Counting(),
    }
    convert(TOC_PDF, **args)
    after_first = calls
    convert(TOC_PDF, **args)
    assert after_first > 0
    assert calls == after_first


def test_convert_refuses_a_scanned_pdf(tmp_path):
    from book2audio.extract.base import NoTextLayer

    with pytest.raises(NoTextLayer):
        convert(SCANNED_PDF, language="ru", voice="fake_a", out_dir=tmp_path, engine=FakeEngine())


def test_convert_rejects_a_voice_the_engine_does_not_have(tmp_path):
    with pytest.raises(ValueError, match="неизвестный голос"):
        convert(
            TOC_PDF,
            language="ru",
            voice="nope",
            out_dir=tmp_path,
            selection=Selection(pages=(1, 1)),
            engine=FakeEngine(),
        )


def test_convert_rejects_unknown_file_format(tmp_path):
    book = tmp_path / "book.txt"
    book.write_text("привет", encoding="utf-8")
    with pytest.raises(ValueError, match="неизвестный формат"):
        convert(book, language="ru", voice="fake_a", out_dir=tmp_path, engine=FakeEngine())
