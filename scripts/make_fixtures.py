"""Нарезка тестовых фикстур из реальных книг.

Книги целиком в репозиторий не кладём, только вырезки в несколько страниц.
Источники лежат в ~/Downloads и на другой машине могут отсутствовать,
поэтому скрипт запускается руками, а не тестами.

Запуск:
    uv run python scripts/make_fixtures.py
"""

from pathlib import Path

import pymupdf

SOURCES = Path.home() / "Downloads"
FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"

# имя фикстуры -> (файл-источник, первая страница, последняя, зачем нужна)
RECIPES: dict[str, tuple[str, int, int, str]] = {
    "toc_ru.pdf": ("430741.pdf", 22, 30, "есть закладки и метаданные"),
    "no_toc_ru.pdf": (
        "Нил Штраус Правда Неудобная книга об отношениях.pdf",
        30,
        36,
        "закладок нет, главы ищем по размеру шрифта",
    ),
    "scanned_ru.pdf": (
        "Glavnoe_v_istorii_iskusstv.pdf",
        10,
        12,
        "нет текстового слоя, ждём понятную ошибку",
    ),
    "typeset_ru.pdf": (
        "7-hist-05.pdf",
        44,
        51,
        "две колонки, колонтитулы, сноски мелким шрифтом, переносы",
    ),
    "typeset_en.pdf": (
        "Cracking the Coding Interview 189 Programming Questions and Solutions.pdf",
        60,
        66,
        "колонтитулы, номера страниц, листинги кода",
    ),
}


def cut(source: Path, first: int, last: int, target: Path) -> None:
    """Вырезает страницы с first по last включительно, нумерация с единицы."""
    src = pymupdf.open(source)
    out = pymupdf.open()
    out.insert_pdf(src, from_page=first - 1, to_page=last - 1)
    out.set_metadata(src.metadata)
    # Закладки указывают на страницы оригинала, во вырезке нумерация своя.
    kept = [
        [level, title, page - first + 1]
        for level, title, page in src.get_toc()
        if first <= page <= last
    ]
    if kept:
        out.set_toc(kept)
    out.save(target, garbage=4, deflate=True)
    out.close()
    src.close()


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, (source_name, first, last, why) in RECIPES.items():
        source = SOURCES / source_name
        if not source.exists():
            print(f"пропуск {name}: нет источника {source}")
            continue
        target = FIXTURES / name
        cut(source, first, last, target)
        size_kb = target.stat().st_size // 1024
        print(f"{name:16} {size_kb:5} КБ  стр {first}-{last}  {why}")


if __name__ == "__main__":
    main()
