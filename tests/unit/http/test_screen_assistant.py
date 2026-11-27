"""The screen setup assistant.

The assistant opens as a full page on a choice of goals. A goal leads into
the questions of its screen type, ending on the channel questions, and the
answers create in one go the screens (or the paged screen, or one screen
per tournament behind a menu) and, if asked, the channel showing them.
"""

from collections.abc import Iterator

import re

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from data.screens.assistant import assistant_goal, assistant_wizard
from data.pairings.variations import BergerRoundRobinVariation
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredDisplayController, StoredTournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.conftest import TEAM_EVENT_ID

EVENT_ID = 'test-screen-assistant-http'
TOURNAMENT_NAME = 'test-screen-assistant-http-tournament'

# The option indexes of the radio questions of the assistant: the layout
# (a page per tournament comes third, or second for the round-robin grids,
# which never run over several pages; for the input goals, index 1 of
# 'paged' is the pages-in-a-menu option)...
ONE_PAGE = '0'
SEVERAL_PAGES = '1'
PAGE_PER_TOURNAMENT = '2'
GRID_PAGE_PER_TOURNAMENT = '1'
INPUT_PAGES_MENU = '1'
NUMBER_PER_PAGE = '0'
PAGES = '1'
# ... how people move between the pages or the tournaments...
PAGES_ROTATE = '0'
PAGES_MENU = '1'
# ... how the players reach their tournament...
MENU = '0'
SINGLE_PAGE = '1'
# ... and the channel question when the event has none.
NEW_CHANNEL = '0'
NO_CHANNEL = '1'


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
def test_the_assistant_opens_on_the_goals(
    http: TestClient, tournament: StoredTournament
):
    response = http.get(f'/screen-assistant/{EVENT_ID}')
    assert response.status_code == 200
    for goal_id in (
        'check-in',
        'check-in-input',
        'boards',
        'players',
        'results-input',
        'ranking',
    ):
        assert f'screen-assistant-goal-{goal_id}' in response.text


@pytest.mark.unit
def test_a_goal_opens_its_questions(http: TestClient, tournament: StoredTournament):
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=boards')
    assert response.status_code == 200
    assert 'screen-assistant-question-layout' in response.text
    assert 'screen-assistant-question-channel' in response.text
    # The event has no timer: the timer question is not asked.
    assert 'screen-assistant-question-timer' not in response.text
    # The event is not a team event: no question on the matches.
    assert 'screen-assistant-question-hide_players' not in response.text
    # A single tournament: the tournament picks answer themselves, and the
    # first question only opposes one page to several.
    assert 'screen-assistant-question-tournaments' not in response.text
    assert 'screen-assistant-question-paged_tournament' not in response.text
    assert 'screen-assistant-question-split_tournaments' not in response.text
    assert 'On one page, or over several pages?' in response.text
    assert 'Several tournaments, one page each' not in response.text

    # The same for the input goals: their tournament and navigation
    # questions are skipped.
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=results-input')
    assert response.status_code == 200
    assert 'screen-assistant-question-tournaments' not in response.text
    assert 'screen-assistant-question-nav' not in response.text
    assert 'screen-assistant-question-paged' in response.text

    # An unknown goal is a 404, redirected to the error page.
    response = http.get(
        f'/screen-assistant/{EVENT_ID}?goal=unknown', follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers['location'] == '/error/404'


@pytest.mark.unit
def test_the_boards_goal_asks_for_the_matches_only_in_a_team_event(
    http: TestClient, tournament: StoredTournament, team_round_robin: int
):
    response = http.get(f'/screen-assistant/{TEAM_EVENT_ID}?goal=boards')
    assert response.status_code == 200
    assert 'screen-assistant-question-hide_players' in response.text


@pytest.mark.unit
def test_the_assistant_creates_a_screen_on_one_page(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'check-in',
            'answer_layout': ONE_PAGE,
            'answer_tournaments': str(tournament.id),
            'answer_columns': '1',  # 2 columns
            'answer_channel': NO_CHANNEL,
            # Not on the path of the answers: ignored.
            'answer_paged_pages': 'not a number',
        },
    )
    assert response.status_code == 200
    event = reload_event()
    screens = event.sorted_basic_screens_by_screen_type[ScreenType.CHECK_IN.value]
    assert len(screens) == 1
    # Redirected to the screens tab, scrolling to the screen created.
    assert response.headers['HX-Redirect'] == (
        f'/event/{EVENT_ID}/screens?scroll_to={screens[0].id}'
    )
    stored_screen = screens[0].stored_screen
    assert stored_screen is not None
    assert not stored_screen.accepts_input
    assert stored_screen.columns == 2
    assert stored_screen.timer_id is None
    assert [screen_set.tournament.id for screen_set in screens[0].screen_sets] == [
        tournament.id
    ]
    assert not event.families_by_screen_type.get(ScreenType.CHECK_IN.value)
    assert not event.display_controllers_by_id


