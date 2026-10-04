from types import UnionType
from typing import override

from common.exception import OptionError
from common.i18n import _
from data.player import TournamentPlayer
from data.print_documents import IndividualTeamType, PrintOption
from data.print_documents.documents import IndividuelTeamRankingPrintDocument
from data.print_documents.options import (
    TournamentPrintOption,
    RoundPrintOption,
    IndividualTeamDisplayIncompletePrintOption,
    IndividualTeamMaxPerEntityPrintOption,
)
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.utils import FRASchool, FRASchoolsUtils


class FraSchoolsIndividualTeamType(IndividualTeamType[FRASchool]):
    @staticmethod
    def static_id() -> str:
        return 'fra-schools-team-type'

    @staticmethod
    def static_name() -> str:
        return _('French schools (FRA)')

    @staticmethod
    def get_player_entity(player: TournamentPlayer) -> FRASchool | None:
        player_plugin_data = FRASchoolsUtils.get_player_plugin_data(player)
        school_id: int | None = player_plugin_data.fra_school_id
        if not school_id:
            return None
        plugin_data = FRASchoolsUtils.get_event_plugin_data(player.event)
        try:
            return plugin_data.fra_schools_by_id[school_id]
        except KeyError:
            return None

    def get_team_base_id(self, school: FRASchool) -> str:
        return str(school.id)

    def get_team_base_name(self, school: FRASchool) -> str:
        return school.name

    def get_team_name_suffix(self, school: FRASchool, is_title: bool) -> str | None:
        if not school.city:
            return None
        suffix = school.city
        if is_title and school.postal_code:
            suffix += f' ({school.postal_code})'
        return suffix

    @staticmethod
    def document_title(round_: int) -> str:
        return _('Ranking by school after round #{round}').format(round=round_)

    @property
    def overall_table_header(self) -> str:
        return _('School')

    @property
    def max_per_entity_label(self) -> str:
        return _('Max. teams per school:')

    @property
    def missing_women_label(self) -> str:
        return _('Missing girls')

    @property
    def missing_men_label(self) -> str:
        return _('Missing boys')


FRA_SCHOOLS_CATEGORY_PRIMARY_MIDDLE = 'primary-middle'
FRA_SCHOOLS_CATEGORY_HIGH = 'high'


class FRASchoolsCategoryPrintOption(PrintOption[str]):
    """J03 art. 2.3.2: the per-school ranking counts the 8 best pupils of a
    primary or middle school, including the first 2 girls and the first 2
    boys, and the 4 best of a high school, including the first girl and the
    first boy."""

    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-category'

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> str:
        return FRA_SCHOOLS_CATEGORY_PRIMARY_MIDDLE

    @property
    def template_name(self) -> str:
        return '/fra_schools_category.html'

    @property
    def category_options(self) -> dict[str, str]:
        return {
            FRA_SCHOOLS_CATEGORY_PRIMARY_MIDDLE: _('Primary and middle schools'),
            FRA_SCHOOLS_CATEGORY_HIGH: _('High schools'),
        }

    @property
    def is_high_school(self) -> bool:
        return self.value == FRA_SCHOOLS_CATEGORY_HIGH

    @override
    def validate(self) -> None:
        super().validate()
        if self.value not in self.category_options:
            # Untranslated, should not happen
            raise OptionError(f'Unknown category: {self.value}', self)


class FRASchoolsIndividualTeamMaxPerSchoolPrintOption(
    IndividualTeamMaxPerEntityPrintOption
):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-individual-team-max-per-school'

    @property
    def template_name(self) -> str:
        return '/fra_schools_individual_team_max_per_school.html'


class FRASchoolsIndividualTeamDisplayIncompletePrintOption(
    IndividualTeamDisplayIncompletePrintOption
):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-individual-team-display-incomplete'

    @property
    def template_name(self) -> str:
        return '/fra_schools_individual_team_display_incomplete.html'


class FraSchoolsRankingPrintDocument(IndividuelTeamRankingPrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'fra-schools-ranking'

    @staticmethod
    def static_name() -> str:
        return _('FFE Scholar Championship')

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [
            TournamentPrintOption,
            RoundPrintOption,
            FRASchoolsCategoryPrintOption,
            FRASchoolsIndividualTeamMaxPerSchoolPrintOption,
            FRASchoolsIndividualTeamDisplayIncompletePrintOption,
        ]

    @property
    def display_incomplete_teams(self) -> bool:
        return self._get_option(
            FRASchoolsIndividualTeamDisplayIncompletePrintOption
        ).value

    @property
    def max_teams_per_entity(self) -> int | None:
        return self._get_option(FRASchoolsIndividualTeamMaxPerSchoolPrintOption).value

    @property
    def team_type(self) -> IndividualTeamType:
        return FraSchoolsIndividualTeamType()

    @property
    def team_size(self) -> int:
        return (
            4 if self._get_option(FRASchoolsCategoryPrintOption).is_high_school else 8
        )

    @property
    def min_gender_count(self) -> int:
        return (
            1 if self._get_option(FRASchoolsCategoryPrintOption).is_high_school else 2
        )

    @property
    def youngest_team_last_tie_break(self) -> bool:
        return True
