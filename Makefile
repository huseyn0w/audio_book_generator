# book2audio. Every command runs from here.
#
#   make              start the interface and open the browser
#   make stop         free the port
#   make help         the whole list
#
# If book2audio is not installed globally, the Makefile falls back to uv run.

BIN := $(shell command -v book2audio 2>/dev/null || echo "uv run book2audio")

HOST      ?= 127.0.0.1
PORT      ?= 8000
LANG_CODE ?= ru
GENDER    ?= female
FORMAT    ?= m4b
OUT       ?= output

SERVE_FLAGS := --host $(HOST) --port $(PORT)
ifdef COPY_TO
SERVE_FLAGS += --copy-to $(COPY_TO)
endif
ifdef RELOAD
SERVE_FLAGS += --reload
endif

CONVERT_FLAGS := --lang $(LANG_CODE) --gender $(GENDER) --format $(FORMAT) --out $(OUT)
ifdef VOICE
CONVERT_FLAGS += --voice $(VOICE)
endif
ifdef PAGES
CONVERT_FLAGS += --pages $(PAGES)
endif
ifdef CHAPTERS
CONVERT_FLAGS += --chapters $(CHAPTERS)
endif
ifdef COPY_TO
CONVERT_FLAGS += --copy-to $(COPY_TO)
endif
ifdef RAW
CONVERT_FLAGS += --no-clean
endif

define need_book
	@if [ -z "$(BOOK)" ]; then \
	    echo "Name a book: make $@ BOOK=yourbook.pdf"; \
	    exit 1; \
	fi
	@if [ ! -f "$(BOOK)" ]; then \
	    echo "No such file: $(BOOK)"; \
	    exit 1; \
	fi
endef

.DEFAULT_GOAL := serve
.PHONY: serve stop restart open install help convert chapters voices test slow lint fmt fixtures bakeoff clean

serve: stop
	@echo "interface on http://$(HOST):$(PORT)"
	@( sleep 2 && open "http://$(HOST):$(PORT)" ) &
	@$(BIN) serve $(SERVE_FLAGS)

stop:
	@pids=$$(lsof -ti :$(PORT) 2>/dev/null); \
	if [ -n "$$pids" ]; then \
	    kill $$pids && echo "port $(PORT) is free"; \
	    sleep 1; \
	fi

restart: stop serve

open:
	@open "http://$(HOST):$(PORT)"

install:
	uv sync
	@mkdir -p $(HOME)/.local/bin
	@ln -sf "$(CURDIR)/.venv/bin/book2audio" "$(HOME)/.local/bin/book2audio"
	@echo "book2audio now runs from any folder"

convert:
	$(need_book)
	@$(BIN) convert "$(BOOK)" $(CONVERT_FLAGS)

chapters:
	$(need_book)
	@$(BIN) chapters "$(BOOK)" --lang $(LANG_CODE)

voices:
	@$(BIN) voices --lang $(LANG_CODE)

test:
	uv run pytest

slow:
	uv run pytest -m slow

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

fixtures:
	uv run python scripts/make_fixtures.py

bakeoff:
	uv run python scripts/voice_bakeoff.py --out ./bakeoff
	@open bakeoff/index.html

clean:
	@rm -rf .pytest_cache .ruff_cache
	@find . -name __pycache__ -type d -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	@echo "caches removed, output left alone"

help:
	@echo ""
	@echo "  make                interface on http://$(HOST):$(PORT), the browser opens itself"
	@echo "  make stop           free port $(PORT)"
	@echo "  make restart        stop and start again"
	@echo "  make open           open the browser"
	@echo ""
	@echo "  make install        uv sync, then book2audio on your PATH"
	@echo ""
	@echo "  make chapters BOOK=book.fb2       chapter list"
	@echo "  make convert  BOOK=book.pdf       build the audiobook"
	@echo "  make voices                       available voices"
	@echo ""
	@echo "  convert variables:  LANG_CODE=en GENDER=male VOICE=eugene"
	@echo "                      PAGES=22-40 CHAPTERS=4-7 FORMAT=mp3"
	@echo "                      OUT=~/Desktop COPY_TO=~/Desktop/Audiobooks RAW=1"
	@echo ""
	@echo "  make test           fast tests"
	@echo "  make slow           tests that load real model weights"
	@echo "  make lint fmt       ruff check, ruff format"
	@echo "  make fixtures       rebuild test fixtures from books in ~/Downloads"
	@echo "  make bakeoff        blind voice comparison page"
	@echo "  make clean          remove caches, keep output"
	@echo ""
