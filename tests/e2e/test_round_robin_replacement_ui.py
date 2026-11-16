"""Replacing a player who leaves a round-robin from the player form: the
form asks for the player replaced and the round from which the newcomer
takes over their seat."""

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.loader import EventLoader
from data.pairings.variations import BergerRoundRobinVariation
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils
from utils.enum import Result

EVENT_ID = 'round-robin-replacement-ui'
TOURNAMENT_NAME = 'Berger Round-Robin'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={'pairing': BergerRoundRobinVariation.static_id()},
    )
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    for index in range(4):
        event.add_player(
            StoredPlayer(id=None, last_name=f'PLAYER{index + 1}'), [tournament]
        )
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    for round_ in range(1, tournament.rounds + 1):
        assert tournament.generate_round_pairings(round_) == ''
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    for board in tournament.get_round_boards(1):
        tournament.add_result(board, Result.DRAW)
    yield
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.e2e
def test_replace_a_player_from_the_player_form(page: Page):
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    leaver = next(
        player
        for player in tournament.tournament_players
        if player.last_name == 'PLAYER1'
    )

    page.goto(f'/event/{EVENT_ID}/players')
    page.get_by_test_id('add-player-button').click()
    fields = page.locator(f'.replacement-fields[data-tournament-id="{tournament.id}"]')
    expect(fields).to_be_visible()
    TestUtils.fill_and_confirm(page.locator('input[name=last_name]'), 'NEWCOMER')
    TestUtils.select_and_confirm(
        page.locator(f'select[name=replaces_player_id_{tournament.id}]'),
        str(leaver.id),
    )
    expect(
        page.locator(f'select[name=replaced_from_round_{tournament.id}]')
    ).to_have_value('2')
    TestUtils.submit_modal(page, page.get_by_role('button', name='Create', exact=True))
    expect(page.locator('#modal-form')).to_have_count(0)

    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    newcomer = next(
        player
        for player in tournament.tournament_players
        if player.last_name == 'NEWCOMER'
    )
    assert newcomer.replaced_player is not None
    assert newcomer.replaced_player.id == leaver.id
    assert newcomer.replaced_from_round == 2
    assert tournament.rounds == 3
    assert sorted(
        round_
        for round_, pairing in newcomer.pairings_by_round.items()
        if pairing.opponent_id is not None
    ) == [2, 3]
