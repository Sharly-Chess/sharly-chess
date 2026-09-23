"""The FFE team-module connection fields of the tournament form."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest
from utils.enum import EventType

EVENT_ID = 'test-ffe-team-connection-http'
TOURNAMENT_NAME = 'test-ffe-team-connection-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament() -> Iterator[Tournament]:
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
    yield EVENT.tournament()
    EVENT.delete()


@pytest.mark.unit
def test_the_form_offers_the_team_module_fields(
    http: TestClient, tournament: Tournament
):
    response = http.get(f'/tournament-modal/update/{EVENT_ID}/{tournament.id}')
    assert response.status_code == 200
    assert 'ffe-team-connection-section' in response.text
    assert 'name="ffe_team_login"' in response.text
    assert 'name="ffe_team_group"' in response.text
    assert '"ffe-coupe-jean-claude-loubatiere"' in response.text


@pytest.mark.unit
def test_the_lists_wait_for_credentials(http: TestClient, tournament: Tournament):
    """Without credentials the fragment renders with the stored choice
    only, and no site access."""
    response = http.post(
        f'/ffe/team-auth/{EVENT_ID}',
        data={
            'rule_set': 'ffe-coupe-jean-claude-loubatiere',
            'ffe_team_login': '',
            'ffe_team_password': '',
            'ffe_team_division': '706|Phase Departementale',
            'ffe_team_group': '3593|Test group',
            'ffe_team_division_hint': 'Phase Departementale',
        },
    )
    assert response.status_code == 200
    assert 'value="706|Phase Departementale"' in response.text
    assert 'value="3593|Test group"' in response.text
    assert 'Invalid FFE group account' not in response.text


@pytest.mark.unit
def test_refused_credentials_clear_the_valid_mark(
    http: TestClient, tournament: Tournament, monkeypatch
) -> None:
    """The site answers a refused login with the page of a successful
    one, so a wrong password used to leave the fields looking valid."""
    from common.network import NetworkMonitor
    from plugins.ffe.ffe_tournament_controller import FfeTournamentController

    monkeypatch.setattr(NetworkMonitor, 'connected', staticmethod(lambda: True))
    monkeypatch.setattr(
        FfeTournamentController,
        '_team_lists',
        staticmethod(lambda *args, **kwargs: (False, None, None)),
    )
    response = http.post(
        f'/ffe/team-auth/{EVENT_ID}',
        data={
            'rule_set': 'ffe-coupe-jean-claude-loubatiere',
            'ffe_team_login': 'group',
            'ffe_team_password': 'wrong',
            'ffe_team_division': '706|Phase Departementale',
            'ffe_team_group': '3593|Test group',
            'ffe_team_division_hint': 'Phase Departementale',
            'ffe_team_password_visible': 'false',
        },
    )
    assert response.status_code == 200
    assert 'Invalid FFE group account or password.' in response.text
    assert 'is-valid' not in response.text
