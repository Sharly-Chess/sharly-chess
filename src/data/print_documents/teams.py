import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from statistics import mean
from typing import Optional

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.player import TournamentPlayer
from data.tournament import Tournament
from utils.enum import PlayerGender
from utils.types import Club, Federation


@dataclass
class Team[T](ABC):
    tournament: Tournament
    team_size: int
    min_gender_count: int
    entity: T
    label: str
    players: list[TournamentPlayer]

    @property
    @abstractmethod
    def base_id(self) -> str:
        """Returns the base ID of the entity (without the label)."""
        raise NotImplementedError

    @property
    @abstractmethod
    def base_name(self) -> str:
        """Returns the base name of the entity (without the label)."""
        raise NotImplementedError

    @property
    def id(self) -> str:
        """Returns the ID"""
        id_ = re.sub('[^A-Za-z0-9]', '-', self.base_id)
        if self.label:
            id_ += f'-{self.label}'
        return id_

    @property
    def name(self) -> str:
        """Returns the name to print on documents."""
        name = self.base_name
        if self.label:
            name += f' <span class="team-label">{self.label}</span>'
        return name

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
        return _('Missing women: {count}').format(count=self.missing_women)

    @property
    def missing_men_str(self) -> str:
        """Returns the number of missing men as a printable string."""
        return _('Missing men: {count}').format(count=self.missing_men)

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
    def avg_age_years(self) -> Optional[float]:
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


@dataclass
class ClubTeam(Team[Club]):
    @property
    def club(self) -> Club:
        return self.entity

    @property
    def base_id(self) -> str:
        return self.club.name

    @property
    def base_name(self) -> str:
        return self.club.name


@dataclass
class FederationTeam(Team[Federation]):
    @property
    def federation(self) -> Federation:
        return self.entity

    @property
    def base_id(self) -> str:
        return self.federation.name

    @property
    def base_name(self) -> str:
        return SharlyChessConfig().federations[self.federation.name]
