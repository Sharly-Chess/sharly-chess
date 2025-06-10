# Needs to be imported first to avoid circular import
from plugins import manager  # Noqa E402

from data.tournament import Tournament

from data.prize.player_filter_options import GenderOption, MaxRatingOption
from data.prize.player_filters import (
    GenderPlayerFilter,
    PlayerFilter,
    RatingPlayerFilter,
)


from data.pairing import Pairing
from data.prize.prize import Prize

from datetime import date
from data.prize.prize_sharing import (
    AveragePrizeSharing,
    HortSystemPrizeSharing,
    NoPrizeSharing,
    PrizeSharing,
)

from data.player import Federation, Player, PlayerRating
from data.prize.prize_group import AssignedPrize
from database.sqlite.event.event_store import (
    StoredPrize,
    StoredPrizeCategory,
    StoredPrizeCriterion,
    StoredPrizeGroup,
    StoredTournament,
)
from utils.enum import (
    BoardColor,
    PlayerGender,
    PlayerRatingType,
    PlayerTitle,
    Result,
    TournamentRating,
)
from utils.tests import BaseTestCase

ROUNDS = 6


class PrizesTestCase(BaseTestCase):
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
        self, stored_categories: list[StoredPrizeCategory], players: list[Player]
    ):
        self.stored_prize_group.stored_prize_categories = stored_categories
        for index, stored_category in enumerate(stored_categories):
            stored_category.index = index
        self.tournament = Tournament(
            self.event,
            StoredTournament(
                uniq_id='empty',
                name='empty',
                id=1,
                path='',
                filename='',
                current_round=ROUNDS,
                stored_prize_groups=[self.stored_prize_group],
            ),
        )
        for index, player in enumerate(players):
            player.id = 1001 + index
            player.tournament = self.tournament
        self.tournament._players = players
        return self.tournament.prize_groups_by_id[1].assign_prizes()

    def player(
        self, elo: int, points: float, gender: PlayerGender = PlayerGender.NONE
    ) -> Player:
        player = Player(
            id=0,
            first_name='A',
            last_name='B' + str(elo),
            date_of_birth=date(1973, 6, 30),
            gender=gender,
            fide_id=None,
            federation=Federation('FRA'),
            title=PlayerTitle.NONE,
            pairings={},
            mail=None,
            phone=None,
            comment=None,
            owed=0,
            paid=0,
            ratings={
                TournamentRating.STANDARD: PlayerRating(elo, PlayerRatingType.FIDE),
                TournamentRating.RAPID: PlayerRating(1199, PlayerRatingType.FIDE),
                TournamentRating.BLITZ: PlayerRating(1199, PlayerRatingType.FIDE),
            },
            club=None,
            fixed=False,
            check_in=False,
        )
        player.points = points
        player.pairings = {}
        for i in range(1, 7):
            result = Result.GAIN if i <= points else Result.LOSS
            player.pairings[i] = Pairing(BoardColor.WHITE, 1, result)
        player.points = points
        return player

    def stored_category(
        self,
        name: str,
        is_main: bool = False,
        prize_sharing: PrizeSharing = NoPrizeSharing(),
        stored_prizes: list[StoredPrize] | None = None,
        stored_prize_criteria: list[StoredPrizeCriterion] | None = None,
    ):
        if not stored_prizes:
            stored_prizes = []
        if not stored_prize_criteria:
            stored_prize_criteria = []
        for index, prize in enumerate(stored_prizes):
            prize.index = index
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
            index=self.criterion_index,
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
            index=self.prize_index,
        )
        self.prize_index += 1
        return prize

    def assert_has_prize(
        self,
        player: Player,
        prize: Prize | StoredPrize,
        prize_list: list[AssignedPrize],
    ):
        self.assertIn(
            player.id,
            [prize.assigned_to.id for prize in prize_list if prize.assigned_to],
        )
        for assigned_prize in prize_list:
            if (p := assigned_prize.assigned_to) is not None and p.id == player.id:
                self.assertIsNotNone(assigned_prize.prize)
                self.assertEqual(
                    assigned_prize.prize and assigned_prize.prize.id, prize.id
                )

    def assert_has_prize_value(
        self, player: Player, value: float, prize_list: list[AssignedPrize]
    ):
        self.assertIn(
            player.id,
            [prize.assigned_to.id for prize in prize_list if prize.assigned_to],
        )
        for prize in prize_list:
            if (p := prize.assigned_to) is not None and p.id == player.id:
                self.assertEqual(prize.value, value)

    def assert_has_no_prize(self, player: Player, prize_list: list[AssignedPrize]):
        self.assertNotIn(
            player.id,
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

        (prizes, warnings) = self.assign_prizes([category], players)

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

        (prizes, warnings) = self.assign_prizes([category], players)

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

        (prizes, warnings) = self.assign_prizes([category], players)

        self.assertEqual(warnings, [])
        self.assert_has_prize_value(p1, (200 + (200 + 100) / 2) / 2, prizes)
        self.assert_has_prize_value(p2, (100 + (200 + 100) / 2) / 2, prizes)
        self.assert_has_prize_value(p3, (60 + 60 / 3) / 2, prizes)
        self.assert_has_prize_value(p4, (0 + 60 / 3) / 2, prizes)
        self.assert_has_prize_value(p5, (0 + 60 / 3) / 2, prizes)
        self.assert_has_no_prize(p6, prizes)

    def test_basic_gender(self):
        """Test the gender filter"""
        prizes = [
            self.stored_prize(200),
            self.stored_prize(100),
        ]
        criterion = self.stored_criterion(
            GenderPlayerFilter([GenderOption(PlayerGender.FEMALE.value)])
        )
        category = self.stored_category(
            'woman', stored_prizes=prizes, stored_prize_criteria=[criterion]
        )

        p1 = self.player(1000, 4, PlayerGender.FEMALE)
        p2 = self.player(1000, 5, PlayerGender.FEMALE)
        p3 = self.player(1000, 6, PlayerGender.MALE)
        p4 = self.player(1000, 1, PlayerGender.MALE)
        players = [p1, p2, p3, p4]

        (prizes, warnings) = self.assign_prizes([category], players)

        self.assertEqual(warnings, [])
        first, second = self.get_prizes()
        self.assert_has_prize(p1, second, prizes)
        self.assert_has_prize(p2, first, prizes)
        self.assert_has_no_prize(p3, prizes)
        self.assert_has_no_prize(p4, prizes)

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

        (prizes, warnings) = self.assign_prizes(
            [main_category, top_women_category], players
        )

        self.assertEqual(warnings, [])

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

        (prizes, warnings) = self.assign_prizes(
            [main_category, top_women_category], players
        )

        self.assertEqual(warnings, [])

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

        (prizes, warnings) = self.assign_prizes(
            [main_category, top_women_category], players
        )

        self.assertEqual(warnings, [])

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

        (prizes, warnings) = self.assign_prizes(
            [main_category, top_women_category], players
        )

        self.assertEqual(warnings, [])

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

        (prizes, warnings) = self.assign_prizes(
            [main_category, elo_category, top_women_category], players
        )

        self.assertEqual(warnings, [])

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

        (prizes, warnings) = self.assign_prizes(
            [elo_category, top_women_category], players
        )

        self.assertEqual(warnings, [])

        # Elo attributed to first woman,
        self.assert_has_prize(p1, first_1600, prizes)
        self.assert_has_no_prize(p2, prizes)
        self.assert_has_no_prize(p3, prizes)

        (prizes, warnings) = self.assign_prizes(
            [top_women_category, elo_category], players
        )

        # Elo attributed to first woman,
        self.assert_has_prize(p1, first_woman, prizes)
        self.assert_has_prize(p2, first_1600, prizes)
        self.assert_has_no_prize(p3, prizes)

    def test_promotion_waring(self):
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

        (prizes, warnings) = self.assign_prizes(
            [main_category, top_women_category], players
        )

        self.assertEqual(len(warnings), 1)

        self.assert_has_prize_value(p1, 200, prizes)
        self.assert_has_prize(p2, first_woman, prizes)
        self.assert_has_prize_value(p3, 100, prizes)
