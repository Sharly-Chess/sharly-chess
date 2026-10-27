"""The constraint of the prohibited pairings, chosen in the modal over HTTP."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from tests.unit.http.events import EventUnderTest
from utils.enum import ProhibitedPairingConstraint

EVENT_ID = 'test-prohibited-pairings-constraint'
TOURNAMENT_NAME = 'test-prohibited-pairings-constraint-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss')
    tournament = EVENT.tournament()
    with EventDatabase(EVENT_ID, write=True) as database:
        tournament.stored_tournament.rounds = 6
        tournament.stored_tournament.fide_mode = False
        database.update_stored_tournament(tournament.stored_tournament)
    yield EVENT.tournament()
    EVENT.delete()


@pytest.mark.unit
def test_the_automatic_grouping_takes_a_constraint(
    http: TestClient, tournament: Tournament
):
    response = http.patch(
        f'/pairings/prohibited/config/{EVENT_ID}/{tournament.id}/6',
        data={
            'dimension': 'club',
            'constraint': ProhibitedPairingConstraint.LOWEST_CRITERION.value,
        },
    )

    assert response.status_code == 200
    assert 'name="constraint"' in response.text
    prohibited_pairings = EVENT.tournament().prohibited_pairings
    assert prohibited_pairings.dimension_id == 'club'
    assert (
        prohibited_pairings.dimension_constraint
        == ProhibitedPairingConstraint.LOWEST_CRITERION
    )


@pytest.mark.unit
def test_an_unknown_constraint_keeps_the_current_one(
    http: TestClient, tournament: Tournament
):
    http.patch(
        f'/pairings/prohibited/config/{EVENT_ID}/{tournament.id}/6',
        data={'dimension': 'club', 'constraint': 'NONSENSE'},
    )

    assert (
        EVENT.tournament().prohibited_pairings.dimension_constraint
        == ProhibitedPairingConstraint.HARD
    )


@pytest.mark.unit
def test_a_manual_group_takes_its_own_constraint(
    http: TestClient, tournament: Tournament
):
    member_ids = ','.join(
        str(player.id) for player in list(tournament.tournament_players)[:2]
    )
    route = f'/pairings/prohibited/manual-save/{EVENT_ID}/{tournament.id}/6'

    http.post(
        route,
        data={
            'member_ids': member_ids,
            'group_constraint': ProhibitedPairingConstraint.PROTECT_TOP.value,
        },
    )
    http.post(
        route,
        data={
            'member_ids': member_ids,
            'group_constraint': ProhibitedPairingConstraint.NONE.value,
        },
    )

    assert [
        group.constraint
        for group in EVENT.tournament().prohibited_pairings.manual_groups()
    ] == [ProhibitedPairingConstraint.PROTECT_TOP, ProhibitedPairingConstraint.HARD]
