"""The tournament form under the rule sets of the FFE Interclubs Jeunes:
the Nationale 3 fills the form with the federal regulations and leaves
every field to the arbiter, the national divisions lock them, and neither
is changed once the tournament is paired."""

import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.event import Event
from data.loader import EventLoader
from data.pairings.random_tournaments import (
    RandomTournamentGenerator,
    TournamentSettings,
)
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils
from utils.enum import EventType, Result

EVENT_ID = 'interclubs-jeunes-form-ui'
NATIONALE_3 = 'ffe-interclubs-jeunes-n3'
NATIONAL_DIVISIONS = 'ffe-interclubs-jeunes'
SECOND_GAMES = f'#rule-set-config-{NATIONALE_3}-second-games'
FEDERAL_VALUES = {
    '#pairing-system': 'TEAM_ROUND_ROBIN',
    '#team-player-count': '4',
    '#color-pattern': 'WBWB',
    '#team-colour-type': 'A',
    '#criteria-ffe-licence': 'A',
    '#gp-win': '2',
    '#gp-draw': '0',
    '#gp-loss': '0',
    '#mp-win': '3',
    '#mp-draw': '2',
    '#mp-loss': '1',
    '#mp-zpb': '0',
    '#mp-pab': '0',
}


@pytest.fixture(scope='module')
def tournament_id(api_request_context: APIRequestContext):
    """A generated team Swiss of six boards, not paired yet."""
    TestUtils.create_event(
        EVENT_ID,
        via_api_request_context=api_request_context,
        overrides={'event_type': EventType.TEAM.value},
    )
    yield RandomTournamentGenerator(7).generate(
        TournamentSettings(teams=6, players_per_team=6, rounds=5, pair_rounds=False),
        EVENT_ID,
    )
    TestUtils.delete_event(EVENT_ID)


_loaded: list[Event] = []


def _tournament(tournament_id: int) -> Tournament:
    EventLoader.unload_event(EVENT_ID)
    _loaded[:] = [EventLoader().load_event(EVENT_ID)]
    return _loaded[0].tournaments_by_id[tournament_id]


def _open_form(page: Page, tournament_id: int) -> None:
    page.goto(f'/event/{EVENT_ID}/tournaments')
    page.locator(
        f'[hx-get="/tournament-modal/update/{EVENT_ID}/{tournament_id}"]'
    ).first.click()
    expect(page.locator('#modal-form #rule-set')).to_be_attached()
    # The form only fills in the values of a rule set picked once it has
    # settled, a quarter of a second after it opens.
    page.wait_for_timeout(500)


@pytest.mark.e2e
def test_the_nationale_3_fills_the_form_and_leaves_it_open(
    page: Page, tournament_id: int
):
    _open_form(page, tournament_id)
    expect(page.locator(SECOND_GAMES)).to_be_hidden()

    TestUtils.select_and_confirm(page.locator('#rule-set'), NATIONALE_3)
    for selector, value in FEDERAL_VALUES.items():
        expect(page.locator(selector)).to_have_value(value)
        expect(page.locator(selector)).to_be_enabled()
    expect(page.locator(SECOND_GAMES)).to_have_value('last-board')
    expect(page.locator(SECOND_GAMES)).to_be_enabled()
    expect(
        page.locator('#points-attribution-section .collapse-button-summary')
    ).to_have_text('2 · 0 · 0')
    expect(
        page.get_by_text('Boards playing two games, each for half the points')
    ).to_be_visible()

    # What the rule set filled in is the arbiter's to change: a league
    # pairs its Nationale 3 as a Swiss, and the scoring stays as it was.
    TestUtils.select_and_confirm(page.locator('#pairing-system'), 'TEAM_SWISS')
    expect(page.locator('#gp-win')).to_have_value('2')
    expect(page.locator('#team-player-count')).to_be_enabled()

    # The national divisions impose their format, the round robin included.
    TestUtils.select_and_confirm(page.locator('#rule-set'), NATIONAL_DIVISIONS)
    expect(page.locator('#pairing-system')).to_have_value('TEAM_ROUND_ROBIN')
    expect(page.locator('#pairing-system')).to_be_disabled()
    expect(page.locator('#team-player-count')).to_have_value('8')
    expect(page.locator('#team-player-count')).to_be_disabled()
    expect(page.locator('#gp-win')).to_be_disabled()
    expect(page.locator(SECOND_GAMES)).to_be_hidden()

    # Back to the Nationale 3, nothing is left locked.
    TestUtils.select_and_confirm(page.locator('#rule-set'), NATIONALE_3)
    for selector, value in FEDERAL_VALUES.items():
        expect(page.locator(selector)).to_have_value(value)
        expect(page.locator(selector)).to_be_enabled()

    TestUtils.select_and_confirm(page.locator(SECOND_GAMES), 'last-two-boards')
    TestUtils.submit_modal(page, page.get_by_role('button', name='Save'))
    expect(page.locator('#modal-form')).to_have_count(0)

    tournament = _tournament(tournament_id)
    stored = tournament.stored_tournament
    assert stored.rule_set == NATIONALE_3
    assert stored.rule_set_config == {'second_games': 'last-two-boards'}
    assert tournament.pairing_system.id == 'TEAM_ROUND_ROBIN'
    assert stored.team_player_count == 4
    assert stored.color_pattern == 'WBWB'
    assert (stored.game_points or {})[Result.WIN.value] == 2
    assert [tie_break.id for tie_break in tournament.tie_breaks][:2] == [
        'POINTS',
        'ffe-MUTUAL-RESULTS',
    ]
    assert not tournament.rule_set_managed_tie_breaks


