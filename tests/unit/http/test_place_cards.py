"""The life of a place-card template, over HTTP.

Templates are files of the installation rather than of an event, so the
ones a test makes are deleted through the same handler that deletes
them for a user.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.print_documents.place_cards.template import PlaceCardTemplate
from tests.unit.http.events import EventUnderTest

NAME = 'Test place cards'


def templates_by_id() -> dict[str, PlaceCardTemplate]:
    return PlaceCardTemplate.get_place_card_templates_by_id()


def template_ids() -> list[str]:
    return list(templates_by_id())


@pytest.fixture
def created(http: TestClient) -> Iterator[str]:
    before = set(template_ids())
    response = http.post(
        '/place-card-template-create', data={'name': NAME, 'type': 'player'}
    )
    assert response.status_code == 200
    made = [id_ for id_ in template_ids() if id_ not in before]
    assert len(made) == 1
    yield made[0]
    for template_id in template_ids():
        if template_id not in before:
            http.delete(f'/place-card-template-delete/{template_id}')


@pytest.mark.unit
def test_a_template_is_created_and_editable(http: TestClient, created: str):
    assert PlaceCardTemplate.load(created).name == NAME
    response = http.get(f'/place-card-visual-editor/{created}')
    assert response.status_code == 200


@pytest.mark.unit
def test_a_template_needs_a_name(http: TestClient):
    before = template_ids()
    response = http.post(
        '/place-card-template-create', data={'name': '', 'type': 'player'}
    )
    assert response.status_code == 200
    assert template_ids() == before


@pytest.mark.unit
def test_a_template_is_duplicated_under_its_own_name(http: TestClient, created: str):
    response = http.post(
        f'/place-card-template-duplicate/{created}', data={'name': f'{NAME} (copy)'}
    )
    assert response.status_code == 200
    copies = [
        template_id
        for template_id, template in templates_by_id().items()
        if template.name == f'{NAME} (copy)'
    ]
    assert len(copies) == 1
    assert copies[0] != created


@pytest.mark.unit
def test_a_deleted_template_is_gone(http: TestClient, created: str):
    response = http.delete(f'/place-card-template-delete/{created}')
    assert response.status_code == 200
    assert created not in template_ids()


@pytest.mark.unit
def test_the_templates_page_lists_them(http: TestClient, created: str):
    response = http.get('/place-card-templates')
    assert response.status_code == 200
    assert NAME in response.text


EVENT = EventUnderTest('test-place-cards-http', 'test-place-cards-http-tournament')


@pytest.fixture
def event() -> Iterator[str]:
    EVENT.create(json_file='tec-swiss')
    yield EVENT.id
    EVENT.delete()


@pytest.mark.unit
def test_the_documents_modal_links_to_the_templates_page(http: TestClient, event: str):
    """The templates are reached from the place cards document itself."""
    response = http.get(f'/documents-modal/{event}')
    assert response.status_code == 200
    assert 'id="place-card-templates-button"' in response.text
    assert 'hx-get="/place-card-templates"' in response.text


@pytest.mark.unit
@pytest.mark.parametrize('path', ['/current_events', '/event/{event}/tournaments'])
def test_the_sidebar_does_not_link_to_the_templates_page(
    http: TestClient, event: str, path: str
):
    response = http.get(path.format(event=event))
    assert response.status_code == 200
    assert '/place-card-templates"' not in response.text
