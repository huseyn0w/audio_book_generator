"""Командная строка. Тонкая обёртка над конвейером."""

import time
from pathlib import Path
from typing import Annotated

import typer

from book2audio.extract.base import NoTextLayer
from book2audio.models import Selection, parse_page_spec
from book2audio.pipeline import ICLOUD_AUDIOBOOKS, Progress, convert
from book2audio.preflight import INSTALL, MissingTool, check_tools, missing_tools
from book2audio.tts.base import TTSEngine, pick_default
from book2audio.tts.fake import FakeEngine
from book2audio.tts.kokoro import KokoroEngine
from book2audio.tts.silero import SileroEngine

app = typer.Typer(help="Книги в аудиокниги. PDF на входе, wav на выходе.", add_completion=False)

ENGINE_BY_LANGUAGE = {"ru": SileroEngine, "en": KokoroEngine}


def parse_chapters(value: str | None) -> Selection | None:
    """Разбирает 1-3 или 4. Нумерация глав с единицы, как в списке команды chapters."""
    if not value:
        return None
    try:
        if "-" in value:
            first, last = (int(part) for part in value.split("-", 1))
        else:
            first = last = int(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"диапазон глав должен быть вида 1-3 или 4, а не {value!r}"
        ) from exc
    if first < 1 or first > last:
        raise typer.BadParameter(f"неверный диапазон глав: {value!r}")
    return Selection(chapters=tuple(range(first - 1, last)))


def parse_pages(value: str | None) -> Selection | None:
    """Разбирает 10-20 или 7. Правила общие с веб-формой, лежат в models."""
    try:
        return parse_page_spec(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def build_engine(language: str, engine_name: str = "") -> TTSEngine:
    """Собирает движок под язык. Заглушка нужна тестам CLI."""
    if engine_name == "fake":
        return FakeEngine()
    factory = ENGINE_BY_LANGUAGE.get(language)
    if factory is None:
        raise typer.BadParameter(f"язык {language!r} не поддерживается")
    return factory()


def _resolve_voice(language: str, voice: str | None, gender: str) -> str:
    if voice:
        return voice
    try:
        return pick_default(language, gender)
    except KeyError as exc:
        raise typer.BadParameter(f"нет голоса по умолчанию для {language}/{gender}") from exc


@app.command()
def voices(
    lang: Annotated[str, typer.Option(help="ru или en")] = "ru",
) -> None:
    """Показывает голоса движка для языка."""
    engine = build_engine(lang)
    typer.echo(f"движок {engine.name}, версия {engine.version}")
    for v in engine.voices():
        typer.echo(f"  {v.id:16} {v.gender}")


def convert_book(
    path: Annotated[Path, typer.Argument(help="Файл книги", exists=True)],
    lang: Annotated[str, typer.Option(help="ru или en")] = "ru",
    gender: Annotated[str, typer.Option(help="female или male")] = "female",
    voice: Annotated[str | None, typer.Option(help="Конкретный голос, важнее чем --gender")] = None,
    pages: Annotated[str | None, typer.Option(help="Диапазон, например 10-20")] = None,
    out: Annotated[Path, typer.Option(help="Куда класть результат")] = Path("./output"),
    engine: Annotated[str, typer.Option(help="Пусто или fake для тестов", hidden=True)] = "",
    clean: Annotated[
        bool, typer.Option(help="Чистить текст. --no-clean покажет книгу как есть")
    ] = True,
    chapters: Annotated[
        str | None, typer.Option(help="Диапазон глав, например 1-3. Для EPUB и FB2")
    ] = None,
    audio_format: Annotated[str, typer.Option("--format", help="m4b или mp3")] = "m4b",
    icloud: Annotated[bool, typer.Option(help="Копировать результат в папку iCloud Drive")] = True,
) -> None:
    """Превращает книгу в аудио."""
    try:
        check_tools(lang)
    except MissingTool as exc:
        typer.echo(f"Не получится: {exc}")
        raise typer.Exit(code=1) from exc

    tts = build_engine(lang, engine)
    chosen = _resolve_voice(lang, voice, gender) if engine != "fake" else (voice or "fake_a")

    started = time.monotonic()
    last_line = ""

    def show(p: Progress) -> None:
        nonlocal last_line
        if p.stage == "synth":
            share = p.done / p.total
            elapsed = time.monotonic() - started
            eta = elapsed / share - elapsed if share > 0 else 0
            line = f"синтез {p.done}/{p.total} ({share:.0%}), осталось ≈{eta / 60:.1f} мин"
        else:
            line = {"extract": "читаю книгу", "chunk": "режу на куски", "assemble": "склеиваю"}[
                p.stage
            ]
        if line != last_line:
            typer.echo(line)
            last_line = line

    try:
        target = convert(
            path,
            language=lang,
            voice=chosen,
            out_dir=out,
            engine=tts,
            selection=parse_chapters(chapters) if chapters else parse_pages(pages),
            on_progress=show,
            clean=clean,
            audio_format=audio_format,
            copy_to=ICLOUD_AUDIOBOOKS if icloud else None,
        )
    except NoTextLayer as exc:
        typer.echo(f"Не получится: {exc}")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.echo(f"Ошибка: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"готово за {(time.monotonic() - started) / 60:.1f} мин: {target}")
    if icloud:
        typer.echo(f"копия в iCloud: {ICLOUD_AUDIOBOOKS / target.name}")


def chapters_of(
    path: Annotated[Path, typer.Argument(help="Файл книги", exists=True)],
    lang: Annotated[str, typer.Option(help="ru или en")] = "ru",
) -> None:
    """Показывает список глав с номерами для --chapters."""
    from book2audio.pipeline import pick_extractor

    document = pick_extractor(path, clean=True, language=lang).extract(path)
    typer.echo(f"«{document.title}» — {len(document.chapters)} глав")
    for number, chapter in enumerate(document.chapters, start=1):
        minutes = chapter.char_count() / 15 / 60
        typer.echo(f"  {number:3}  {minutes:5.0f} мин  {chapter.title[:60]}")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Адрес. По умолчанию только localhost")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Порт")] = 8000,
    reload: Annotated[bool, typer.Option(help="Перезапуск при правке кода")] = False,
) -> None:
    """Поднимает веб-интерфейс."""
    import uvicorn

    # Веб не знает языка книги заранее, поэтому спрашиваем обо всём сразу.
    # Это предупреждение, а не отказ: русская книга без espeak-ng озвучится.
    absent = missing_tools()
    if absent:
        commands = "; ".join(INSTALL[tool] for tool in absent)
        typer.echo(f"внимание, не хватает: {', '.join(absent)}. Поставить: {commands}")

    typer.echo(f"открой http://{host}:{port}")
    uvicorn.run("book2audio.web.main:app", host=host, port=port, reload=reload)


# typer берёт имя команды из имени функции, поэтому регистрируем явно:
# нужны "convert" и "chapters", а не "convert-book" и "chapters-of".
app.command(name="convert")(convert_book)
app.command(name="chapters")(chapters_of)


if __name__ == "__main__":
    app()
