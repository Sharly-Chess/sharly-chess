"""Copying prize brackets and categories to the other tournaments of the
event, over HTTP."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.criteria.player_filter_options import GenderOption, PlayersFilterOption
from data.criteria.player_filters import GenderPlayerFilter, PlayerIdPlayerFilter
from data.prize.prize_category import PrizeCategory
from data.prize.prize_group import PrizeGroup
from data.prize.prize_sharing import NoPrizeSharing
from data.prize.prize_type import HybridPrizeType
from data.tournament import Tournament
from database.sqlite.event.event_store import (
    StoredPrize,
    StoredPrizeCategory,
    StoredPrizeCriterion,
    StoredPrizeGroup,
)
from tests.test_config import TestUtils
from tests.unit.http.events import EventUnderTest
from utils.enum import PlayerGender, PrizeCategoryRankingBasis

EVENT_ID = 'test-prize-copy-http'
SOURCE_NAME = 'test-prize-copy-source'
TARGET_NAME = 'test-prize-copy-target'

EVENT = EventUnderTest(EVENT_ID, SOURCE_NAME)


@pytest.fixture
def source() -> Iterator[tuple[int, int, int]]:
    """A source tournament with a bracket holding a main category and a
    women category, which also selects one player; and an empty target
    tournament."""
    EVENT.create()
    TestUtils.create_tournament(EVENT_ID, TARGET_NAME)
    tournament = EVENT.tournament()
    group = tournament.add_prize_group(
        StoredPrizeGroup(id=None, tournament_id=tournament.id, name='Prizes')
    )
    add_category(group, 'General', is_main=True)
    women = add_category(group, 'Women', is_main=False)
    women.add_criterion(
        StoredPrizeCriterion(
            id=None,
            prize_category_id=women.id,
            type=GenderPlayerFilter.static_id(),
            options={GenderOption.static_id(): PlayerGender.WOMAN.value},
        )
    )
    women.add_criterion(
        StoredPrizeCriterion(
            id=None,
            prize_category_id=women.id,
            type=PlayerIdPlayerFilter.static_id(),
            options={PlayersFilterOption.static_id(): [1]},
        )
    )
    yield tournament.id, group.id, women.id
    EVENT.delete()


def add_category(group: PrizeGroup, name: str, is_main: bool) -> PrizeCategory:
    category = group.add_category(
        StoredPrizeCategory(
            id=None,
            prize_group_id=group.id,
            name=name,
            prize_sharing=NoPrizeSharing.static_id(),
            sharing_threshold=None,
            is_main=is_main,
            index=0,
            ranking_basis=PrizeCategoryRankingBasis.BEST_ROUND_PERFORMANCE.value,
        )
    )
    category.add_prize(
        StoredPrize(
            id=None,
            prize_category_id=category.id,
            type=HybridPrizeType.static_id(),
            value=100.0,
            description='Book',
            complementary_value=30.0,
        )
    )
    return category


def target() -> Tournament:
    return EVENT.load().tournaments_by_name[TARGET_NAME]


def assert_women_copy(group: PrizeGroup) -> None:
    women = next(category for category in group.categories if category.name == 'Women')
    assert [criterion.stored_prize_criterion.type for criterion in women.criteria] == [
        GenderPlayerFilter.static_id()
    ]
    [prize] = women.prizes
    assert prize.complementary_value == 30.0
    assert women.ranking_basis == PrizeCategoryRankingBasis.BEST_ROUND_PERFORMANCE


@pytest.mark.unit
def test_a_bracket_is_duplicated_in_its_tournament(
    http: TestClient, source: tuple[int, int, int]
):
    tournament_id, group_id, _ = source
    response = http.post(
        f'/prizes/prize-group/duplicate/{EVENT_ID}/{tournament_id}/{group_id}'
    )
    assert response.status_code == 200
    assert sorted(group.name for group in EVENT.tournament().prize_groups) == [
        'Prizes',
        'Prizes (2)',
    ]


@pytest.mark.unit
def test_a_bracket_is_copied_to_another_tournament(
    http: TestClient, source: tuple[int, int, int]
):
    tournament_id, group_id, _ = source
    response = http.post(
        f'/prizes/prize-group/copy/{EVENT_ID}/{tournament_id}/{group_id}',
        data={'tournament_ids': [str(target().id)]},
    )
    assert response.status_code == 200
    assert 'not been copied (categories: Women)' in response.text
    [group] = target().prize_groups
    assert group.name == 'Prizes'
    assert group.main_category is not None
    assert group.main_category.name == 'General'
    assert_women_copy(group)


@pytest.mark.unit
def test_a_bracket_is_not_copied_without_a_target(
    http: TestClient, source: tuple[int, int, int]
):
    tournament_id, group_id, _ = source
    response = http.post(
        f'/prizes/prize-group/copy/{EVENT_ID}/{tournament_id}/{group_id}',
        data={'tournament_ids': [str(tournament_id)]},
    )
    assert response.status_code == 200
    assert 'Select at least one tournament.' in response.text
    assert len(EVENT.tournament().prize_groups) == 1
    assert not target().prize_groups


@pytest.mark.unit
def test_a_category_is_copied_to_a_new_bracket(
    http: TestClient, source: tuple[int, int, int]
):
    tournament_id, group_id, women_id = source
    response = http.post(
        f'/prizes/prize-category/copy/{EVENT_ID}/{tournament_id}/{group_id}/{women_id}',
        data={'target': f'{target().id}-new'},
    )
    assert response.status_code == 200
    [group] = target().prize_groups
    assert group.main_category is None
    assert_women_copy(group)


@pytest.mark.unit
def test_a_category_is_not_copied_to_an_unknown_bracket(
    http: TestClient, source: tuple[int, int, int]
):
    tournament_id, group_id, women_id = source
    response = http.post(
        f'/prizes/prize-category/copy/{EVENT_ID}/{tournament_id}/{group_id}/{women_id}',
        data={'target': f'{tournament_id}-{group_id}'},
    )
    assert response.status_code == 200
    assert 'Select a prize bracket.' in response.text
    assert len(next(iter(EVENT.tournament().prize_groups)).categories) == 2


@pytest.mark.unit
def test_a_cloned_tournament_keeps_its_prizes(
    http: TestClient, source: tuple[int, int, int]
):
    tournament_id, _, _ = source
    response = http.post(
        f'/tournament-clone/{EVENT_ID}/{tournament_id}',
        data={
            'name': 'A copy',
            'rounds': '5',
            'pairing_system': 'SWISS',
            'SWISS_pairing_variation': 'SWISS_STANDARD',
        },
    )
    assert response.status_code == 200
    [group] = EVENT.load().tournaments_by_name['A copy'].prize_groups
    assert_women_copy(group)
