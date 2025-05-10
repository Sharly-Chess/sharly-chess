import math
from typing import TYPE_CHECKING

from common.i18n import _
from data.pairings.settings import PairingSetting
from database.access.papi.papi_database import PapiDatabase, PapiVariable
from plugins.pairing_acceleration import PLUGIN_NAME

if TYPE_CHECKING:
    from data.tournament import Tournament


class RatingLimitSetting(PairingSetting[int]):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-rating_limit'

    @staticmethod
    def static_name() -> str:
        return _('Rating limit')

    @property
    def template_path(self) -> str:
        return f'/{PLUGIN_NAME}/rating_limit.html'

    def tooltip_representation(self, value: int) -> str | None:
        if value != 0:
            return str(value)
        return None

    def from_form_data(self, data: dict[str, str]) -> int:
        return int(data[self.id])

    def to_form_data(self, object_: int) -> dict[str, str]:
        return {self.id: str(object_)}

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        if not data.get(self.id, None) or int(data[self.id]) < 0:
            return {self.id: _('A positive integer is expected.')}
        if not self._check_rating_limit(tournament, int(data[self.id])):
            return {
                self.id: _(
                    'Groups must be composed of at least 25%% of players.'
                ).replace('%%', '%')
            }
        return {}

    @classmethod
    def get_value(cls, tournament: 'Tournament') -> int:
        # TODO remove once papi dependency has been removed
        return tournament.papi_tournament_info.rating_limit1

    @classmethod
    def default_value(cls, tournament: 'Tournament') -> int:
        # TODO replace by recommended value once papi dependency has been removed
        return tournament.papi_tournament_info.rating_limit1

    @classmethod
    def recommended_value(cls, tournament: 'Tournament') -> int:
        ratings = cls.player_ratings(tournament)
        if len(ratings) < 2:
            return 0
        first_b = len(ratings) // 2 - 1
        return math.ceil((ratings[first_b] + ratings[first_b + 1]) / 2)

    @classmethod
    def is_valid(cls, tournament: 'Tournament') -> bool:
        return cls._check_rating_limit(
            tournament, tournament.papi_tournament_info.rating_limit1
        )

    @staticmethod
    def player_ratings(tournament: 'Tournament') -> list[int]:
        return sorted(player.rating for player in tournament.players)

    @classmethod
    def group_counts(
        cls, tournament: 'Tournament', rating_limit: int
    ) -> tuple[int, int]:
        """Number of players in groups A and B."""
        ratings = cls.player_ratings(tournament)
        group_a = len([rating for rating in ratings if rating_limit <= rating])
        return group_a, len(ratings) - group_a

    @classmethod
    def _check_rating_limit(cls, tournament: 'Tournament', rating_limit: int) -> bool:
        a_group, b_group = cls.group_counts(tournament, rating_limit)
        total = a_group + b_group
        return total < 2 or total / 4 <= b_group <= 3 * total / 4

    def save_to_papi_database(self, papi_database: PapiDatabase, object_: int):
        with papi_database:
            papi_database.write_info({PapiVariable.RATING_LIMIT1: object_})
            papi_database.commit()


class DualRatingLimitsSetting(PairingSetting[tuple[int, int]]):
    lower_limit_field = 'lower-limit-field'
    upper_limit_field = 'upper-limit-field'

    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-dual_rating_limits'

    @staticmethod
    def static_name() -> str:
        return _('Rating limits')

    @property
    def template_path(self) -> str:
        return f'/{PLUGIN_NAME}/dual_rating_limits.html'

    def tooltip_representation(self, value: tuple[int, int]) -> str | None:
        if value != (0, 0):
            return f'{value[0]} - {value[1]}'
        return None

    def from_form_data(self, data: dict[str, str]) -> tuple[int, int]:
        return (
            int(data[self.lower_limit_field]),
            int(data[self.upper_limit_field]),
        )

    def to_form_data(self, object_: tuple[int, int]) -> dict[str, str]:
        return {
            self.lower_limit_field: str(object_[0]),
            self.upper_limit_field: str(object_[1]),
        }

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        for field in (self.lower_limit_field, self.upper_limit_field):
            if not data.get(field, None) or int(data[field]) < 0:
                return {field: _('A positive integer is expected.')}

        lower_limit = int(data[self.lower_limit_field])
        upper_limit = int(data[self.upper_limit_field])
        if lower_limit >= upper_limit:
            return {
                self.upper_limit_field: _(
                    'Upper limit expected to be greater than lower limit.'
                )
            }
        group_counts = self.group_counts(tournament, (lower_limit, upper_limit))
        for index, group_count in enumerate(group_counts):
            if self._check_group_count(group_count, sum(group_counts)):
                continue
            field = self.lower_limit_field if index <= 1 else self.upper_limit_field
            return {
                field: _(
                    'Groups must be composed of at least '
                    '25%% and at most 50%% of players.'
                ).replace('%%', '%')
            }
        return {}

    @classmethod
    def papi_limits(cls, tournament: 'Tournament') -> tuple[int, int]:
        # TODO remove once papi dependency has been removed
        return (
            tournament.papi_tournament_info.rating_limit2,
            tournament.papi_tournament_info.rating_limit1,
        )

    @classmethod
    def get_value(cls, tournament: 'Tournament') -> tuple[int, int]:
        # TODO remove once papi dependency has been removed
        return cls.papi_limits(tournament)

    @classmethod
    def default_value(cls, tournament: 'Tournament') -> tuple[int, int]:
        # TODO replace by recommended value once papi dependency has been removed
        return cls.papi_limits(tournament)

    @classmethod
    def recommended_value(cls, tournament: 'Tournament') -> tuple[int, int]:
        ratings = cls.player_ratings(tournament)
        if len(ratings) < 3:
            return 0, 0
        first_c = len(ratings) // 3 - 1
        first_b = 2 * len(ratings) // 3 - 1
        return (
            math.ceil((ratings[first_c] + ratings[first_c + 1]) / 2),
            math.ceil((ratings[first_b] + ratings[first_b + 1]) / 2),
        )

    @classmethod
    def is_valid(cls, tournament: 'Tournament') -> bool:
        group_counts = cls.group_counts(tournament, cls.papi_limits(tournament))
        return all(
            cls._check_group_count(group_count, sum(group_counts))
            for group_count in group_counts
        )

    @staticmethod
    def player_ratings(tournament: 'Tournament') -> list[int]:
        return sorted(player.rating for player in tournament.players)

    @classmethod
    def group_counts(
        cls, tournament: 'Tournament', rating_limits: tuple[int, int]
    ) -> tuple[int, int, int]:
        """Number of players in groups A, B and C."""
        ratings = cls.player_ratings(tournament)
        group_a = len([rating for rating in ratings if rating_limits[1] <= rating])
        group_c = len([rating for rating in ratings if rating < rating_limits[0]])
        return group_a, max(len(ratings) - (group_a + group_c), 0), group_c

    @classmethod
    def _check_group_count(cls, group_count: int, total: int) -> bool:
        return total < 3 or total / 4 <= group_count <= total / 2

    def save_to_papi_database(
        self, papi_database: PapiDatabase, object_: tuple[int, int]
    ):
        with papi_database:
            papi_database.write_info(
                {
                    PapiVariable.RATING_LIMIT1: object_[1],
                    PapiVariable.RATING_LIMIT2: object_[0],
                }
            )
            papi_database.commit()
