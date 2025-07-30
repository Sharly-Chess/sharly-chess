import base64
import weakref
from dataclasses import dataclass
from datetime import date
from functools import total_ordering, cached_property
from typing import Self, Callable, SupportsFloat, TYPE_CHECKING
from trf import Player as TrfPlayer
from trf.Player import Game as TrfGame

from common.i18n import _
from data.pairing import Pairing
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredPairing
from plugins.manager import plugin_manager
from plugins.utils import PluginData
from utils import StaticUtils
from utils.enum import (
    PlayerGender,
    PlayerTitle,
    BoardColor,
    Result,
    TournamentRating,
    PlayerRatingType,
    PlayerCategory,
)

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.event import Event
    from data.tournament import Tournament
    from data.tie_breaks.tie_breaks import SupportsRichComparison


@dataclass(frozen=True)
@total_ordering
class Federation:
    name: str = ''

    @cached_property
    def to_query_param(self) -> str:
        return base64.b64encode(self.name.encode('utf-8')).decode('utf-8')

    @classmethod
    def from_query_param(cls, query_param: str) -> Self:
        return cls(base64.b64decode(query_param).decode('utf-8'))

    def __le__(self, other: Self):
        # p1 <= p2 calls p1.__le__(p2)
        assert isinstance(other, self.__class__), (
            f'Can not compare [{type(other)}] and [{self.__class__}]'
        )
        return self.name <= other.name

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
@total_ordering
class Club:
    name: str = ''

    @cached_property
    def to_query_param(self) -> str:
        return base64.b64encode(self.name.encode('utf-8')).decode('utf-8')

    @classmethod
    def from_query_param(cls, query_param: str) -> Self:
        return cls(base64.b64decode(query_param).decode('utf-8'))

    def __le__(self, other: Self):
        # p1 <= p2 calls p1.__le__(p2)
        assert isinstance(other, self.__class__), (
            f'Can not compare [{type(other)}] and [{self.__class__}]'
        )
        return self.name <= other.name

    def __str__(self) -> str:
        return self.name


@dataclass
class PlayerRating:
    value: int
    type: PlayerRatingType

    @classmethod
    def from_stored_value(cls, dict_rating: dict[str, int]):
        return cls(dict_rating['value'], PlayerRatingType(dict_rating['type']))

    @property
    def stored_value(self) -> dict[str, int]:
        return {
            'value': self.value,
            'type': self.type.value,
        }

    def __str__(self) -> str:
        return f'{self.value} {self.type.short_name}'


