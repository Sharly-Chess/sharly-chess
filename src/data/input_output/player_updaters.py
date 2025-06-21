from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from logging import Logger
from typing import override

from common.i18n import _
from common.logger import get_logger
from data.player import Player
from utils.entity import IdentifiableEntity
from utils.enum import TournamentRating
from database.sqlite.fide.fide_database import FideDatabase

logger: Logger = get_logger()


class PlayerComparator(ABC):
    def __init__(
        self,
        field_ids: list[str],
        player: Player,
        match_player: Player | None = None,
    ):
        self.field_ids = field_ids
        self.player = player
        if match_player:
            match_player.tournament = player.tournament
        self.match_player = match_player

    @property
    @abstractmethod
    def diff_field_ids(self) -> list[str] | None:
        """Returns the list of fields amongst the selected fields on which
        the 2 players have a diff. If match is unset, returns None."""
        ...

    @abstractmethod
    def update_player_from_match(self, field_ids: list[str]):
        """Updates the selected fields of the player from the match_player."""
        ...


class FidePlayerComparator(PlayerComparator):
    def match_date_differs(self) -> bool:
        src_date = self.player.date_of_birth
        match_date = self.match_player.date_of_birth if self.match_player else None
        if src_date is None:
            return match_date is not None
        if match_date is None:
            return False
        if src_date.year != match_date.year:
            return True
        if (match_date.month, match_date.day) == (1, 1):
            return False
        if (src_date.month, src_date.day) == (match_date.month, match_date.day):
            return False
        return True

    @cached_property
    def diff_field_ids(self) -> list[str] | None:
        if not self.match_player:
            return None
        diff_field_ids: list[str] = []
        for tr in TournamentRating:
            field_id: str = f'rating_{tr.value}'
            if field_id in self.field_ids:
                src_rating = self.player.get_rating(tr)
                match_rating = self.match_player.get_rating(tr)
                if match_rating.value and src_rating != match_rating:
                    diff_field_ids.append(field_id)
        field_id: str = 'name'
        if field_id in self.field_ids:
            if (self.player.first_name, self.player.last_name) != (
                self.match_player.first_name,
                self.match_player.last_name,
            ):
                diff_field_ids.append(field_id)
        field_id: str = 'federation'
        if field_id in self.field_ids:
            if self.player.federation.name != self.match_player.federation.name:
                diff_field_ids.append(field_id)
        field_id: str = 'club'
        if field_id in self.field_ids:
            if (not self.player.club and self.match_player.club) or (
                self.player.club
                and self.match_player.club
                and self.player.club.name != self.match_player.club.name
            ):
                diff_field_ids.append(field_id)
        field_id: str = 'gender'
        if field_id in self.field_ids:
            if self.player.gender != self.match_player.gender:
                diff_field_ids.append(field_id)
        field_id: str = 'date_of_birth'
        if field_id in self.field_ids:
            if self.match_date_differs():
                diff_field_ids.append(field_id)
        field_id: str = 'fide_id'
        if field_id in self.field_ids:
            if (
                self.match_player.fide_id
                and self.player.fide_id != self.match_player.fide_id
            ):
                diff_field_ids.append(field_id)
        return diff_field_ids

    def update_player_from_match(self, field_ids: list[str]):
        if not self.match_player:
            return
        for tr in TournamentRating:
            field_id: str = f'rating_{tr.value}'
            if field_id in field_ids:
                match_rating = self.match_player.get_rating(tr)
                if match_rating.value:
                    self.player.ratings[tr] = match_rating
        field_id: str = 'name'
        if field_id in field_ids:
            if (self.player.first_name, self.player.last_name) != (
                self.match_player.first_name,
                self.match_player.last_name,
            ):
                self.player.last_name = self.match_player.last_name
                self.player.first_name = self.match_player.first_name
        field_id: str = 'federation'
        if field_id in field_ids:
            if self.player.federation != self.match_player.federation:
                self.player.federation = self.match_player.federation
        field_id: str = 'club'
        if field_id in field_ids:
            if self.player.club != self.match_player.club:
                self.player.club = self.match_player.club
        field_id: str = 'gender'
        if field_id in field_ids:
            if self.player.gender != self.match_player.gender:
                self.player.gender = self.match_player.gender
        field_id: str = 'date_of_birth'
        if field_id in field_ids:
            if self.match_date_differs():
                self.player.date_of_birth = self.match_player.date_of_birth
        field_id: str = 'fide_id'
        if field_id in field_ids:
            match_fide_id = self.match_player.fide_id
            if match_fide_id and self.player.fide_id != match_fide_id:
                self.player.fide_id = match_fide_id


