from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def sce_host_resolves() -> Iterator[None]:
    """The Sharly-Chess.com requests are mocked: their host must not be looked
    up for real, which would fail or wait on a computer offline."""
    with patch('plugins.sce.sce_session.host_resolves', return_value=True):
        yield
