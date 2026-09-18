"""The request context ``TestUtils`` builds events and screens through,
answered in this process."""

from typing import Any

from litestar.testing import TestClient


class ApiResponse:
    """A response shaped the way ``TestUtils.check_api_response`` reads
    one."""

    def __init__(self, response: Any) -> None:
        self._response = response

    @property
    def ok(self) -> bool:
        return self._response.is_success

    @property
    def status(self) -> int:
        return self._response.status_code

    def body(self) -> bytes:
        return self._response.content

    def text(self) -> str:
        return self._response.text


class ApiClient:
    """Its helpers speak the browser suite's language — a urlencoded body,
    a multipart file — so the same calls set a test up here."""

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        data: str | None = None,
        multipart: dict[str, Any] | None = None,
    ) -> ApiResponse:
        if multipart is not None:
            files = {
                name: (part['name'], part['buffer'], part['mimeType'])
                for name, part in multipart.items()
            }
            return ApiResponse(self._client.post(url, files=files))
        return ApiResponse(
            self._client.post(url, content=data or '', headers=headers or {})
        )

    def patch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        data: str | None = None,
    ) -> ApiResponse:
        return ApiResponse(
            self._client.patch(url, content=data or '', headers=headers or {})
        )

    def delete(self, url: str, headers: dict[str, str] | None = None) -> ApiResponse:
        return ApiResponse(self._client.delete(url, headers=headers or {}))

    def get(self, url: str, headers: dict[str, str] | None = None) -> ApiResponse:
        return ApiResponse(self._client.get(url, headers=headers or {}))
