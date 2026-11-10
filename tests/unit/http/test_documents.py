"""The print documents, rendered in this process.

A document opens in a tab of its own, carrying the modal's choices in one
query parameter, and what those choices put in the markup is read here.
"""

import json
import re
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from database.sqlite.event.event_store import StoredAccount, StoredRole
from tests.unit.http.events import EventUnderTest
from utils.enum import RoleType

EVENT_ID = 'test-documents-http'
TOURNAMENT_NAME = 'test-documents-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament_id() -> Iterator[int]:
    EVENT.create(json_file='tec-swiss')
    tournament = EVENT.tournament()
    assert tournament.id is not None
    yield tournament.id
    EVENT.delete()


def crosstable(http: TestClient, tournament_id: int, **options: str) -> str:
    query = '|'.join(
        f'{key}={value}'
        for key, value in ({'tournament': str(tournament_id)} | options).items()
    )
    response = http.get(
        f'/document-view/{EVENT_ID}/crosstable', params={'options': query}
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_the_crosstable_names_its_players(http: TestClient, tournament_id: int):
    assert 'ALYX' in crosstable(http, tournament_id)


@pytest.mark.unit
@pytest.mark.parametrize(
    ('option', 'included'), [({}, False), ({'player-history': 'on'}, True)]
)
def test_the_crosstable_carries_a_history_per_player_on_request(
    http: TestClient, tournament_id: int, option: dict[str, str], included: bool
):
    markup = crosstable(http, tournament_id, **option)
    assert ('class="player-history"' in markup) is included


@pytest.mark.unit
def test_the_place_cards_remind_the_arbiter_to_update_the_players(
    http: TestClient, tournament_id: int
):
    """Only the cards printed from the player records carry the reminder:
    a board card names no one, and would send the arbiter updating for
    nothing."""
    response = http.get(f'/documents-modal/{EVENT_ID}')
    assert response.status_code == 200
    assert 'before printing the place cards' in response.text

    named = re.search(r'const playerDataTypes = (\[.*?\]);', response.text)
    assert named is not None
    assert set(json.loads(named.group(1))) == {'player', 'pairing', 'team'}


@pytest.mark.unit
def test_the_rating_certificate_states_the_intermediate_rating(
    http: TestClient, tournament_id: int
):
    tournament = EVENT.tournament()
    tournament_player = max(
        tournament.tournament_players,
        key=lambda tournament_player: tournament_player.rating_used_by_fide.value,
    )
    response = http.get(
        f'/document-view/{EVENT_ID}/rating-achievement-certificate',
        params={
            'options': f'tournament={tournament_id}'
            f'|mandatory-player={tournament_player.id}'
        },
    )
    assert response.status_code == 200
    assert 'CERTIFICATE OF FIDE RATING ACHIEVEMENT' in response.text
    assert 'Intermediate FIDE Standard rating after round' in response.text


@pytest.mark.unit
@pytest.mark.parametrize(
    ('form', 'heading'),
    [
        ('FA1', 'FIDE Arbiter Norm Report Form'),
        ('IA1', 'International Arbiter Norm Report Form'),
    ],
)
def test_the_arbiter_norm_report_names_the_candidate(
    http: TestClient, tournament_id: int, form: str, heading: str
):
    candidate = EVENT.load().create_account(
        StoredAccount(
            id=None,
            active=True,
            first_name='Ada',
            last_name='CANDIDATE',
            fide_id=123456,
            stored_roles=[
                StoredRole(
                    account_id=None,
                    role=RoleType.ARBITER.value,
                    tournament_ids=[tournament_id],
                )
            ],
        )
    )
    response = http.get(
        f'/document-view/{EVENT_ID}/arbiter-norm-report',
        params={
            'options': f'tournaments={tournament_id}'
            f'|arbiter-norm-form={form}'
            f'|arbiter-norm-candidate={candidate.id}'
        },
    )
    assert response.status_code == 200
    assert heading in response.text
    assert 'value="CANDIDATE"' in response.text
    assert 'value="123456"' in response.text
