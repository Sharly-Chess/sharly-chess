from datetime import date
from unittest.mock import patch, PropertyMock

import pytest
from unittest import TestCase

# Needs to be imported first to avoid circular import
from plugins import manager  # Noqa E402

from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from data.player import Federation, PlayerRating, Club
from data.prize.player_filter_options import (
    GenderOption,
    MaxRatingOption,
    MinRatingOption,
    AgeCategoriesOption,
    AgeLowerOption,
    AgeGreaterOption,
    ClubsFilterOption,
    FederationsFilterOption,
    RatingTypesFilterOption,
)
from data.prize.player_filters import (
    GenderPlayerFilter,
    PlayerFilter,
    RatingPlayerFilter,
    AgePlayerFilter,
    ClubPlayerFilter,
    FederationPlayerFilter,
    RatingTypePlayerFilter,
)
from data.prize.prize import Prize
from data.prize.prize_sharing import (
    AveragePrizeSharing,
    HortSystemPrizeSharing,
    NoPrizeSharing,
    PrizeSharing,
)
from data.prize.prize_group import AssignedPrize
from database.access.papi.papi_store import (
    StoredPlayer,
    StoredTournamentPlayer,
    StoredPairing,
)
from database.sqlite.event.event_store import (
    StoredPrize,
    StoredPrizeCategory,
    StoredPrizeCriterion,
    StoredPrizeGroup,
    StoredTournament,
)
from plugins.ffe.ffe_entity import FfeLeaguePlayerFilter, FfeLeaguesFilterOption
from tests.test_config import TestUtils
from utils.enum import (
    PlayerGender,
    PlayerRatingType,
    PlayerTitle,
    Result,
    TournamentRating,
    PlayerCategory,
)

ROUNDS = 6


