"""The unrated players' rating of a rating-based tie-break, set in the
tie-break form."""

import re
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from tests.test_config import TestUtils

EVENT_ID = 'test-unrated-rating-form'
RULES_MESSAGE = 'You must confirm that'


@pytest.fixture
def tournament_id(request: pytest.FixtureRequest) -> Iterator[int]:
    """A tournament with one unrated player, or none when the test is
    parametrized with ``tournament_id=False``."""
    yield from _tournament(request)


@pytest.fixture
def tournament_without_estimates_id(request: pytest.FixtureRequest) -> Iterator[int]:
    """A tournament with one unrated player, in an event without the plugin
    that would give them an estimate."""
    yield from _tournament(request, {'enabled_plugins': []})


def _tournament(
    request: pytest.FixtureRequest, event_overrides: dict | None = None
) -> Iterator[int]:
    TestUtils.create_event(EVENT_ID, overrides=event_overrides)
    TestUtils.create_tournament(EVENT_ID, 'tournament')
    with EventDatabase(EVENT_ID, write=True) as database:
        tournament_id = next(iter(database.load_stored_tournaments())).id
        assert tournament_id is not None
        if getattr(request, 'param', True):
            player_id = database.add_stored_player(
                StoredPlayer(id=None, last_name='UNRATED')
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(tournament_id=tournament_id, player_id=player_id)
            )
    yield tournament_id
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def _create(http: TestClient, tournament_id: int, fixed: bool, rules: bool) -> str:
    """Post the form as a browser does: an unticked switch is not sent."""
    data = {
        'type': 'RATING',
        'UNRATED_RATING_MODE': 'FIXED' if fixed else 'ESTIMATED',
        'UNRATED_RATING': '1400' if fixed else '',
    }
    if rules:
        data['ESTIMATED_RATINGS'] = 'on'
    response = http.post(
        f'/tournaments/tie-break/create/{EVENT_ID}/{tournament_id}', data=data
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_the_form_holds_a_single_fixed_rating_field(
    http: TestClient, tournament_id: int
):
    """A browser posts every field of the name; two of them would turn the
    value into a list the form cannot read."""
    modal = http.get(f'/tournaments/tie-break-modal/create/{EVENT_ID}/{tournament_id}')
    assert re.findall(r'name="UNRATED_RATING"', modal.text) == ['name="UNRATED_RATING"']


@pytest.mark.unit
@pytest.mark.parametrize('fixed', [False, True])
def test_the_rules_must_state_how_unrated_players_are_rated(
    http: TestClient, tournament_id: int, fixed: bool
):
    """The message stands under the switch that confirms it."""
    switch_error = re.search(
        r'id="ESTIMATED-RATINGS-error"[^>]*>\s*([^<]*)',
        _create(http, tournament_id, fixed, rules=False),
    )
    assert switch_error is not None
    assert RULES_MESSAGE in switch_error.group(1)
    assert RULES_MESSAGE not in _create(http, tournament_id, fixed, rules=True)


@pytest.mark.unit
@pytest.mark.parametrize('tournament_id', [False], indirect=True)
@pytest.mark.parametrize('fixed', [False, True])
def test_the_rules_need_not_be_confirmed_without_unrated_players(
    http: TestClient, tournament_id: int, fixed: bool
):
    assert RULES_MESSAGE not in _create(http, tournament_id, fixed, rules=False)


def _error(page: str, field_id: str) -> str | None:
    match = re.search(rf'id="{field_id}-error"[^>]*>\s*([^<]*)', page)
    return match.group(1).strip() if match else None


@pytest.mark.unit
def test_players_without_estimates_need_a_fixed_rating(
    http: TestClient, tournament_without_estimates_id: int
):
    """The message stands under the choice that settles it."""
    page = _create(http, tournament_without_estimates_id, fixed=False, rules=True)
    error = _error(page, 'UNRATED-RATING-MODE')
    assert error is not None
    assert 'without estimated ratings' in error


@pytest.mark.unit
def test_a_fixed_rating_for_players_without_estimates_needs_the_rules(
    http: TestClient, tournament_without_estimates_id: int
):
    page = _create(http, tournament_without_estimates_id, fixed=True, rules=False)
    error = _error(page, 'ESTIMATED-RATINGS')
    assert error is not None
    assert RULES_MESSAGE in error
    page = _create(http, tournament_without_estimates_id, fixed=True, rules=True)
    assert _error(page, 'ESTIMATED-RATINGS') is None
    assert _error(page, 'UNRATED-RATING-MODE') is None