@pytest.mark.unit
@pytest.mark.parametrize(
    ('method', 'field', 'answer', 'number', 'parts'),
    [
        # 10 rows over 2 columns: 20 players on each page.
        (NUMBER_PER_PAGE, 'answer_paged_number', 10, 20, None),
        (PAGES, 'answer_paged_pages', 3, None, 3),
    ],
)
def test_the_assistant_creates_a_paged_screen(
    http: TestClient,
    tournament: StoredTournament,
    method: str,
    field: str,
    answer: int,
    number: int | None,
    parts: int | None,
):
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'players',
            'answer_show_unpaired': '0',  # yes
            'answer_format': '0',  # full
            'answer_layout': SEVERAL_PAGES,
            'answer_paged_tournament': str(tournament.id),
            'answer_paged_nav': PAGES_ROTATE,
            'answer_paged_method': method,
            field: str(answer),
            'answer_columns': '1',  # 2 columns
            'answer_channel': NO_CHANNEL,
        },
    )
    assert response.status_code == 200
    event = reload_event()
    families = event.families_by_screen_type[ScreenType.PLAYERS.value]
    assert len(families) == 1
    # Redirected to the screens tab, scrolling to the paged screen created.
    assert response.headers['HX-Redirect'] == (
        f'/event/{EVENT_ID}/screens?scroll_to=family-{families[0].id}'
    )
    stored_family = families[0].stored_family
    assert not stored_family.accepts_input
    assert stored_family.players_show_unpaired
    assert stored_family.tournament_id == tournament.id
    assert stored_family.number == number
    assert stored_family.parts == parts
    assert stored_family.columns == 2
    assert not event.sorted_basic_screens_by_screen_type[ScreenType.PLAYERS.value]


@pytest.mark.unit
def test_the_assistant_creates_a_paged_screen_behind_a_page_menu(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'check-in',
            'answer_layout': SEVERAL_PAGES,
            'answer_paged_tournament': str(tournament.id),
            'answer_paged_nav': PAGES_MENU,
            'answer_paged_method': PAGES,
            'answer_paged_pages': '2',
            'answer_columns': '0',  # 1 column
            'answer_channel': NO_CHANNEL,
        },
    )
    assert response.status_code == 200
    # The page moves on to the menu created to pick the pages.
    assert response.headers['HX-Redirect'].startswith(
        f'/event/{EVENT_ID}/menus?scroll_to='
    )
    event = reload_event()
    families = event.families_by_screen_type[ScreenType.CHECK_IN.value]
    assert len(families) == 1
    menus = list(event.menus_by_id.values())
    assert len(menus) == 1
    assert [family.id for family in menus[0].families] == [families[0].id]


@pytest.mark.unit
def test_the_layout_is_asked_before_the_tournaments(
    http: TestClient, tournament: StoredTournament
):
    """With several tournaments, the first question offers the three
    layouts, the tournaments being picked after it."""
    TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    reload_event()
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=check-in')
    assert response.status_code == 200
    assert 'How do you want to show the tournaments?' in response.text
    assert 'One or more tournaments, on one page' in response.text
    assert 'One tournament, over several pages' in response.text
    assert 'Several tournaments, one page each' in response.text
    assert 'data-first-question="layout"' in response.text
    for question_id in ('tournaments', 'paged_tournament', 'split_tournaments'):
        assert f'screen-assistant-question-{question_id}"' in response.text
    # The input goals still pick the tournaments first.
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=check-in-input')
    assert 'data-first-question="tournaments"' in response.text


