"""The documents of an event that has no tournament yet.

The network QR code needs no tournament, so the arbiter can print it
before the first tournament is created.
"""

import re
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-documents-without-tournaments-http'

EVENT = EventUnderTest(EVENT_ID)


@pytest.fixture
def event() -> Iterator[str]:
    EVENT.create()
    yield EVENT_ID
    EVENT.delete()


@pytest.mark.unit
def test_the_documents_button_is_shown(http: TestClient, event: str):
    response = http.get(f'/event/{event}/tournaments', follow_redirects=False)
    assert response.status_code == 200
    assert 'id="print-button"' in response.text


@pytest.mark.unit
def test_the_modal_offers_the_network_qr_code(http: TestClient, event: str):
    response = http.get(f'/documents-modal/{event}', follow_redirects=False)
    assert response.status_code == 200
    documents = re.search(
        r'<select[^>]*name="document".*?</select>', response.text, re.DOTALL
    )
    assert documents is not None
    assert re.findall(r'<option value="([^"]+)"', documents.group(0)) == ['qrcode']
    qrcode_types = re.search(
        r'<select[^>]*name="qrcode-type".*?</select>', response.text, re.DOTALL
    )
    assert qrcode_types is not None
    assert re.findall(r'<option value="([^"]+)"', qrcode_types.group(0)) == ['network']


@pytest.mark.unit
def test_the_network_qr_code_is_generated(http: TestClient, event: str):
    response = http.post(
        f'/event-generate-document/{event}',
        data={'document': 'qrcode', 'qrcode-type': 'network'},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert 'has been generated in another tab' in response.text

    view = http.get(
        f'/document-view/{event}/qrcode',
        params={'options': 'qrcode-type=network|qrcode-network='},
        follow_redirects=False,
    )
    assert view.status_code == 200
    assert 'Please choose a network.' in view.text
