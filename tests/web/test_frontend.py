"""Проверки статики. Регрессии в разметке ломают интерфейс молча."""

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).parent.parent.parent / "book2audio" / "web" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")


def test_page_declares_english_by_default():
    """Интерфейс по умолчанию английский, переключатель меняет lang на лету."""
    assert '<html lang="en">' in HTML


def test_page_has_exactly_one_h1():
    assert HTML.count("<h1") == 1


def test_all_four_screens_exist():
    for name in ("upload", "review", "progress", "done"):
        assert f'id="screen-{name}"' in HTML


def test_every_screen_has_a_heading_and_label():
    for name in ("upload", "review", "progress", "done", "failed"):
        assert f'aria-labelledby="h-{name}"' in HTML
        assert f'id="h-{name}"' in HTML


def test_dropzone_is_keyboard_reachable():
    assert 'id="dropzone"' in HTML
    assert 'tabindex="0"' in HTML
    assert "aria-label" in HTML


def test_progress_is_announced_to_screen_readers():
    assert 'role="status"' in HTML
    assert 'aria-live="polite"' in HTML


def test_errors_are_announced():
    assert HTML.count('role="alert"') >= 2


def test_only_supported_formats_are_offered():
    assert 'accept=".pdf,.epub,.fb2"' in HTML


def test_no_external_resources_are_loaded():
    """Инструмент локальный, внешние CDN ему не нужны и недоступны офлайн."""
    assert "http://" not in HTML
    assert "https://" not in HTML


# --- стили ---

# Zinc из дизайн-системы намеренно чуть холодный: у #71717a разброс каналов 9.
# Всё, что выше, это уже посторонний оттенок.
ZINC_TOLERANCE = 12


def test_palette_is_monochrome():
    """Цветом обозначается только состояние, а не оформление."""
    colors = set(re.findall(r"#[0-9a-fA-F]{6}", CSS))
    allowed_state = {"#15803d", "#22c55e", "#dc2626", "#ef4444", "#fee2e2", "#2a1213"}
    for color in colors - allowed_state:
        red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
        spread = max(red, green, blue) - min(red, green, blue)
        assert spread <= ZINC_TOLERANCE, f"посторонний оттенок {color}, разброс {spread}"


def test_no_gradients_or_glows():
    assert "gradient" not in CSS
    assert "box-shadow: 0 0" not in CSS


def test_focus_ring_is_defined_for_interactive_elements():
    assert CSS.count("focus-visible") >= 4
    assert "outline: 2px solid var(--ring)" in CSS


def test_reduced_motion_is_respected():
    assert "prefers-reduced-motion: reduce" in CSS
    assert "0.01ms" in CSS


def test_dark_scheme_is_defined():
    assert "prefers-color-scheme: dark" in CSS


def test_geist_is_the_font_with_a_system_fallback():
    assert "Geist" in CSS
    assert "system-ui" in CSS


# --- скрипт ---


def test_script_uses_the_documented_api():
    for route in ("/api/jobs", "/api/voices", "/synthesize", "/cancel", "/events", "/download"):
        assert route in JS


def test_script_reconnects_the_event_stream():
    """Соединение SSE ограничено по времени, браузер обязан переподключиться."""
    assert "EventSource" in JS
    assert "onerror" in JS
    assert "setTimeout(watch" in JS


def test_script_sends_edited_text_before_starting():
    assert JS.index("collectReview") < JS.index("/synthesize")


@pytest.mark.parametrize("stage", ["extract", "synth", "assemble"])
def test_every_pipeline_stage_has_a_russian_label(stage):
    assert stage in JS


def test_progress_heading_does_not_duplicate_the_stage_line():
    """Заголовок «Озвучиваю» над строкой «озвучиваю» это шум.

    Текст теперь в словарях, поэтому сверяем ключи, а не подписи.
    """
    stage_keys = {"progress.extract", "progress.synth", "progress.assemble"}
    heading = re.search(r'<h2 id="h-progress" data-i18n="([^"]+)"', HTML).group(1)
    assert heading not in stage_keys


def test_progress_screen_shows_the_book_title():
    assert 'id="progress-title"' in HTML
    assert "progress-title" in JS
