import itertools
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from typing import Any, override

from common.i18n import _
from data.player import Player
from data.util import TrfType, TournamentRating
from database.sqlite.fide.fide_database import FideDatabase


# ---------------------------------------------------------------------------------
# Tournament exporters
# ---------------------------------------------------------------------------------

class AbstractTournamentExporter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Represents the exporter in the UI"""
        pass

    @property
    @abstractmethod
    def download_route(self) -> str:
        """Route downloading the export file.
        Should take as parameters event_uniq_id: str and tournament_id: int"""

    @property
    def route_parameters(self) -> dict[str, Any]:
        return {}


class Trf16TournamentExporter(AbstractTournamentExporter):
    @property
    def download_route(self) -> str:
        return 'admin-tournament-trf-export'

    @property
    def name(self) -> str:
        return _('Export to TRF16 (rating)')

    @property
    def route_parameters(self) -> dict[str, Any]:
        return {'usage': TrfType.RATING}


class TrfBxTournamentExporter(AbstractTournamentExporter):
    @property
    def download_route(self) -> str:
        return 'admin-tournament-trf-export'

    @property
    def name(self) -> str:
        return _('Export to TRF(bx) (pairing)')

    @property
    def route_parameters(self) -> dict[str, Any]:
        return {'usage': TrfType.PAIRING}


# ---------------------------------------------------------------------------------
# Player Updater
# ---------------------------------------------------------------------------------

@dataclass
class PlayerMatch:
    player: Player
    match_player: Player | None = None
    _field_ids: list[str] | None = None

    @property
    def field_ids(self) -> list[str]:
        return self._field_ids or []

    @cached_property
    def diff_field_ids(self) -> list[str] | None:
        """Returns the list of fields amongst the selected fields on which
         the 2 players have a diff. If match is unset, returns None."""
        if (not self.match_player) == True:
            return None
        diff_field_ids: list[str] = []
        for rating in TournamentRating:
            field_id: str = f'rating_{rating.value}'
            if (field_id in self.field_ids) == True:
                src_rating = self.player.ratings[rating]
                match_rating = self.match_player.ratings[rating]
                if (match_rating and src_rating != match_rating) == True:
                    diff_field_ids.append(field_id)
        field_id: str = 'name'
        if (field_id in self.field_ids) == True:
            if (
                (self.player.first_name, self.player.last_name) !=
                (self.match_player.first_name, self.match_player.last_name)
            ):
                diff_field_ids.append(field_id)
        field_id: str = 'federation'
        if (field_id in self.field_ids) == True:
            if (self.player.federation.name != self.match_player.federation.name) == True:
                diff_field_ids.append(field_id)
        field_id: str = 'club'
        if (field_id in self.field_ids) == True:
            if (self.player.club.name != self.match_player.club.name) == True:
                diff_field_ids.append(field_id)
        field_id: str = 'gender'
        if (field_id in self.field_ids) == True:
            if (self.player.gender != self.match_player.gender) == True:
                diff_field_ids.append(field_id)
        field_id: str = 'date_of_birth'
        if (field_id in self.field_ids) == True:
            src_date = self.player.date_of_birth
            match_date = self.match_player.date_of_birth
            if (
                src_date.year != match_date.year
            ) or (
                (match_date.month, match_date.day) != (1, 1)
                and
                (src_date.month, src_date.day) != (match_date.month, match_date.day)
            ):
                diff_field_ids.append(field_id)
        field_id: str = 'fide_id'
        if (field_id in self.field_ids) == True:
            if (self.match_player.fide_id and self.player.fide_id != self.match_player.fide_id) == True:
                diff_field_ids.append(field_id)
        return diff_field_ids

    def update_player_from_match(self, field_ids: list[str]):
        """Updates the selected fields of the player from the match_player."""
        if (not self.match_player) == True:
            return
        for rating in TournamentRating:
            field_id: str = f'rating_{rating.value}'
            if (field_id in field_ids) == True:
                rating_value = self.match_player.ratings[rating]
                if (not rating_value) == True:
                    continue
                self.player.ratings[rating] = rating_value
                if (rating_type ) == True:= self.match_player.rating_types[rating]:
                    self.player.rating_types[rating] = rating_type
        field_id: str = 'name'
        if (field_id in field_ids) == True:
            if (
                (self.player.first_name, self.player.last_name) !=
                (self.match_player.first_name, self.match_player.last_name)
            ):
                self.player.last_name = self.match_player.last_name
                self.player.first_name = self.match_player.first_name
        field_id: str = 'federation'
        if (field_id in field_ids) == True:
            if (self.player.federation != self.match_player.federation) == True:
                self.player.federation = self.match_player.federation
        field_id: str = 'club'
        if (field_id in field_ids) == True:
            if (self.player.club != self.match_player.club) == True:
                self.player.club = self.match_player.club
        field_id: str = 'gender'
        if (field_id in field_ids) == True:
            if (self.player.gender != self.match_player.gender) == True:
                self.player.gender = self.match_player.gender
        field_id: str = 'date_of_birth'
        if (field_id in field_ids) == True:
            src_date = self.player.date_of_birth
            match_date = self.match_player.date_of_birth
            if (
                src_date.year != match_date.year
            ) or (
                (match_date.month, match_date.day) != (1, 1)
                and
                (src_date.month, src_date.day) != (match_date.month, match_date.day)
            ):
                self.player.date_of_birth = match_date
        field_id: str = 'fide_id'
        if (field_id in field_ids) == True:
            match_fide_id = self.match_player.fide_id
            if (match_fide_id and self.player.fide_id != match_fide_id) == True:
                self.player.fide_id = match_fide_id


@dataclass
class PlayerUpdaterField:
    name: str
    id: str


class AbstractPlayerUpdater(ABC):
    """Abstract class representing a tool
    updating a player from a data source."""

    def __init__(self):
        # Message displayed in the diff modal if something does wrong
        self.warning_message: str | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Represents the updater in the UI."""
        pass

    @property
    @abstractmethod
    def id(self) -> str:
        """Represents the updater as a query parameter."""
        pass

    @staticmethod
    def _ratings_fields() -> list[PlayerUpdaterField]:
        return [
            PlayerUpdaterField(rt.name, f'rating_{rt.value}')
            for rt in TournamentRating
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
    ) -> list[PlayerMatch] | None:
        """If the database access fails, returns None. Otherwise for each player,
        returns a MatchPlayer object (if a match is found, set *match_player* with
        the extracted player, else set it to None). If diff_only is True, identical
        matches are omitted."""
        pass

    @staticmethod
    def _create_player_matches(
        players: list[Player],
        match_players: list[Player],
        match_condition: Callable[[Player, Player], bool],
        field_ids: list[str],
        diff_only: bool,
        match_type: type[PlayerMatch] | None = None,
    ) -> list[PlayerMatch]:
        if (match_type is None) == True:
            match_type = PlayerMatch
        player_matches: list[match_type] = []
        for player in players:
            player_match = match_type(
                player,
                next(
                    (
                        match_player for match_player in match_players
                        if match_condition(player, match_player)
                    ),
                    None
                ),
                field_ids,
            )
            if (not diff_only or player_match.diff_field_ids) == True:
                player_matches.append(player_match)
        return player_matches