@pytest.mark.unit
@pytest.mark.parametrize(
    ('goal', 'answers', 'nav', 'group_name', 'screen_type'),
    [
        # A screen per tournament, shown in turn by a rotator named after
        # what the screens show.
        ('check-in', {}, PAGES_ROTATE, 'Check-in', ScreenType.CHECK_IN),
        (
            'ranking',
            {'answer_ranking_kind': '1'},
            PAGES_ROTATE,
            'Cross-table',
            ScreenType.RANKING,
        ),
        # Or picked in a menu.
        (
            'players',
            {'answer_show_unpaired': '1', 'answer_format': '2'},
            PAGES_MENU,
            'Pairings by player',
            ScreenType.PLAYERS,
        ),
    ],
)
def test_the_assistant_creates_a_screen_per_tournament(
    http: TestClient,
    tournament: StoredTournament,
    goal: str,
    answers: dict[str, str],
    nav: str,
    group_name: str,
    screen_type: ScreenType,
):
    other = TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    reload_event()
    data = {
        'goal': goal,
        **answers,
        'answer_layout': PAGE_PER_TOURNAMENT,
        'answer_split_tournaments': f'{tournament.id};{other.id}',
        'answer_split_nav': nav,
        'answer_columns': '0',
        'answer_channel': NEW_CHANNEL,
        'answer_channel_name': 'Main hall',
    }
    # The summary names the rotator or the menu as it will be created.
    summary = re.findall(
        r'<li>(.*?)</li>',
        http.post(f'/screen-assistant-summary/{EVENT_ID}', data=data).text,
    )
    group_kind = 'rotator' if nav == PAGES_ROTATE else 'menu'
    group_line = (
        f'Create a rotator named “{group_name}” showing them in turn'
        if nav == PAGES_ROTATE
        else f'Create a menu named “{group_name}” to pick the tournament'
    )
    assert summary[2] == (
        f'{group_line} and mark it as designed for the channel “Main hall”.'
    )
    assert summary[3] == f'Show the new {group_kind} on the channel “Main hall”.'
    response = http.post(f'/screen-assistant-create/{EVENT_ID}', data=data)
    assert response.is_success
    event = reload_event()
    screens = event.sorted_basic_screens_by_screen_type[screen_type.value]
    assert len(screens) == 2
    assert sorted(
        screen_set.tournament.id
        for screen in screens
        for screen_set in screen.screen_sets
    ) == sorted([tournament.id, other.id])
    channel = next(iter(event.display_controllers_by_id.values()))
    if nav == PAGES_ROTATE:
        rotator = next(iter(event.rotators_by_id.values()))
        assert rotator.name == group_name
        assert [screen.id for screen in rotator.rotating_screens] == [
            screen.id for screen in screens
        ]
        assert channel.rotator_id == rotator.id
        assert response.headers['HX-Redirect'] == (
            f'/event/{EVENT_ID}/rotators?scroll_to={rotator.id}'
        )
        assert not event.menus_by_id
    else:
        menu = next(iter(event.menus_by_id.values()))
        assert menu.name == group_name
        assert {screen.id for screen in menu.resolved_screens()} == {
            screen.id for screen in screens
        }
        assert channel.menu_id == menu.id
        assert not event.rotators_by_id
    # The answers of the goal are set on every screen.
    for screen in screens:
        stored_screen = screen.stored_screen
        assert stored_screen is not None
        if goal == 'ranking':
            assert stored_screen.ranking_crosstable
        if goal == 'players':
            assert not stored_screen.players_show_unpaired


@pytest.mark.unit
def test_a_page_per_tournament_needs_two_tournaments(
    http: TestClient, tournament: StoredTournament
):
    other = TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    reload_event()
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'boards',
            'answer_layout': PAGE_PER_TOURNAMENT,
            'answer_split_tournaments': str(other.id),
            'answer_split_nav': PAGES_ROTATE,
            'answer_columns': '0',
            'answer_channel': NO_CHANNEL,
        },
    )
    assert response.status_code == 200
    assert 'Please choose at least 2 tournaments.' in response.text
    event = reload_event()
    assert not event.sorted_basic_screens_by_screen_type[ScreenType.BOARDS.value]


@pytest.mark.unit
def test_the_assistant_creates_an_input_screen_and_its_channel(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'results-input',
            # A single tournament: the navigation question is skipped.
            'answer_tournaments': str(tournament.id),
            'answer_paged': ONE_PAGE,
            'answer_columns': '0',  # 1 column
            'answer_channel': NEW_CHANNEL,
            'answer_channel_name': 'Main hall',
        },
    )
    assert response.status_code == 200
    event = reload_event()
    screens = event.sorted_basic_screens_by_screen_type[ScreenType.BOARDS.value]
    assert len(screens) == 1
    stored_screen = screens[0].stored_screen
    assert stored_screen is not None
    assert stored_screen.accepts_input
    assert stored_screen.columns == 1
    # The channel is created, the screen designed for it, and the channel
    # shows it.
    channels = list(event.display_controllers_by_id.values())
    assert len(channels) == 1
    assert channels[0].name == 'Main hall'
    assert channels[0].screen_id == screens[0].id
    assert channels[0].stored_display_controller.item_screen_ids == [screens[0].id]


@pytest.mark.unit
def test_the_assistant_creates_one_screen_per_tournament_behind_a_menu(
    http: TestClient, tournament: StoredTournament
):
    other = TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'check-in-input',
            'answer_tournaments': f'{tournament.id};{other.id}',
            # Each tournament is a page of the menu: no pages question.
            'answer_nav': MENU,
            'answer_columns': '0',  # 1 column
            'answer_channel': NEW_CHANNEL,
            'answer_channel_name': 'iPad',
        },
    )
    assert response.status_code == 200
    # The page moves on to the menu created.
    assert response.headers['HX-Redirect'].startswith(
        f'/event/{EVENT_ID}/menus?scroll_to='
    )
    event = reload_event()
    screens = event.sorted_basic_screens_by_screen_type[ScreenType.CHECK_IN.value]
    assert len(screens) == 2
    assert all(
        screen.stored_screen is not None and screen.stored_screen.accepts_input
        for screen in screens
    )
    assert sorted(
        screen_set.tournament.id
        for screen in screens
        for screen_set in screen.screen_sets
    ) == sorted([tournament.id, other.id])
    # One menu pointing to both screens, designed for the channel and shown
    # by it, named after the goal.
    menus = list(event.menus_by_id.values())
    assert len(menus) == 1
    assert menus[0].name == 'Check-in'
    assert {screen.id for screen in menus[0].resolved_screens()} == {
        screen.id for screen in screens
    }
    channels = list(event.display_controllers_by_id.values())
    assert len(channels) == 1
    assert channels[0].name == 'iPad'
    assert channels[0].menu_id == menus[0].id
    assert channels[0].screen_id is None
    assert channels[0].stored_display_controller.item_menu_ids == [menus[0].id]


