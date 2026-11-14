"""The All tournaments modal of the pairings tab pairs the next round of the
ticked tournaments, deciding what becomes of their absent players as the Pair
button would, then publishes the rounds it ticks, a round-robin's next round
among them; the tournaments left out are left out again the next time."""

import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.event import Event
from data.loader import EventLoader
from data.pairings.variations import BergerRoundRobinVariation
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils
from utils.enum import Result

EVENT_ID = 'pair-all-tournaments-ui'
OPEN_A = 'Open A'
OPEN_B = 'Open B'
BLITZ = 'Blitz'
ROUND_ROBIN = 'Round-robin'
DUEL = 'Duel'
ABSENT_PLAYERS = ('BPLAYER5', 'BPLAYER6')


def _play_round(tournament: Tournament, round_: int) -> None:
    with EventDatabase(tournament.event.uniq_id, True) as database:
        for board in tournament.get_round_boards(round_):
            if board.black_tournament_player is None:
                continue
            board.white_pairing.update_result(database, Result.WIN)
            board.black_pairing.update_result(database, Result.LOSS)


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    for name in (OPEN_A, OPEN_B, BLITZ):
        TestUtils.create_tournament(EVENT_ID, name, overrides={'rounds': 3})
    TestUtils.create_tournament(EVENT_ID, DUEL, overrides={'rounds': 3})
    TestUtils.create_tournament(
        EVENT_ID,
        ROUND_ROBIN,
        overrides={'rounds': 3, 'pairing': BergerRoundRobinVariation.static_id()},
    )
    event = EventLoader().load_event(EVENT_ID)
    for name, prefix, count in (
        (OPEN_A, 'A', 4),
        (OPEN_B, 'B', 6),
        (BLITZ, 'C', 4),
        (ROUND_ROBIN, 'R', 4),
        (DUEL, 'D', 4),
    ):
        tournament = event.tournaments_by_name[name]
        for index in range(count):
            event.add_player(
                StoredPlayer(
                    id=None, last_name=f'{prefix}PLAYER{index + 1}', check_in=True
                ),
                [tournament],
            )
    event = EventLoader().load_event(EVENT_ID)
    for name in (OPEN_A, OPEN_B, DUEL):
        tournament = event.tournaments_by_name[name]
        assert tournament.generate_round_pairings(1) == ''
    round_robin = event.tournaments_by_name[ROUND_ROBIN]
    for round_ in range(1, round_robin.rounds + 1):
        assert round_robin.generate_round_pairings(round_) == ''
    event = EventLoader().load_event(EVENT_ID)
    for name in (OPEN_A, OPEN_B, ROUND_ROBIN, DUEL):
        tournament = event.tournaments_by_name[name]
        _play_round(tournament, 1)
        tournament.set_published_round(1)
    event = EventLoader().load_event(EVENT_ID)
    for player in event.tournaments_by_name[OPEN_B].tournament_players:
        if player.last_name in ABSENT_PLAYERS:
            event.tournaments_by_name[OPEN_B].check_in_player(player, check_in=False)
    # Half the duel is absent: the two players left have already met.
    duel = event.tournaments_by_name[DUEL]
    first_board = duel.get_round_boards(1)[0]
    for player in duel.tournament_players:
        if player.id not in (first_board.white_player_id, first_board.black_player_id):
            duel.check_in_player(player, check_in=False)
    yield
    TestUtils.delete_event(EVENT_ID)


def _event() -> Event:
    EventLoader.unload_event(EVENT_ID)
    return EventLoader().load_event(EVENT_ID)


def _open_modal(page: Page) -> None:
    page.goto(f'/event/{EVENT_ID}/pairings/{_event().tournaments_by_name[OPEN_A].id}/1')
    page.get_by_role('button', name='All tournaments').click()
    expect(page.locator('#modal-wrapper .modal-title')).to_have_text('All tournaments')
    TestUtils.wait_for_htmx_idle(page)


