import pytest

from data.criteria.player_filter_options import (
    ExcludeFilterOption,
    GenderOption,
    PlayersFilterOption,
)
from data.criteria.player_filters import GenderPlayerFilter, PlayerIdPlayerFilter
from data.event import Event
from data.loader import EventLoader
from data.prize.prize_category import PrizeCategory
from data.prize.prize_group import PrizeGroup
from data.prize.prize_sharing import AveragePrizeSharing, NoPrizeSharing
from data.prize.prize_type import HybridPrizeType, MonetaryPrizeType
from database.sqlite.event.event_store import (
    StoredPrize,
    StoredPrizeCategory,
    StoredPrizeCriterion,
    StoredPrizeGroup,
)
from tests.test_config import TestUtils
from utils.enum import PlayerGender, PrizeCategoryRankingBasis

EVENT_UNIQ_ID = 'test-prize-copy'


@pytest.fixture
def event():
    TestUtils.create_event(EVENT_UNIQ_ID)
    TestUtils.create_tournament(EVENT_UNIQ_ID, 'A')
    TestUtils.create_tournament(EVENT_UNIQ_ID, 'B')
    yield EventLoader().load_event(EVENT_UNIQ_ID)
    TestUtils.delete_event(EVENT_UNIQ_ID)


def _add_category(
    prize_group: PrizeGroup, name: str, is_main: bool = False
) -> PrizeCategory:
    category = prize_group.add_category(
        StoredPrizeCategory(
            id=None,
            prize_group_id=prize_group.id,
            name=name,
            prize_sharing=AveragePrizeSharing.static_id(),
            sharing_threshold=10.0,
            is_main=is_main,
            index=0,
            ranking_basis=PrizeCategoryRankingBasis.AVERAGE_PERFORMANCE.value,
        )
    )
    category.add_prize(
        StoredPrize(
            id=None,
            prize_category_id=category.id,
            type=MonetaryPrizeType.static_id(),
            value=100.0,
            description='',
        )
    )
    category.add_prize(
        StoredPrize(
            id=None,
            prize_category_id=category.id,
            type=HybridPrizeType.static_id(),
            value=50.0,
            description='Book',
            complementary_value=20.0,
        )
    )
    category.add_criterion(
        StoredPrizeCriterion(
            id=None,
            prize_category_id=category.id,
            type=GenderPlayerFilter.static_id(),
            options={GenderOption.static_id(): PlayerGender.WOMAN.value},
        )
    )
    category.add_criterion(
        StoredPrizeCriterion(
            id=None,
            prize_category_id=category.id,
            type=PlayerIdPlayerFilter.static_id(),
            options={
                PlayersFilterOption.static_id(): [1, 2],
                ExcludeFilterOption.static_id(): True,
            },
        )
    )
    return category


def _add_group(event: Event, tournament_name: str, name: str) -> PrizeGroup:
    tournament = event.tournaments_by_name[tournament_name]
    return tournament.add_prize_group(
        StoredPrizeGroup(id=None, tournament_id=tournament.id, name=name)
    )


def _get_group(event: Event, tournament_name: str, group_name: str) -> PrizeGroup:
    return next(
        group
        for group in event.tournaments_by_name[tournament_name].prize_groups
        if group.name == group_name
    )


def _criterion_types(category: PrizeCategory) -> list[str]:
    return [criterion.stored_prize_criterion.type for criterion in category.criteria]


@pytest.mark.unit
def test_copy_category_keeps_settings_and_prizes(event: Event):
    group = _add_group(event, 'A', 'Group')
    source = _add_category(group, 'Women')
    other_group = _add_group(event, 'B', 'Group')

    other_group.copy_category(source)

    reloaded_event = EventLoader().load_event(EVENT_UNIQ_ID)
    [copy] = _get_group(reloaded_event, 'B', 'Group').categories
    assert copy.name == 'Women'
    assert copy.prize_sharing == AveragePrizeSharing()
    assert copy.sharing_threshold == 10.0
    assert copy.ranking_basis == PrizeCategoryRankingBasis.AVERAGE_PERFORMANCE
    assert [
        (prize.type.id, prize.value, prize.description, prize.complementary_value)
        for prize in copy.sorted_prizes
    ] == [
        (MonetaryPrizeType.static_id(), 100.0, '', None),
        (HybridPrizeType.static_id(), 50.0, 'Book', 20.0),
    ]


@pytest.mark.unit
def test_copy_category_to_another_tournament_drops_player_criteria(event: Event):
    group = _add_group(event, 'A', 'Group')
    source = _add_category(group, 'Women')

    _add_group(event, 'B', 'Group').copy_category(source)

    reloaded_event = EventLoader().load_event(EVENT_UNIQ_ID)
    [copy] = _get_group(reloaded_event, 'B', 'Group').categories
    assert _criterion_types(copy) == [GenderPlayerFilter.static_id()]
    assert source.tournament_bound_criteria


@pytest.mark.unit
def test_copy_category_in_same_tournament_keeps_player_criteria(event: Event):
    group = _add_group(event, 'A', 'Group')
    source = _add_category(group, 'Women')

    group.copy_category(source)

    reloaded_event = EventLoader().load_event(EVENT_UNIQ_ID)
    categories = _get_group(reloaded_event, 'A', 'Group').sorted_categories
    assert [category.name for category in categories] == ['Women', 'Women (2)']
    assert _criterion_types(categories[1]) == _criterion_types(categories[0])


@pytest.mark.unit
def test_copy_main_category_stays_main_only_without_main(event: Event):
    group = _add_group(event, 'A', 'Group')
    source = _add_category(group, 'General', is_main=True)
    empty_group = _add_group(event, 'B', 'Empty')
    group_with_main = _add_group(event, 'B', 'With main')
    _add_category(group_with_main, 'Other main', is_main=True)

    empty_group.copy_category(source)
    group_with_main.copy_category(source)

    reloaded_event = EventLoader().load_event(EVENT_UNIQ_ID)
    assert _get_group(reloaded_event, 'B', 'Empty').main_category is not None
    reloaded = _get_group(reloaded_event, 'B', 'With main')
    assert reloaded.main_category is not None
    assert reloaded.main_category.name == 'Other main'


@pytest.mark.unit
def test_copy_prize_group(event: Event):
    group = _add_group(event, 'A', 'Group')
    _add_category(group, 'General', is_main=True)
    _add_category(group, 'Women')
    target = event.tournaments_by_name['B']
    target.add_prize_group(
        StoredPrizeGroup(id=None, tournament_id=target.id, name='Group')
    )

    target.copy_prize_group(group)

    reloaded_event = EventLoader().load_event(EVENT_UNIQ_ID)
    copy = _get_group(reloaded_event, 'B', 'Group (2)')
    assert [category.name for category in copy.sorted_categories] == [
        'General',
        'Women',
    ]
    assert copy.main_category is not None
    assert copy.main_category.name == 'General'
    assert all(
        category.prize_sharing != NoPrizeSharing() for category in copy.categories
    )
