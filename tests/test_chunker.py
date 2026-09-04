import pytest

from book2audio.chunker import (
    PAUSE_BETWEEN_CHAPTERS,
    PAUSE_BETWEEN_PARAGRAPHS,
    PAUSE_IN_PARAGRAPH,
    Chunk,
    chunk_document,
    split_long_sentence,
)
from book2audio.models import Block, Chapter, Document


def doc_with(*chapters):
    return Document(title="Книга", author=None, language="ru", chapters=list(chapters))


def chapter(title, *texts):
    return Chapter(title=title, blocks=[Block(kind="paragraph", text=t) for t in texts])


def body(chunks):
    """Чанки без объявления заголовка главы. Само объявление проверяется отдельно."""
    return chunks[1:]


def test_chunk_carries_text_and_pause():
    c = Chunk(text="привет", pause_after=0.25)
    assert c.text == "привет"
    assert c.pause_after == 0.25


def test_chunk_rejects_negative_pause():
    with pytest.raises(ValueError, match="пауза"):
        Chunk(text="привет", pause_after=-1.0)


def test_short_paragraph_becomes_one_chunk():
    chunks = chunk_document(doc_with(chapter("Гл", "Одно предложение.")), "ru")
    assert [c.text for c in body(chunks)] == ["Одно предложение."]


def test_no_chunk_exceeds_the_limit():
    text = " ".join(f"Предложение номер {i} про запас." for i in range(200))
    chunks = chunk_document(doc_with(chapter("Гл", text)), "ru", limit=200)
    assert chunks
    assert all(len(c.text) <= 200 for c in chunks)


def test_sentences_are_not_split_across_chunks():
    text = "Первое предложение тут. Второе предложение здесь. Третье предложение там."
    chunks = chunk_document(doc_with(chapter("Гл", text)), "ru", limit=50)
    for c in body(chunks):
        assert c.text.endswith((".", "!", "?"))


def test_last_chunk_of_paragraph_gets_paragraph_pause():
    d = doc_with(chapter("Гл", "Абзац раз.", "Абзац два."))
    chunks = body(chunk_document(d, "ru"))
    assert chunks[0].pause_after == PAUSE_BETWEEN_PARAGRAPHS
    assert chunks[-1].pause_after == PAUSE_BETWEEN_CHAPTERS


def test_chunks_inside_a_paragraph_get_the_short_pause():
    text = "Первое предложение тут. Второе предложение здесь."
    chunks = body(chunk_document(doc_with(chapter("Гл", text)), "ru", limit=30))
    assert len(chunks) == 2
    assert chunks[0].pause_after == PAUSE_IN_PARAGRAPH


def test_chapter_title_is_read_aloud_first():
    chunks = chunk_document(doc_with(chapter("Глава первая", "Текст главы.")), "ru")
    assert chunks[0].text == "Глава первая"


def test_chapter_title_is_not_repeated_when_it_is_already_a_heading_block():
    ch = Chapter(
        title="Глава первая",
        blocks=[
            Block(kind="heading", text="Глава первая"),
            Block(kind="paragraph", text="Текст главы."),
        ],
    )
    chunks = chunk_document(doc_with(ch), "ru")
    assert [c.text for c in chunks].count("Глава первая") == 1


def test_empty_document_gives_no_chunks():
    assert chunk_document(doc_with(), "ru") == []


def test_english_document_is_segmented_too():
    text = "The first sentence here. The second one follows. A third arrives."
    chunks = chunk_document(doc_with(chapter("Ch", text)), "en", limit=40)
    assert len(chunks) >= 2


# --- разрезание слишком длинного предложения ---


def test_split_long_sentence_prefers_semicolons():
    sentence = "а" * 60 + "; " + "б" * 60
    parts = split_long_sentence(sentence, limit=100)
    assert len(parts) == 2
    assert parts[0].endswith(";")


def test_split_long_sentence_falls_back_to_commas():
    sentence = "а" * 60 + ", " + "б" * 60
    parts = split_long_sentence(sentence, limit=100)
    assert len(parts) == 2
    assert parts[0].endswith(",")


def test_split_long_sentence_falls_back_to_words():
    sentence = " ".join(["слово"] * 60)
    parts = split_long_sentence(sentence, limit=100)
    assert all(len(p) <= 100 for p in parts)
    assert " ".join(parts) == sentence


def test_split_long_sentence_never_loses_a_word_without_separators():
    """Одно слово длиннее лимита режем как есть: лучше кривая пауза, чем падение."""
    parts = split_long_sentence("я" * 250, limit=100)
    assert all(len(p) <= 100 for p in parts)
    assert "".join(parts) == "я" * 250


def test_chapter_title_is_announced_once_end_to_end():
    """На реальной книге заголовок дублировался: блок был paragraph, а не heading."""
    ch = Chapter(
        title="Глава 1 Императив роста",
        blocks=[
            Block(kind="heading", text="Глава 1 Императив роста"),
            Block(kind="paragraph", text="Финансовые рынки предъявляют требования."),
        ],
    )
    texts = [c.text for c in chunk_document(doc_with(ch), "ru")]
    assert texts.count("Глава 1 Императив роста") == 1


# --- куски, в которых нечего произносить ---


def test_scene_separator_is_not_a_chunk():
    """«* * *» это разделитель сцен. Букв нет, движку он не по зубам."""
    doc = Document(
        "Книга",
        None,
        "ru",
        [
            Chapter(
                "Глава",
                [
                    Block(kind="paragraph", text="Первый абзац."),
                    Block(kind="paragraph", text="* * *"),
                    Block(kind="paragraph", text="Второй абзац."),
                ],
            )
        ],
    )
    texts = [c.text for c in chunk_document(doc, "ru")]
    assert "* * *" not in texts
    assert any("Первый" in t for t in texts)
    assert any("Второй" in t for t in texts)


def test_digits_alone_still_count_as_speakable():
    """«1861» произносится, в отличие от «* * *»."""
    doc = Document("Книга", None, "ru", [Chapter("Глава", [Block(kind="paragraph", text="1861")])])
    assert [c.text for c in chunk_document(doc, "ru")] == ["Глава", "1861"]
