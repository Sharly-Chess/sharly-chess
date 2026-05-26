import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from statistics import mean
from typing import Any

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.player import TournamentPlayer
from data.tournament import Tournament
from utils.entity import IdentifiableEntity
from utils.enum import PlayerGender


@dataclass
class IndividualTeam:
    tournament: Tournament
    team_size: int
    min_gender_count: int
    entity: Any
    label: str
    players: list[TournamentPlayer]
    type: 'IndividualTeamType'

    @property
    def base_id(self) -> str:
        return self.type.get_team_base_id(self.entity)

    @property
    def base_name(self) -> str:
        return self.type.get_team_base_name(self.entity)

    @property
    def id(self) -> str:
        """Returns the ID"""
        id_ = re.sub('[^A-Za-z0-9]', '-', self.base_id)
        if self.label:
            id_ += f'-{self.label}'
        return id_

    @property
    def name(self) -> str:
        return self.type.build_team_name(self.entity, self.label)

    @property
    def title_name(self) -> str:
        return self.type.build_team_name(self.entity, self.label, is_title=True)

    def _missing_gender(self, gender: PlayerGender) -> int:
        return max(
            self.min_gender_count
            - len([player for player in self.players if player.gender == gender]),
            0,
        )

    @cached_property
    def missing_women(self) -> int:
        """Returns the number of missing women."""
        return self._missing_gender(PlayerGender.WOMAN)

    @cached_property
    def missing_men(self) -> int:
        """Returns the number of missing men."""
        return self._missing_gender(PlayerGender.MAN)

    @property
    def missing_any(self) -> int:
        """Returns the number of missing players."""
        return (
            self.team_size - len(self.players) - self.missing_men - self.missing_women
        )

    @property
    def missing_women_str(self) -> str:
        """Returns the number of missing women as a printable string."""
        return _('{string}: {value}').format(
            string=self.type.missing_women_label,
            value=self.missing_women,
        )

    @property
    def missing_men_str(self) -> str:
        """Returns the number of missing men as a printable string."""
        return _('{string}: {value}').format(
            string=self.type.missing_men_label,
            value=self.missing_men,
        )

    @property
    def missing_any_str(self) -> str:
        """Returns the number of missing players as a printable string."""
        return _('Other missing players: {count}').format(count=self.missing_any)

    @property
    def is_complete(self) -> bool:
        """Returns True if the team is complete."""
        return len(self.players) == self.team_size

    @cached_property
    def total_points(self) -> float:
        """Returns The total number of points of the team."""
        total_points: float = 0.0
        for player in self.players:
            if player.points:
                total_points += player.points
        return total_points

    @cached_property
    def tie_break_sums(self) -> list[float]:
        """Returns the sums of the tie-breaks."""
        # sum over contributors
        tie_breaks_count: int = len(self.tournament.team_ranking_tie_breaks)
        tie_break_sums: list[float] = [0.0] * tie_breaks_count
        for player in self.players:
            for tie_break_idx in range(tie_breaks_count):
                val = player.team_ranking_tie_break_values[tie_break_idx].value
                tie_break_sums[tie_break_idx] += float(val) if val is not None else 0.0
        return tie_break_sums

    @cached_property
    def avg_age_years(self) -> float | None:
        """Returns the average age of the team, in years (or None if no DOB/YOB)."""
        today = date.today()
        ages = []
        for player in self.players:
            dob: date | None = None
            if player.date_of_birth:
                dob = player.date_of_birth
            elif player.year_of_birth:
                dob = date(player.year_of_birth, 1, 1)
            if dob:
                # Compute precise age in years (fractional)
                age = (today - dob).days / 365.2425  # average solar year
                ages.append(age)
        return mean(ages) if ages else None


class IndividualTeamType[T](IdentifiableEntity, ABC):
    @staticmethod
    @abstractmethod
    def document_title(round_: int) -> str:
        """Returns the main title of the document."""

    @property
    @abstractmethod
    def overall_table_header(self) -> str:
        """Returns the string used for the team column header."""

    @staticmethod
    @abstractmethod
    def get_player_entity(player: TournamentPlayer) -> T | None:
        """Returns the entity the player belongs to (club, federation...), or None."""

    @abstractmethod
    def get_team_base_id(self, entity: T) -> str:
        """Get the base id of a team from an entity."""

    @abstractmethod
    def get_team_base_name(self, entity: T) -> str:
        """Get the base name of a team from an entity."""

    def get_team_name_suffix(self, entity: T, is_title: bool) -> str | None:
        """Get a suffix to add to the team name."""
        return None

    def build_team_name(self, entity: T, label: str, is_title: bool = False) -> str:
        """Get the name of a team from an entity and its label."""
        name = self.get_team_base_name(entity)
        if label:
            name += f' <span class="team-label">{label}</span>'
            suffix = self.get_team_name_suffix(entity, is_title)
            if suffix:
                name += f', <span class="team-suffix">{suffix}</span>'
        return name

    @property
    def missing_women_label(self) -> str:
        """Label used to represent the number of missing women."""
        return _('Missing women')

    @property
    def missing_men_label(self) -> str:
        """Label used to represent the number of missing men."""
        return _('Missing men')

    @property
    @abstractmethod
    def max_per_entity_label(self) -> str:
        """Returns the label to use on the document modal for the "Max teams:" input."""


class ClubIndividualTeamType(IndividualTeamType[str]):
    @staticmethod
    def static_id() -> str:
        return 'club-team-type'

    @staticmethod
    def static_name() -> str:
        return _('Clubs')

    @staticmethod
    def get_player_entity(player: TournamentPlayer) -> str | None:
        return player.club.name or None

    def get_team_base_id(self, club: str) -> str:
        return club

    def get_team_base_name(self, club: str) -> str:
        return club

    @staticmethod
    def document_title(round_: int) -> str:
        return _('Ranking by club after round #{round}').format(round=round_)

    @property
    def overall_table_header(self) -> str:
        return _('Club')

    @property
    def max_per_entity_label(self) -> str:
        return _('Max. teams per club:')


class FederationIndividualTeamType(IndividualTeamType[str]):
    @staticmethod
    def static_id() -> str:
        return 'federation-team-type'

    @staticmethod
    def static_name() -> str:
        return _('Federations')

    @staticmethod
    def get_player_entity(player: TournamentPlayer) -> str | None:
        return player.federation.name or None

    def get_team_base_id(self, federation: str) -> str:
        return federation

    def get_team_base_name(self, federation: str) -> str:
        return SharlyChessConfig().federations[federation]

    @staticmethod
    def document_title(round_: int) -> str:
        return _('Ranking by federation after round #{round}').format(round=round_)

    @property
    def overall_table_header(self) -> str:
        return _('Federation')

    @property
    def max_per_entity_label(self) -> str:
        return _('Max. teams per federation:')
