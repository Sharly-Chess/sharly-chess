"""The wizard creating a screen.

Creating a screen of a type that has a wizard first offers the choice between
the wizard and the standard form. The wizard asks its questions one after the
other, as the answers lead, and creates the screen (or the paged screen) from
the answers.
"""

import re
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from data.wizard import (
    WizardBoolQuestion,
    WizardIntQuestion,
    WizardOption,
    WizardRadioQuestion,
    WizardStrQuestion,
    WizardTournamentQuestion,
    WizardTournamentsQuestion,
)
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils
from utils.enum import (
    PlayersScreenBoardFormat,
    PlayersScreenOpponentFormat,
    PlayersScreenPlayerFormat,
)
from tests.unit.http.client import ApiClient
from tests.unit.http.conftest import TEAM_EVENT_ID

EVENT_ID = 'test-screen-wizard-http'
TOURNAMENT_NAME = 'test-screen-wizard-http-tournament'

# The option indexes of the radio questions of the wizards: check-in...
SHOW_STATUS = '0'
LET_CHECK_IN = '1'
# ... pairings by board...
SHOW_PAIRINGS = '0'
ENTER_RESULTS = '1'
MATCHES_ONLY = '1'
# ... pairings by player...
SHOW_UNPAIRED = '0'
HIDE_UNPAIRED = '1'
FULL_FORMAT = '0'
MINIMAL_FORMAT = '2'
# ... and all.
ONE_PAGE = '0'
SEVERAL_PAGES = '1'
NUMBER_PER_PAGE = '0'
PAGES = '1'


@pytest.fixture
def tournament(api: ApiClient) -> Iterator[StoredTournament]:
    TestUtils.create_event(EVENT_ID)
    stored = TestUtils.create_tournament(
        EVENT_ID, TOURNAMENT_NAME, json_file='test-screens'
    )
    yield stored
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def reload_event():
    EventLoader.unload_event(EVENT_ID)
    return EventLoader().load_event(EVENT_ID)


@pytest.mark.unit
@pytest.mark.parametrize(
    'screen_type', [ScreenType.CHECK_IN, ScreenType.BOARDS, ScreenType.PLAYERS]
)
def test_the_creation_of_a_screen_offers_the_wizard(
    http: TestClient, tournament: StoredTournament, screen_type: ScreenType
):
    response = http.get(f'/screen-create-choice-modal/{EVENT_ID}/{screen_type.value}')
    assert response.status_code == 200
    assert 'screen-create-choice-wizard' in response.text
    assert 'screen-create-choice-form' in response.text


@pytest.mark.unit
def test_a_type_without_wizard_opens_the_standard_form(
    http: TestClient, tournament: StoredTournament
):
    response = http.get(
        f'/screen-create-choice-modal/{EVENT_ID}/{ScreenType.RESULTS.value}'
    )
    assert response.status_code == 200
    assert 'screen-create-choice-wizard' not in response.text
    assert 'id="modal-form"' in response.text


@pytest.mark.unit
def test_the_wizard_modal_opens(http: TestClient, tournament: StoredTournament):
    response = http.get(f'/screen-wizard-modal/{EVENT_ID}/{ScreenType.CHECK_IN.value}')
    assert response.status_code == 200
    assert 'screen-wizard-question-accepts_input' in response.text
    # The event has no timer: the timer question is not asked.
    assert 'screen-wizard-question-timer' not in response.text
    # The questions are set to their default values.
    assert re.search(
        r'name="answer_accepts_input"\s+value="0"[^>]*\schecked', response.text
    )
    assert not re.search(
        r'name="answer_accepts_input"\s+value="1"[^>]*\schecked', response.text
    )


@pytest.mark.unit
def test_the_default_values_of_the_wizard():
    def radio(default_value: object) -> WizardRadioQuestion:
        return WizardRadioQuestion(
            text='',
            options=[
                WizardOption(value=0, text=''),
                WizardOption(value=False, text=''),
                WizardOption(value=True, text=''),
            ],
            default_value=default_value,
        )

    assert radio(False).default_form_value == '1'
    assert radio(True).default_form_value == '2'
    # No default value: the first option.
    assert radio(None).default_form_value == '0'
    assert WizardIntQuestion(text='', default_value=10).default_form_value == '10'
    assert WizardIntQuestion(text='').default_form_value == ''
    assert WizardStrQuestion(text='', default_value='a').default_form_value == 'a'
    assert WizardBoolQuestion(text='', default_value=True).default_form_value == 'on'
    assert WizardBoolQuestion(text='').default_form_value == ''