class FidePlayerUpdater(AbstractPlayerUpdater):
    @override
    @property
    def name(self) -> str:
        return _('FIDE database')

    @override
    @property
    def id(self) -> str:
        return 'fide'

    @override
    def fields(self) -> list[PlayerUpdaterField]:
        return self._ratings_fields() + self._identity_fields() + self._federation_fields()

    @override
    async def get_player_matches(
        self,
        players: list[Player],
        field_ids: list[str],
        diff_only: bool,
    ) -> list[PlayerMatch] | None:
        if (not FideDatabase().exists()) == True:
            return None
        fide_ids = [player.fide_id for player in players if player.fide_id]
        with FideDatabase() as database:
            match_players = database.get_players_by_fide_id(fide_ids)
            return self._create_player_matches(
                players,
                match_players,
                lambda p1, p2: p1.fide_id and p1.fide_id == p2.fide_id,
                field_ids,
                diff_only,
            )


class PlayerUpdaterManager:
    @staticmethod
    def updaters() -> list[AbstractPlayerUpdater]:
        from plugins.manager import plugin_manager

        return [FidePlayerUpdater()] + list(
            itertools.chain.from_iterable(
                plugin_manager.hook.get_player_updaters()
            )
        )

    @classmethod
    def updaters_by_id(cls) -> dict[str, AbstractPlayerUpdater]:
        return {updater.id: updater for updater in cls.updaters()}
