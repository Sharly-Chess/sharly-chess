"""Editing the schedule of a custom round-robin from the pairings tab: the
draft cannot be saved while it breaks the round-robin rules, and saving it
pairs every round."""

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.loader import EventLoader
from data.pairings.round_robin_editor import RoundRobinScheduleEditor
from data.pairings.variations import (
    BergerRoundRobinVariation,
    CustomRoundRobinVariation,
    CustomTeamRoundRobinVariation,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType, Result

EVENT_ID = 'round-robin-schedule-ui'
TOURNAMENT_NAME = 'Custom Round-Robin'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={'pairing': CustomRoundRobinVariation.static_id()},
    )
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    for index in range(5):
        event.add_player(
            StoredPlayer(id=None, last_name=f'PLAYER{index + 1}'), [tournament]
        )
    yield
    TestUtils.delete_event(EVENT_ID)


def _tournament_id() -> int:
    return EventLoader().load_event(EVENT_ID).tournaments_by_name[TOURNAMENT_NAME].id


@pytest.mark.e2e
def test_edit_and_save_the_schedule(page: Page):
    # A custom round-robin opens on the editing of its schedule.
    page.goto(f'/event/{EVENT_ID}/pairings/{_tournament_id()}/1')
    banner = page.locator('#schedule-banner')
    expect(banner).to_be_visible()
    expect(page.get_by_role('button', name='Cancel editing')).to_have_count(0)
    expect(page.locator('#schedule-save')).to_be_disabled()
    expect(page.locator('#schedule-violations')).to_be_visible()
    expect(page.locator('#schedule-editor-table .schedule-table-row')).to_have_count(2)
    expect(page.locator('#schedule-editor-table .schedule-rest-row')).to_have_count(1)

    page.get_by_role('button', name='Fill from the Berger tables').click()
    expect(page.locator('#schedule-violations')).to_have_count(0)
    expect(page.locator('#schedule-save')).to_be_enabled()

    # Seating the white player of the second table at the first one empties
    # the seat they leave.
    second_white_label = page.locator(
        '#schedule-editor-table select[data-table="1"][data-side="0"] option:checked'
    ).inner_text()
    page.locator(
        '#schedule-editor-table select[data-table="0"][data-side="0"] + .select2'
    ).click()
    results = page.locator('.select2-results')
    expect(results.locator('.select2-results__group')).to_have_text(['Paired'])
    results.get_by_role('option', name=second_white_label).click()
    expect(
        page.locator('#schedule-editor-table select[data-table="1"][data-side="0"]')
    ).to_have_value('')
    expect(page.locator('#schedule-violations')).to_be_visible()
    expect(page.locator('#schedule-save')).to_be_disabled()

    # An empty seat keeps its width.
    boxes = [
        page.locator(
            f'#schedule-editor-table select[data-table="1"][data-side="{side}"]'
            ' + .select2'
        ).bounding_box()
        for side in (0, 1)
    ]
    assert boxes[0] is not None and boxes[1] is not None
    assert abs(boxes[0]['width'] - boxes[1]['width']) < 1, boxes

    # The player left without a seat is offered first.
    page.locator(
        '#schedule-editor-table select[data-table="1"][data-side="0"] + .select2'
    ).click()
    expect(results.locator('.select2-results__group')).to_have_text(
        ['To pair', 'Paired']
    )
    page.keyboard.press('Escape')

    # Filling from the Berger tables is offered on an empty schedule only;
    # emptying it is confirmed first.
    expect(page.locator('#schedule-fill-berger')).to_have_count(0)
    page.locator('#schedule-clear').click()
    page.locator('#schedule-confirm').click()
    page.locator('#schedule-fill-berger').click()
    expect(page.locator('#schedule-save')).to_be_enabled()
    page.locator('#schedule-save').click()

    expect(banner).to_have_count(0)
    expect(page.locator('#pairings-table')).to_be_visible()
    expect(page.locator('#schedule-edit')).to_be_visible()
    expect(page.get_by_text('Pair tournament', exact=True)).to_have_count(0)
    # The tournament keeps only a weak reference to its event.
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    assert tournament.round_robin_schedule is not None
    assert all(tournament.round_has_pairings(round_) for round_ in range(1, 6))

    # Its pairings are changed by editing the schedule, not by unpairing.
    expect(page.get_by_role('button', name='Unpair tournament')).to_have_count(0)


