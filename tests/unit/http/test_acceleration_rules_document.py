"""The acceleration rules document, printed for each accelerated system."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.pairings.acceleration import (
    ACCELERATED_SWISS_VARIATIONS,
    AcceleratedSwissVariation,
    CustomAccelerationSetting,
    CustomAccelerationSwissVariation,
    ProgressiveSwissVariation,
)
from data.pairings.settings import AccelerationRule
from data.pairings.variations import StandardSwissVariation, SwissVariation
from database.sqlite.event.event_database import EventDatabase
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-acceleration-rules-http'
TOURNAMENT_NAME = 'test-acceleration-rules-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


def create_tournament(variation: type[SwissVariation]) -> int:
    EVENT.create(json_file='tec-swiss')
    with EventDatabase(EVENT_ID, True) as database:
        stored_tournament = database.load_stored_tournaments()[0]
        stored_tournament.pairing = variation.static_id()
        database.update_stored_tournament(stored_tournament)
    tournament = EVENT.tournament()
    assert tournament.id is not None
    assert isinstance(tournament.pairing_variation, variation)
    return tournament.id


@pytest.fixture
def cleanup() -> Iterator[None]:
    yield
    EVENT.delete()


def print_rules(http: TestClient, tournament_id: int) -> str:
    response = http.get(
        f'/document-view/{EVENT_ID}/acceleration-rules',
        params={'options': f'tournament={tournament_id}'},
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
@pytest.mark.parametrize(
    'variation', ACCELERATED_SWISS_VARIATIONS, ids=lambda v: v.variation_id()
)
def test_the_rules_of_every_accelerated_system_print(
    http: TestClient, cleanup: None, variation: type[AcceleratedSwissVariation]
):
    tournament_id = create_tournament(variation)
    markup = print_rules(http, tournament_id)
    tournament = EVENT.tournament()
    assert isinstance(tournament.pairing_variation, AcceleratedSwissVariation)
    assert tournament.pairing_variation.name in markup
    for paragraph in tournament.pairing_variation.rules_description(tournament):
        assert paragraph in markup
    assert 'ALYX' in markup


@pytest.mark.unit
def test_the_progressive_rules_list_the_points_thresholds(
    http: TestClient, cleanup: None
):
    markup = print_rules(http, create_tournament(ProgressiveSwissVariation))
    assert 'Points scored from' in markup


@pytest.mark.unit
def test_the_custom_rules_list_the_rules_of_the_arbiter(
    http: TestClient, cleanup: None
):
    tournament_id = create_tournament(CustomAccelerationSwissVariation)
    rules = [
        AccelerationRule(vpoints=1.5, first_round=1, last_round=3, number_range=(1, 4)),
        AccelerationRule(vpoints=0.5, first_round=2, last_round=2, number_range=(7, 7)),
    ]
    tournament = EVENT.tournament()
    with EventDatabase(EVENT_ID, True) as database:
        database.set_tournament_pairing_settings(
            tournament_id,
            tournament.stored_pairing_settings
            | {
                CustomAccelerationSetting.static_id(): (
                    CustomAccelerationSetting.to_stored_value(rules)
                )
            },
        )
    player_7 = next(
        player
        for player in EVENT.tournament().tournament_players
        if player.pairing_number == 7
    )
    markup = print_rules(http, tournament_id)
    assert 'Rounds 1-3' in markup
    assert 'Nos. 1–4' in markup
    assert '1½' in markup
    assert f'No. 7 ({player_7.full_name})' in markup


@pytest.mark.unit
def test_the_rules_are_refused_for_a_tournament_without_acceleration(
    http: TestClient, cleanup: None
):
    tournament_id = create_tournament(StandardSwissVariation)
    response = http.post(
        f'/event-generate-document/{EVENT_ID}',
        data={'document': 'acceleration-rules', 'tournament': str(tournament_id)},
    )
    assert response.status_code == 200
    assert 'only available for tournaments paired' in response.text


@pytest.mark.unit
@pytest.mark.parametrize(
    ('variation', 'linked'),
    [(ProgressiveSwissVariation, True), (StandardSwissVariation, False)],
)
def test_the_pairing_settings_link_to_the_printed_rules(
    http: TestClient, cleanup: None, variation: type[SwissVariation], linked: bool
):
    tournament_id = create_tournament(variation)
    response = http.get(
        f'/pairings/settings-modal/{EVENT_ID}/{tournament_id}/1',
        params={'configure': '1'},
    )
    assert response.status_code == 200
    assert ('/acceleration-rules?' in response.text) is linked


@pytest.mark.unit
@pytest.mark.parametrize(
    ('variation', 'linked'),
    [(ProgressiveSwissVariation, True), (StandardSwissVariation, False)],
)
def test_the_tournament_card_links_to_the_printed_rules(
    http: TestClient, cleanup: None, variation: type[SwissVariation], linked: bool
):
    create_tournament(variation)
    response = http.get(f'/event/{EVENT_ID}/tournaments')
    assert response.status_code == 200
    assert ('/acceleration-rules?' in response.text) is linked