@pytest.mark.unit
def test_the_assistant_creates_a_paged_input_screen_behind_a_page_menu(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'results-input',
            # A single tournament, over several pages picked in a menu.
            'answer_tournaments': str(tournament.id),
            'answer_paged': INPUT_PAGES_MENU,
            'answer_paged_method': PAGES,
            'answer_paged_pages': '2',
            'answer_columns': '0',  # 1 column
            'answer_channel': NO_CHANNEL,
        },
    )
    assert response.status_code == 200
    assert response.headers['HX-Redirect'].startswith(
        f'/event/{EVENT_ID}/menus?scroll_to='
    )
    event = reload_event()
    families = event.families_by_screen_type[ScreenType.BOARDS.value]
    assert len(families) == 1
    assert families[0].stored_family.accepts_input
    assert families[0].stored_family.parts == 2
    assert families[0].tournament.id == tournament.id
    # The menu is named after the goal, not after the screen type (these
    # are boards screens).
    menus = list(event.menus_by_id.values())
    assert len(menus) == 1
    assert menus[0].name == 'Result entry'
    assert [family.id for family in menus[0].families] == [families[0].id]


@pytest.mark.unit
def test_the_assistant_offers_the_existing_channels(
    http: TestClient, tournament: StoredTournament
):
    # A first run creates a channel...
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'check-in',
            'answer_layout': ONE_PAGE,
            'answer_tournaments': str(tournament.id),
            'answer_columns': '0',
            'answer_channel': NEW_CHANNEL,
            'answer_channel_name': 'Main hall',
        },
    )
    assert response.status_code == 200
    reload_event()
    # ... which the next run offers, with what it shows.
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=boards')
    assert response.status_code == 200
    assert 'Main hall' in response.text
    assert 'This channel is currently showing' in response.text
    # The same name is refused for another channel.
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'boards',
            'answer_layout': ONE_PAGE,
            'answer_tournaments': str(tournament.id),
            'answer_columns': '0',
            'answer_channel': '1',  # a new channel (after the existing one)
            'answer_channel_name': 'Main hall',
        },
    )
    assert response.status_code == 200
    assert 'This name is already used.' in response.text
    event = reload_event()
    assert len(event.display_controllers_by_id) == 1
    assert not event.sorted_basic_screens_by_screen_type[ScreenType.BOARDS.value]


@pytest.mark.unit
@pytest.mark.parametrize(
    ('nav', 'item'),
    [(PAGES_MENU, 'menu'), (PAGES_ROTATE, 'rotator'), (None, 'screen')],
)
def test_the_channel_question_names_what_is_designed_for_the_channel(
    http: TestClient, tournament: StoredTournament, nav: str | None, item: str
):
    other = TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    with EventDatabase(EVENT_ID, write=True) as database:
        database.add_stored_display_controller(
            StoredDisplayController(id=None, name='Projector')
        )
    reload_event()
    data = {'goal': 'boards', 'answer_columns': '0'} | (
        {'answer_layout': ONE_PAGE, 'answer_tournaments': str(tournament.id)}
        if nav is None
        else {
            'answer_layout': PAGE_PER_TOURNAMENT,
            'answer_split_tournaments': f'{tournament.id};{other.id}',
            'answer_split_nav': nav,
        }
    )
    # The question, asked of the server once shown, names the menu or the
    # rotator when one is created (what the channel is designed for)...
    url = f'/screen-assistant-text/{EVENT_ID}?question=channel'
    assert http.post(url, data=data).text == (
        f'Which channel is this {item} designed for?'
    )
    assert http.post(f'{url}&part=help', data=data).text.startswith(
        f'The {item} is marked as designed for the channel you pick.'
    )
    # ... and so do the helps of the new channel and no channel answers.
    assert http.post(f'{url}&option=1&part=help', data=data).text == (
        f'The {item} is marked as designed for this new channel, which shows it.'
    )
    assert http.post(f'{url}&option=2&part=help', data=data).text == (
        f'You will need to select the {item} on your display.'
    )


