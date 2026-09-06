"""Static file checks. A regression in the markup breaks the interface quietly."""

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).parent.parent.parent / "book2audio" / "web" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")


def test_page_declares_english_by_default():
    """The interface starts in English, and the switch changes lang on the fly."""
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
    """The tool is local: it needs no CDN and could not reach one offline.

    Only tags that fetch something count. An anchor the reader clicks loads
    nothing by itself, so the credit link in the footer is allowed.
    """
    loading = re.finditer(r"<(?:script|link|img|iframe|source|video|audio)\b[^>]*>", HTML)
    external = [
        tag.group(0) for tag in loading if "http://" in tag.group(0) or "https://" in tag.group(0)
    ]
    assert not external, external


# --- styles ---

# The zinc of the design system is deliberately a little cold: #71717a has a channel
# spread of 9. Anything above that is already a foreign hue.
ZINC_TOLERANCE = 12


def test_palette_is_monochrome():
    """Color marks state only, never decoration."""
    colors = set(re.findall(r"#[0-9a-fA-F]{6}", CSS))
    allowed_state = {"#15803d", "#22c55e", "#dc2626", "#ef4444", "#fee2e2", "#2a1213"}
    for color in colors - allowed_state:
        red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
        spread = max(red, green, blue) - min(red, green, blue)
        assert spread <= ZINC_TOLERANCE, f"foreign hue {color}, spread {spread}"


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


# --- the script ---


def test_script_uses_the_documented_api():
    for route in ("/api/jobs", "/api/voices", "/synthesize", "/cancel", "/events", "/download"):
        assert route in JS


def test_script_reconnects_the_event_stream():
    """The SSE connection is time limited, so the browser has to reconnect."""
    assert "EventSource" in JS
    assert "onerror" in JS
    assert "setTimeout(watch" in JS


def test_script_sends_edited_text_before_starting():
    assert JS.index("collectReview") < JS.index("/synthesize")


@pytest.mark.parametrize("stage", ["extract", "synth", "assemble"])
def test_every_pipeline_stage_has_a_label(stage):
    assert stage in JS


def test_progress_heading_does_not_duplicate_the_stage_line():
    """A "Reading" heading above a "reading" line is noise.

    The text now lives in the dictionaries, so we compare keys, not labels.
    """
    stage_keys = {"progress.extract", "progress.synth", "progress.assemble"}
    heading = re.search(r'<h2 id="h-progress" data-i18n="([^"]+)"', HTML).group(1)
    assert heading not in stage_keys


def test_progress_screen_shows_the_book_title():
    assert 'id="progress-title"' in HTML
    assert "progress-title" in JS
