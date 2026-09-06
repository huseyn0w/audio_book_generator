"""A blind comparison of voices.

Runs the same paragraph through every voice and writes an x1 and an x2 version
under anonymous names. The key lives in key/mapping.json.

Usage:
    uv run python scripts/voice_bakeoff.py --out ./bakeoff
"""

import argparse
import json
from pathlib import Path

from book2audio.audio import change_speed
from book2audio.tts.base import TTSEngine
from book2audio.tts.kokoro import KokoroEngine
from book2audio.tts.silero import SileroEngine

RU_TEXT = (
    "Замок на двери был старше самого дома, и открыть его удавалось не с первого раза. "
    "Она стояла на пороге, перебирая связку ключей, и думала о том, что за двадцать лет "
    "здесь не поменялось ровным счётом ничего. «А ты изменился?» — спросила она вслух, "
    "хотя в комнате никого не было. Ответа, разумеется, не последовало."
)

EN_TEXT = (
    "The lock on the door was older than the house itself, and it never opened on the "
    "first try. She stood on the threshold, turning the keyring over in her hands, "
    'thinking that in twenty years nothing here had changed at all. "And have you?" '
    "she asked aloud, though the room was empty. No answer came, of course."
)

TEXT_BY_LANG = {"ru": RU_TEXT, "en": EN_TEXT}

# The native Russian voices come first, the CIS narrators read with an accent.
ENGINE_SETS: dict[str, list[str]] = {
    "native": ["silero:v5_5_ru", "kokoro"],
    "all": ["silero:v5_5_ru", "silero:v5_cis_base", "kokoro"],
    # Russian only: you usually revisit the choice for one language, and there is
    # no reason to run 11 English voices while doing it.
    "ru-native": ["silero:v5_5_ru"],
    "ru-all": ["silero:v5_5_ru", "silero:v5_cis_base"],
}

# Below this a paragraph is too short to judge a voice on.
MIN_SAMPLE_CHARS = 200

# The sample limit. Measured: v5_5_ru takes ~1097 characters, v5_cis_base ~795.
# We stay below the smaller one so the comparison runs on every voice.
SAMPLE_LIMIT = 600


def build_engines(names: list[str]) -> list[tuple[TTSEngine, str]]:
    """Builds the engines by name. It loads no weights, the constructors are lazy."""
    built: list[tuple[TTSEngine, str]] = []
    for name in names:
        if name.startswith("silero:"):
            built.append((SileroEngine(model_id=name.split(":", 1)[1]), "ru"))
        elif name == "kokoro":
            built.append((KokoroEngine(), "en"))
        else:
            raise ValueError(f"unknown engine: {name}")
    return built


PAGE_STYLE = """
  :root { color-scheme: light dark; }
  body { font: 15px/1.5 -apple-system, system-ui, sans-serif; max-width: 760px;
         margin: 0 auto; padding: 32px 20px 80px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  p.hint { color: #71717a; margin: 0 0 24px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .08em;
       color: #71717a; margin: 32px 0 8px; }
  .row { display: grid; grid-template-columns: 62px 1fr 1fr 92px; gap: 10px;
         align-items: center; padding: 7px 0; border-bottom: 1px solid #e4e4e7; }
  .label { font-variant-numeric: tabular-nums; font-weight: 600; }
  .speed { font-size: 11px; color: #a1a1aa; }
  audio { width: 100%; height: 34px; }
  button { font: inherit; font-size: 12px; padding: 4px 8px; cursor: pointer;
           border: 1px solid #d4d4d8; border-radius: 6px; background: transparent; }
  .voice { font-family: ui-monospace, monospace; font-size: 12px; }
  @media (prefers-color-scheme: dark) { .row { border-bottom-color: #27272a; } }
"""

PAGE_SCRIPT = """
  function reveal(el) { el.textContent = el.dataset.voice; el.onclick = null; }
  document.getElementById('all').onclick = () => {
    document.querySelectorAll('button[data-voice]').forEach(reveal);
  };
  document.querySelectorAll('button[data-voice]').forEach(b => {
    b.onclick = () => reveal(b);
  });
  document.addEventListener('play', e => {
    document.querySelectorAll('audio').forEach(a => { if (a !== e.target) a.pause(); });
  }, true);
"""


GENDER_MARK = {"female": "\u2640", "male": "\u2642", "unknown": "\u00b7"}