@pytest.mark.unit
def test_an_existing_channel_is_not_switched_to_the_new_screen(
    http: TestClient, tournament: StoredTournament
):
    # A first run creates a channel, showing the screen created...
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'check-in',
            'answer_layout': ONE_PAGE,
            'answer_tournaments': str(tournament.id),
            'answer_columns': '0',
            'answer_channel': NEW_CHANNEL,
            'answer_channel_name': 'Main hall',
        },
    )
    assert response.status_code == 200
    event = reload_event()
    check_in_screens = event.sorted_basic_screens_by_screen_type[
        ScreenType.CHECK_IN.value
    ]
    assert len(check_in_screens) == 1
    channel = next(iter(event.display_controllers_by_id.values()))
    # ... which the next run asks to switch, saying what it shows.
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=boards')
    assert response.status_code == 200
    assert 'Do you want the channel “Main hall” to show the new screen?' in (
        response.text
    )
    assert f'currently shows “{check_in_screens[0].name}”' in response.text
    # Picking that channel without switching it marks the new screen as
    # designed for it, but the channel keeps showing the first screen.
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'boards',
            'answer_layout': ONE_PAGE,
            'answer_tournaments': str(tournament.id),
            'answer_columns': '0',
            'answer_channel': '0',  # the existing channel
            f'answer_channel_switch_{channel.id}': '1',  # No
        },
    )
    assert response.status_code == 200
    event = reload_event()
    boards_screens = event.sorted_basic_screens_by_screen_type[ScreenType.BOARDS.value]
    assert len(boards_screens) == 1
    channels = list(event.display_controllers_by_id.values())
    assert len(channels) == 1
    assert channels[0].screen_id == check_in_screens[0].id
    assert boards_screens[0].id in channels[0].stored_display_controller.item_screen_ids


@pytest.mark.unit
def test_an_existing_channel_is_switched_to_the_new_menu_when_asked(
    http: TestClient, tournament: StoredTournament
):
    other = TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    with EventDatabase(EVENT_ID, write=True) as database:
        channel = database.add_stored_display_controller(
            StoredDisplayController(id=None, name='Projector')
        )
    assert channel.id is not None
    event = reload_event()
    # A channel showing nothing is switched by default.
    goal = assistant_goal(event, 'check-in-input')
    assert goal is not None
    question = assistant_wizard(event, goal).questions[f'channel_switch_{channel.id}']
    assert question.default_form_value == '0'
    assert question.help == 'The channel “Projector” currently shows nothing.'
    # The question and the answer switching it name what is created, asked
    # of the server once the question is shown: the screen until then...
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=check-in-input')
    assert 'Do you want the channel “Projector” to show the new screen?' in (
        response.text
    )
    assert 'Yes, show the new screen on this channel' in response.text
    question_url = (
        f'/screen-assistant-text/{EVENT_ID}?question=channel_switch_{channel.id}'
    )
    assert question_url in response.text
    assert f'{question_url}&option=0' in response.text
    # ... the menu for one screen per tournament behind a menu...
    data = {
        'goal': 'check-in-input',
        'answer_tournaments': f'{tournament.id};{other.id}',
        'answer_nav': MENU,
        'answer_columns': '0',
        'answer_channel': '0',  # the existing channel
    }
    response = http.post(question_url, data=data)
    assert response.text == 'Do you want the channel “Projector” to show the new menu?'
    response = http.post(f'{question_url}&option=0', data=data)
    assert response.text == 'Yes, show the new menu on this channel'
    # ... and the screen for a single tournament.
    response = http.post(
        f'{question_url}&option=0',
        data=data
        | {'answer_tournaments': str(tournament.id), 'answer_paged': ONE_PAGE},
    )
    assert response.text == 'Yes, show the new screen on this channel'
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'check-in-input',
            'answer_tournaments': f'{tournament.id};{other.id}',
            'answer_nav': MENU,
            'answer_columns': '0',
            'answer_channel': '0',  # the existing channel
            f'answer_channel_switch_{channel.id}': '0',  # Yes
        },
    )
    assert response.status_code == 200
    event = reload_event()
    menus = list(event.menus_by_id.values())
    assert len(menus) == 1
    # The channel shows the menu, which is designed for it.
    switched = event.display_controllers_by_id[channel.id]
    assert switched.menu_id == menus[0].id
    assert switched.screen_id is None
    assert switched.stored_display_controller.item_menu_ids == [menus[0].id]


@pytest.mark.unit
def test_the_goals_point_at_the_other_screen_types(
    http: TestClient, tournament: StoredTournament
):
    response = http.get(f'/screen-assistant/{EVENT_ID}')
    assert response.status_code == 200
    # The types the assistant has no goal for are listed, to be created
    # directly from the standard forms.
    assert 'Other kinds of screens exist too' in response.text
    assert 'Image' in response.text
    assert 'Round-robin grid' in response.text


