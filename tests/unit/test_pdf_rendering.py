import json

import msgspec
import pytest

from data.print_documents.pdf_rendering import decode_pdf_export
from web.controllers.document_pdf_source_controller import DocumentPdfSources


@pytest.mark.unit
class TestPdfRendering:
    def test_decode(self) -> None:
        export = decode_pdf_export(
            json.dumps({'title': 'T1', 'html': '<html></html>'}).encode()
        )
        assert export.title == 'T1'
        assert export.html == '<html></html>'
        assert round(export.margins.left / 72 * 25.4) == 10

    def test_decode_margins(self) -> None:
        export = decode_pdf_export(
            json.dumps(
                {
                    'title': 'T1',
                    'html': '',
                    'margins': {'top': 1, 'right': 2, 'bottom': 3, 'left': 4},
                }
            ).encode()
        )
        assert (export.margins.top, export.margins.left) == (1, 4)

    @pytest.mark.parametrize(
        'content',
        [
            b'not json',
            b'{"title": "T1"}',
            b'{"title": 1, "html": ""}',
            b'{"title": "T1", "html": "", "margins": {"top": 500}}',
        ],
    )
    def test_invalid_documents_are_refused(self, content: bytes) -> None:
        with pytest.raises(msgspec.DecodeError):
            decode_pdf_export(content)

    def test_sources(self) -> None:
        first = DocumentPdfSources.add('<p>First</p>')
        second = DocumentPdfSources.add('<p>Second</p>')
        assert first != second
        assert DocumentPdfSources.get(first) == '<p>First</p>'
        DocumentPdfSources.discard(first)
        assert DocumentPdfSources.get(first) is None
        assert DocumentPdfSources.get(second) == '<p>Second</p>'
        DocumentPdfSources.discard(second)
        DocumentPdfSources.discard(second)
