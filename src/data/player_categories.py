import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from functools import total_ordering
from typing import TYPE_CHECKING

from common.i18n import _

if TYPE_CHECKING:
    from data.event import Event


@total_ordering
class PlayerCategory(ABC):
    def __init__(self, age_limit: int):
        self.age_limit = age_limit

    @property
    @abstractmethod
    def id(self) -> str:
        """Represents the category in the database and the form."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Represents the category in the UI."""

    @property
    @abstractmethod
    def _representative_age(self) -> int:
        """Get an age that always is in the category."""

    @staticmethod
    def get_junior_categories(age_limits: list[int]) -> list['JuniorCategory']:
        return [JuniorCategory(age_limit) for age_limit in age_limits]

    @staticmethod
    def get_senior_categories(age_limits: list[int]) -> list['SeniorCategory']:
        return [SeniorCategory(age_limit) for age_limit in age_limits]

    @classmethod
    def get_categories(
        cls, junior_age_limits: list[int], senior_age_limits: list[int]
    ) -> list['PlayerCategory']:
        categories: list[PlayerCategory] = []
        categories += cls.get_junior_categories(junior_age_limits)
        categories += cls.get_senior_categories(senior_age_limits)
        return categories

    @classmethod
    def from_id(cls, category_id: str) -> 'PlayerCategory':
        if category_id == NoCategory().id:
            return NoCategory()
        if not re.match(r'^[UO]\d+$', category_id):
            raise ValueError(f'{category_id=}')
        age_limit = int(category_id[1:])
        if category_id[0] == 'U':
            return JuniorCategory(age_limit)
        else:
            return SeniorCategory(age_limit)

    @staticmethod
    def _reference_year(
        event: 'Event',
        tournament_start: date,
        tournament_stop: date,
    ) -> int:
        if event.age_category_base_date:
            ref_date = event.age_category_base_date
        else:
            if (tournament_stop - tournament_start) > timedelta(days=30):
                base = date.today()
                if base < tournament_start:
                    ref_date = tournament_start
                elif base > tournament_stop:
                    ref_date = tournament_stop
                else:
                    ref_date = base
            else:
                ref_date = tournament_start
        ref_year = ref_date.year
        if 1 < event.age_category_change_month <= ref_date.month:
            ref_year += 1
        return ref_year

    @classmethod
    def from_year_of_birth(
        cls,
        event: 'Event',
        year_of_birth: int | None,
        tournament_start: date,
        tournament_stop: date,
        junior_categories: list['JuniorCategory'] | None = None,
        senior_categories: list['SeniorCategory'] | None = None,
    ) -> 'PlayerCategory':
        if not year_of_birth:
            return NoCategory()
        if not junior_categories:
            junior_categories = event.junior_categories
        if not senior_categories:
            senior_categories = event.senior_categories
        ref_year = cls._reference_year(event, tournament_start, tournament_stop)
        age = ref_year - year_of_birth
        junior_category = next(
            (category for category in junior_categories if age <= category.age_limit),
            None,
        )
        if junior_category:
            return junior_category
        return next(
            category for category in senior_categories[::-1] if age > category.age_limit
        )

    def representative_year(
        self,
        event: 'Event',
        tournament_start: date,
        tournament_stop: date,
    ) -> int:
        ref_year = self._reference_year(event, tournament_start, tournament_stop)
        return ref_year - self._representative_age

    def __hash__(self):
        return hash(self.id)

    def __lt__(self, other):
        if not isinstance(other, PlayerCategory):
            return NotImplemented
        is_senior = isinstance(self, SeniorCategory)
        other_is_senior = isinstance(other, SeniorCategory)
        if is_senior and not other_is_senior:
            return False
        if other_is_senior and not is_senior:
            return True
        return self.age_limit < other.age_limit

    def __eq__(self, other):
        if not isinstance(other, PlayerCategory):
            return NotImplemented
        return self.id == other.id

    def __repr__(self):
        return f'{self.__class__.__name__}({self.age_limit})'


class NoCategory(PlayerCategory):
    def __init__(self):
        super().__init__(0)

    @property
    def id(self) -> str:
        return 'NONE'

    @property
    def name(self) -> str:
        return '-'

    @property
    def _representative_age(self) -> int:
        return 0


class JuniorCategory(PlayerCategory):
    @property
    def id(self) -> str:
        return f'U{self.age_limit}'

    @property
    def name(self) -> str:
        return _('U{age_limit} *** YOUTH AGE CATEGORY').format(age_limit=self.age_limit)

    @property
    def _representative_age(self) -> int:
        return self.age_limit


class SeniorCategory(PlayerCategory):
    @property
    def id(self) -> str:
        return f'O{self.age_limit}'

    @property
    def name(self) -> str:
        return _('{age_limit}+ *** SENIOR AGE CATEGORY').format(
            age_limit=self.age_limit
        )

    @property
    def _representative_age(self) -> int:
        return self.age_limit + 1


@dataclass
class PlayerCategorySet:
    id: int
    name: str
    categories: list[PlayerCategory]
    is_default: bool = False

    @property
    def categories_str(self) -> str:
        return ', '.join(category.name for category in self.categories)

    @property
    def category_ids(self) -> list[str]:
        return [category.id for category in self.categories]

    @property
    def form_key(self) -> str:
        return f'category-set-{self.id}'


SELECTABLE_JUNIOR_CATEGORIES = PlayerCategory.get_junior_categories(
    [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
)


SELECTABLE_SENIOR_CATEGORIES = PlayerCategory.get_senior_categories(
    [50, 55, 60, 65, 70, 75]
)


EVEN_PRESET_CATEGORIES = PlayerCategory.get_categories(
    [8, 10, 12, 14, 16, 18, 20], [50, 65]
)


ODD_PRESET_CATEGORIES: list[PlayerCategory] = PlayerCategory.get_categories(
    [7, 9, 11, 13, 15, 17, 19], [50, 65]
)
