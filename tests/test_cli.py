from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from book2audio.cli import app, build_engine, parse_pages

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_pages_reads_a_range():
    assert parse_pages("10-20").pages == (10, 20)


def test_parse_pages_reads_a_single_page():
    assert parse_pages("7").pages == (7, 7)


def test_parse_pages_returns_none_for_whole_document():
    assert parse_pages(None) is None


def test_parse_pages_rejects_garbage():
    with pytest.raises(typer.BadParameter, match="диапазон страниц"):
        parse_pages("десять")


def test_build_engine_picks_silero_for_russian():
    engine = build_engine("ru")
    assert engine.name == "silero"


def test_build_engine_picks_kokoro_for_english():
    engine = build_engine("en")
    assert engine.name == "kokoro"


def test_voices_command_lists_voices_with_gender():
    result = runner.invoke(app, ["voices", "--lang", "ru"])
    assert result.exit_code == 0
    assert "xenia" in result.stdout
    assert "eugene" in result.stdout


def test_convert_command_runs_end_to_end_with_the_fake_engine(tmp_path):
    result = runner.invoke(
        app,
        [
            "convert",
            str(FIXTURES / "toc_ru.pdf"),
            "--lang",
            "ru",
            "--pages",
            "1-2",
            "--out",
            str(tmp_path),
            "--engine",
            "fake",
            "--voice",
            "fake_a",
            "--no-icloud",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert list(tmp_path.glob("*.m4b"))


def test_convert_command_explains_a_scanned_pdf(tmp_path):
    result = runner.invoke(
        app,
        [
            "convert",
            str(FIXTURES / "scanned_ru.pdf"),
            "--lang",
            "ru",
            "--out",
            str(tmp_path),
            "--engine",
            "fake",
            "--voice",
            "fake_a",
        ],
    )
    assert result.exit_code != 0
    assert "OCR" in result.stdout


def test_serve_command_exists_and_defaults_to_localhost():
    """Инструмент внутренний, авторизации нет: наружу светить нельзя."""
    import inspect

    from book2audio.cli import serve

    defaults = {name: param.default for name, param in inspect.signature(serve).parameters.items()}
    assert defaults["host"] == "127.0.0.1"
    assert defaults["port"] == 8000


def test_convert_stops_early_when_ffmpeg_is_missing(tmp_path, monkeypatch):
    """Полчаса синтеза, а потом «нет ffmpeg» — худший из возможных порядков."""
    monkeypatch.setattr("book2audio.preflight.shutil.which", lambda name: None)
    result = runner.invoke(
        app,
        ["convert", str(FIXTURES / "toc_ru.pdf"), "--lang", "ru", "--engine", "fake"],
    )
    assert result.exit_code == 1
    assert "brew install ffmpeg" in result.output


def test_convert_does_not_demand_espeak_for_russian(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "book2audio.preflight.shutil.which",
        lambda name: None if name == "espeak-ng" else "/opt/homebrew/bin/x",
    )
    result = runner.invoke(
        app,
        [
            "convert",
            str(FIXTURES / "toc_ru.pdf"),
            "--lang",
            "ru",
            "--engine",
            "fake",
            "--pages",
            "1-1",
            "--out",
            str(tmp_path),
            "--no-icloud",
        ],
    )
    assert result.exit_code == 0, result.output
