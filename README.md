# book2audio

PDF, EPUB and FB2 into an m4b audiobook. Russian and English, synthesis runs
locally, no cloud and no paid APIs.

## What it does

Takes a book, strips running heads, page numbers, footnotes and figure
captions, shows you the result to check, reads it aloud and builds an m4b
with chapters and cover art. You download the finished file from the browser,
on a phone or a computer, or point it at a folder to copy into.

The interface is in English, with a Russian switch in the header. The
review screen tells you how long the audio will be, how long the synthesis
will take, lets you pick a folder to copy the finished book into, and warns
you if the text is not in the language you picked. The done screen shows
what the cleaning removed.

## Install

Needs a Mac on Apple Silicon.

```bash
brew install ffmpeg espeak-ng uv
make install
```

`make install` runs `uv sync` and puts `book2audio` on your PATH, so nothing
afterwards needs `uv run` or an activated venv. If `~/.local/bin` is not on
your PATH, add it in `~/.zshrc`.

Model weights download on first run, about 300 MB. After that no network is
needed.

## Run it

```bash
make
```

That frees the port, starts the server and opens http://127.0.0.1:8000.
Drop a book on the page.

```bash
make stop                              # free port 8000
make restart                           # stop and start again
make COPY_TO=~/Desktop/Audiobooks      # also copy every finished book there
make help                              # every command
```

## Command line

Optional. The web interface covers the same thing.

```bash
make chapters BOOK=mybook.fb2                  # chapter list with durations
make convert  BOOK=mybook.pdf                  # the whole book
make convert  BOOK=mybook.pdf PAGES=22-40      # a range of pages
make convert  BOOK=mybook.epub CHAPTERS=4-7    # a range of chapters
make convert  BOOK=mybook.fb2 FORMAT=mp3       # a folder of mp3, not one m4b
make convert  BOOK=mybook.pdf RAW=1            # no cleaning, to compare
make voices   LANG_CODE=en                     # available voices
```

Other variables: `LANG_CODE=en`, `GENDER=male`, `VOICE=eugene`,
`OUT=~/Desktop`, `COPY_TO=~/Desktop/Audiobooks`.

## Voices

Picked by a blind comparison of 45 voices, see
`docs/superpowers/specs/voice-choice.md`.

| Language | Female  | Male       | Engine     |
| -------- | ------- | ---------- | ---------- |
| Russian  | kseniya | eugene     | Silero v5  |
| English  | af_nova | am_michael | Kokoro-82M |

Silero v5 places Russian stress marks and resolves homographs on its own.
Without that, Russian speech gets tiring after twenty minutes.

The language you pick drives normalization as well as the voice, so numbers
in an English book are read in English.

The web interface has a Listen button next to the voice picker: one phrase
in the selected voice, synthesized on the spot.

Rebuild the comparison for yourself with `make bakeoff`.

## Speed

Measured on an M-series Mac:

| Engine     | Realtime | A 12-hour book |
| ---------- | -------- | -------------- |
| Silero v5  | x32-x46  | 20-25 minutes  |
| Kokoro-82M | x5.8     | about 2 hours  |

Synthesis is cached by chunk content. Running the same book again takes
seconds. A chunk that fails gets three attempts, then becomes silence of
the same length and a line in `synth_report.json`, so one bad chunk never
costs a whole run.

## Which format to feed it

If a book exists in several formats, take FB2 or EPUB. In PDF, footnotes
are often set in the same size as body text, and nothing distinguishes them
from prose. On the Christensen book, the PDF yields 714 thousand characters
against 539 thousand from the EPUB: the difference is endnotes, read aloud.

Scans with no text layer are not supported. OCR is out of scope.

## How it works

```
upload → extract → clean → review → segment → synthesize → assemble
```

The core is a library plus a CLI; the web layer is a thin wrapper. Two
protocols hold the whole thing together: `Extractor` returns a `Document`,
`TTSEngine` takes text and writes a wav. Swapping an engine touches one file.

| Module            | Responsibility                                                 |
| ----------------- | -------------------------------------------------------------- |
| `extract/`        | PDF via PyMuPDF, EPUB via ebooklib, FB2 via lxml               |
| `clean/`          | layout heuristics, text repair, normalization for speech       |
| `script_check.py` | warns when the text is not in the language you picked          |
| `chunker.py`      | sentences into chunks of up to 800 characters, pauses          |
| `tts/`            | Silero, Kokoro, sha256 cache                                   |
| `assemble.py`     | ffmpeg, m4b with chapters and cover art, mp3 per chapter       |
| `preflight.py`    | required tools and free disk space, checked before work starts |
| `web/`            | FastAPI, SQLite job registry, SSE, the interface               |

## Development

```bash
make test      # fast tests
make slow      # the tests that load real model weights
make lint fmt  # ruff
```

Fixtures are cut from real books. `make fixtures` rebuilds them, provided the
books are in ~/Downloads.

## Out of scope

OCR for scans, languages other than Russian and English, mixed languages
inside one book, voice cloning, position sync across devices, multi-user
mode.
