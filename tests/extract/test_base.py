from pathlib import Path

from book2audio.extract.base import Extractor, NoTextLayer
from book2audio.models import Document, Selection


def test_no_text_layer_is_an_exception():
    assert issubclass(NoTextLayer, Exception)


def test_protocol_accepts_a_minimal_implementation():
    class Stub:
        def extract(self, path: Path, selection: Selection | None = None) -> Document:
            return Document(title="t", author=None, language="ru", chapters=[])

    assert isinstance(Stub(), Extractor)


def test_protocol_rejects_object_without_extract():
    class NotAnExtractor:
        pass

    assert not isinstance(NotAnExtractor(), Extractor)
