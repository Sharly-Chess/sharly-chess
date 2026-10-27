"""PDF files of print documents.

A PDF is rendered by the web engine of the desktop application, which lays the
document out as it prints; without the desktop application, documents have no
PDF export.
"""

from abc import ABC, abstractmethod

import msgspec

from data.print_documents.page_margins import PageMargins


class PdfExport(msgspec.Struct):
    """A document to export, as the browser shows it, its fields holding what
    was typed in them."""

    title: str
    html: str
    margins: PageMargins = msgspec.field(default_factory=PageMargins)


class PdfRenderingError(Exception):
    """A page could not be rendered as a PDF."""


class PdfRenderer(ABC):
    @abstractmethod
    async def render(self, url: str, margins: PageMargins) -> bytes:
        """The PDF of the page at ``url``, printed on A4 paper with ``margins``.

        :raises PdfRenderingError: when the page could not be rendered.
        """


class PdfRenderers:
    renderer: PdfRenderer | None = None
    """The renderer the desktop application provides."""

    @classmethod
    def register(cls, renderer: PdfRenderer) -> None:
        cls.renderer = renderer


def decode_pdf_export(content: bytes) -> PdfExport:
    """Decode the document sent by the browser.

    :raises msgspec.ValidationError: when the content is not a document.
    """
    return msgspec.json.decode(content, type=PdfExport)