@pytest.mark.unit
def test_the_summary_says_what_will_be_created(
    http: TestClient, tournament: StoredTournament
):
    other = TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    response = http.post(
        f'/screen-assistant-summary/{EVENT_ID}',
        data={
            'goal': 'results-input',
            'answer_tournaments': f'{tournament.id};{other.id}',
            'answer_nav': MENU,
            'answer_columns': '0',
            'answer_channel': NEW_CHANNEL,
            'answer_channel_name': 'Main hall',
        },
    )
    assert response.status_code == 200
    # The new channel first, then what is created, the menu designed for
    # the channel, and last the channel showing the menu.
    lines = re.findall(r'<li>(.*?)</li>', response.text)
    assert lines == [
        'Create a new channel named “Main hall”.',
        (
            f'Create one “Result entry” screen per tournament: '
            f'{TOURNAMENT_NAME}, {TOURNAMENT_NAME}-2.'
        ),
        (
            'Create a menu named “Result entry” for the players to pick their tournament '
            'and mark it as designed for the channel “Main hall”.'
        ),
        'Show the new menu on the channel “Main hall”.',
    ]

    # An existing channel not switched: the screen itself is designed for
    # it, with no line for the channel.
    with EventDatabase(EVENT_ID, write=True) as database:
        channel = database.add_stored_display_controller(
            StoredDisplayController(id=None, name='Projector')
        )
    assert channel.id is not None
    reload_event()
    data = {
        'goal': 'ranking',
        'answer_ranking_kind': '0',
        'answer_layout': ONE_PAGE,
        'answer_tournaments': f'{tournament.id};{other.id}',
        'answer_columns': '0',
        # The existing channel comes first among the options.
        'answer_channel': '0',
        f'answer_channel_switch_{channel.id}': '1',  # No
    }
    response = http.post(f'/screen-assistant-summary/{EVENT_ID}', data=data)
    assert re.findall(r'<li>(.*?)</li>', response.text) == [
        (
            f'Create a “Standings” screen for tournaments {TOURNAMENT_NAME}, '
            f'{TOURNAMENT_NAME}-2 and mark it as designed for the channel “Projector”.'
        ),
    ]
    # Switched, the channel says it shows the screen.
    response = http.post(
        f'/screen-assistant-summary/{EVENT_ID}',
        data=data | {f'answer_channel_switch_{channel.id}': '0'},  # Yes
    )
    assert re.findall(r'<li>(.*?)</li>', response.text) == [
        (
            f'Create a “Standings” screen for tournaments {TOURNAMENT_NAME}, '
            f'{TOURNAMENT_NAME}-2 and mark it as designed for the channel “Projector”.'
        ),
        'Show the new screen on the channel “Projector”.',
    ]


@pytest.mark.unit
def test_the_summary_names_the_menu_as_it_will_be_created(
    http: TestClient, tournament: StoredTournament
):
    other = TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    data = {
        'goal': 'check-in-input',
        'answer_tournaments': f'{tournament.id};{other.id}',
        'answer_nav': MENU,
        'answer_columns': '0',
        'answer_channel': NO_CHANNEL,
    }
    assert http.post(f'/screen-assistant-create/{EVENT_ID}', data=data).is_success
    reload_event()
    # A second run cannot reuse the name: the summary says the name the menu
    # will really get.
    response = http.post(f'/screen-assistant-summary/{EVENT_ID}', data=data)
    assert 'Create a menu named “Check-in (2)”' in response.text
    assert http.post(f'/screen-assistant-create/{EVENT_ID}', data=data).is_success
    event = reload_event()
    assert sorted(menu.name for menu in event.menus_by_id.values()) == [
        'Check-in',
        'Check-in (2)',
    ]


@pytest.mark.unit
def test_the_automatic_name_of_a_screen_stays_short(
    http: TestClient, tournament: StoredTournament
):
    """The name of a screen over many tournaments: their names for one or
    two, "All tournaments" when it shows them all, else the first one and
    how many others."""
    others = [
        TestUtils.create_tournament(
            EVENT_ID, f'{TOURNAMENT_NAME}-{index}', json_file='test-screens'
        )
        for index in range(2, 5)
    ]
    ids = [tournament.id, *(other.id for other in others)]

    def create(tournament_ids: list[int | None]) -> None:
        response = http.post(
            f'/screen-assistant-create/{EVENT_ID}',
            data={
                'goal': 'boards',
                'answer_layout': ONE_PAGE,
                'answer_tournaments': ';'.join(
                    str(tournament_id) for tournament_id in tournament_ids
                ),
                'answer_columns': '0',
                'answer_channel': NO_CHANNEL,
            },
        )
        assert response.is_success

    create(ids[:2])
    create(ids[:3])
    create(ids)
    event = reload_event()
    names = [
        screen.name
        for screen in event.sorted_basic_screens_by_screen_type[ScreenType.BOARDS.value]
    ]
    assert sorted(names) == sorted(
        [
            f'{TOURNAMENT_NAME} / {TOURNAMENT_NAME}-2',
            f'{TOURNAMENT_NAME} and 2 other tournaments',
            'All tournaments',
        ]
    )


