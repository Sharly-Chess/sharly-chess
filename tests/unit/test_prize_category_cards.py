"""Tests for the players of the prize category place cards."""

import pytest
from unittest import TestCase

from common.exception import OptionError
from common.i18n.utils import parse_jinja_template
from data.event import Event
from data.loader import EventLoader
from data.print_documents.options import PlaceCardPrizeCategoryPrintOption
from data.print_documents.place_cards.crop_marks import CornersPlaceCardCropMarks
from data.print_documents.place_cards.template import PlaceCardTemplate
from data.print_documents.place_cards.types import (
    PrizeCardSelection,
    PrizeCategoryCardType,
)
from data.prize.prize_group import PrizeGroup
from data.prize.prize_sharing import NoPrizeSharing
from data.prize.prize_type import MonetaryPrizeType
from data.tournament import Tournament
from database.sqlite.event.event_store import (
    StoredPrize,
    StoredPrizeCategory,
    StoredPrizeGroup,
)
from tests.test_config import TestUtils
from utils.enum import PrizeCategoryRankingBasis

EVENT_ID = 'test-prize-category-cards-event'
TOURNAMENT_ID = 'test-prize-category-cards-tournament'


@pytest.mark.unit
class PrizeCategoryCardsTestCase(TestCase):
    event: Event

    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')
        self.event = EventLoader().load_event(EVENT_ID)
        self.prize_group = PrizeGroup(
            self.tournament,
            StoredPrizeGroup(
                id=1,
                tournament_id=self.tournament.id,
                name='Prizes',
                stored_prize_categories=[
                    self._category(1, 'General', True, [(1, 300), (2, 200)]),
                    self._category(2, 'Second', False, [(3, 50)]),
                ],
            ),
        )
        self.tournament.compute_tournament_player_ranks()
        self.by_rank = list(self.tournament.tournament_players_by_rank.values())

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    @property
    def tournament(self) -> Tournament:
        return self.event.tournaments_by_name[TOURNAMENT_ID]

    @staticmethod
    def _category(
        category_id: int,
        name: str,
        is_main: bool,
        prizes: list[tuple[int, float]],
    ) -> StoredPrizeCategory:
        return StoredPrizeCategory(
            id=category_id,
            prize_group_id=1,
            name=name,
            prize_sharing=NoPrizeSharing.static_id(),
            sharing_threshold=None,
            is_main=is_main,
            index=category_id,
            ranking_basis=PrizeCategoryRankingBasis.FINAL_STANDING.value,
            stored_prizes=[
                StoredPrize(
                    id=prize_id,
                    prize_category_id=category_id,
                    type=MonetaryPrizeType.static_id(),
                    value=value,
                    description='',
                )
                for prize_id, value in prizes
            ],
        )

    def _cards(
        self,
        category_id: int | None,
        winners_only: bool,
        player_ids: list[int] | None = None,
    ):
        return PrizeCategoryCardType.tournament_players(
            self.tournament,
            player_ids=player_ids,
            prize_selection=PrizeCardSelection(
                prize_group=self.prize_group,
                prize_category=(
                    self.prize_group.categories_by_id[category_id]
                    if category_id is not None
                    else None
                ),
                winners_only=winners_only,
            ),
        )

    def test_all_players_of_a_category(self):
        """Every player of the category gets a card, whatever the number of
        prizes, ranked in the category with the prize they won in it."""
        cards = self._cards(2, winners_only=False)
        ranks = self.tournament.ex_aequo_rank_by_player_id
        self.assertEqual(
            [card.full_name for card in cards],
            [player.full_name for player in self.by_rank],
        )
        for card, player in zip(cards, self.by_rank, strict=True):
            assert card.prize is not None
            self.assertEqual(card.prize.category, 'Second')
            self.assertEqual(card.prize.category_rank, str(ranks[player.id]))
            self.assertEqual(card.prize.category_player_count, str(len(self.by_rank)))
            self.assertEqual(card.rank, str(ranks[player.id]))
        # The two leaders hold the larger main prizes: the third player wins the
        # prize of the category.
        self.assertEqual([card.prize.place for card in cards[:4]], ['', '', '1', ''])
        self.assertTrue(cards[2].prize.name)
        self.assertEqual(cards[0].prize.name, '')

    def test_prize_winners_of_a_category(self):
        cards = self._cards(1, winners_only=True)
        self.assertEqual(
            [card.full_name for card in cards],
            [player.full_name for player in self.by_rank[:2]],
        )
        self.assertEqual([card.prize.place for card in cards], ['1', '2'])

    def test_prize_winners_of_all_categories(self):
        cards = self._cards(None, winners_only=True)
        self.assertEqual(
            [(card.full_name, card.prize.category) for card in cards],
            [
                (self.by_rank[0].full_name, 'General'),
                (self.by_rank[1].full_name, 'General'),
                (self.by_rank[2].full_name, 'Second'),
            ],
        )

    def test_chosen_players(self):
        player = self.by_rank[5]
        cards = self._cards(2, winners_only=False, player_ids=[player.id])
        self.assertEqual([card.full_name for card in cards], [player.full_name])

    def test_certificate_template_renders(self):
        template = PlaceCardTemplate.load('prize_category_01_certificate')
        self.assertIsInstance(template.type, PrizeCategoryCardType)
        self.assertNotIn('Jinja error', template.preview())
        winner = self.by_rank[2]
        html = parse_jinja_template(
            '/admin/print/place_cards/place_cards.html',
            template.template_context(
                event=self.event,
                tournament=self.tournament,
                round_=self.tournament.rounds,
                mirror=False,
                place_card_crop_marks=CornersPlaceCardCropMarks(),
                board_numbers=set(),
                player_ids=[winner.id],
                prize_selection=PrizeCardSelection(
                    prize_group=self.prize_group,
                    prize_category=self.prize_group.categories_by_id[2],
                    winners_only=False,
                ),
            ),
        )
        self.assertNotIn('Jinja error', html)
        self.assertIn(winner.full_name, html)
        self.assertIn('Second', html)

    def test_category_option_value(self):
        self.tournament.prize_groups_by_id[1] = self.prize_group
        option = PlaceCardPrizeCategoryPrintOption(self.event, '1:2')
        self.assertEqual(
            option.prize_group_and_category(self.tournament),
            (self.prize_group, self.prize_group.categories_by_id[2]),
        )
        option = PlaceCardPrizeCategoryPrintOption(self.event, '1:*')
        self.assertEqual(
            option.prize_group_and_category(self.tournament),
            (self.prize_group, None),
        )
        for value in (None, '1:9', '9:1', 'junk'):
            with self.assertRaises(OptionError):
                PlaceCardPrizeCategoryPrintOption(
                    self.event, value
                ).prize_group_and_category(self.tournament)