@pytest.mark.e2e
def test_the_rule_set_and_its_boards_playing_twice_are_kept_once_paired(
    page: Page, tournament_id: int
):
    with EventDatabase(EVENT_ID, write=True) as database:
        stored = next(
            stored
            for stored in database.load_stored_tournaments()
            if stored.id == tournament_id
        )
        stored.rule_set = NATIONALE_3
        stored.rule_set_config = {'second_games': 'last-two-boards'}
        database.update_stored_tournament(stored)
    tournament = _tournament(tournament_id)
    assert tournament.generate_round_pairings(1) == ''
    board_count = tournament.team_player_count

    _open_form(page, tournament_id)
    expect(page.locator('#rule-set')).to_be_disabled()
    expect(page.locator(SECOND_GAMES)).to_be_disabled()
    expect(page.locator(SECOND_GAMES)).to_have_value('last-two-boards')
    expect(page.locator('#team-player-count')).to_be_disabled()
    expect(page.locator('#gp-win')).to_be_enabled()

    # A request is not bound by what the form offers: one that leaves the
    # rule set out, or asks for other boards, changes none of them.
    page.evaluate(
        """(secondGames) => {
            const values = {
                '#rule-set': '',
                [secondGames]: 'none',
                '#team-player-count': '3',
            };
            for (const [selector, value] of Object.entries(values)) {
                const input = document.querySelector(selector);
                input.disabled = false;
                input.value = value;
            }
        }""",
        SECOND_GAMES,
    )
    TestUtils.submit_modal(page, page.get_by_role('button', name='Save'))
    expect(page.locator('#modal-form')).to_have_count(0)
    stored = _tournament(tournament_id).stored_tournament
    assert stored.rule_set == NATIONALE_3
    assert stored.rule_set_config == {'second_games': 'last-two-boards'}
    assert stored.team_player_count == board_count


@pytest.mark.e2e
def test_the_keyboard_goes_from_the_last_board_to_its_second_game(
    page: Page, tournament_id: int
):
    with EventDatabase(EVENT_ID, write=True) as database:
        stored = next(
            stored
            for stored in database.load_stored_tournaments()
            if stored.id == tournament_id
        )
        stored.rule_set = NATIONALE_3
        database.update_stored_tournament(stored)
    tournament = _tournament(tournament_id)
    if not tournament.round_has_pairings(1):
        assert tournament.generate_round_pairings(1) == ''

    page.goto(f'/event/{EVENT_ID}/pairings?tournament_id={tournament_id}&round=1')
    second_game = page.locator('tr.extra-game-row').first
    boards = second_game.locator('xpath=preceding-sibling::tr')
    last_board = boards.last
    boards.first.locator('td').first.click()
    expect(boards.first).to_have_class(re.compile(r'\bhighlight\b'))

    for index in range(boards.count()):
        page.keyboard.press('1')
        expect(boards.nth(index).locator('.pairing-cell-result')).not_to_have_text('-')
    page.wait_for_load_state('networkidle')
    expect(second_game).to_have_class(re.compile(r'\bhighlight\b'))
    expect(last_board).not_to_have_class(re.compile(r'\bhighlight\b'))

    # The result of the second game changes no row of the boards above it,
    # so none lights up as changed from elsewhere.
    page.keyboard.press('1')
    expect(second_game.locator('.pairing-cell-result')).not_to_have_text('-')
    page.wait_for_timeout(1500)
    expect(page.locator('tr.live-updated')).to_have_count(0)