@dataclass
class PlayerUpdaterField:
    name: str
    id: str


class PlayerUpdater(IdentifiableEntity, ABC):
    """Abstract class representing a tool
    updating a player from a data source."""

    def __init__(self):
        # Message displayed in the diff modal if something does wrong
        self.warning_message: str | None = None

    @staticmethod
    def _ratings_fields() -> list[PlayerUpdaterField]:
        return [
            PlayerUpdaterField(rt.name, f'rating_{rt.value}') for rt in TournamentRating
        ]

    @staticmethod
    def _identity_fields() -> list[PlayerUpdaterField]:
        return [
            PlayerUpdaterField(_('Name'), 'name'),
            PlayerUpdaterField(_('Gender'), 'gender'),
            PlayerUpdaterField(_('Date of birth'), 'date_of_birth'),
        ]

    @staticmethod
    def _federation_fields() -> list[PlayerUpdaterField]:
        return [
            PlayerUpdaterField(_('Federation'), 'federation'),
        ]

    @staticmethod
    def _club_fields() -> list[PlayerUpdaterField]:
        return [
            PlayerUpdaterField(_('Club'), 'club'),
        ]

    @staticmethod
    def _fide_fields() -> list[PlayerUpdaterField]:
        return [
            PlayerUpdaterField(_('FIDE ID'), 'fide_id'),
        ]

    @abstractmethod
    def fields(
        self,
    ) -> list[PlayerUpdaterField]:
        """Returns the fields that can be updated by the updater."""
        pass

    @abstractmethod
    async def get_player_matches(
        self,
        players: list[Player],
        field_ids: list[str],
        diff_only: bool,
    ) -> list[PlayerComparator] | None:
        """If the database access fails, returns None. Otherwise for each player,
        returns a MatchPlayer object (if a match is found, set *match_player* with
        the extracted player, else set it to None). If diff_only is True, identical
        matches are omitted."""
        pass

    @staticmethod
    def _create_player_comparators(
        players: list[Player],
        match_players: list[Player],
        match_condition: Callable[[Player, Player], bool],
        field_ids: list[str],
        diff_only: bool,
        comparator: type[PlayerComparator],
    ) -> list[PlayerComparator]:
        player_comparators: list[PlayerComparator] = []
        for player in players:
            player_comparator = comparator(
                field_ids,
                player,
                next(
                    (
                        match_player
                        for match_player in match_players
                        if match_condition(player, match_player)
                    ),
                    None,
                ),
            )
            if not diff_only or player_comparator.diff_field_ids:
                player_comparators.append(player_comparator)
        return player_comparators


class FidePlayerUpdater(PlayerUpdater):
    @staticmethod
    def static_name() -> str:
        return _('FIDE database')

    @staticmethod
    def static_id() -> str:
        return 'fide'

    @override
    def fields(self) -> list[PlayerUpdaterField]:
        return (
            self._ratings_fields() + self._identity_fields() + self._federation_fields()
        )

    @override
    async def get_player_matches(
        self,
        players: list[Player],
        field_ids: list[str],
        diff_only: bool,
    ) -> list[PlayerComparator] | None:
        database = FideDatabase()
        if not database.exists():
            return None
        fide_ids = [player.fide_id for player in players if player.fide_id]
        with database:
            match_players = database.get_players_by_fide_id(fide_ids)
            return self._create_player_comparators(
                players,
                match_players,
                lambda p1, p2: p1.fide_id is not None and p1.fide_id == p2.fide_id,
                field_ids,
                diff_only,
                FidePlayerComparator,
            )
