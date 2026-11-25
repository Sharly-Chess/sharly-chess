"""The screen setup assistant.

The assistant opens as a full page on a choice of goals. A goal leads into
the questions of its screen type, ending on the channel questions, and the
answers create in one go the screens (or the paged screen, or one screen
per tournament behind a menu) and, if asked, the channel showing them.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from data.pairings.variations import BergerRoundRobinVariation
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.conftest import TEAM_EVENT_ID

EVENT_ID = 'test-screen-assistant-http'
TOURNAMENT_NAME = 'test-screen-assistant-http-tournament'

# The option indexes of the radio questions of the assistant: the layout
# (for the input goals, index 1 of 'paged' is the pages-in-a-menu option)...
ONE_PAGE = '0'
SEVERAL_PAGES = '1'
INPUT_PAGES_MENU = '1'
NUMBER_PER_PAGE = '0'
PAGES = '1'
# ... how people move between the pages...
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
    assert 'screen-assistant-question-paged' in response.text
    assert 'screen-assistant-question-channel' in response.text
    # The event has no timer: the timer question is not asked.
    assert 'screen-assistant-question-timer' not in response.text
    # The event is not a team event: no question on the matches.
    assert 'screen-assistant-question-hide_players' not in response.text
    # A single tournament: the tournament picks answer themselves, and the
    # first question only opposes one page to several.
    assert 'screen-assistant-question-switch_tournaments' not in response.text
    assert 'screen-assistant-question-paged_tournament' not in response.text
    assert 'On one page, or over several pages?' in response.text

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
            'answer_paged': ONE_PAGE,
            'answer_switch_tournaments': str(tournament.id),
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
            'answer_paged': SEVERAL_PAGES,
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
            'answer_paged': SEVERAL_PAGES,
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
    # The channel is created and the screen designed for it, but the
    # channel is not switched to it.
    channels = list(event.display_controllers_by_id.values())
    assert len(channels) == 1
    assert channels[0].name == 'Main hall'
    assert channels[0].screen_id is None
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
    # One menu pointing to both screens, designed for the channel, named
    # after the goal.
    menus = list(event.menus_by_id.values())
    assert len(menus) == 1
    assert menus[0].name == 'Check-in'
    assert {screen.id for screen in menus[0].resolved_screens()} == {
        screen.id for screen in screens
    }
    channels = list(event.display_controllers_by_id.values())
    assert len(channels) == 1
    assert channels[0].name == 'iPad'
    assert channels[0].menu_id is None
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
            'answer_paged': ONE_PAGE,
            'answer_switch_tournaments': str(tournament.id),
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
    assert 'Currently showing' in response.text
    # The same name is refused for another channel.
    response = http.post(
        f'/screen-assistant-create/{EVENT_ID}',
        data={
            'goal': 'boards',
            'answer_paged': ONE_PAGE,
            'answer_switch_tournaments': str(tournament.id),
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
    assert (
        f'One “Result entry” screen per tournament: '
        f'{TOURNAMENT_NAME}, {TOURNAMENT_NAME}-2.'
    ) in response.text
    assert (
        'A menu named “Result entry” for the players to pick their tournament.'
    ) in response.text
    assert (
        'A new channel named “Main hall”, with everything designed for it.'
    ) in response.text


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
    assert 'A menu named “Check-in (2)”' in response.text
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
                'answer_paged': ONE_PAGE,
                'answer_switch_tournaments': ';'.join(
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
            'answer_paged': SEVERAL_PAGES,
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
    one is created, even behind a page menu, and to the menu leading to
    the screens when there are several."""

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
            'answer_paged': ONE_PAGE,
            'answer_switch_tournaments': str(tournament.id),
            'edit_after': '1',
        }
    )
    event = reload_event()
    screen = event.sorted_basic_screens_by_screen_type[ScreenType.CHECK_IN.value][0]
    assert redirect == f'/event/{EVENT_ID}/screens?scroll_to={screen.id}&edit=1'

    redirect = create(
        {
            'goal': 'results-input',
            'answer_tournaments': str(tournament.id),
            'answer_paged': INPUT_PAGES_MENU,
            'answer_paged_method': PAGES,
            'answer_paged_pages': '2',
            'edit_after': '1',
        }
    )
    event = reload_event()
    family = event.families_by_screen_type[ScreenType.BOARDS.value][0]
    assert redirect == f'/event/{EVENT_ID}/screens?scroll_to=family-{family.id}&edit=1'

    other = TestUtils.create_tournament(
        EVENT_ID, f'{TOURNAMENT_NAME}-2', json_file='test-screens'
    )
    redirect = create(
        {
            'goal': 'check-in-input',
            'answer_tournaments': f'{tournament.id};{other.id}',
            'answer_nav': MENU,
            'edit_after': '1',
        }
    )
    event = reload_event()
    menu = next(menu for menu in event.menus_by_id.values() if menu.name == 'Check-in')
    assert redirect == f'/event/{EVENT_ID}/menus?scroll_to={menu.id}&edit=1'

    # The tabs then open the edit form.
    response = http.get(f'/event/{EVENT_ID}/screens?scroll_to={screen.id}&edit=1')
    assert f'/screen-modal/update/{EVENT_ID}/{screen.id}' in response.text
    response = http.get(
        f'/event/{EVENT_ID}/screens?scroll_to=family-{family.id}&edit=1'
    )
    assert f'/family-modal/update/{EVENT_ID}/{family.id}' in response.text
    response = http.get(f'/event/{EVENT_ID}/menus?scroll_to={menu.id}&edit=1')
    assert f'/menu-modal/update/{EVENT_ID}/{menu.id}' in response.text


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
            'answer_paged': ONE_PAGE,
            'answer_switch_tournaments': str(tournament.id),
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
    assert (f'A “Round-robin grid” screen covering {TOURNAMENT_NAME}-rr.') in summary
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
        ('0', 1, 0, 0),
        # One page per grid, turning by themselves: a rotator.
        ('1', 2, 1, 0),
        # One page per grid, picked in a menu.
        ('2', 2, 0, 1),
    ],
)
def test_several_round_robin_grids_on_one_page_or_a_page_each(
    http: TestClient,
    tournament: StoredTournament,
    split: str,
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
    assert 'screen-assistant-question-grid_split' in response.text
    data = {
        'goal': 'ranking',
        'answer_ranking_kind': '2',
        'answer_grid_tournaments': ';'.join(
            str(round_robin.id) for round_robin in round_robins
        ),
        'answer_grid_split': split,
        'answer_grid_order': '0',
        'answer_channel': NO_CHANNEL,
    }
    summary = http.post(f'/screen-assistant-summary/{EVENT_ID}', data=data).text
    if rotators:
        assert 'A rotator named “Round-robin grids” showing them in turn.' in summary
    if menus:
        assert 'A menu named “Round-robin grids” to pick the grid.' in summary
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
