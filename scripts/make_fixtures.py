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


def cut_fb2(source: Path, keep_sections: int, target: Path) -> None:
    """Оставляет первые секции первого body и урезает примечания.

    Второй body с атрибутом name="notes" сохраняем нарочно: фикстура нужна
    именно для проверки, что примечания не попадают в озвучку.
    """
    from lxml import etree

    tree = etree.parse(str(source), etree.XMLParser(recover=True))
    root = tree.getroot()
    ns = {"fb": root.nsmap.get(None, "")}

    bodies = root.findall("fb:body", ns)
    for index, body in enumerate(bodies):
        sections = body.findall("fb:section", ns)
        limit = keep_sections if index == 0 else 3
        for section in sections[limit:]:
            body.remove(section)

    # Картинки весят больше самого текста, для тестов они не нужны.
    for binary in root.findall("fb:binary", ns)[1:]:
        root.remove(binary)

    target.write_bytes(etree.tostring(tree, xml_declaration=True, encoding="utf-8"))


def cut_epub(source: Path, keep_docs: int, target: Path) -> None:
    """Оставляет первые документы spine вместе с их частью оглавления."""
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(str(source))
    kept_ids = [item_id for item_id, _ in book.spine[:keep_docs]]
    kept_names = set()

    trimmed = epub.EpubBook()
    trimmed.set_identifier("fixture")
    for key in ("title", "creator", "language"):
        values = book.get_metadata("DC", key)
        if values:
            setter = {
                "title": trimmed.set_title,
                "creator": trimmed.add_author,
                "language": trimmed.set_language,
            }[key]
            setter(values[0][0])

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        if item.get_id() in kept_ids:
            trimmed.add_item(item)
            kept_names.add(item.get_name())

    def keep_entry(entry):
        link = entry[0] if isinstance(entry, tuple) else entry
        return getattr(link, "href", "").split("#")[0] in kept_names

    trimmed.toc = [
        (e[0], [k for k in e[1] if keep_entry(k)]) if isinstance(e, tuple) else e
        for e in book.toc
        if keep_entry(e)
    ]
    trimmed.spine = [item_id for item_id in kept_ids]
    trimmed.add_item(epub.EpubNcx())
    trimmed.add_item(epub.EpubNav())
    epub.write_epub(str(target), trimmed)


EBOOK_RECIPES: dict[str, tuple[str, int, str]] = {
    "book_ru.fb2": ("430741.fb2", 5, "секции, вложенность, отдельный body примечаний"),
    "book_ru.epub": (
        "Kristensen_Reshenie-problemy-innovaciy-v-biznese-Kak-sozdat-rastushchiy-biznes-"
        "i-uspeshno-podderzhivat-ego-rost.430741.fb2.epub",
        12,
        "вложенное оглавление с якорями, нет заголовков h1-h3",
    ),
}


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

    for name, (source_name, keep, why) in EBOOK_RECIPES.items():
        source = SOURCES / source_name
        if not source.exists():
            print(f"пропуск {name}: нет источника {source}")
            continue
        target = FIXTURES / name
        if name.endswith(".fb2"):
            cut_fb2(source, keep, target)
        else:
            cut_epub(source, keep, target)
        print(f"{name:16} {target.stat().st_size // 1024:5} КБ  {why}")


if __name__ == "__main__":
    main()