BERGER_EVENT_ID = 'berger-round-robin-schedule-ui'
BERGER_TOURNAMENT_NAME = 'Berger Round-Robin'


@pytest.fixture
def berger_event(api_request_context: APIRequestContext):
    TestUtils.create_event(BERGER_EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.create_tournament(
        BERGER_EVENT_ID,
        BERGER_TOURNAMENT_NAME,
        overrides={'pairing': BergerRoundRobinVariation.static_id()},
    )
    event = EventLoader().load_event(BERGER_EVENT_ID)
    tournament = event.tournaments_by_name[BERGER_TOURNAMENT_NAME]
    for index in range(4):
        event.add_player(
            StoredPlayer(id=None, last_name=f'PLAYER{index + 1}'), [tournament]
        )
    yield tournament.id
    TestUtils.delete_event(BERGER_EVENT_ID)


@pytest.mark.e2e
def test_berger_round_robin_is_paired_before_its_schedule_is_edited(
    page: Page, berger_event: int
):
    page.goto(f'/event/{BERGER_EVENT_ID}/pairings/{berger_event}/1')
    expect(page.get_by_text('Pair tournament', exact=True)).to_be_visible()
    expect(page.locator('#schedule-edit')).to_have_count(0)

    # The tournament keeps only a weak reference to its event.
    event = EventLoader().load_event(BERGER_EVENT_ID)
    tournament = event.tournaments_by_name[BERGER_TOURNAMENT_NAME]
    for round_ in range(1, tournament.rounds + 1):
        assert tournament.generate_round_pairings(round_) == ''
    page.reload()
    expect(page.locator('#schedule-edit')).to_be_visible()
    expect(page.get_by_text('Pair tournament', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Unpair tournament')).to_be_visible()

    page.locator('#schedule-edit').click()
    expect(page.locator('#schedule-banner')).to_be_visible()
    expect(page.get_by_role('button', name='Cancel editing')).to_be_visible()
    # Swapping the colours of the first game keeps the rules but leaves the
    # Berger tables.
    page.locator('.schedule-swap-colours').first.click()
    expect(page.locator('#schedule-violations')).to_have_count(0)
    expect(page.locator('#schedule-save')).to_be_enabled()
    page.locator('#schedule-save').click()
    expect(page.locator('#schedule-banner')).to_have_count(0)
    expect(page.get_by_text('now uses a custom schedule')).to_be_visible()
    event = EventLoader().load_event(BERGER_EVENT_ID)
    assert (
        event.tournaments_by_name[BERGER_TOURNAMENT_NAME].pairing_variation.id
        == CustomRoundRobinVariation.static_id()
    )


TEAM_EVENT_ID = 'team-round-robin-schedule-ui'
TEAM_TOURNAMENT_NAME = 'Custom Team Round-Robin'


@pytest.fixture
def team_event():
    TestUtils.create_event(
        TEAM_EVENT_ID,
        overrides={'event_type': EventType.TEAM},
    )
    TestUtils.create_tournament(
        TEAM_EVENT_ID,
        TEAM_TOURNAMENT_NAME,
        overrides={
            'team_player_count': 2,
            'pairing': CustomTeamRoundRobinVariation.static_id(),
        },
    )
    with EventDatabase(TEAM_EVENT_ID, write=True) as database:
        tournament_id = next(
            stored_tournament.id
            for stored_tournament in database.load_stored_tournaments()
            if stored_tournament.name == TEAM_TOURNAMENT_NAME
        )
        assert tournament_id is not None
        for seed in range(1, 5):
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'TEAM{seed}',
                    tournament_id=tournament_id,
                    pairing_number=seed,
                    check_in=True,
                )
            )
            for index in range(2):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'T{seed}P{index}',
                        team_id=team_id,
                        team_index=index,
                        check_in=True,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        pairing_number=index,
                    )
                )
    yield tournament_id
    TestUtils.delete_event(TEAM_EVENT_ID)


