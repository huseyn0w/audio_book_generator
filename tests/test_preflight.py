"""Checks before the run: a missing ffmpeg has to surface at once."""

import shutil

import pytest

from book2audio.preflight import (
    MissingTool,
    NotEnoughSpace,
    check_space,
    check_tools,
    estimate_bytes,
    missing_tools,
)


@pytest.fixture
def no_tools(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)


@pytest.fixture
def all_tools(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/opt/homebrew/bin/{name}")


def test_russian_does_not_need_espeak(monkeypatch):
    """Silero phonemizes on its own. Demanding espeak for a Russian book is wrong."""
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "espeak-ng" else "/bin/x")
    assert missing_tools("ru") == []
    assert missing_tools("en") == ["espeak-ng"]


def test_ffmpeg_is_required_for_every_language(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "ffmpeg" else "/bin/x")
    assert missing_tools("ru") == ["ffmpeg"]
    assert missing_tools("en") == ["ffmpeg"]


def test_missing_tools_without_language_checks_everything(no_tools):
    assert missing_tools() == ["ffmpeg", "espeak-ng"]


def test_check_tools_names_the_brew_command(no_tools):
    with pytest.raises(MissingTool, match="brew install ffmpeg"):
        check_tools("ru")


def test_check_tools_passes_when_everything_is_installed(all_tools):
    check_tools("en")


def test_estimate_grows_with_text():
    hour_of_speech = int(15.0 * 3600)
    assert estimate_bytes(hour_of_speech) > 400_000_000
    assert estimate_bytes(hour_of_speech * 2) == 2 * estimate_bytes(hour_of_speech)


def test_check_space_passes_with_room(tmp_path):
    check_space(tmp_path, chars=1000)


def test_check_space_reports_both_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr("book2audio.preflight.free_bytes", lambda path: 1_000_000)
    with pytest.raises(NotEnoughSpace, match=r"needed.*free"):
        check_space(tmp_path, chars=10_000_000)


def test_check_space_looks_at_the_nearest_existing_parent(tmp_path):
    """The work folder does not exist yet: measure space on what does."""
    check_space(tmp_path / "work" / "job" / "cache", chars=1000)