@pytest.mark.unit
def test_the_tournament_questions(tournament: StoredTournament):
    event = reload_event()
    assert tournament.id is not None
    other_id = tournament.id + 1

    # All the tournaments are offered, and selected by default...
    question = WizardTournamentsQuestion(event.sorted_tournaments, next='next')
    assert question.type == 'tournaments'
    assert question.select_options == {str(tournament.id): TOURNAMENT_NAME}
    assert question.default_form_value == str(tournament.id)
    assert question.read_answer(f'{tournament.id};') == ([tournament.id], 'next')
    # ... only them can be chosen.
    with pytest.raises(ValueError, match=r'Please choose the tournaments\.'):
        question.read_answer(f'{tournament.id};{other_id}')
    with pytest.raises(ValueError, match=r'Please choose the tournaments\.'):
        question.read_answer('')

    # The first tournament is selected by default.
    single = WizardTournamentQuestion(event.sorted_tournaments, next='next')
    assert single.type == 'tournament'
    assert single.select_options == {str(tournament.id): TOURNAMENT_NAME}
    assert single.default_form_value == str(tournament.id)
    assert single.read_answer(str(tournament.id)) == (tournament.id, 'next')
    with pytest.raises(ValueError, match=r'Please choose the tournament\.'):
        single.read_answer(str(other_id))

    # The text, the default value... can be given; the question can be the
    # last one.
    custom = WizardTournamentsQuestion(
        event.sorted_tournaments, text='Which?', default_value=[], help='Help'
    )
    assert (custom.text, custom.help, custom.next) == ('Which?', 'Help', None)
    assert custom.default_form_value == ''
    assert WizardTournamentQuestion([]).default_form_value == ''


@pytest.mark.unit
def test_the_wizard_creates_a_screen_on_one_page(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-wizard-create/{EVENT_ID}/{ScreenType.CHECK_IN.value}',
        data={
            'answer_accepts_input': LET_CHECK_IN,
            'answer_paged': ONE_PAGE,
            'answer_switch_tournaments': str(tournament.id),
            'answer_columns': '1',  # 2 columns
            # Not on the path of the answers: ignored.
            'answer_paged_pages': 'not a number',
        },
    )
    assert response.status_code == 200
    # Redirected to the screens of the type, with the URL of the screen
    # created to open it.
    assert response.headers['HX-Redirect'] == (
        f'/event/{EVENT_ID}/screens?screen_type_filter={ScreenType.CHECK_IN.value}'
    )
    event = reload_event()
    screens = event.sorted_basic_screens_by_screen_type[ScreenType.CHECK_IN.value]
    assert len(screens) == 1
    stored_screen = screens[0].stored_screen
    assert stored_screen is not None
    assert stored_screen.accepts_input
    assert stored_screen.columns == 2
    assert stored_screen.timer_id is None
    assert [screen_set.tournament.id for screen_set in screens[0].screen_sets] == [
        tournament.id
    ]
    assert not event.families_by_screen_type.get(ScreenType.CHECK_IN.value)
    assert response.headers['SC-Screen-Url'] == (
        f'/view/screen/{EVENT_ID}/{screens[0].uniq_id}'
    )


@pytest.mark.unit
@pytest.mark.parametrize('screen_type', [ScreenType.CHECK_IN, ScreenType.BOARDS])
@pytest.mark.parametrize(
    ('method', 'field', 'number', 'parts'),
    [
        (NUMBER_PER_PAGE, 'answer_paged_number', 10, None),
        (PAGES, 'answer_paged_pages', None, 3),
    ],
)
def test_the_wizard_creates_a_paged_screen(
    http: TestClient,
    tournament: StoredTournament,
    screen_type: ScreenType,
    method: str,
    field: str,
    number: int | None,
    parts: int | None,
):
    # The first option of the first question (showing, not taking input)
    # leads to the layout questions in both wizards (the event is not a team
    # event: no question on the matches).
    response = http.post(
        f'/screen-wizard-create/{EVENT_ID}/{screen_type.value}',
        data={
            'answer_accepts_input': SHOW_STATUS,
            'answer_paged': SEVERAL_PAGES,
            'answer_paged_tournament': str(tournament.id),
            'answer_paged_method': method,
            field: str(number or parts),
            'answer_columns': '1',  # 2 columns
        },
    )
    assert response.status_code == 200
    event = reload_event()
    families = event.families_by_screen_type[screen_type.value]
    assert len(families) == 1
    stored_family = families[0].stored_family
    assert not stored_family.accepts_input
    assert stored_family.tournament_id == tournament.id
    assert stored_family.number == number
    assert stored_family.parts == parts
    assert stored_family.columns == 2
    assert not event.sorted_basic_screens_by_screen_type[screen_type.value]


@pytest.mark.unit
def test_the_wizard_creates_a_boards_screen_taking_results(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-wizard-create/{EVENT_ID}/{ScreenType.BOARDS.value}',
        data={
            'answer_accepts_input': ENTER_RESULTS,
            'answer_paged': ONE_PAGE,
            'answer_switch_tournaments': str(tournament.id),
            'answer_columns': '0',  # 1 column
        },
    )
    assert response.status_code == 200
    assert response.headers['HX-Redirect'] == (
        f'/event/{EVENT_ID}/screens?screen_type_filter={ScreenType.BOARDS.value}'
    )
    event = reload_event()
    screens = event.sorted_basic_screens_by_screen_type[ScreenType.BOARDS.value]
    assert len(screens) == 1
    stored_screen = screens[0].stored_screen
    assert stored_screen is not None
    assert stored_screen.accepts_input
    assert not stored_screen.boards_hide_players
    assert stored_screen.columns == 1
    assert [screen_set.tournament.id for screen_set in screens[0].screen_sets] == [
        tournament.id
    ]


