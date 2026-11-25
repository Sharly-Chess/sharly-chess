"""The confirmation asked before a team competition upload that would
destroy the data of its group on the FFE website."""

from collections.abc import Iterator
from typing import Any

import pytest
from litestar.testing import TestClient

from data.tournament import Tournament
from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader
from plugins.ffe.ffe_team_session import FFETeamSession, GroupOverwrite
from plugins.ffe.utils import FFEUtils
from tests.unit.http.events import EventUnderTest
from utils.enum import EventType

EVENT_ID = 'test-ffe-team-overwrite-http'
TOURNAMENT_NAME = 'test-ffe-team-overwrite-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)

OVERWRITE = GroupOverwrite(
    empties_group=True,
    site_team_names=['Club A', 'Club B'],
    unmatched_team_names=['Club A', 'Club B'],
    filled_report_count=7,
)


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    """An empty team competition pointed at a group of the site."""
    EVENT.create(
        event={'event_type': EventType.TEAM},
        tournament={
            'pairing': 'TEAM_SWISS_STANDARD',
            'team_player_count': 4,
            'rounds': 3,
            'rule_set': 'ffe-coupe-jean-claude-loubatiere',
            'rule_set_config': {'phase': 'departmental'},
        },
    )
    tournament = EVENT.tournament()
    plugin_data = FFEUtils.get_tournament_plugin_data(tournament)
    plugin_data.team_login = 'group'
    plugin_data.team_password = 'secret'
    plugin_data.team_division_id = 706
    plugin_data.team_division_name = 'Phase Departementale'
    plugin_data.team_group_id = 3593
    plugin_data.team_group_name = 'Groupe Ille-et-Vilaine'
    FFEUtils.update_tournament_plugin_data(tournament, plugin_data)
    yield EVENT.tournament()
    EVENT.delete()


@pytest.fixture
def uploads(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The uploads started, with their arguments, none sent."""
    started: list[dict[str, Any]] = []
    monkeypatch.setattr(
        FfeBackgroundUploader,
        'schedule_upload',
        classmethod(
            lambda cls, tournament, force=False, confirm_overwrite=False: (
                started.append({'confirm_overwrite': confirm_overwrite})
            )
        ),
    )
    monkeypatch.setattr(
        FfeBackgroundUploader,
        'upload_tournament',
        classmethod(
            lambda cls, event_uniq_id, tournament_id, **kwargs: started.append(kwargs)
        ),
    )
    return started


def _site_answers(monkeypatch: pytest.MonkeyPatch, overwrite: GroupOverwrite | None):
    monkeypatch.setattr(FFETeamSession, 'preview_upload', lambda self: overwrite)


@pytest.mark.unit
def test_an_upload_that_would_empty_the_group_asks_first(
    http: TestClient,
    tournament: Tournament,
    uploads: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
):
    _site_answers(monkeypatch, OVERWRITE)
    response = http.post(
        f'/ffe/upload-modal/upload-tournament/{EVENT_ID}/{tournament.id}'
    )
    assert response.status_code == 200
    assert 'ffe-overwrite-submit' in response.text
    assert 'Groupe Ille-et-Vilaine' in response.text
    assert 'Club A, Club B' in response.text
    assert uploads == []


@pytest.mark.unit
def test_a_harmless_upload_starts_at_once(
    http: TestClient,
    tournament: Tournament,
    uploads: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
):
    _site_answers(monkeypatch, None)
    response = http.post(
        f'/ffe/upload-modal/upload-tournament/{EVENT_ID}/{tournament.id}'
    )
    assert response.status_code == 200
    assert 'ffe-overwrite-submit' not in response.text
    assert uploads == [{'confirm_overwrite': False}]


@pytest.mark.unit
def test_the_tournament_card_asks_first_too(
    http: TestClient,
    tournament: Tournament,
    uploads: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
):
    _site_answers(monkeypatch, OVERWRITE)
    response = http.post(f'/ffe/upload-tournament/{EVENT_ID}/{tournament.id}')
    assert response.status_code == 200
    assert 'ffe-overwrite-submit' in response.text
    assert 'name="from_card" value="on"' in response.text
    assert uploads == []


@pytest.mark.unit
def test_a_wrong_group_name_uploads_nothing(
    http: TestClient,
    tournament: Tournament,
    uploads: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
):
    _site_answers(monkeypatch, OVERWRITE)
    response = http.post(
        f'/ffe/upload-modal/confirm-overwrite/{EVENT_ID}/{tournament.id}',
        data={'group_name': 'Groupe Morbihan', 'from_card': ''},
    )
    assert response.status_code == 200
    assert 'The name typed is not the name of the group.' in response.text
    assert uploads == []


@pytest.mark.unit
def test_the_typed_group_name_confirms_the_overwrite(
    http: TestClient,
    tournament: Tournament,
    uploads: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
):
    _site_answers(monkeypatch, OVERWRITE)
    response = http.post(
        f'/ffe/upload-modal/confirm-overwrite/{EVENT_ID}/{tournament.id}',
        data={'group_name': '  groupe   ille-et-vilaine ', 'from_card': ''},
    )
    assert response.status_code == 200
    assert uploads == [{'confirm_overwrite': True}]


@pytest.mark.unit
def test_the_upload_screen_offers_no_auto_upload_for_teams(
    http: TestClient, tournament: Tournament
):
    response = http.get(f'/ffe/upload-modal/{EVENT_ID}')
    assert response.status_code == 200
    assert 'ffe-auto-upload-all' not in response.text
    assert f'tournament_auto_upload_{tournament.id}' not in response.text