@total_ordering
class Player:
    # TODO (Molrn - multi tournament) Split into 2 classes:
    #  - Player(event, stored_player)
    #  - TournamentPlayer(tournament, player, stored_tournament_player)
    def __init__(
        self,
        tournament: 'Tournament',
        stored_player: StoredPlayer,
    ):
        self._tournament_ref: 'ReferenceType[Tournament]' = weakref.ref(tournament)
        self.stored_player = stored_player
        self.stored_tournament_player = self.stored_player.stored_tournament_player
        self.ratings = self._get_ratings()
        self.plugin_data: dict[str, PluginData] = {
            plugin_id: plugin_data_class.from_stored_value(
                self.stored_player.plugin_data.get(plugin_id, {})
            )
            for plugin_id, plugin_data_class in self.plugin_data_class_by_plugin_id().items()
        }

        # TournamentPlayer
        self.pairings_by_round = self._get_pairings_by_round()
        self._estimation: int | None = None
        self.points: float | None = None
        self.vpoints: float | None = None
        self.board_id: int | None = None
        self.board_number: int | None = None
        self.color: BoardColor | None = None
        self.illegal_moves: int = 0
        self._tie_break_values: list['SupportsRichComparison'] | None = None
        self._rank: int | None = None
        self.time_control_initial_time: int | None = None
        self.time_control_increment: int | None = None
        self.time_control_modified: bool | None = None

    @staticmethod
    def plugin_data_class_by_plugin_id() -> dict[str, type[PluginData]]:
        return {
            plugin_id: plugin_data_class
            for plugin_id, plugin_data_class in plugin_manager.hook.get_player_plugin_data_class()
        }

    @property
    def event(self) -> 'Event':
        # TODO (Molrn - multi tournament) replace by an event ref
        return self.tournament.event

    @property
    def id(self) -> int:
        assert self.stored_player.id is not None
        return self.stored_player.id

    @property
    def last_name(self) -> str:
        return self.stored_player.last_name

    @property
    def first_name(self) -> str | None:
        return self.stored_player.first_name

    @property
    def full_name(self) -> str:
        if self.first_name:
            return _('{first_name} {last_name}').format(
                first_name=self.first_name, last_name=self.last_name
            )
        return self.last_name

    @property
    def date_of_birth(self) -> date | None:
        return self.stored_player.date_of_birth

    @property
    def year_of_birth(self) -> int:
        return self.date_of_birth.year if self.date_of_birth else 0

    @property
    def gender(self) -> PlayerGender:
        return PlayerGender(self.stored_player.gender)

    @property
    def mail(self) -> str | None:
        return self.stored_player.mail

    @property
    def phone(self) -> str | None:
        return self.stored_player.phone

    @property
    def comment(self) -> str | None:
        return self.stored_player.comment

    @property
    def owed(self) -> float:
        return self.stored_player.owed

    @property
    def paid(self) -> float:
        return self.stored_player.paid

    @property
    def title(self) -> PlayerTitle:
        return PlayerTitle(self.stored_player.title)

    @property
    def fide_id(self) -> int | None:
        return self.stored_player.fide_id

    @property
    def federation(self) -> Federation:
        return Federation(self.stored_player.federation)

    @property
    def club(self) -> Club:
        return Club(self.stored_player.club)

    @property
    def fixed(self) -> int | None:
        return self.stored_player.fixed

    @property
    def check_in(self) -> bool:
        return self.stored_player.check_in

    def _get_ratings(self) -> dict[TournamentRating, PlayerRating]:
        return {
            TournamentRating(tr_value): PlayerRating.from_stored_value(rating)
            for tr_value, rating in self.stored_player.ratings.items()
        }

    def get_rating(self, tournament_rating: TournamentRating) -> PlayerRating:
        return (
            self.ratings.get(tournament_rating, None)
            or plugin_manager.hook.get_player_estimated_rating(
                self.event.federation, tournament_rating, self
            )
            or PlayerRating(0, PlayerRatingType.ESTIMATED)
        )

    def update_ratings(self, ratings: dict[TournamentRating, PlayerRating]):
        for tournament_rating, player_rating in ratings.items():
            self.stored_player.ratings[tournament_rating.value] = (
                player_rating.stored_value
            )
        self.ratings = self._get_ratings()

    @property
    def not_paired_str(self) -> str:
        return (
            _('Unpaired *** FEMALE')
            if self.gender == PlayerGender.FEMALE
            else _('Unpaired *** MALE')
        )

    @property
    def exempt_str(self) -> str:
        return (
            _('Exempt *** FEMALE')
            if self.gender == PlayerGender.FEMALE
            else _('Exempt *** MALE')
        )

    # --------------------------------------------------------------------------
    # TournamentPlayer
    # --------------------------------------------------------------------------

    @property
    def tournament(self) -> 'Tournament':
        if (tournament := self._tournament_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return tournament

    def _get_default_pairing(self, round_: int) -> Pairing:
        return Pairing(
            self,
            StoredPairing(
                tournament_id=self.tournament.id,
                player_id=self.id,
                round_=round_,
                result=Result.NO_RESULT.value,
                board_id=None,
            ),
            exists=False,
        )

    def _get_pairings_by_round(self) -> dict[int, Pairing]:
        known_pairings: dict[int, Pairing] = {}
        for stored_pairing in self.stored_tournament_player.stored_pairings:
            pairing = Pairing(self, stored_pairing)
            known_pairings[pairing.round] = pairing
        return {
            round_: (
                known_pairings[round_]
                if round_ in known_pairings
                else self._get_default_pairing(round_)
            )
            for round_ in range(1, self.tournament.rounds + 1)
        }

    def delete_pairing(self, round_: int, event_database: EventDatabase):
        event_database.delete_stored_pairing(
            self.pairings_by_round[round_].stored_pairing
        )
        self.pairings_by_round[round_] = self._get_default_pairing(round_)

    @property
    def estimation(self) -> int:
        if not self.estimated:
            return self.rating
        return self._estimation or 0

    @estimation.setter
    def estimation(self, value: int):
        if not self.estimated:
            self._estimation = self.rating
        else:
            self._estimation = value

    @property
    def estimated(self) -> bool:
        return self.rating_type == PlayerRatingType.ESTIMATED

    @cached_property
    def category(self) -> PlayerCategory:
        if self.tournament:
            tournament_start = self.tournament.start_datetime
            tournament_end = self.tournament.stop_datetime
        else:
            tournament_start, tournament_end = None, None
        return PlayerCategory.from_year_of_birth(
            self.year_of_birth, tournament_start, tournament_end
        )

    @property
    def rating(self) -> int:
        return self._tournament_rating.value

    @property
    def rating_type(self) -> PlayerRatingType:
        return self._tournament_rating.type

    @property
    def rating_str(self) -> str:
        return str(self._tournament_rating)

    @property
    def _tournament_rating(self) -> PlayerRating:
        return self.get_rating(self.tournament.rating)

    @property
    def ratings_str(self) -> str:
        return '/'.join(
            [
                str(self.get_rating(tournament_rating))
                for tournament_rating in TournamentRating
            ]
        )

    @property
    def point_values(self) -> dict[Result, float] | None:
        return self.tournament.point_values

    def points_before(self, before_round: int, only_played: bool = False) -> float:
        # NOTE(Amaras) this does not rely on the fact that insertion order
        # is preserved in 3.6+ dict, because I can't be sure insertion order
        # is the correct (increasing) round order
        # NOTE(Amaras) if you were to include the current round
        # in the computation, boards regularly change their ordering
        # during the current round as results are added
        return sum(
            pairing.result.points(self.point_values)
            for round_, pairing in self.pairings.items()
            if round_ < before_round and (pairing.played or not only_played)
        )

    def points_after(self, after_round: int) -> float:
        # NOTE(Amaras) this does not rely on the fact that insertion order
        # is preserved in 3.6+ dict, because I can't be sure insertion order
        # is the correct (increasing) round order
        # NOTE(Amaras) if you were to include the current round
        # in the computation, boards regularly change their ordering
        # during the current round as results are added
        return sum(
            pairing.result.points(self.point_values)
            for round_index, pairing in self.pairings.items()
            if round_index <= after_round
        )

    def total_points(self, only_played: bool = False) -> float:
        return sum(
            pairing.result.points(self.point_values)
            for pairing in self.pairings.values()
            if pairing.played or not only_played
        )

    def compute_points(self, *, before_round: int):
        """Computes and stores the points scored by the player before round `before_round` (returns None)"""
        self.points = self.points_before(before_round)

    def points_total(self) -> float:
        return sum(
            pairing.result.points(self.point_values)
            for pairing in self.pairings.values()
        )

    def add_points(self, points: float):
        """If `self.points` is set, add `points` to it.
        Otherwise, leave `self.points` as None."""
        if self.points is not None:
            self.points += points

    @property
    def points_str(self) -> str:
        return StaticUtils.points_str(self.points)

    def add_vpoints(self, vpoints: float):
        """If `self.vpoints` is set, add `vpoints` to it.
        Otherwise, leave `self.vpoints` as None."""
        if self.vpoints is not None:
            self.vpoints += vpoints

    @property
    def vpoints_str(self) -> str:
        return StaticUtils.points_str(self.vpoints)

    def to_trf(
        self,
        player_id_to_trf_id: Callable[[int], int],
        /,
        *,
        after_round: int,
        include_next_round_bye: bool,
        next_round_pairings_as_zpb: bool,
    ) -> TrfPlayer:
        games: list[TrfGame] = []
        for round_nb, pairing in self.pairings.items():
            trf_game = pairing.to_trf(round_nb, player_id_to_trf_id)
            if round_nb <= after_round:
                games.append(trf_game)
            elif round_nb == after_round + 1:
                if include_next_round_bye and pairing.next_round_bye:
                    games.append(trf_game)
                elif next_round_pairings_as_zpb and not pairing.not_paired:
                    games.append(
                        TrfGame(
                            startrank='0000',  # type: ignore
                            color='-',
                            result=Result.ZERO_POINT_BYE.to_trf,
                            round=round_nb,
                        )
                    )

        return TrfPlayer(
            startrank=player_id_to_trf_id(self.id),
            name=f'{self.last_name}, {self.first_name}',
            sex=self.gender.to_trf,
            title=self.title.to_trf,
            rating=self.rating,
            fed=self.federation.name,
            id=self.fide_id,
            birthdate=(
                self.date_of_birth.strftime('%Y/%m/%d') if self.date_of_birth else ''
            ),
            points=self.points_after(after_round),
            rank=self.rank,
            games=games,
        )

    def set_board(self, board_id: int, board_number: int, color: BoardColor):
        self.board_id = board_id
        self.board_number = board_number
        self.color = color

    @cached_property
    def has_real_pairings(self) -> bool:
        """Returns True if the player has already been paired with an opponent
        (i.e. can not be deleted from the tournament anymore)."""
        for pairing in self.pairings.values():
            if pairing.opponent_id is not None or pairing.exempt:
                return True
        return False

    @property
    def first_pab_round(self) -> int | None:
        return next(
            (
                round_
                for round_, pairing in self.pairings.items()
                if pairing.result == Result.PAIRING_ALLOCATED_BYE
            ),
            None,
        )

    def round_played_against(self, opponent_id: int) -> int | None:
        """Get the round at which the player has played against the player *opponent_id*.
        Return None if they have not played against each other."""
        return next(
            (
                round_
                for round_, pairing in self.pairings.items()
                if pairing.opponent_id == opponent_id
            ),
            None,
        )

    @cached_property
    def can_check_in_out(self) -> bool:
        """Returns True if the player can check-in/out, i.e. does not have a ZPB for the next round."""
        if self.tournament.finished:
            return False
        if self.tournament.playing:
            return False
        if not self.tournament.check_in_open:
            return False
        pairing: Pairing = self.pairings[self.tournament.current_round + 1]
        return (
            not pairing.zero_point_bye
            and not pairing.half_point_bye
            and not pairing.full_point_bye
        )

    @property
    def color_str(self) -> str:
        return str(self.color or '')

    @property
    def time_control_initial_time_minutes(self) -> int | None:
        if self.time_control_initial_time:
            return self.time_control_initial_time // 60
        return None

    @property
    def time_control_initial_time_seconds(self) -> int | None:
        if self.time_control_initial_time:
            return self.time_control_initial_time % 60
        return None

    @property
    def handicap_str(self) -> str | None:
        if self.time_control_initial_time is None:
            return None
        (minutes, seconds) = divmod(self.time_control_initial_time, 60)
        minutes_str: str = f"{minutes}'" if minutes > 0 else ''
        seconds_str: str = f'{seconds}"' if seconds > 0 else ''
        class_str: str = 'modified-time' if self.time_control_modified else 'base-time'
        return f'<span class="{class_str}">{minutes_str}{seconds_str}</span> + {self.time_control_increment}"/cp'

    def set_time_control(self, initial_time: int, increment: int, modified: bool):
        self.time_control_initial_time = initial_time
        self.time_control_increment = increment
        self.time_control_modified = modified

    @property
    def tie_break_values_as_strings(self) -> list[str]:
        """Returns the player's tie-break values as strings."""
        assert self._tie_break_values is not None, (
            'Player._tie_break_values is not set, call Tournament.compute_player_ranks() before.'
        )
        return [
            StaticUtils.points_str(float(tie_break_value))
            for tie_break_value in self._tie_break_values
            if isinstance(tie_break_value, SupportsFloat)
        ]

    def compute_tie_break_values(self, *, after_round: int | None):
        assert self.tournament is not None
        self._tie_break_values = [
            tie_break.compute_player_value(self, after_round=after_round)
            for tie_break in self.tournament.tie_breaks
        ]

    @property
    def rank(self) -> int:
        assert self._rank, (
            'Player._rank is not set, call Tournament.compute_player_ranks() before.'
        )
        return self._rank

    @rank.setter
    def rank(self, rank: int):
        self._rank = rank

    @cached_property
    def crosstable_strings(self) -> list[str]:
        assert self.tournament is not None
        return [
            pairing.result.to_crosstable
            + (
                f'{self.tournament.players_by_id[pairing.opponent_id].rank:>3}'
                f'{pairing.color.to_crosstable}'
                if pairing.opponent_id and pairing.color
                else ''
            )
            for pairing in self.pairings.values()
        ]

    @property
    def starting_rank_sort_key(self) -> tuple[int, int, str, str]:
        return -self.rating, -self.title, self.last_name, self.first_name or ''

    @property
    def board_number_sort_key(self) -> tuple[float, int, int, str, str]:
        return (
            -self.vpoints if self.vpoints is not None else 0.0,
            -self.rating,
            -self.title,
            self.last_name,
            self.first_name or '',
        )

    @property
    def rank_sort_key(self) -> tuple:
        # NOTE(Tim) we need to handle the DirectEncounter TieBreak, which is a Tuple.
        tie_breaks = tuple(
            (-float(tie_break) if isinstance(tie_break, SupportsFloat) else 0.0)
            for tie_break in self._tie_break_values or []
        )
        return (
            (-self.points if self.points is not None else 0.0,)
            + tie_breaks
            + self.starting_rank_sort_key
        )

    def clear_cache(self):
        """Clears the cache of the player."""
        cached_property_names = [
            name
            for name in dir(self)
            if isinstance(getattr(type(self), name, None), cached_property)
        ]
        for property_name in cached_property_names:
            if property_name in self.__dict__:
                del self.__dict__[property_name]

    def __le__(self, other: 'Player') -> bool:
        # p1 <= p2 calls p1.__le__(p2)
        if not isinstance(other, Player):
            return NotImplemented
        # A false positive warning is raised in PyCharm, cf https://youtrack.jetbrains.com/issue/PY-76256
        return self.board_number_sort_key > other.board_number_sort_key

    def __eq__(self, other):
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, Player):
            return NotImplemented
        return self.board_number_sort_key == other.board_number_sort_key

    def __repr__(self):
        ratings_str: str = '/'.join(
            f'{self.ratings.get(tournament_rating, "  -  ")}'
            for tournament_rating in TournamentRating
        )
        return (
            f'(#{self.id} rank={self._rank} ratings={ratings_str} title={self.title.value} gender={self.gender.value} '
            f'name={self.last_name} {self.first_name} points={self.points})'
        )

    # --------------------------------------------------------------------------
    # Legacy
    # --------------------------------------------------------------------------

    @property
    def pairings(self) -> dict[int, Pairing]:
        return self.pairings_by_round