@pytest.mark.unit
def test_the_assistant_comes_back_on_the_question_in_error(
    http: TestClient, tournament: StoredTournament
):
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'check-in',
            'answer_layout': SEVERAL_PAGES,
            'answer_paged_tournament': str(tournament.id),
            'answer_paged_nav': PAGES_ROTATE,
            'answer_paged_method': PAGES,
            'answer_paged_pages': '0',
        },
    )
    assert response.status_code == 200
    assert 'screen-assistant-question-paged_pages' in response.text
    assert 'The value must be at least 1.' in response.text
    event = reload_event()
    assert not event.families_by_screen_type.get(ScreenType.CHECK_IN.value)


@pytest.mark.unit
def test_create_and_edit_opens_the_form_of_what_was_created(
    http: TestClient, tournament: StoredTournament
):
    """Create and edit leads to the edit form of the screen when a single
    one is created, even behind a page menu. It is not offered when a screen
    per tournament is created behind a menu or a rotator, which then opens
    with no form."""

    def create(data: dict[str, str]) -> str:
        response = http.post(
            f'/screen-assistant-create/{EVENT_ID}',
            data=data | {'answer_columns': '0', 'answer_channel': NO_CHANNEL},
        )
        assert response.is_success
        return response.headers['HX-Redirect']

    redirect = create(
        {
            'goal': 'check-in',
            'answer_layout': ONE_PAGE,
            'answer_tournaments': str(tournament.id),
            'edit_after': '1',
        }
    )
    event = reload_event()
    screen = event.sorted_basic_screens_by_screen_type[ScreenType.CHECK_IN.value][0]
    assert redirect == f'/event/{EVENT_ID}/screens?scroll_to={screen.id}&edit=1'

    paged_data = {
        'goal': 'results-input',
        'answer_tournaments': str(tournament.id),
        'answer_paged': INPUT_PAGES_MENU,
        'answer_paged_method': PAGES,
        'answer_paged_pages': '2',
        'answer_columns': '0',
        'answer_channel': NO_CHANNEL,
    }
    paged_summary = http.post(f'/screen-assistant-summary/{EVENT_ID}', data=paged_data)
    assert 'data-editable="true"' in paged_summary.text
    redirect = create(paged_data | {'edit_after': '1'})
    event = reload_event()
    family = event.families_by_screen_type[ScreenType.BOARDS.value][0]
    assert redirect == f'/event/{EVENT_ID}/screens?scroll_to=family-{family.id}&edit=1'

    other = TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    data = {
        'goal': 'check-in-input',
        'answer_tournaments': f'{tournament.id};{other.id}',
        'answer_nav': MENU,
        'answer_columns': '0',
        'answer_channel': NO_CHANNEL,
    }
    summary = http.post(f'/screen-assistant-summary/{EVENT_ID}', data=data).text
    assert 'data-editable="false"' in summary
    redirect = create(data | {'edit_after': '1'})
    event = reload_event()
    menu = next(menu for menu in event.menus_by_id.values() if menu.name == 'Check-in')
    assert redirect == f'/event/{EVENT_ID}/menus?scroll_to={menu.id}'

    # The tabs then open the edit form.
    response = http.get(f'/event/{EVENT_ID}/screens?scroll_to={screen.id}&edit=1')
    assert f'/screen-modal/update/{EVENT_ID}/{screen.id}' in response.text
    response = http.get(
        f'/event/{EVENT_ID}/screens?scroll_to=family-{family.id}&edit=1'
    )
    assert f'/family-modal/update/{EVENT_ID}/{family.id}' in response.text


@pytest.mark.unit
def test_the_standings_goal_offers_the_cross_table_and_the_grid(
    http: TestClient, tournament: StoredTournament
):
    """The standings goal asks what to show: the ranking, the cross-table,
    or — once there is a round robin — the round-robin grid, which is then
    no longer listed among the kinds of screens to create directly."""
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=ranking')
    assert 'The cross-table' in response.text
    assert 'The round-robin grid' not in response.text
    assert 'Round-robin grid' in http.get(f'/screen-assistant/{EVENT_ID}').text

    # No players imported: the import would bring its own pairing system.
    round_robin = TestUtils.create_tournament(
        EVENT_ID,
        f'{TOURNAMENT_NAME}-rr',
        overrides={'pairing': BergerRoundRobinVariation.static_id()},
    )
    reload_event()
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=ranking')
    assert 'The round-robin grid' in response.text
    assert 'Other kinds of screens exist too: Last results, Image.' in (
        http.get(f'/screen-assistant/{EVENT_ID}').text
    )

    # The cross-table: a ranking screen with the switch on.
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'ranking',
            'answer_ranking_kind': '1',
            'answer_layout': ONE_PAGE,
            'answer_tournaments': str(tournament.id),
            'answer_columns': '0',
            'answer_channel': NO_CHANNEL,
        },
    )
    assert response.is_success
    # The round-robin grid, of the single round robin, by rank.
    data = {
        'goal': 'ranking',
        'answer_ranking_kind': '2',
        'answer_grid_order': '1',
        'answer_channel': NO_CHANNEL,
    }
    summary = http.post(f'/screen-assistant-summary/{EVENT_ID}', data=data).text
    assert (
        f'Create a “Round-robin grid” screen for tournaments {TOURNAMENT_NAME}-rr.'
    ) in summary
    assert http.post(f'/screen-assistant-create/{EVENT_ID}', data=data).is_success
    event = reload_event()
    rankings = event.sorted_basic_screens_by_screen_type[ScreenType.RANKING.value]
    assert len(rankings) == 1
    assert rankings[0].stored_screen is not None
    assert rankings[0].stored_screen.ranking_crosstable
    grids = event.sorted_basic_screens_by_screen_type[ScreenType.ROUND_ROBIN_GRID.value]
    assert len(grids) == 1
    assert grids[0].stored_screen is not None
    assert grids[0].stored_screen.round_robin_grid_by_rank
    assert [screen_set.tournament.id for screen_set in grids[0].screen_sets] == [
        round_robin.id
    ]


