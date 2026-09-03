"""Слепое сравнение голосов.

Гоняет один и тот же абзац через все голоса, пишет версии x1 и x2
под обезличенными именами. Расшифровка лежит в key/mapping.json.

Запуск:
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

# Родные русские голоса идут первыми, дикторы СНГ читают с акцентом.
ENGINE_SETS: dict[str, list[str]] = {
    "native": ["silero:v5_5_ru", "kokoro"],
    "all": ["silero:v5_5_ru", "silero:v5_cis_base", "kokoro"],
}


def build_engines(names: list[str]) -> list[tuple[TTSEngine, str]]:
    """Собирает движки по именам. Веса не грузит, конструкторы ленивые."""
    built: list[tuple[TTSEngine, str]] = []
    for name in names:
        if name.startswith("silero:"):
            built.append((SileroEngine(model_id=name.split(":", 1)[1]), "ru"))
        elif name == "kokoro":
            built.append((KokoroEngine(), "en"))
        else:
            raise ValueError(f"неизвестный движок: {name}")
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


def write_player_page(mapping: dict[str, str], out_dir: Path) -> None:
    """Локальная страница для прослушивания. Имя голоса скрыто до клика."""
    rows: list[str] = []
    last_lang = None
    for label, voice in mapping.items():
        lang = label.split("_")[0]
        if lang != last_lang:
            rows.append(f"<h2>{'русский' if lang == 'ru' else 'английский'}</h2>")
            last_lang = lang
        rows.append(
            f'<div class="row"><span class="label">{label}</span>'
            f'<span><span class="speed">x1</span>'
            f'<audio controls preload="none" src="{label}.wav"></audio></span>'
            f'<span><span class="speed">x2</span>'
            f'<audio controls preload="none" src="{label}_x2.wav"></audio></span>'
            f'<button class="voice" data-voice="{voice}">показать</button></div>'
        )
    html = (
        "<!doctype html><meta charset=utf-8><title>Сравнение голосов</title>"
        f"<style>{PAGE_STYLE}</style>"
        "<h1>Слепое сравнение голосов</h1>"
        "<p class=hint>Слушай, отмечай понравившиеся. Имя голоса откроется по кнопке. "
        "Русские родные голоса идут первыми, дальше дикторы СНГ с акцентом.</p>"
        '<p><button id="all">показать все имена</button></p>'
        + "".join(rows)
        + f"<script>{PAGE_SCRIPT}</script>"
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def run_bakeoff(engines: list[tuple[TTSEngine, str]], out_dir: Path) -> dict[str, str]:
    """Синтезирует тестовый абзац всеми голосами. Возвращает расшифровку имён."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "key").mkdir(exist_ok=True)

    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    for engine, lang in engines:
        for voice in engine.voices():
            counters[lang] = counters.get(lang, 0) + 1
            label = f"{lang}_{counters[lang]:02d}"
            x1 = out_dir / f"{label}.wav"
            engine.synth(TEXT_BY_LANG[lang], voice, x1)
            change_speed(x1, out_dir / f"{label}_x2.wav", 2.0)
            mapping[label] = f"{engine.name}/{voice}"
            print(f"{label}  готово")

    (out_dir / "key" / "mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_player_page(mapping, out_dir)
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Слепое сравнение голосов")
    parser.add_argument("--out", type=Path, default=Path("./bakeoff"))
    parser.add_argument(
        "--set",
        dest="engine_set",
        choices=sorted(ENGINE_SETS),
        default="all",
        help="native это 5 родных русских плюс 11 английских, all добавляет 29 голосов СНГ",
    )
    args = parser.parse_args()

    mapping = run_bakeoff(build_engines(ENGINE_SETS[args.engine_set]), args.out)
    print(f"\n{len(mapping)} голосов в {args.out}")
    print(f"Открой {args.out / 'index.html'} в браузере и слушай.")
    print("Расшифровка также лежит в key/mapping.json")


if __name__ == "__main__":
    main()
