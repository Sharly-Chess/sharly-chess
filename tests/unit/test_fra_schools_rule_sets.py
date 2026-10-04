"""The French school championship's team format follows its category:
écoles and collèges field 8 boards, lycées 4."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest import TestCase

import pytest

from plugins.fra_schools.fra_schools_rule_sets import ChampionnatScolaireRuleSet
from utils.enum import PlayerGender, PlayerRatingType, TournamentRating
from utils.types import PlayerRatingAndType

if TYPE_CHECKING:
    from data.player import Player
    from data.teams.team import Team


def team_of(*genders: PlayerGender) -> 'Team':
    players = [
        SimpleNamespace(full_name=f'Player {index}', gender=gender)
        for index, gender in enumerate(genders)
    ]
    return cast('Team', SimpleNamespace(players=players))


@pytest.mark.unit
class CategoryFormatTestCase(TestCase):
    def test_primary_and_middle_schools_field_eight_boards_from_ten(self) -> None:
        for category in ('ecoles', 'colleges'):
            rule_set = ChampionnatScolaireRuleSet({'category': category})
            defaults = rule_set.form_defaults()
            self.assertEqual(defaults['team_player_count'], '8')
            self.assertEqual(defaults['roster_max_size'], '10')
            self.assertEqual(rule_set.roster_max_size, 10)

    def test_high_schools_field_four_boards_from_five(self) -> None:
        rule_set = ChampionnatScolaireRuleSet({'category': 'lycees'})
        defaults = rule_set.form_defaults()
        self.assertEqual(defaults['team_player_count'], '4')
        self.assertEqual(defaults['roster_max_size'], '5')
        self.assertEqual(rule_set.roster_max_size, 5)

    def test_the_default_category_is_primary_schools(self) -> None:
        defaults = ChampionnatScolaireRuleSet({}).form_defaults()
        self.assertEqual(defaults['team_player_count'], '8')

    def test_an_exempt_team_wins_5_to_0_on_8_boards(self) -> None:
        for category in ('ecoles', 'colleges'):
            defaults = ChampionnatScolaireRuleSet(
                {'category': category}
            ).form_defaults()
            self.assertEqual(defaults['gp_pab'], '5')

    def test_an_exempt_high_school_team_wins_3_to_0(self) -> None:
        defaults = ChampionnatScolaireRuleSet({'category': 'lycees'}).form_defaults()
        self.assertEqual(defaults['gp_pab'], '3')

    def test_players_are_rated_on_the_rapid_list(self) -> None:
        rule_set = ChampionnatScolaireRuleSet({})
        self.assertIn('rating', rule_set.managed_fields)
        self.assertEqual(
            rule_set.form_defaults()['rating'], str(TournamentRating.RAPID.value)
        )

    def test_game_points_decide_colours(self) -> None:
        rule_set = ChampionnatScolaireRuleSet({})
        self.assertIn('secondary_score_for_colours', rule_set.managed_fields)
        self.assertEqual(rule_set.form_defaults()['secondary_score_for_colours'], 'on')


@pytest.mark.unit
class GenderBalanceTestCase(TestCase):
    def test_primary_schools_need_two_girls_and_two_boys(self) -> None:
        rule_set = ChampionnatScolaireRuleSet({'category': 'ecoles'})
        team = team_of(PlayerGender.MAN, PlayerGender.WOMAN, PlayerGender.WOMAN)
        self.assertEqual(len(rule_set._gender_balance_warnings(team)), 1)

    def test_high_schools_need_one_girl_and_one_boy(self) -> None:
        rule_set = ChampionnatScolaireRuleSet({'category': 'lycees'})
        self.assertEqual(
            rule_set._gender_balance_warnings(
                team_of(PlayerGender.MAN, PlayerGender.WOMAN)
            ),
            [],
        )
        self.assertEqual(
            len(
                rule_set._gender_balance_warnings(
                    team_of(PlayerGender.MAN, PlayerGender.MAN)
                )
            ),
            1,
        )


def player_rated(value: int, rating_type: PlayerRatingType) -> 'Player':
    return cast(
        'Player',
        SimpleNamespace(
            event_default_rating_and_type=PlayerRatingAndType(value, rating_type)
        ),
    )


@pytest.mark.unit
class TeamAverageRatingTestCase(TestCase):
    def test_an_estimated_rating_counts_for_the_category_value(self) -> None:
        for category, expected in (
            ('ecoles', 799),
            ('colleges', 999),
            ('lycees', 1199),
        ):
            rule_set = ChampionnatScolaireRuleSet({'category': category})
            self.assertEqual(
                rule_set.player_rating_in_team_average(
                    player_rated(1099, PlayerRatingType.ESTIMATED)
                ),
                expected,
            )

    def test_a_real_rating_counts_as_it_is(self) -> None:
        rule_set = ChampionnatScolaireRuleSet({'category': 'ecoles'})
        for rating_type in (PlayerRatingType.NATIONAL, PlayerRatingType.FIDE):
            self.assertEqual(
                rule_set.player_rating_in_team_average(player_rated(1350, rating_type)),
                1350,
            )


@pytest.mark.unit
class TeamAverageRatingExplanationTestCase(TestCase):
    def test_estimated_ratings_are_explained(self) -> None:
        rule_set = ChampionnatScolaireRuleSet({'category': 'colleges'})
        team = cast(
            'Team',
            SimpleNamespace(
                players=[
                    player_rated(1350, PlayerRatingType.NATIONAL),
                    player_rated(1099, PlayerRatingType.ESTIMATED),
                    player_rated(1199, PlayerRatingType.ESTIMATED),
                ]
            ),
        )
        explanation = rule_set.team_average_rating_explanation(team)
        assert explanation is not None
        self.assertIn('2', explanation)
        self.assertIn('999', explanation)

    def test_a_fully_rated_team_has_no_explanation(self) -> None:
        rule_set = ChampionnatScolaireRuleSet({'category': 'colleges'})
        team = cast(
            'Team',
            SimpleNamespace(players=[player_rated(1350, PlayerRatingType.NATIONAL)]),
        )
        self.assertIsNone(rule_set.team_average_rating_explanation(team))
