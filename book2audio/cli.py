"""Command line. A thin wrapper around the pipeline."""

import time
from pathlib import Path
from typing import Annotated

import typer

from book2audio.extract.base import NoTextLayer
from book2audio.models import Selection, parse_page_spec
from book2audio.pipeline import COPY_TO_ENV, Progress, convert, destination
from book2audio.preflight import INSTALL, MissingTool, check_tools, missing_tools
from book2audio.tts.base import TTSEngine, pick_default
from book2audio.tts.fake import FakeEngine
from book2audio.tts.kokoro import KokoroEngine
from book2audio.tts.silero import SileroEngine

app = typer.Typer(help="Books into audiobooks. A PDF in, a wav out.", add_completion=False)

ENGINE_BY_LANGUAGE = {"ru": SileroEngine, "en": KokoroEngine}


def parse_chapters(value: str | None) -> Selection | None:
    """Parses 1-3 or 4. Chapters count from one, same as the chapters command lists them."""
    if not value:
        return None
    try:
        if "-" in value:
            first, last = (int(part) for part in value.split("-", 1))
        else:
            first = last = int(value)
    except ValueError as exc:
        raise typer.BadParameter(f"a chapter range looks like 1-3 or 4, not {value!r}") from exc
    if first < 1 or first > last:
        raise typer.BadParameter(f"bad chapter range: {value!r}")
    return Selection(chapters=tuple(range(first - 1, last)))


def parse_pages(value: str | None) -> Selection | None:
    """Parses 10-20 or 7. The rules are shared with the web form and live in models."""
    try:
        return parse_page_spec(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def build_engine(language: str, engine_name: str = "") -> TTSEngine:
    """Builds the engine for a language. The stub is there for the CLI tests."""
    if engine_name == "fake":
        return FakeEngine()
    factory = ENGINE_BY_LANGUAGE.get(language)
    if factory is None:
        raise typer.BadParameter(f"language {language!r} is not supported")
    return factory()


def _resolve_voice(language: str, voice: str | None, gender: str) -> str:
    if voice:
        return voice
    try:
        return pick_default(language, gender)
    except KeyError as exc:
        raise typer.BadParameter(f"no default voice for {language}/{gender}") from exc


@app.command()
def voices(
    lang: Annotated[str, typer.Option(help="ru or en")] = "ru",
) -> None:
    """Shows the voices the engine has for a language."""
    engine = build_engine(lang)
    typer.echo(f"engine {engine.name}, version {engine.version}")
    for v in engine.voices():
        typer.echo(f"  {v.id:16} {v.gender}")


def convert_book(
    path: Annotated[Path, typer.Argument(help="Book file", exists=True)],
    lang: Annotated[str, typer.Option(help="ru or en")] = "ru",
    gender: Annotated[str, typer.Option(help="female or male")] = "female",
    voice: Annotated[str | None, typer.Option(help="A specific voice, wins over --gender")] = None,
    pages: Annotated[str | None, typer.Option(help="A range, for example 10-20")] = None,
    out: Annotated[Path, typer.Option(help="Where to put the result")] = Path("./output"),
    engine: Annotated[str, typer.Option(help="Empty or fake for tests", hidden=True)] = "",
    clean: Annotated[
        bool, typer.Option(help="Clean the text. --no-clean shows the book as it is")
    ] = True,
    chapters: Annotated[
        str | None, typer.Option(help="A chapter range, for example 1-3. EPUB and FB2 only")
    ] = None,
    audio_format: Annotated[str, typer.Option("--format", help="m4b or mp3")] = "m4b",
    copy_to: Annotated[
        str | None,
        typer.Option(
            "--copy-to",
            help="Folder for the finished book, for example ~/Desktop/Audiobooks",
        ),
    ] = None,
) -> None:
    """Turns a book into audio."""
    if copy_to is not None and not copy_to.strip():
        raise typer.BadParameter("--copy-to cannot be empty")
    chosen_folder = Path(copy_to) if copy_to else None
    target_folder = destination(chosen_folder)

    try:
        check_tools(lang)
    except MissingTool as exc:
        typer.echo(f"Cannot run: {exc}")
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
            line = f"synthesis {p.done}/{p.total} ({share:.0%}), about {eta / 60:.1f} min left"
        else:
            line = {
                "extract": "reading the book",
                "chunk": "cutting into pieces",
                "assemble": "putting it together",
            }[p.stage]
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
            copy_to=target_folder,
        )
    except NoTextLayer as exc:
        typer.echo(f"Cannot run: {exc}")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"done in {(time.monotonic() - started) / 60:.1f} min: {target}")
    if target_folder:
        typer.echo(f"copy: {target_folder / target.name}")


def chapters_of(
    path: Annotated[Path, typer.Argument(help="Book file", exists=True)],
    lang: Annotated[str, typer.Option(help="ru or en")] = "ru",
) -> None:
    """Lists the chapters with the numbers --chapters takes."""
    from book2audio.pipeline import pick_extractor

    document = pick_extractor(path, clean=True, language=lang).extract(path)
    typer.echo(f"«{document.title}» — {len(document.chapters)} chapters")
    for number, chapter in enumerate(document.chapters, start=1):
        minutes = chapter.char_count() / 15 / 60
        typer.echo(f"  {number:3}  {minutes:5.0f} min  {chapter.title[:60]}")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Address. Localhost only by default")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port")] = 8000,
    reload: Annotated[bool, typer.Option(help="Restart when the code changes")] = False,
    copy_to: Annotated[
        str | None,
        typer.Option(
            "--copy-to",
            help="Folder for finished books, for example ~/Desktop/Audiobooks. "
            "Without it nothing is copied and you download the book from the browser",
        ),
    ] = None,
) -> None:
    """Starts the web interface."""
    import os

    import uvicorn

    # uvicorn with --reload builds the app itself from the import string, so the
    # path travels through the environment instead of an argument.
    if copy_to is not None:
        if not copy_to.strip():
            raise typer.BadParameter("--copy-to cannot be empty")
        os.environ[COPY_TO_ENV] = str(Path(copy_to).expanduser())
    folder = destination(Path(copy_to) if copy_to else None)
    typer.echo(f"finished books: {folder}" if folder else "copying is off")

    # The web does not know the book language up front, so ask about everything at once.
    # This is a warning, not a refusal: a Russian book reads fine without espeak-ng.
    absent = missing_tools()
    if absent:
        commands = "; ".join(INSTALL[tool] for tool in absent)
        typer.echo(f"warning, missing: {', '.join(absent)}. Install with: {commands}")

    typer.echo(f"open http://{host}:{port}")
    uvicorn.run("book2audio.web.main:app", host=host, port=port, reload=reload)


# typer takes the command name from the function name, so register them explicitly:
# we want "convert" and "chapters", not "convert-book" and "chapters-of".
app.command(name="convert")(convert_book)
app.command(name="chapters")(chapters_of)


if __name__ == "__main__":
    app()
