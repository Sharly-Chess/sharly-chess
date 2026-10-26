import secrets
from typing import ClassVar

from litestar import Response, get
from litestar.exceptions import NotFoundException
from litestar.params import FromPath

from web.controllers.base_controller import BaseController


class DocumentPdfSources:
    """The documents being rendered as PDF files. The web engine that renders a
    document has no session, so it is served the document at a URL holding a
    token that cannot be guessed."""

    _sources: ClassVar[dict[str, str]] = {}

    @classmethod
    def add(cls, html: str) -> str:
        """Hold a document until it is discarded, returning its token."""
        token = secrets.token_urlsafe(32)
        cls._sources[token] = html
        return token

    @classmethod
    def get(cls, token: str) -> str | None:
        return cls._sources.get(token)

    @classmethod
    def discard(cls, token: str) -> None:
        cls._sources.pop(token, None)


class DocumentPdfSourceController(BaseController):
    @get(
        path='/document-pdf-source/{token:str}',
        name='document-pdf-source',
    )
    async def document_pdf_source(self, token: FromPath[str]) -> Response[str]:
        html = DocumentPdfSources.get(token)
        if html is None:
            raise NotFoundException()
        return Response(content=html, media_type='text/html')