def write_player_page(mapping: dict[str, str], genders: dict[str, str], out_dir: Path) -> None:
    """A local page for listening. The voice name stays hidden until you click."""
    rows: list[str] = []
    last_lang = None
    for label, voice in mapping.items():
        lang = label.split("_")[0]
        if lang != last_lang:
            rows.append(f"<h2>{'Russian' if lang == 'ru' else 'English'}</h2>")
            last_lang = lang
        mark = GENDER_MARK[genders.get(label, "unknown")]
        rows.append(
            f'<div class="row"><span class="label">{label} {mark}</span>'
            f'<span><span class="speed">x1</span>'
            f'<audio controls preload="none" src="{label}.wav"></audio></span>'
            f'<span><span class="speed">x2</span>'
            f'<audio controls preload="none" src="{label}_x2.wav"></audio></span>'
            f'<button class="voice" data-voice="{voice}">show</button></div>'
        )
    html = (
        "<!doctype html><meta charset=utf-8><title>Voice comparison</title>"
        f"<style>{PAGE_STYLE}</style>"
        "<h1>A blind comparison of voices</h1>"
        "<p class=hint>Listen and mark the ones you like. The button reveals the voice "
        "name. The native Russian voices come first, then the CIS narrators with an "
        "accent.</p>"
        '<p><button id="all">show every name</button></p>'
        + "".join(rows)
        + f"<script>{PAGE_SCRIPT}</script>"
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def sample_text(path: Path, language: str) -> str:
    """The first paragraph of the book that is long enough.

    A voice is judged on your own material: somebody else's paragraph may land
    well, while on your book the same narrator grates after ten minutes.
    """
    from book2audio.chunker import chunk_document
    from book2audio.models import Chapter, Document
    from book2audio.pipeline import pick_extractor

    document = pick_extractor(path, clean=True, language=language).extract(path)
    for chapter in document.chapters:
        for block in chapter.blocks:
            if len(block.text) < MIN_SAMPLE_CHARS:
                continue
            # Silero will not take a whole paragraph: the model has a length limit.
            # We cut with the same chunker as in production and take the first piece.
            one = Document("sample", None, language, [Chapter("", [block])])
            chunks = chunk_document(one, language, limit=SAMPLE_LIMIT)
            if chunks:
                return chunks[0].text
    raise ValueError(f"no paragraph long enough for a sample in {path.name}")


def run_bakeoff(
    engines: list[tuple[TTSEngine, str]], out_dir: Path, text: str | None = None
) -> dict[str, str]:
    """Synthesizes the paragraph in every voice. Returns the name key."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "key").mkdir(exist_ok=True)

    mapping: dict[str, str] = {}
    genders: dict[str, str] = {}
    counters: dict[str, int] = {}

    for engine, lang in engines:
        for voice in engine.voices():
            counters[lang] = counters.get(lang, 0) + 1
            label = f"{lang}_{counters[lang]:02d}"
            x1 = out_dir / f"{label}.wav"
            engine.synth(text or TEXT_BY_LANG[lang], voice.id, x1)
            change_speed(x1, out_dir / f"{label}_x2.wav", 2.0)
            mapping[label] = f"{engine.name}/{voice.id}"
            genders[label] = voice.gender
            print(f"{label}  done")

    (out_dir / "key" / "mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_player_page(mapping, genders, out_dir)
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="A blind comparison of voices")
    parser.add_argument("--out", type=Path, default=Path("./bakeoff"))
    parser.add_argument(
        "--set",
        dest="engine_set",
        choices=sorted(ENGINE_SETS),
        default="all",
        help=(
            "native is the 5 native Russian plus 11 English, all adds 29 CIS voices, "
            "ru-native and ru-all are the same without the English ones"
        ),
    )
    parser.add_argument(
        "--text-from",
        type=Path,
        default=None,
        help="The book to take the comparison paragraph from. Defaults to the built-in text",
    )
    parser.add_argument("--lang", default="ru", help="The language of the book in --text-from")
    args = parser.parse_args()

    text = sample_text(args.text_from, args.lang) if args.text_from else None
    if text:
        print(f"paragraph from the book, {len(text)} characters:\n{text[:200]}...\n")

    mapping = run_bakeoff(build_engines(ENGINE_SETS[args.engine_set]), args.out, text)
    print(f"\n{len(mapping)} voices in {args.out}")
    print(f"Открой {args.out / 'index.html'} в браузере и слушай.")
    print("Расшифровка также лежит в key/mapping.json")


if __name__ == "__main__":
    main()