@pytest.mark.e2e
def test_team_round_robin_is_paired_from_the_saved_schedule(
    page: Page, team_event: int
):
    page.goto(f'/event/{TEAM_EVENT_ID}/pairings/{team_event}/1')
    expect(page.locator('#schedule-banner')).to_be_visible()
    expect(page.get_by_role('columnheader', name='First team')).to_be_visible()

    page.get_by_role('button', name='Fill from the Berger tables').click()
    expect(page.locator('#schedule-save')).to_be_enabled()
    page.locator('#schedule-save').click()
    expect(page.locator('#schedule-banner')).to_have_count(0)

    # The members of each round are still paired round by round.
    expect(page.locator('#schedule-edit')).to_be_visible()
    event = EventLoader().load_event(TEAM_EVENT_ID)
    tournament = event.tournaments_by_name[TEAM_TOURNAMENT_NAME]
    assert tournament.round_robin_schedule is not None
    assert not tournament.has_pairings


CORRECTION_EVENT_ID = 'round-robin-schedule-correction-ui'
CORRECTION_TOURNAMENT_NAME = 'Corrected Round-Robin'


@pytest.fixture
def played_round(api_request_context: APIRequestContext):
    """A custom round-robin of four players, its first round played: the
    first player of each game won."""
    TestUtils.create_event(
        CORRECTION_EVENT_ID, via_api_request_context=api_request_context
    )
    TestUtils.create_tournament(
        CORRECTION_EVENT_ID,
        CORRECTION_TOURNAMENT_NAME,
        overrides={'pairing': CustomRoundRobinVariation.static_id()},
    )
    event = EventLoader().load_event(CORRECTION_EVENT_ID)
    tournament = event.tournaments_by_name[CORRECTION_TOURNAMENT_NAME]
    for index in range(4):
        event.add_player(
            StoredPlayer(id=None, last_name=f'PLAYER{index + 1}'), [tournament]
        )
    event = EventLoader().load_event(CORRECTION_EVENT_ID)
    tournament = event.tournaments_by_name[CORRECTION_TOURNAMENT_NAME]
    editor = RoundRobinScheduleEditor(tournament)
    assert editor.fill_from_berger_tables() is None
    assert editor.save() is None
    event = EventLoader().load_event(CORRECTION_EVENT_ID)
    tournament = event.tournaments_by_name[CORRECTION_TOURNAMENT_NAME]
    for board in tournament.get_round_boards(1):
        tournament.add_result(board, Result.WIN)
    yield tournament.id
    TestUtils.delete_event(CORRECTION_EVENT_ID)


@pytest.mark.e2e
def test_games_played_at_the_wrong_boards_are_corrected(page: Page, played_round: int):
    page.goto(f'/event/{CORRECTION_EVENT_ID}/pairings/{played_round}/1')
    page.locator('#schedule-edit').click()
    expect(page.locator('#schedule-banner')).to_be_visible()
    # The games played are locked until unlocked.
    expect(page.locator('#schedule-editor-table select')).to_have_count(0)
    page.locator('#schedule-unlock-played-games').click()
    page.locator('#schedule-confirm').click()
    expect(page.locator('#schedule-editor-table select')).to_have_count(4)

    def seat(table: int, side: int):
        return page.locator(
            f'#schedule-editor-table select[data-table="{table}"][data-side="{side}"]'
        )

    def choose(table: int, side: int, label: str) -> None:
        seat(table, side).locator('+ .select2').click()
        page.locator('.select2-results').get_by_role('option', name=label).click()
        expect(seat(table, side).locator('option:checked')).to_have_text(label)

    # The black players of the two games really played the other game.
    second = seat(0, 1).locator('option:checked').inner_text()
    fourth = seat(1, 1).locator('option:checked').inner_text()
    choose(0, 1, fourth)
    choose(1, 1, second)
    expect(page.locator('#schedule-save')).to_be_disabled()
    page.locator('#schedule-force-save').click()
    page.locator('#schedule-confirm').click()

    expect(page.locator('#schedule-banner')).to_have_count(0)
    expect(page.locator('[hx-get*="/pairings/fide-log-modal/"]')).to_be_visible()
    event = EventLoader().load_event(CORRECTION_EVENT_ID)
    tournament = event.tournaments_by_name[CORRECTION_TOURNAMENT_NAME]
    assert tournament.schedule_breaches
    assert tournament.pibes == []
    assert all(board.result == Result.WIN for board in tournament.get_round_boards(1))
