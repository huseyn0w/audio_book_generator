import json
from pathlib import Path

import pytest

from book2audio.models import Selection
from book2audio.pipeline import Progress, convert
from book2audio.tts.fake import FakeEngine

FIXTURES = Path(__file__).parent / "fixtures"
TOC_PDF = FIXTURES / "toc_ru.pdf"
SCANNED_PDF = FIXTURES / "scanned_ru.pdf"


def _fb2(title: str, paragraph: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>Книга</book-title>"
        "<lang>ru</lang></title-info></description>"
        f"<body><section><title><p>{title}</p></title>"
        f"<p>{paragraph}</p></section></body></FictionBook>"
    )


def test_convert_produces_an_m4b_with_chapters(tmp_path):
    import subprocess

    out = convert(
        TOC_PDF,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path,
        selection=Selection(pages=(1, 2)),
        engine=FakeEngine(),
    )
    assert out.exists()
    assert out.suffix == ".m4b"
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_chapters", "-of", "default=nw=1", str(out)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.count("TAG:title=") >= 1


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
    assert out.suffix == ".m4b"


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


def test_convert_writes_a_clean_report(tmp_path):
    import json

    convert(
        TOC_PDF,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path,
        selection=Selection(pages=(1, 2)),
        engine=FakeEngine(),
    )
    report = json.loads((tmp_path / ".work" / "clean_report.json").read_text(encoding="utf-8"))
    assert report["kept"] > 0
    assert report["chars_after"] <= report["chars_before"]


def test_convert_can_skip_cleaning(tmp_path):
    """--no-clean нужен, чтобы понять, эвристика испортила текст или он таким и был."""
    out = convert(
        TOC_PDF,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path,
        selection=Selection(pages=(1, 2)),
        engine=FakeEngine(),
        clean=False,
    )
    assert out.exists()
    assert not (tmp_path / ".work" / "clean_report.json").exists()


class OneBadChunkEngine(FakeEngine):
    """Срывается на чанке с заданной подстрокой, остальное синтезирует."""

    def __init__(self, poison: str) -> None:
        self.poison = poison

    def synth(self, text: str, voice: str, out_path) -> None:
        if self.poison in text:
            raise RuntimeError("движок сорвался")
        super().synth(text, voice, out_path)


def test_convert_survives_one_failed_chunk(tmp_path):
    book = tmp_path / "book.fb2"
    book.write_text(_fb2("Первая глава", "Обычный абзац."), encoding="utf-8")
    work = tmp_path / "work"
    out = convert(
        book,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path / "out",
        engine=OneBadChunkEngine("Обычный"),
        work_dir=work,
    )
    assert out.exists()
    report = json.loads((work / "synth_report.json").read_text(encoding="utf-8"))
    assert report["failed"] == 1
    assert "Обычный" in report["chunks"][0]


def test_convert_writes_no_synth_report_when_nothing_failed(tmp_path):
    book = tmp_path / "book.fb2"
    book.write_text(_fb2("Первая глава", "Обычный абзац."), encoding="utf-8")
    work = tmp_path / "work"
    convert(
        book,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path / "out",
        engine=FakeEngine(),
        work_dir=work,
    )
    assert not (work / "synth_report.json").exists()


class ShortLimitEngine(FakeEngine):
    """Движок с коротким пределом, как модель голосов СНГ."""

    max_chars = 120

    def synth(self, text: str, voice: str, out_path) -> None:
        if len(text) > self.max_chars:
            raise RuntimeError(f"кусок длиннее предела: {len(text)}")
        super().synth(text, voice, out_path)


def test_convert_respects_the_engine_chunk_limit(tmp_path):
    """Общий лимит в 800 символов ломает движок, который держит меньше."""
    book = tmp_path / "book.fb2"
    long_text = "Довольно длинное предложение про инновации и рынки. " * 20
    book.write_text(_fb2("Глава", long_text), encoding="utf-8")
    work = tmp_path / "work"
    convert(
        book,
        language="ru",
        voice="fake_a",
        out_dir=tmp_path / "out",
        engine=ShortLimitEngine(),
        work_dir=work,
    )
    assert not (work / "synth_report.json").exists()