@pytest.mark.unit
def test_the_wizard_creates_a_players_screen_taking_results(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-wizard-create/{EVENT_ID}/{ScreenType.PLAYERS.value}',
        data={
            'answer_accepts_input': ENTER_RESULTS,
            'answer_show_unpaired': HIDE_UNPAIRED,
            'answer_format': MINIMAL_FORMAT,
            'answer_paged': ONE_PAGE,
            'answer_switch_tournaments': str(tournament.id),
            'answer_columns': '2',  # 3 columns
        },
    )
    assert response.status_code == 200
    event = reload_event()
    screens = event.sorted_basic_screens_by_screen_type[ScreenType.PLAYERS.value]
    assert len(screens) == 1
    stored_screen = screens[0].stored_screen
    assert stored_screen is not None
    assert stored_screen.accepts_input
    assert stored_screen.players_show_unpaired is False
    assert stored_screen.players_player_format == PlayersScreenPlayerFormat.NAME
    assert stored_screen.players_board_format == PlayersScreenBoardFormat.MINIMAL
    assert stored_screen.players_opponent_format == PlayersScreenOpponentFormat.NONE
    assert stored_screen.columns == 3
    # The screen shows.
    response = http.get(f'/view/screen/{EVENT_ID}/{screens[0].uniq_id}')
    assert response.status_code == 200


@pytest.mark.unit
def test_the_wizard_creates_a_paged_players_screen(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-wizard-create/{EVENT_ID}/{ScreenType.PLAYERS.value}',
        data={
            'answer_accepts_input': SHOW_PAIRINGS,
            'answer_show_unpaired': SHOW_UNPAIRED,
            'answer_format': FULL_FORMAT,
            'answer_paged': SEVERAL_PAGES,
            'answer_paged_tournament': str(tournament.id),
            'answer_paged_method': PAGES,
            'answer_paged_pages': '2',
            'answer_columns': '0',
        },
    )
    assert response.status_code == 200
    event = reload_event()
    families = event.families_by_screen_type[ScreenType.PLAYERS.value]
    assert len(families) == 1
    stored_family = families[0].stored_family
    assert not stored_family.accepts_input
    assert stored_family.players_show_unpaired
    assert (
        stored_family.players_player_format
        == PlayersScreenPlayerFormat.NAME_RATING_TYPE_POINTS
    )
    assert stored_family.players_board_format == PlayersScreenBoardFormat.FULL
    assert (
        stored_family.players_opponent_format
        == PlayersScreenOpponentFormat.NAME_RATING_TYPE_POINTS
    )
    assert stored_family.parts == 2


@pytest.mark.unit
def test_the_boards_wizard_asks_for_the_matches_only_in_a_team_event(
    http: TestClient, tournament: StoredTournament, team_round_robin: int
):
    def wizard_html(event_id: str) -> str:
        response = http.get(
            f'/screen-wizard-modal/{event_id}/{ScreenType.BOARDS.value}'
        )
        assert response.status_code == 200
        return response.text

    assert 'screen-wizard-question-hide_players' not in wizard_html(EVENT_ID)
    assert 'screen-wizard-question-hide_players' in wizard_html(TEAM_EVENT_ID)

    response = http.post(
        f'/screen-wizard-create/{TEAM_EVENT_ID}/{ScreenType.BOARDS.value}',
        data={
            'answer_accepts_input': SHOW_PAIRINGS,
            'answer_hide_players': MATCHES_ONLY,
            'answer_paged': ONE_PAGE,
            'answer_switch_tournaments': str(team_round_robin),
            'answer_columns': '0',
        },
    )
    assert response.status_code == 200
    EventLoader.unload_event(TEAM_EVENT_ID)
    event = EventLoader().load_event(TEAM_EVENT_ID)
    screens = event.sorted_basic_screens_by_screen_type[ScreenType.BOARDS.value]
    assert len(screens) == 1
    stored_screen = screens[0].stored_screen
    assert stored_screen is not None
    assert not stored_screen.accepts_input
    assert stored_screen.boards_hide_players


@pytest.mark.unit
def test_the_wizard_comes_back_on_the_question_in_error(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-wizard-create/{EVENT_ID}/{ScreenType.CHECK_IN.value}',
        data={
            'answer_accepts_input': LET_CHECK_IN,
            'answer_paged': SEVERAL_PAGES,
            'answer_paged_tournament': str(tournament.id),
            'answer_paged_method': PAGES,
            'answer_paged_pages': '0',
        },
    )
    assert response.status_code == 200
    assert 'screen-wizard-question-paged_pages' in response.text
    assert 'The value must be at least 1.' in response.text
    event = reload_event()
    assert not event.families_by_screen_type.get(ScreenType.CHECK_IN.value)
