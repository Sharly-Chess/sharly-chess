from dataclasses import dataclass
from functools import cached_property
from typing import Any

from common.i18n import _
from data.player import TournamentPlayer
from data.print_documents import PrintOption, IndividualTeamType
from data.print_documents.documents import (
    RoundPrintOption,
    TournamentPrintOption,
    IndividuelTeamRankingPrintDocument,
)
from data.print_documents.options import (
    IndividualTeamMaxPerEntityPrintOption,
    IndividualTeamDisplayIncompletePrintOption,
)
from data.print_documents.teams import IndividualTeam
from plugins.fra_schools.fra_schools_controller import FRASchool, FRASchoolsUtils


@dataclass
class FraSchoolsIndividualTeam(IndividualTeam[FRASchool]):
    @property
    def school(self) -> FRASchool:
        return self.entity

    @property
    def base_id(self) -> str:
        return self.school.name

    @property
    def base_name(self) -> str:
        return self.school.name

    @property
    def name(self) -> str:
        name = super().name
        if self.school.city:
            name += f', {self.school.city}'
        return name

    @property
    def missing_women_str(self) -> str:
        return _('Missing girls: {count}').format(count=self.missing_women)

    @property
    def missing_men_str(self) -> str:
        """Returns the number of missing men as a printable string."""
        return _('Missing boys: {count}').format(count=self.missing_men)


class FraSchoolsIndividualTeamType(IndividualTeamType):
    @staticmethod
    def static_id() -> str:
        return 'fra-schools-team-type'

    @staticmethod
    def static_name() -> str:
        return _('French schools (FRA)')

    @property
    def team_class(self) -> type:
        return FraSchoolsIndividualTeam

    @staticmethod
    def get_player_entity(player: TournamentPlayer) -> Any | None:
        player_plugin_data = FRASchoolsUtils.get_player_plugin_data(player)
        school_id: int | None = player_plugin_data.fra_school_id
        if not school_id:
            return None
        plugin_data = FRASchoolsUtils.get_event_plugin_data(player.event)
        try:
            return plugin_data.fra_schools_by_id[school_id]
        except KeyError:
            return None

    @staticmethod
    def document_title(round_: int) -> str:
        return _('Ranking by school after round #{round}').format(round=round_)

    @property
    def overall_table_header(self) -> str:
        return _('School')

    @property
    def modal_info_display_incomplete_tooltip(self) -> str:
        return _(
            'Teams are considered complete when they have 8 players including 2 boys and 2 girls.'
        )

    @property
    def modal_info_max_per_entity_label(self) -> str:
        return _('Number of teams per school:')

    @property
    def modal_info_max_per_entity_tooltip(self) -> str:
        return _('The maximum number of teams per school.')


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
            IndividualTeamMaxPerEntityPrintOption,
            IndividualTeamDisplayIncompletePrintOption,
        ]

    @property
    def team_type(self) -> IndividualTeamType:
        return FraSchoolsIndividualTeamType()

    @cached_property
    def rank_incomplete_teams_first(self) -> bool:
        return True

    @property
    def team_size(self) -> int:
        return 8

    @property
    def min_gender_count(self) -> int:
        return 2

    @property
    def youngest_team_last_tie_break(self) -> bool:
        return True
