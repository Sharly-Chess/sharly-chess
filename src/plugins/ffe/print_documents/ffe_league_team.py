from dataclasses import dataclass
from typing import Any

from common.i18n import _
from data.player import TournamentPlayer
from data.print_documents import TeamType
from data.print_documents.teams import Team
from plugins.ffe.utils import FFEUtils, FFE_LEAGUES


@dataclass
class FfeLeagueTeam(Team[str]):
    @property
    def league(self) -> str:
        return self.entity

    @property
    def base_id(self) -> str:
        return self.league

    @property
    def base_name(self) -> str:
        name: str = self.league
        if self.league in FFE_LEAGUES:
            name += f' - {FFE_LEAGUES[self.league]}'
        return name


class FfeLeagueTeamType(TeamType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-league-team-type'

    @staticmethod
    def static_name() -> str:
        return _('Leagues (FFE)')

    @property
    def team_class(self) -> type:
        return FfeLeagueTeam

    @staticmethod
    def get_player_entity(player: TournamentPlayer) -> Any | None:
        return FFEUtils.get_player_plugin_data(player).league

    @staticmethod
    def document_title(round_: int) -> str:
        return _('Ranking by league after round #{round}').format(round=round_)

    @property
    def overall_table_header(self) -> str:
        return _('League')

    @property
    def max_teams_per_entity_label(self) -> str:
        return _('Teams per league:')

    @property
    def max_teams_per_entity_tooltip(self) -> str:
        return _('The maximum number of teams per league.')