@pytest.mark.unit
class PrizesTestCase(TestCase):
    event: Event

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        TestUtils.create_event_direct('test-prizes-event')
        cls.event = EventLoader().load_event('test-prizes-event')

    @classmethod
    def tearDownClass(cls):
        TestUtils.delete_event_direct('test-prizes-event')
        super().tearDownClass()

    def setUp(self):
        self.category_index = 1
        self.criterion_index = 1
        self.prize_index = 1
        self.stored_prize_group = StoredPrizeGroup(id=1, tournament_id=1, name='test')
        self.tournament: Tournament | None = None

    def get_prizes(self, category_id: int = 1) -> list[Prize]:
        assert self.tournament is not None
        return (
            self.tournament.prize_groups_by_id[1]
            .categories_by_id[category_id]
            .sorted_prizes
        )

    def assign_prizes(
        self,
        stored_categories: list[StoredPrizeCategory],
        stored_players: list[StoredPlayer],
    ):
        self.stored_prize_group.stored_prize_categories = stored_categories
        for index, stored_category in enumerate(stored_categories):
            stored_category.index = index
        for index, stored_player in enumerate(stored_players):
            id_ = 1001 + index
            stored_player.id = id_
            stored_player.stored_tournament_player.player_id = id_
            for (
                stored_pairing
            ) in stored_player.stored_tournament_player.stored_pairings:
                stored_pairing.player_id = id_
        with patch(
            'data.tournament.Tournament.rounds', new_callable=PropertyMock
        ) as mock_rounds:
            mock_rounds.return_value = ROUNDS
            self.tournament = Tournament(
                self.event,
                StoredTournament(
                    uniq_id='empty',
                    name='empty',
                    id=1,
                    path='',
                    filename='',
                    current_round=ROUNDS,
                    rounds=ROUNDS,
                    stored_prize_groups=[self.stored_prize_group],
                    stored_players=stored_players,
                ),
            )
            return self.tournament.prize_groups_by_id[1].assign_prizes()

    def player(
        self,
        elo: int,
        points: int,
        gender: PlayerGender = PlayerGender.NONE,
        rating_type: PlayerRatingType = PlayerRatingType.FIDE,
        year_of_birth: int = 2000,
        federation: str = 'FRA',
        club: str = '',
        ffe_league: str = '',
    ) -> StoredPlayer:
        stored_pairings: list[StoredPairing] = []
        for round_ in range(1, 7):
            result = Result.GAIN if round_ <= points else Result.LOSS
            stored_pairings.append(
                StoredPairing(
                    tournament_id=1,
                    player_id=0,
                    round_=round_,
                    result=result.value,
                    board_id=None,
                )
            )
        stored_player = StoredPlayer(
            id=None,
            first_name='A',
            last_name='B' + str(elo),
            date_of_birth=date(year_of_birth, 1, 1),
            gender=gender,
            fide_id=None,
            federation=federation,
            title=PlayerTitle.NONE,
            mail=None,
            phone=None,
            comment=None,
            owed=0,
            paid=0,
            ratings={
                rating: PlayerRating(elo, rating_type).stored_value
                for rating in TournamentRating
            },
            club=club,
            fixed=False,
            check_in=False,
            plugin_data={'ffe': {'league': ffe_league}},
            stored_tournament_player=StoredTournamentPlayer(
                tournament_id=1,
                stored_pairings=stored_pairings,
            ),
        )
        return stored_player

    def stored_category(
        self,
        name: str = 'category',
        is_main: bool = False,
        prize_sharing: PrizeSharing = NoPrizeSharing(),
        stored_prizes: list[StoredPrize] | None = None,
        stored_prize_criteria: list[StoredPrizeCriterion] | None = None,
        threshold: float | None = None,
    ):
        if not stored_prizes:
            stored_prizes = []
        if not stored_prize_criteria:
            stored_prize_criteria = []
        for index, prize in enumerate(stored_prizes):
            prize.prize_category_id = self.category_index
        for criterion in stored_prize_criteria:
            criterion.prize_category_id = self.category_index
        category = StoredPrizeCategory(
            id=self.category_index,
            index=0,
            prize_group_id=1,
            name=name,
            prize_sharing=prize_sharing.static_id(),
            is_main=is_main,
            sharing_threshold=threshold,
            stored_prize_criteria=stored_prize_criteria,
            stored_prizes=stored_prizes,
        )
        self.category_index += 1
        return category

    def stored_criterion(self, player_filter: PlayerFilter):
        criterion = StoredPrizeCriterion(
            id=self.criterion_index,
            prize_category_id=0,
            type=player_filter.id,
            options={option.id: option.value for option in player_filter.options},
        )
        self.criterion_index += 1
        return criterion

    def stored_prize(self, value: int, is_monetary: bool = True):
        prize = StoredPrize(
            id=self.prize_index,
            prize_category_id=0,
            value=value,
            is_monetary=is_monetary,
            description='',
        )
        self.prize_index += 1
        return prize

    def assert_has_prize(
        self,
        stored_player: StoredPlayer,
        prize: Prize | StoredPrize,
        prize_list: list[AssignedPrize],
        has_warning: bool = False,
    ):
        assigned_prize = next(
            (
                prize
                for prize in prize_list
                if prize.assigned_to and prize.assigned_to.id == stored_player.id
            ),
            None,
        )
        self.assertIsNotNone(assigned_prize)
        assert assigned_prize is not None
        self.assertEqual(bool(assigned_prize.warning), has_warning)
        self.assertIsNotNone(assigned_prize.prize)
        self.assertEqual(assigned_prize.prize and assigned_prize.prize.id, prize.id)

    def assert_has_prize_value(
        self,
        stored_player: StoredPlayer,
        value: float,
        prize_list: list[AssignedPrize],
        has_warning: bool = False,
    ):
        assigned_prize = next(
            (
                prize
                for prize in prize_list
                if prize.assigned_to and prize.assigned_to.id == stored_player.id
            ),
            None,
        )
        assert assigned_prize is not None, (
            f'No assigned prize for player {stored_player.id}'
        )
        self.assertEqual(bool(assigned_prize.warning), has_warning)
        self.assertIn(
            stored_player.id,
            [prize.assigned_to.id for prize in prize_list if prize.assigned_to],
        )
        self.assertEqual(assigned_prize.value, value)

    def assert_has_no_prize(
        self, stored_player: StoredPlayer, prize_list: list[AssignedPrize]
    ):
        self.assertNotIn(
            stored_player.id,
            [prize.assigned_to.id for prize in prize_list if prize.assigned_to],
        )

    def test_basic_no_sharing(self):
        """Main category, no prize sharing."""
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
            self.stored_prize(50),
        ]
        category = self.stored_category('all', True, NoPrizeSharing(), prizes)
        p1 = self.player(2000, 4)
        p2 = self.player(1900, 5)
        p3 = self.player(1800, 3)
        p4 = self.player(1700, 2)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        self.assert_has_prize_value(p1, 100, prizes)
        self.assert_has_prize_value(p2, 200, prizes)
        self.assert_has_prize_value(p3, 50, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_basic_average_sharing(self):
        """Main category, average prize sharing."""
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
            self.stored_prize(60),
        ]
        category = self.stored_category('all', True, AveragePrizeSharing(), prizes)
        p1 = self.player(1000, 5)
        p2 = self.player(1000, 5)
        p3 = self.player(1000, 4)
        p4 = self.player(1000, 4)
        p5 = self.player(1000, 4)
        p6 = self.player(1000, 3)
        players = [p1, p2, p3, p4, p5, p6]

        prizes = self.assign_prizes([category], players)

        self.assert_has_prize_value(p1, (200 + 100) / 2, prizes)
        self.assert_has_prize_value(p2, (200 + 100) / 2, prizes)
        self.assert_has_prize_value(p3, 60 / 3, prizes)
        self.assert_has_prize_value(p4, 60 / 3, prizes)
        self.assert_has_prize_value(p5, 60 / 3, prizes)
        self.assert_has_no_prize(p6, prizes)

    def test_basic_hort_sharing(self):
        """Main category, hort prize sharing."""
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
            self.stored_prize(60),
        ]
        category = self.stored_category('all', True, HortSystemPrizeSharing(), prizes)
        p1 = self.player(1000, 5)
        p2 = self.player(1000, 5)
        p3 = self.player(1000, 4)
        p4 = self.player(1000, 4)
        p5 = self.player(1000, 4)
        p6 = self.player(1000, 3)
        players = [p1, p2, p3, p4, p5, p6]

        prizes = self.assign_prizes([category], players)

        self.assert_has_prize_value(p1, (200 + (200 + 100) / 2) / 2, prizes)
        self.assert_has_prize_value(p2, (100 + (200 + 100) / 2) / 2, prizes)
        self.assert_has_prize_value(p3, (60 + 60 / 3) / 2, prizes)
        self.assert_has_prize_value(p4, (0 + 60 / 3) / 2, prizes)
        self.assert_has_prize_value(p5, (0 + 60 / 3) / 2, prizes)
        self.assert_has_no_prize(p6, prizes)

    def test_average_threshold(self):
        """Main category, average prize sharing with threshold."""
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
            self.stored_prize(60),
        ]
        category = self.stored_category(
            'all', True, AveragePrizeSharing(), prizes, threshold=30
        )
        p1 = self.player(1000, 5)
        p2 = self.player(1000, 4)
        p3 = self.player(1000, 3)
        p4 = self.player(1000, 3)
        p5 = self.player(1000, 3)
        players = [p1, p2, p3, p4, p5]

        prizes = self.assign_prizes([category], players)

        self.assert_has_prize_value(p1, 200, prizes)
        self.assert_has_prize_value(p2, 100, prizes)
        self.assert_has_prize_value(p3, 60 / 2, prizes)
        self.assert_has_prize_value(p4, 60 / 2, prizes, True)
        self.assert_has_no_prize(p5, prizes)

    def test_hort_threshold(self):
        """Main category, hort prize sharing with threshold."""
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
            self.stored_prize(60),
        ]
        category = self.stored_category(
            'all', True, HortSystemPrizeSharing(), prizes, threshold=15
        )
        p1 = self.player(1000, 5)
        p2 = self.player(1000, 4)
        p3 = self.player(1000, 3)
        p4 = self.player(1000, 3)
        p5 = self.player(1000, 3)
        players = [p1, p2, p3, p4, p5]

        prizes = self.assign_prizes([category], players)

        self.assert_has_prize_value(p1, 200, prizes)
        self.assert_has_prize_value(p2, 100, prizes)
        self.assert_has_prize_value(p3, (60 + 60 / 2) / 2, prizes)
        self.assert_has_prize_value(p4, 60 / 2 / 2, prizes, True)
        self.assert_has_no_prize(p5, prizes)

    def test_single_entrant_promotion(self):
        """Test that a player in the main category can be promoted to a better prize,
        and that the players below are promoted to a better place"""
        main_category = self.stored_category(
            'all',
            True,
            NoPrizeSharing(),
            [
                self.stored_prize(200),
                self.stored_prize(100),
                self.stored_prize(50),
            ],
        )

        first_woman = self.stored_prize(150)
        second_woman = self.stored_prize(90)

        top_women_category = self.stored_category(
            'woman',
            stored_prizes=[
                first_woman,
                second_woman,
            ],
            stored_prize_criteria=[
                self.stored_criterion(
                    GenderPlayerFilter([GenderOption(PlayerGender.FEMALE.value)])
                )
            ],
        )

        p1 = self.player(1000, 6, PlayerGender.MALE)
        p2 = self.player(1000, 5, PlayerGender.FEMALE)
        p3 = self.player(1000, 4, PlayerGender.MALE)
        p4 = self.player(1000, 3, PlayerGender.MALE)
        p5 = self.player(1000, 2, PlayerGender.FEMALE)
        players = [p1, p2, p3, p4, p5]

        prizes = self.assign_prizes([main_category, top_women_category], players)

        # First place
        self.assert_has_prize_value(p1, 200, prizes)

        # First woman, promoted from second place
        self.assert_has_prize(p2, first_woman, prizes)

        # Second place, promoted from third place
        self.assert_has_prize_value(p3, 100, prizes)

        # Third place, promoted from fourth place
        self.assert_has_prize_value(p4, 50, prizes)

        # Second woman
        self.assert_has_prize(p5, second_woman, prizes)

    def test_multiple_entrants_promotion_average(self):
        """Test that multiple people may enter the prize pool if another one
        gets a better prize"""
        main_category = self.stored_category(
            'all',
            True,
            AveragePrizeSharing(),
            [
                self.stored_prize(200),
                self.stored_prize(100),
                self.stored_prize(50),
            ],
        )

        first_woman = self.stored_prize(150)
        second_woman = self.stored_prize(90)

        top_women_category = self.stored_category(
            'woman',
            stored_prizes=[
                first_woman,
                second_woman,
            ],
            stored_prize_criteria=[
                self.stored_criterion(
                    GenderPlayerFilter([GenderOption(PlayerGender.FEMALE.value)])
                )
            ],
        )

        p1 = self.player(1000, 6, PlayerGender.MALE)
        p2 = self.player(1001, 5, PlayerGender.FEMALE)
        p3 = self.player(1002, 4, PlayerGender.MALE)
        p4 = self.player(1003, 3, PlayerGender.MALE)
        p5 = self.player(1004, 3, PlayerGender.MALE)
        p6 = self.player(1005, 2, PlayerGender.FEMALE)
        players = [p1, p2, p3, p4, p5, p6]

        prizes = self.assign_prizes([main_category, top_women_category], players)

        # First place
        self.assert_has_prize_value(p1, 200, prizes)

        # First woman, promoted from second place
        self.assert_has_prize(p2, first_woman, prizes)

        # Second place, promoted from third place
        self.assert_has_prize_value(p3, 100, prizes)

        # Third place, promoted from fourth place, shares prize
        self.assert_has_prize_value(p4, 25, prizes)
        self.assert_has_prize_value(p5, 25, prizes)  # Shares third place

        # Second woman
        self.assert_has_prize(p6, second_woman, prizes)

    def test_promotion_entrant_gets_higher_prize(self):
        """Test that a player entering the main category can still be promoted to a better prize"""
        main_category = self.stored_category(
            'all',
            True,
            AveragePrizeSharing(),
            [
                self.stored_prize(200),
                self.stored_prize(100),
                self.stored_prize(50),
            ],
        )

        first_woman = self.stored_prize(150)
        second_woman = self.stored_prize(120)

        top_women_category = self.stored_category(
            'woman',
            stored_prizes=[
                first_woman,
                second_woman,
            ],
            stored_prize_criteria=[
                self.stored_criterion(
                    GenderPlayerFilter([GenderOption(PlayerGender.FEMALE.value)])
                )
            ],
        )

        p1 = self.player(1000, 6, PlayerGender.MALE)
        p2 = self.player(1000, 5, PlayerGender.FEMALE)
        p3 = self.player(1000, 4, PlayerGender.MALE)
        p4 = self.player(1000, 3, PlayerGender.FEMALE)
        p5 = self.player(1000, 3, PlayerGender.MALE)
        p6 = self.player(1000, 3, PlayerGender.MALE)
        p7 = self.player(1000, 2, PlayerGender.FEMALE)
        players = [p1, p2, p3, p4, p5, p6, p7]

        prizes = self.assign_prizes([main_category, top_women_category], players)

        # First place
        self.assert_has_prize_value(p1, 200, prizes)

        # First woman, promoted from second place
        self.assert_has_prize(p2, first_woman, prizes)

        # Second place, promoted from third place
        self.assert_has_prize_value(p3, 100, prizes)

        # Second woman
        self.assert_has_prize(p4, second_woman, prizes)

        # Third place
        self.assert_has_prize_value(p5, 25, prizes)
        self.assert_has_prize_value(p5, 25, prizes)

        # Third woman
        self.assert_has_no_prize(p7, prizes)

    def test_promotion_entrant_gets_lower_prize(self):
        """Test that a player in the main category stays there if they receive a lower prize"""
        main_category = self.stored_category(
            'all',
            True,
            AveragePrizeSharing(),
            [
                self.stored_prize(200),
                self.stored_prize(100),
                self.stored_prize(60),
            ],
        )

        first_woman = self.stored_prize(90)
        second_woman = self.stored_prize(60)

        top_women_category = self.stored_category(
            'woman',
            stored_prizes=[first_woman, second_woman],
            stored_prize_criteria=[
                self.stored_criterion(
                    GenderPlayerFilter([GenderOption(PlayerGender.FEMALE.value)])
                )
            ],
        )

        p1 = self.player(1000, 6, PlayerGender.MALE)
        p2 = self.player(1001, 5, PlayerGender.FEMALE)
        p3 = self.player(1002, 3, PlayerGender.MALE)
        p4 = self.player(1003, 3, PlayerGender.FEMALE)
        p5 = self.player(1004, 3, PlayerGender.MALE)
        p6 = self.player(1005, 3, PlayerGender.MALE)
        p7 = self.player(1006, 3, PlayerGender.FEMALE)
        players = [p1, p2, p3, p4, p5, p6, p7]

        prizes = self.assign_prizes([main_category, top_women_category], players)

        # First place
        self.assert_has_prize_value(p1, 200, prizes)

        # Second place, not downgraded to first woman
        self.assert_has_prize_value(p2, 100, prizes)

        # First woman, promoted from second woman
        self.assert_has_prize(p7, first_woman, prizes)

        # Second woman, promoted from third woman
        # Would have shared third place if the second woman prize was not higher than the shared prize
        self.assert_has_prize(p4, second_woman, prizes)

        # Sharing third place
        self.assert_has_prize_value(p3, 20, prizes)
        self.assert_has_prize_value(p5, 20, prizes)
        self.assert_has_prize_value(p5, 20, prizes)

    def test_promotion_with_higher_prize(self):
        """Test that a player that enters the main category with a higher prize, keeps the prize instead"""
        main_category = self.stored_category(
            'all',
            True,
            AveragePrizeSharing(),
            [
                self.stored_prize(200),
                self.stored_prize(100),
                self.stored_prize(50),
            ],
        )

        first_1600 = self.stored_prize(75)
        elo_category = self.stored_category(
            'elo',
            stored_prizes=[first_1600],
            stored_prize_criteria=[
                self.stored_criterion(RatingPlayerFilter([MaxRatingOption(1600)]))
            ],
        )

        first_woman = self.stored_prize(70)
        top_women_category = self.stored_category(
            'woman',
            stored_prizes=[first_woman],
            stored_prize_criteria=[
                self.stored_criterion(
                    GenderPlayerFilter([GenderOption(PlayerGender.FEMALE.value)])
                )
            ],
        )

        p1 = self.player(2000, 6, PlayerGender.MALE)
        p2 = self.player(1900, 5, PlayerGender.MALE)
        p3 = self.player(1800, 3, PlayerGender.FEMALE)
        p4 = self.player(1600, 3, PlayerGender.MALE)
        p5 = self.player(1004, 2, PlayerGender.MALE)

        players = [p1, p2, p3, p4, p5]

        prizes = self.assign_prizes(
            [main_category, elo_category, top_women_category], players
        )

        # First place
        self.assert_has_prize_value(p1, 200, prizes)

        # Second place
        self.assert_has_prize_value(p2, 100, prizes)

        # First woman, promoted from third place
        self.assert_has_prize(p3, first_woman, prizes)

        # First 1600 player
        self.assert_has_prize(p4, first_1600, prizes)

        # Third place
        self.assert_has_prize_value(p5, 50, prizes)

    def test_priority_order(self):
        """Test that the priority order is respected"""
        first_1600 = self.stored_prize(70)
        elo_category = self.stored_category(
            'elo',
            stored_prizes=[first_1600],
            stored_prize_criteria=[
                self.stored_criterion(RatingPlayerFilter([MaxRatingOption(1600)]))
            ],
        )

        first_woman = self.stored_prize(70)
        top_women_category = self.stored_category(
            'woman',
            stored_prizes=[first_woman],
            stored_prize_criteria=[
                self.stored_criterion(
                    GenderPlayerFilter([GenderOption(PlayerGender.FEMALE.value)])
                )
            ],
        )

        p1 = self.player(1550, 6, PlayerGender.FEMALE)
        p2 = self.player(1550, 3, PlayerGender.MALE)
        p3 = self.player(1004, 2, PlayerGender.MALE)

        players = [p1, p2, p3]

        prizes = self.assign_prizes([elo_category, top_women_category], players)

        # Elo attributed to first woman,
        self.assert_has_prize(p1, first_1600, prizes)
        self.assert_has_no_prize(p2, prizes)
        self.assert_has_no_prize(p3, prizes)

        prizes = self.assign_prizes([top_women_category, elo_category], players)

        # Elo attributed to first woman,
        self.assert_has_prize(p1, first_woman, prizes)
        self.assert_has_prize(p2, first_1600, prizes)
        self.assert_has_no_prize(p3, prizes)

    def test_promotion_warning(self):
        """Test that the priority order is respected"""
        main_category = self.stored_category(
            'all',
            True,
            AveragePrizeSharing(),
            [
                self.stored_prize(200),
                self.stored_prize(100),
            ],
        )

        first_woman = self.stored_prize(70)
        top_women_category = self.stored_category(
            'woman',
            stored_prizes=[first_woman],
            stored_prize_criteria=[
                self.stored_criterion(
                    GenderPlayerFilter([GenderOption(PlayerGender.FEMALE.value)])
                )
            ],
        )

        p1 = self.player(1000, 6, PlayerGender.MALE)
        p2 = self.player(2000, 5, PlayerGender.FEMALE)
        p3 = self.player(1000, 5, PlayerGender.MALE)

        players = [p1, p2, p3]

        prizes = self.assign_prizes([main_category, top_women_category], players)

        self.assert_has_prize_value(p1, 200, prizes)
        self.assert_has_prize(p2, first_woman, prizes, True)
        self.assert_has_prize_value(p3, 100, prizes)

    # ---------------------------------------------------------------------------------
    # Criteria
    # ---------------------------------------------------------------------------------

    def test_gender_criterion(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            GenderPlayerFilter([GenderOption(PlayerGender.FEMALE.value)])
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, PlayerGender.FEMALE)
        p2 = self.player(1000, 5, PlayerGender.FEMALE)
        p3 = self.player(1000, 6, PlayerGender.MALE)
        p4 = self.player(1000, 4, PlayerGender.MALE)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_rating_criterion_min(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(RatingPlayerFilter([MinRatingOption(1200)]))
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1300, 3)
        p2 = self.player(1200, 5)
        p3 = self.player(1100, 6)
        p4 = self.player(1000, 4)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_rating_criterion_max(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(RatingPlayerFilter([MaxRatingOption(1100)]))
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1100, 3)
        p2 = self.player(1000, 5)
        p3 = self.player(1200, 6)
        p4 = self.player(1300, 4)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_rating_criterion_min_max(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            RatingPlayerFilter([MinRatingOption(1100), MaxRatingOption(1300)])
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1100, 3)
        p2 = self.player(1200, 5)
        p3 = self.player(1000, 6)
        p4 = self.player(1400, 4)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_age_criterion_single(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            AgePlayerFilter([AgeCategoriesOption([PlayerCategory.U14.value])])
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, year_of_birth=2012)
        p2 = self.player(1000, 5, year_of_birth=2011)
        p3 = self.player(1000, 6, year_of_birth=2010)
        p4 = self.player(1000, 4, year_of_birth=2013)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_age_criterion_multi(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            AgePlayerFilter(
                [
                    AgeCategoriesOption(
                        [PlayerCategory.U14.value, PlayerCategory.U12.value]
                    )
                ]
            )
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, year_of_birth=2012)
        p2 = self.player(1000, 5, year_of_birth=2013)
        p3 = self.player(1000, 6, year_of_birth=2010)
        p4 = self.player(1000, 4, year_of_birth=2015)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_age_criterion_lower(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            AgePlayerFilter(
                [
                    AgeCategoriesOption([PlayerCategory.U14.value]),
                    AgeLowerOption(True),
                ]
            )
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, year_of_birth=2012)
        p2 = self.player(1000, 5, year_of_birth=2015)
        p3 = self.player(1000, 6, year_of_birth=2010)
        p4 = self.player(1000, 4, year_of_birth=2009)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_age_criterion_greater(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            AgePlayerFilter(
                [
                    AgeCategoriesOption([PlayerCategory.O50.value]),
                    AgeGreaterOption(True),
                ]
            )
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, year_of_birth=1974)
        p2 = self.player(1000, 5, year_of_birth=1959)
        p3 = self.player(1000, 6, year_of_birth=2000)
        p4 = self.player(1000, 4, year_of_birth=1980)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_club_criterion_single(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        filter_in = 'Filtered in club'
        filter_out = 'Filtered out club'
        criterion = self.stored_criterion(
            ClubPlayerFilter([ClubsFilterOption([Club(filter_in).to_query_param])])
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, club=filter_in)
        p2 = self.player(1000, 5, club=filter_in)
        p3 = self.player(1000, 6, club=filter_out)
        p4 = self.player(1000, 4, club=filter_out)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_club_criterion_multi(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        filter_in_1 = 'Filtered in club 1'
        filter_in_2 = 'Filtered in club 2'
        filter_out = 'Filtered out club'
        criterion = self.stored_criterion(
            ClubPlayerFilter(
                [
                    ClubsFilterOption(
                        [
                            Club(filter_in_1).to_query_param,
                            Club(filter_in_2).to_query_param,
                        ]
                    )
                ]
            )
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, club=filter_in_1)
        p2 = self.player(1000, 5, club=filter_in_2)
        p3 = self.player(1000, 6, club=filter_out)
        p4 = self.player(1000, 4, club=filter_out)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_federation_criterion_single(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            FederationPlayerFilter(
                [FederationsFilterOption([Federation('FRA').to_query_param])]
            )
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, federation='FRA')
        p2 = self.player(1000, 5, federation='FRA')
        p3 = self.player(1000, 6, federation='BEL')
        p4 = self.player(1000, 4, federation='FID')
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_federation_criterion_multi(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            FederationPlayerFilter(
                [
                    FederationsFilterOption(
                        [
                            Federation('FRA').to_query_param,
                            Federation('BEL').to_query_param,
                        ]
                    )
                ]
            )
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, federation='FRA')
        p2 = self.player(1000, 5, federation='BEL')
        p3 = self.player(1000, 6, federation='GER')
        p4 = self.player(1000, 4, federation='FID')
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_ffe_league_criterion_single(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            FfeLeaguePlayerFilter([FfeLeaguesFilterOption(['BRE'])])
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, ffe_league='BRE')
        p2 = self.player(1000, 5, ffe_league='BRE')
        p3 = self.player(1000, 6, ffe_league='IDF')
        p4 = self.player(1000, 4, ffe_league='BFC')
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_ffe_league_criterion_multi(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            FfeLeaguePlayerFilter([FfeLeaguesFilterOption(['BRE', 'BFC'])])
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, ffe_league='BRE')
        p2 = self.player(1000, 5, ffe_league='BFC')
        p3 = self.player(1000, 6, ffe_league='IDF')
        p4 = self.player(1000, 4, ffe_league='CRS')
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_rating_type_criterion_single(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            RatingTypePlayerFilter(
                [RatingTypesFilterOption([PlayerRatingType.ESTIMATED.value])]
            )
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, rating_type=PlayerRatingType.ESTIMATED)
        p2 = self.player(1000, 5, rating_type=PlayerRatingType.ESTIMATED)
        p3 = self.player(1000, 6, rating_type=PlayerRatingType.FIDE)
        p4 = self.player(1000, 4, rating_type=PlayerRatingType.NATIONAL)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

    def test_rating_type_criterion_multi(self):
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            RatingTypePlayerFilter(
                [
                    RatingTypesFilterOption(
                        [
                            PlayerRatingType.FIDE.value,
                            PlayerRatingType.NATIONAL.value,
                        ]
                    )
                ]
            )
        )
        category = self.stored_category(
            stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 3, rating_type=PlayerRatingType.FIDE)
        p2 = self.player(1000, 5, rating_type=PlayerRatingType.NATIONAL)
        p3 = self.player(1000, 6, rating_type=PlayerRatingType.ESTIMATED)
        p4 = self.player(1000, 4, rating_type=PlayerRatingType.ESTIMATED)
        players = [p1, p2, p3, p4]

        prizes = self.assign_prizes([category], players)

        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)