@pytest.mark.e2e
def test_pair_then_publish_all_tournaments(page: Page):
    event = _event()
    open_a_id = event.tournaments_by_name[OPEN_A].id
    open_b_id = event.tournaments_by_name[OPEN_B].id
    page.goto(f'/event/{EVENT_ID}/pairings/{open_b_id}/1')
    _open_modal(page)
    modal = page.locator('#modal-wrapper')
    expect(modal.get_by_label(f'{OPEN_A} Round 2')).to_be_checked()
    expect(modal.get_by_label(f'{OPEN_B} Round 2')).to_be_checked()
    for name in ABSENT_PLAYERS:
        expect(modal.get_by_text(name)).to_be_visible()
    expect(modal.get_by_text(BLITZ)).to_be_visible()
    expect(modal.get_by_label(f'{BLITZ} Round 1')).to_have_count(0)
    expect(modal.get_by_label(f'{ROUND_ROBIN} Round 2')).to_be_checked()

    # Every absent player of Open B is paired, but the last one.
    event = _event()
    open_b = event.tournaments_by_name[OPEN_B]
    last_absent = next(
        player
        for player in open_b.tournament_players
        if player.last_name == ABSENT_PLAYERS[-1]
    )
    modal.locator(f'label[for="t{open_b.id}_present-all"]').click()
    modal.locator(f'label[for="t{open_b.id}_zpb-{last_absent.id}"]').click()

    modal.locator('.modal-footer').get_by_role(
        'button', name='Pair', exact=True
    ).click()
    expect(modal.get_by_text(f'{OPEN_A}: round 2 paired.')).to_be_visible()
    expect(modal.get_by_text(f'{OPEN_B}: round 2 paired.')).to_be_visible()
    # The players left in the duel have met: the failure is told first, with
    # a link to the tournament, and stops none of the others.
    failure = modal.locator('.alert-danger')
    expect(failure).to_contain_text('1 tournament could not be paired')
    expect(failure.get_by_role('link', name=DUEL)).to_be_visible()

    event = _event()
    open_a = event.tournaments_by_name[OPEN_A]
    open_b = event.tournaments_by_name[OPEN_B]
    assert open_a.round_has_pairings(2)
    assert open_b.round_has_pairings(2)
    assert open_a.published_round == 1
    assert open_b.published_round == 1
    results = {
        player.last_name: player.pairings_by_round[2].result
        for player in open_b.tournament_players
        if player.last_name in ABSENT_PLAYERS
    }
    assert results[ABSENT_PLAYERS[0]] != Result.ZERO_POINT_BYE
    assert results[ABSENT_PLAYERS[-1]] == Result.ZERO_POINT_BYE
    assert not event.tournaments_by_name[BLITZ].has_pairings
    assert not event.tournaments_by_name[DUEL].round_has_pairings(2)
    assert event.tournaments_by_name[ROUND_ROBIN].published_round == 1

    # Closing the summary shows the round just paired, and the tournaments
    # come back at the round they have moved on to.
    modal.get_by_role('button', name='OK').click()
    expect(page).to_have_url(re.compile(rf'/pairings/{open_a_id}/2$'))
    expect(page.locator('#round-select')).to_have_value('2')
    for tournament_id in (open_b_id, open_a_id):
        page.goto(f'/event/{EVENT_ID}/pairings?tournament_id={tournament_id}')
        expect(page.locator('#round-select')).to_have_value('2')

    _open_modal(page)
    modal.get_by_label(f'{OPEN_B} Round 2').uncheck()
    modal.locator('.modal-footer').get_by_role('button', name='Publish').click()
    expect(modal.get_by_text(f'{OPEN_A}: round 2 published.')).to_be_visible()
    expect(modal.get_by_text(f'{ROUND_ROBIN}: round 2 published.')).to_be_visible()
    event = _event()
    assert event.tournaments_by_name[OPEN_A].published_round == 2
    assert event.tournaments_by_name[OPEN_B].published_round == 1
    assert event.tournaments_by_name[ROUND_ROBIN].published_round == 2

    # The tournament left out is left out again.
    _open_modal(page)
    expect(modal.get_by_label(f'{OPEN_B} Round 2')).not_to_be_checked()