@pytest.mark.unit
def test_short_answers_are_put_in_words(http: TestClient, tournament: StoredTournament):
    """The answers listed beside the questions say what they answer: a bare
    Yes or a number would not."""
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=players')
    assert 'data-summary="Unpaired players shown"' in response.text
    assert 'data-summary="Unpaired players hidden"' in response.text
    assert 'data-summary="Format: Full"' in response.text
    assert 'data-summary="{answer} pages"' in response.text
    assert 'data-summary="{answer} rows per page"' in response.text


@pytest.mark.unit
@pytest.mark.parametrize(
    ('split', 'grids', 'rotators', 'menus'),
    [
        # All the grids on one page.
        (None, 1, 0, 0),
        # One page per grid, turning by themselves: a rotator.
        (PAGES_ROTATE, 2, 1, 0),
        # One page per grid, picked in a menu.
        (PAGES_MENU, 2, 0, 1),
    ],
)
def test_several_round_robin_grids_on_one_page_or_a_page_each(
    http: TestClient,
    tournament: StoredTournament,
    split: str | None,
    grids: int,
    rotators: int,
    menus: int,
):
    """With several round robins, the standings goal asks whether their
    grids share one page or take a page each, shown in turn by a rotator or
    picked in a menu."""
    round_robins = [
        TestUtils.create_tournament(
            EVENT_ID,
            f'{TOURNAMENT_NAME}-rr-{index}',
            overrides={'pairing': BergerRoundRobinVariation.static_id()},
        )
        for index in (1, 2)
    ]
    reload_event()
    response = http.get(f'/screen-assistant/{EVENT_ID}?goal=ranking')
    assert 'screen-assistant-question-grid_layout' in response.text
    # A grid never runs over several pages.
    assert 'screen-assistant-question-grid_paged_tournament' not in response.text
    round_robin_ids = ';'.join(str(round_robin.id) for round_robin in round_robins)
    data = {
        'goal': 'ranking',
        'answer_ranking_kind': '2',
        'answer_grid_order': '0',
        'answer_channel': NO_CHANNEL,
    }
    if split is None:
        data |= {
            'answer_grid_layout': ONE_PAGE,
            'answer_grid_tournaments': round_robin_ids,
        }
    else:
        data |= {
            'answer_grid_layout': GRID_PAGE_PER_TOURNAMENT,
            'answer_grid_split_tournaments': round_robin_ids,
            'answer_grid_split_nav': split,
        }
    summary = http.post(f'/screen-assistant-summary/{EVENT_ID}', data=data).text
    if rotators:
        assert (
            'Create a rotator named “Round-robin grids” showing them in turn.'
            in summary
        )
    if menus:
        assert (
            'Create a menu named “Round-robin grids” to pick the tournament.' in summary
        )
    response = http.post(f'/screen-assistant-create/{EVENT_ID}', data=data)
    assert response.is_success
    event = reload_event()
    created = event.sorted_basic_screens_by_screen_type[
        ScreenType.ROUND_ROBIN_GRID.value
    ]
    assert len(created) == grids
    assert len(event.rotators_by_id) == rotators
    assert len(event.menus_by_id) == menus
    if rotators:
        rotator = next(iter(event.rotators_by_id.values()))
        assert rotator.name == 'Round-robin grids'
        assert {screen.id for screen in rotator.rotating_screens} == {
            screen.id for screen in created
        }
        assert response.headers['HX-Redirect'] == (
            f'/event/{EVENT_ID}/rotators?scroll_to={rotator.id}'
        )
    if menus:
        menu = next(iter(event.menus_by_id.values()))
        assert {screen.id for screen in menu.resolved_screens()} == {
            screen.id for screen in created
        }
