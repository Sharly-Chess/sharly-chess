import weakref
from collections import Counter
from functools import cached_property
from itertools import groupby
from logging import Logger
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable
from _weakref import ReferenceType

from trf import Tournament as TrfTournament

from common import format_timestamp_date_time, format_timestamp
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from common.logger import get_logger

from data.board import Board
from data.pairing import Pairing
from data.family import Family
from data.player import Player, Federation, Club
from data.screen import Screen
from data.tie_breaks import (
    TieBreak,
    TieBreakOption,
    TieBreakManager,
    TieBreakOptionManager,
)
from utils import SharedUtils
from utils.enum import (
    BoardColor,
    PlayerGender,
    PointValueType,
    Result,
    TournamentRating,
    TrfType,
)
from database.access.papi.papi_database import (
    PapiDatabase,
    PapiTournamentInfo,
    PapiVariable,
    BYE_COLOR,
    UNPLAYED_COLOR,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament
from plugins.manager import plugin_manager

if TYPE_CHECKING:
    from data.event import Event
    from data.pairings import PairingVariation, PairingSystem

logger: Logger = get_logger()


class Tournament:
    """A data wrapper around a stored tournament."""

    def __init__(
        self,
        event: 'Event',
        stored_tournament: StoredTournament,
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_tournament: StoredTournament = stored_tournament
        if not stored_tournament.path:
            self.event.add_debug(
                _('No directory set for the Papi file, by default [{path}].').format(
                    path=self.path
                ),
                tournament=self,
            )
        if not self.path.exists():
            self.event.add_warning(
                _('Directory [{path}] not found.').format(path=self.path),
                tournament=self,
            )
        elif not self.path.is_dir():
            self.event.add_error(
                _('[{path}] is not a directory.').format(path=self.path),
                tournament=self,
            )
        if not self.stored_tournament.filename:
            self.event.add_info(
                _(
                    'The name of the Papi file is not set, by default [{filename}]'
                ).format(filename=self.filename),
                tournament=self,
            )
        self.stored_file_modified_timestamp: float | None = None
        if self.file_exists:
            self.stored_file_modified_timestamp = self.file_modified_timestamp
        self._players: Iterable[Player] | None = None
        self._players_by_rank: dict[int, Player] | None = None
        # Give plugin the chance to initialise their data
        plugin_manager.hook.on_tournament_init(tournament=self)

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int:
        assert self.stored_tournament.id is not None
        return self.stored_tournament.id

    @property
    def uniq_id(self) -> str:
        return self.stored_tournament.uniq_id

    @property
    def name(self) -> str:
        return (
            self.stored_tournament.name if self.stored_tournament.name else self.uniq_id
        )

    @property
    def full_name(self) -> str:
        return (
            f'{self.event.name} - {self.name}'
            if len(self.event.tournaments_by_id.values()) > 1
            else self.name
        )

    @property
    def path(self) -> Path:
        return (
            Path(self.stored_tournament.path)
            if self.stored_tournament.path
            else self.event.path
        )

    @property
    def filename(self) -> str:
        if self.stored_tournament.filename:
            return self.stored_tournament.filename
        return self.uniq_id

    @property
    def file(self) -> Path:
        return self.path / f'{self.filename}.{SharlyChessConfig.papi_ext}'

    @property
    def file_exists(self) -> bool:
        return self.file.exists()

    @property
    def file_modified_timestamp(self) -> float:
        return self.file.lstat().st_mtime

    @property
    def log_prefix(self) -> str:
        return f'Event [{self.event.uniq_id}] - Tournament [{self.uniq_id}] - '

    @property
    def papi_write_database(self) -> PapiDatabase:
        """This database should be used instead of creating a new instance
        in write mode to ensure not reloading it unnecessarily."""
        return PapiDatabase(
            self.file,
            write=True,
            on_exit=self.update_stored_file_modified_timestamp,
        )

    @property
    def start_timestamp(self) -> float:
        return self.stored_tournament.start or self.event.start

    @property
    def stop_timestamp(self) -> float:
        return self.stored_tournament.stop or self.event.stop

    @property
    def location(self) -> str | None:
        return self.stored_tournament.location or self.event.location

    @property
    def time_control_initial_time(self) -> int | None:
        return self.stored_tournament.time_control_initial_time

    @property
    def time_control_increment(self) -> int | None:
        return self.stored_tournament.time_control_increment

    @property
    def time_control_handicap_penalty_value(self) -> int | None:
        return self.stored_tournament.time_control_handicap_penalty_value

    @property
    def time_control_handicap_penalty_step(self) -> int | None:
        return self.stored_tournament.time_control_handicap_penalty_step

    @property
    def time_control_handicap_min_time(self) -> int | None:
        return self.stored_tournament.time_control_handicap_min_time

    @property
    def record_illegal_moves(self) -> int:
        if self.stored_tournament.record_illegal_moves is not None:
            return self.stored_tournament.record_illegal_moves
        return self.event.record_illegal_moves

    @property
    def rules(self) -> str | None:
        if self.stored_tournament.rules is not None:
            return self.stored_tournament.rules
        return self.event.rules

    @property
    def check_in_open(self) -> bool:
        return self.stored_tournament.check_in_open

    @property
    def first_board_number(self) -> int:
        return (
            self.stored_tournament.first_board_number
            or SharlyChessConfig.default_first_board_number
        )

    @property
    def paired_bye_result(self) -> Result:
        if self.stored_tournament.paired_bye_result is None:
            return SharlyChessConfig.default_paired_bye_result
        else:
            return Result(self.stored_tournament.paired_bye_result)

    @property
    def max_byes(self) -> int:
        return self.stored_tournament.max_byes or SharlyChessConfig.default_max_byes

    @property
    def last_rounds_no_byes(self) -> int:
        return (
            self.stored_tournament.last_rounds_no_byes
            or SharlyChessConfig.default_last_rounds_no_byes
        )

    @cached_property
    def players_by_check_in_status(self) -> dict[bool | None, list[Player]]:
        if self.finished or self.playing or not self.check_in_open:
            return {
                None: list(self.players),
                True: [],
                False: [],
            }
        else:
            result: dict[bool | None, list[Player]] = {
                None: [],
                True: [],
                False: [],
            }
            for player in self.players:
                if not player.can_check_in_out:
                    result[None].append(player)
                else:
                    result[player.check_in].append(player)
            return result

    @cached_property
    def check_in_counts(self) -> Counter[bool | None]:
        counter: Counter[bool | None] = Counter[bool | None]()
        if self.finished or self.playing or not self.check_in_open:
            counter[None] = len(self.players_by_id)
            counter[True] = 0
            counter[False] = 0
        else:
            for player in self.players:
                if not player.can_check_in_out:
                    counter[None] += 1
                else:
                    counter[player.check_in] += 1
        return counter

    @property
    def last_update(self) -> float:
        return self.stored_tournament.last_update

    @property
    def last_update_str(self) -> str:
        return format_timestamp_date_time(self.last_update)

    @property
    def last_illegal_move_update(self) -> float:
        return self.stored_tournament.last_illegal_move_update

    @property
    def last_result_update(self) -> float:
        return self.stored_tournament.last_result_update

    @property
    def last_check_in_update(self) -> float:
        return self.stored_tournament.last_check_in_update

    @property
    def stored_tie_breaks(self) -> list[TieBreak] | None:
        if not self.stored_tournament.tie_breaks:
            return None
        tie_breaks: list[TieBreak] = []
        tie_break_type_by_id: dict[str, type[TieBreak]] = TieBreakManager.type_by_id()
        option_type_by_id: dict[str, type[TieBreakOption]] = (
            TieBreakOptionManager.type_by_id()
        )
        for tie_break_dict in self.stored_tournament.tie_breaks:
            assert isinstance(tie_break_dict['type'], str)
            assert isinstance(tie_break_dict['options'], dict)
            tie_break_id = tie_break_dict['type']
            options: list[TieBreakOption] = []
            for option_id, value in tie_break_dict['options'].items():
                if option_type := option_type_by_id.get(option_id, None):
                    options.append(option_type(value))
            if tie_break_type := tie_break_type_by_id.get(tie_break_id, None):
                tie_breaks.append(tie_break_type(options))
        return tie_breaks

    @property
    def stored_rounds(self) -> int:
        return self.stored_tournament.rounds

    @property
    def stored_rating(self) -> TournamentRating:
        return TournamentRating(self.stored_tournament.rating)

    @property
    def stored_pairing_variation(self) -> 'PairingVariation | None':
        from data.pairings import PairingVariationManager

        if variation_id := self.stored_tournament.pairing:
            return PairingVariationManager.get_object(variation_id)
        return None

    @property
    def download_allowed(self) -> bool:
        return self.file_exists

    @property
    def handicap(self) -> bool:
        return bool(self.time_control_handicap_penalty_value)

    @cached_property
    def papi_tournament_info(self) -> PapiTournamentInfo:
        papi_tournament_info, _ = self.papi_values
        return papi_tournament_info

    @property
    def rounds(self) -> int:
        return self.papi_tournament_info.rounds

    @property
    def pairing_variation(self) -> 'PairingVariation':
        from data.pairings.variations import (
            BergerRoundRobinVariation,
            DoubleBergerRoundRobinVariation,
        )

        papi_variation = self.papi_tournament_info.pairing_variation
        stored_variation = self.stored_pairing_variation
        if (
            papi_variation == BergerRoundRobinVariation()
            and stored_variation
            and stored_variation == DoubleBergerRoundRobinVariation()
        ):
            return stored_variation
        return papi_variation

    @property
    def pairing_system(self) -> 'PairingSystem':
        return self.pairing_variation.system()

    @property
    def pairing_settings(self) -> dict[str, Any] | None:
        return self.stored_tournament.pairing_settings

    def set_default_pairing_settings(self):
        stored_settings: dict[str, Any] = {
            setting.id: setting.to_stored_value(setting.default_value(self))
            for setting in self.pairing_variation.settings
        }
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_tournament_pairing_settings(self.id, stored_settings)
            database.commit()
        self.stored_tournament.pairing_settings = stored_settings

    @cached_property
    def are_pairing_settings_valid(self) -> bool:
        return not self.pairing_variation.settings or (
            self.pairing_settings is not None
            and self.pairing_variation.validate_settings(self)
        )

    @property
    def rating(self) -> TournamentRating:
        return self.papi_tournament_info.rating

    @property
    def point_value_type(self) -> PointValueType:
        return self.papi_tournament_info.point_value_type

    @property
    def tie_breaks(self) -> list[TieBreak]:
        return self.papi_tournament_info.tie_breaks

    @property
    def arbiter(self) -> str:
        return self.papi_tournament_info.arbiter

    @cached_property
    def players_by_id(self) -> dict[int, Player]:
        _, players_by_id = self.papi_values
        # The computation of the property `current_round` needs to access a players' iterable.
        # Calling `self.players` in the context of this function creates a circular dependency
        # as it itself calls `self.players_by_id`.
        # To avoid this dependency, `self._players` is temporarily allocated.
        self._players = players_by_id.values()
        illegal_moves: Counter[int] = self.get_illegal_moves(self.current_round)
        for player in self.players:
            player.illegal_moves = illegal_moves[player.id]
            player.tournament = self
            self.set_player_points(player, before_round=self.current_round)
        self._estimate_players(self.players, after_round=self.current_round)
        self._players = None
        return players_by_id

    @property
    def players(self) -> Iterable[Player]:
        if self._players is not None:
            return self._players
        return self.players_by_id.values()

    @cached_property
    def player_count(self) -> int:
        return len(self.players_by_id)

    @cached_property
    def players_by_fide_id(self) -> dict[int, Player]:
        return {player.fide_id: player for player in self.players if player.fide_id}

    @cached_property
    def players_by_starting_rank(self) -> dict[int, Player]:
        ordered_players = sorted(
            self.players,
            key=lambda player: player.starting_rank_sort_key,
        )
        return {
            trf_id: player for trf_id, player in enumerate(ordered_players, start=1)
        }

    @cached_property
    def players_by_name_with_unpaired(self) -> list[Player]:
        return sorted(
            self.players,
            key=lambda player: (player.last_name, player.first_name),
        )

    @cached_property
    def players_by_name_without_unpaired(self) -> list[Player]:
        return sorted(
            [
                player
                for player in self.players
                if not self.current_round or player.board_id
            ],
            key=lambda p: (p.last_name, p.first_name),
        )

    @cached_property
    def gender_counts(self) -> Counter[PlayerGender]:
        """Returns the number of players by gender."""
        counter: Counter[PlayerGender] = Counter[PlayerGender]()
        for player in self.players:
            counter[player.gender] += 1
        return counter

    @cached_property
    def federation_counts(self) -> Counter[Federation]:
        """Returns the number of players by federation."""
        counter: Counter[Federation] = Counter[Federation]()
        for player in self.players:
            counter[player.federation] += 1
        return counter

    @cached_property
    def club_counts(self) -> Counter[Club]:
        """Returns the number of players by club."""
        counter: Counter[Club] = Counter[Club]()
        for player in self.players:
            if player.club is not None:
                counter[player.club] += 1
        return counter

    @property
    def max_ranking_round(self) -> int:
        if not self.started:
            return 0
        if self.playing:
            return self.current_round - 1
        return self.current_round

    @property
    def started(self) -> bool:
        return self.current_round != 0

    @property
    def finished(self) -> bool:
        return self.current_round == self.rounds and not self.playing

    @cached_property
    def boards(self) -> list[Board]:
        return self.build_boards()

    @cached_property
    def unpaired_players(self) -> list[Player]:
        return self.get_unpaired_players(self.boards)

    @cached_property
    def dependent_families(self) -> list[Family]:
        return [
            family
            for family in self.event.families_by_id.values()
            if family.tournament.id == self.id
        ]

    @cached_property
    def dependent_screens(self) -> list[Screen]:
        dependent_screens = []
        for screen in self.event.basic_screens_by_id.values():
            for screen_set in screen.screen_sets_sorted_by_order:
                if screen_set.tournament.id == self.id:
                    dependent_screens.append(screen)
        return dependent_screens

    @property
    def print_real_points(self) -> bool:
        return self.pairing_variation.print_real_points(self.current_round, self.rounds)

    @property
    def point_values(self) -> dict[Result, float]:
        return self.point_value_type.point_values

    @property
    def plugin_data(self) -> dict[str, dict[str, Any]]:
        return self.stored_tournament.plugin_data or {}

    @cached_property
    def current_round(self) -> int:
        return (
            self.stored_tournament.current_round
            or self.pairing_system.default_current_round(self)
        )

    @cached_property
    def is_fully_paired(self) -> bool:
        return all(self.is_round_paired(round_) for round_ in range(1, self.rounds + 1))

    @cached_property
    def has_results(self) -> bool:
        return any(
            self.round_has_result(round_) for round_ in range(1, self.rounds + 1)
        )

    @cached_property
    def has_pairings(self) -> bool:
        return any(
            self.round_has_pairings(round_) for round_ in range(1, self.rounds + 1)
        )

    @cached_property
    def last_paired_round(self) -> int:
        return next(
            (
                round_
                for round_ in reversed(range(1, self.rounds + 1))
                if self.round_has_pairings(round_)
            ),
            0,
        )

    @cached_property
    def can_add_players(self) -> bool:
        """Determines if players can be added to the tournament."""
        return (
            self.file_exists
            and not self.finished
            and (
                not self.has_pairings
                or self.pairing_system.allow_player_addition_once_paired
            )
        )

    @cached_property
    def playing(self) -> bool:
        return self.is_round_in_tournament(
            self.current_round
        ) and not self.is_round_finished(self.current_round)

    @cached_property
    def papi_values(self) -> tuple[PapiTournamentInfo, dict[int, Player]]:
        if self.file_exists:
            with PapiDatabase(self.file) as database:
                info = database.read_info()
                players = database.read_players(self.id, info.rounds)
                return info, players
        else:
            return PapiTournamentInfo(), {}

    def check_papi_update(self):
        if not self.file_exists:
            self.clear_cache(clear_papi_cache=True)
        elif self.stored_file_modified_timestamp != self.file_modified_timestamp:
            self.clear_cache(clear_papi_cache=True)
            self.update_stored_file_modified_timestamp()

    def update_stored_file_modified_timestamp(self):
        self.stored_file_modified_timestamp = self.file_modified_timestamp

    def clear_cache(self, clear_papi_cache: bool = False):
        """Clears the cache of the tournament."""
        cached_property_names = [
            name
            for name in dir(self)
            if isinstance(getattr(type(self), name, None), cached_property)
        ]
        if not clear_papi_cache:
            cached_property_names.remove('papi_values')
            cached_property_names.remove('players_by_id')
            cached_property_names.remove('papi_tournament_info')
        for property_name in cached_property_names:
            if property_name in self.__dict__:
                del self.__dict__[property_name]
        self._players_by_rank = None
        self.event.clear_screen_cache(self.id)
        self.event.clear_player_cache()

    def pairings_generation_disabled_message(self, at_round: int) -> str | None:
        return self.pairing_variation.engine.pairings_generation_disabled_message(
            self, at_round
        )

    def is_round_finished(self, round_: int) -> bool:
        return all(
            player.pairings[round_].result != Result.NO_RESULT
            for player in self.players
        )

    def is_round_paired(self, round_: int) -> bool:
        return all(
            player.pairings[round_].opponent_id is not None
            or player.pairings[round_].result.is_bye
            for player in self.players
        )

    def round_has_result(self, round_: int) -> bool:
        return any(
            player.pairings[round_].result != Result.NO_RESULT
            and player.pairings[round_].opponent_id is not None
            for player in self.players
        )

    def round_has_played_result(self, round_: int) -> bool:
        return any(player.pairings[round_].played for player in self.players)

    def round_has_pairings(self, round_: int) -> bool:
        return any(
            player.pairings[round_].opponent_id is not None
            or player.pairings[round_].exempt
            for player in self.players
        )

    def round_has_pab(self, round_: int) -> bool:
        return any(player.pairings[round_].exempt for player in self.players)

    def is_round_in_tournament(self, round_: int) -> bool:
        return 1 <= round_ <= self.rounds

    def to_trf(
        self, trf_type: TrfType, after_round: int | None = None
    ) -> TrfTournament:
        if after_round is None:
            after_round = self.rounds
        self.compute_player_ranks(after_round=after_round)
        return TrfTournament(
            name=self.full_name,
            city=self.location,
            startdate=format_timestamp(self.start_timestamp, '%Y/%m/%d'),
            enddate=format_timestamp(self.stop_timestamp, '%Y/%m/%d'),
            numplayers=len(self.players_by_id),
            chiefarbiter=self.arbiter,
            players=[
                player.to_trf(
                    self._player_id_to_trf_id,
                    after_round=after_round,
                    include_next_round_bye=trf_type == TrfType.TRF_BX,
                )
                for player in self.players_by_starting_rank.values()
            ],
            federation=self.event.federation,
            xx_fields=(
                self._trf_xx_fields(after_round + 1)
                if trf_type == TrfType.TRF_BX
                else {}
            ),
            bb_fields=(
                self._trf_bb_fields(point_values=self.point_values)
                if trf_type == TrfType.TRF_BX
                else {}
            ),
        )

    def _player_id_to_trf_id(self, player_id: int) -> int:
        for value, player in self.players_by_starting_rank.items():
            if player.id == player_id:
                return value
        raise KeyError(f'Id of unknown player: {player_id}')

    def _player_id_to_rank(self, player_id: int) -> int:
        return self.players_by_id[player_id].rank

    def _trf_xx_fields(self, next_round: int):
        from data.pairings.settings import ColorSeedSetting

        fields: dict[str, str] = {
            'XXR': str(self.rounds),
            'XXC': ColorSeedSetting.get_value(self).to_trf_first_round_pairing,
            'XXZ': ' '.join(
                [
                    str(trf_id)
                    for trf_id, player in self.players_by_starting_rank.items()
                    if next_round in player.pairings
                    and player.pairings[next_round].next_round_bye
                ]
            ),
        }
        for trf_id, player in self.players_by_starting_rank.items():
            vpoints_history = [
                self._calculate_player_virtual_points(player, at_round=round_)
                for round_ in range(1, next_round + 1)
            ]
            if sum(vpoints_history) > 0:
                fields[f'XXA {trf_id:>4}'] = ' '.join(
                    [f'{float(vpoints):>4}' for vpoints in vpoints_history]
                )
        return fields

    @staticmethod
    def _trf_bb_fields(
        result_class: type[Result] = Result,
        point_values: dict[Result, float] | None = None,
    ) -> dict[str, str]:
        fields: dict[str, str] = {}
        for result in [
            result_class.GAIN,
            result_class.DRAW,
            result_class.LOSS,
            result_class.FORFEIT_LOSS,
            result_class.PAIRING_ALLOCATED_BYE,
            result_class.ZERO_POINT_BYE,
        ]:
            fields[result.bbp_field] = f'{result.points(point_values):>4}'
        return fields

    def set_player_points(self, player: Player, *, before_round: int):
        """Sets the points of a player before round *before_round*."""
        vpoints = self._calculate_player_virtual_points(player, at_round=before_round)
        player.compute_points(before_round=before_round)
        assert player.points is not None
        player.vpoints = player.points + vpoints

    def _calculate_player_virtual_points(
        self, player: Player, *, at_round: int
    ) -> float:
        return self.pairing_variation.compute_virtual_points(self, player, at_round)

    def _estimate_players(self, players: Iterable[Player], *, after_round: int):
        """Estimate the players after round *after_round*."""
        if after_round <= 1:
            return
        if not any(player.estimated for player in players):
            return

        max_possible_points = Result.GAIN.points(self.point_values) * after_round

        # NOTE(Amaras): only points from played games should be counted
        players = sorted(
            players,
            key=lambda player: player.points_after(after_round, only_played=True),
        )
        players_by_points: dict[float, list[Player]] = {
            points: list(group)
            for points, group in groupby(
                players,
                key=lambda player: player.points_after(after_round, only_played=True),
            )
        }

        point_keys = sorted(players_by_points.keys())
        level_estimations = {points: 0 for points in point_keys}

        # NOTE(Amaras): if there are rated players in the score group,
        # use the average of their ratings as the level's estimation.
        for points, test_group in players_by_points.items():
            group_ratings = [
                player.estimation for player in test_group if not player.estimated
            ]
            if group_ratings:
                average_rating = SharedUtils.round_ranking(
                    sum(group_ratings) / len(group_ratings)
                )
                level_estimations[points] = average_rating

        # NOTE(Amaras): If there are no players with a rating, use the
        # estimation of the higher level, added with the difference
        # between the score group's performance bonus and the previous
        # group's performance bonus.
        previous_estimation = previous_bonus = 0
        for points in reversed(point_keys):
            estimation = level_estimations[points]
            if estimation > 0:
                # No need to touch a group's estimation if it already has one
                previous_bonus = SharedUtils.rounded_performance_bonus(
                    points / max_possible_points
                )
                previous_estimation = estimation
            elif previous_estimation > 0:
                bonus = SharedUtils.rounded_performance_bonus(
                    points / max_possible_points
                )
                level_estimations[points] = previous_estimation - previous_bonus + bonus
                previous_estimation = level_estimations[points]
                previous_bonus = bonus

        # NOTE(Amaras): There may be additional levels with no estimation
        # (usually the best score groups but might be all but the last),
        # in which case, travel the groups upwards and estimate them
        for points in point_keys:
            estimation = level_estimations[points]
            if estimation > 0:
                previous_bonus = SharedUtils.rounded_performance_bonus(
                    points / max_possible_points
                )
                previous_estimation = estimation
            elif previous_estimation > 0:
                bonus = SharedUtils.rounded_performance_bonus(
                    points / max_possible_points
                )
                level_estimations[points] = previous_estimation - previous_bonus + bonus
                previous_estimation = level_estimations[points]
                previous_bonus = bonus

        # NOTE(Amaras): There may be a single case where all players
        # have no estimation (*estimation == 0*), which is if no
        # player is rated in the tournament.
        # In this case, obviously, no rating-based tie-break
        # should be used.
        # This includes ARO, TPR, PTP, APRO, APPO and their variants
        for points, test_group in players_by_points.items():
            estimation = level_estimations[points]
            for player in test_group:
                player.estimation = estimation

    def store_illegal_move(self, player: Player):
        """Store an illegal move for the given `player`, for the current
        round."""
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            if event_database.add_stored_illegal_move(
                self.id, self.current_round, player.id
            ):
                player.illegal_moves += 1
            event_database.commit()
        logger.info('An illegal move has been recorded for player [%s].', player.id)

    def delete_illegal_move(self, player: Player) -> bool:
        """Deletes one illegal move for the given `player` for the current
        round. If no illegal move was stored, don't do anything in the database."""
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            deleted: bool = event_database.delete_stored_illegal_move(
                self.id, self.current_round, player.id
            )
            event_database.commit()
        if deleted:
            player.illegal_moves -= 1
            player.illegal_moves = max(player.illegal_moves, 0)
            logger.info('An illegal move has been deleted for player [%s].', player.id)
        else:
            logger.info('No illegal move found for player [%s].', player.id)
        return deleted

    def get_illegal_moves(self, at_round: int) -> Counter[int]:
        """Retrieves all the illegal moves for the round *at_round*.
        Returns a Counter, ordered by player id."""
        with EventDatabase(self.event.uniq_id) as event_database:
            return event_database.get_stored_illegal_moves(self.id, at_round)

    def correct_ranking_round(self, ranking_round: int | None = None) -> int:
        """Returns a correct round number that corresponds the best to a given round number."""
        if ranking_round is None:
            return self.max_ranking_round
        else:
            return max(0, min(ranking_round, self.max_ranking_round))

    def compute_player_ranks(self, *, after_round: int | None) -> dict[int, Player]:
        """compute and return the ranks of all the players after round *after_round*."""
        after_round = self.correct_ranking_round(after_round)
        if after_round:
            # Estimate ratings to ensure we have a defined rating for everyone
            self._estimate_players(self.players, after_round=after_round)
            for player in self.players:
                player.points = player.points_after(after_round)
                player.compute_tie_break_values(after_round=after_round)
            self._players_by_rank = {
                rank: player
                for rank, player in enumerate(
                    sorted(
                        self.players,
                        key=lambda p: p.rank_sort_key,
                    ),
                    start=1,
                )
            }
        else:
            # set 0.0 tie-break values for all the players
            for player in self.players:
                player.compute_tie_break_values(after_round=0)
            self._players_by_rank = self.players_by_starting_rank
        for rank, player in self._players_by_rank.items():
            player.rank = rank
        return self._players_by_rank

    @property
    def players_by_rank(self) -> dict[int, Player]:
        assert self._players_by_rank is not None, (
            'Tournament._players_by_rank is not set, call Tournament.compute_player_ranks() before.'
        )
        return self._players_by_rank

    def build_boards(self, at_round: int | None = None) -> list[Board]:
        """Build boards for round *at_round*. Defaults to the current round.
        Returns the boards in order and the unpaired players."""
        if at_round is None:
            at_round = self.current_round
        if not at_round:
            return []
        boards: list[Board] = []
        for player in self.players:
            opponent_id = player.pairings[at_round].opponent_id
            if opponent_id in self.players_by_id:
                player_board: Board | None = None
                for board in boards:
                    if (
                        board.white_player is not None
                        and board.white_player.id == opponent_id
                    ):
                        player_board = board
                        player_board.black_player = player
                        break
                    elif (
                        board.black_player is not None
                        and board.black_player.id == opponent_id
                    ):
                        player_board = board
                        player_board.white_player = player
                        break
                if player_board is None:
                    if player.pairings[at_round].color == BoardColor.WHITE:
                        boards.append(Board(white_player=player))
                    else:
                        boards.append(Board(black_player=player))
            elif player.pairings[at_round].exempt:
                boards.append(Board(white_player=player))

        boards = sorted(boards, reverse=True)
        for index, board in enumerate(boards, start=1):
            board.id = index
            assert board.white_player is not None
            number: int = (
                board.white_player.fixed
                or (board.black_player.fixed if board.black_player else None)
                or index
            )
            board.number = number
            board.white_player.set_board(index, number, BoardColor.WHITE)
            if board.black_player is not None:
                board.black_player.set_board(index, number, BoardColor.BLACK)
            board.result = board.white_player.pairings[at_round].result
            if self.handicap and board.black_player is not None:
                strong_player: Player
                weak_player: Player
                strong_player, weak_player = sorted(
                    (board.white_player, board.black_player),
                    key=attrgetter('rating'),
                    reverse=True,
                )
                weak_time = self.time_control_initial_time or 0
                rating_diff = strong_player.rating - weak_player.rating
                if not self.time_control_handicap_penalty_step:
                    penalties = 0
                else:
                    penalties = rating_diff // self.time_control_handicap_penalty_step
                strong_time = max(
                    weak_time
                    - penalties * (self.time_control_handicap_penalty_value or 0),
                    self.time_control_handicap_min_time or 0,
                )
                strong_player.set_time_control(
                    strong_time, self.time_control_increment or 0, penalties > 0
                )
                weak_player.set_time_control(
                    weak_time, self.time_control_increment or 0, False
                )
        return boards

    def get_unpaired_players(self, boards: list[Board]) -> list[Player]:
        paired_player_ids: list[int] = []
        for board in boards:
            if board.white_player:
                paired_player_ids.append(board.white_player.id)
            if board.black_player:
                paired_player_ids.append(board.black_player.id)
        return [player for player in self.players if player.id not in paired_player_ids]

    def add_result(self, board: Board, white_result: Result, round_: int | None = None):
        """Stores the given result for the given `board` in the current round.
        Stores the `white_result` directly, and uses the opposite result
        as the black's result.
        Assumes that no asymmetric result was entered."""
        black_result = white_result.opposite_result
        assert board.white_player is not None
        assert board.black_player is not None

        if round_ is None:
            round_ = self.current_round

        with self.papi_write_database as papi_database:
            papi_database.set_player_result(
                board.white_player.ref_id, round_, white_result, True
            )
            papi_database.set_player_result(
                board.black_player.ref_id, round_, black_result, True
            )
            papi_database.commit()
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            event_database.add_stored_result(self.id, round_, board, white_result)
            event_database.commit()
        self.players_by_id[board.white_player.id].pairings[round_].result = white_result
        self.players_by_id[board.black_player.id].pairings[round_].result = black_result
        self.clear_cache()
        board.white_player.clear_cache()
        board.black_player.clear_cache()
        logger.info(
            'Added result: %s %s %d.%d %s %s %d %s %s %s %d.',
            self.event.uniq_id,
            self.uniq_id,
            round_,
            board.id,
            board.white_player.last_name,
            board.white_player.first_name,
            board.white_player.rating,
            white_result,
            board.black_player.last_name,
            board.black_player.first_name,
            board.black_player.rating,
        )

    def delete_result(self, board: Board):
        """Deletes the result for the given `board` in the current round."""
        assert self.stored_tournament.id is not None
        assert board.white_player is not None
        assert board.black_player is not None
        assert board.id is not None
        with self.papi_write_database as papi_database:
            for player in (board.white_player, board.black_player):
                papi_database.set_player_result(
                    player.ref_id, self.current_round, Result.NO_RESULT, True
                )
            papi_database.commit()
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            event_database.delete_stored_result(self.id, self.current_round, board.id)
            event_database.commit()
        logger.info(
            'Removed result: %s %s %d.%d.',
            self.event.uniq_id,
            self.uniq_id,
            self.current_round,
            board.id,
        )

    def check_in_player(self, player: Player, check_in: bool):
        """Stores the `check_in` status for the given `player`."""
        with self.papi_write_database as papi_database:
            with EventDatabase(self.event.uniq_id, write=True) as event_database:
                papi_database.check_in_player(player.id, check_in)
                event_database.set_tournament_last_check_in_update(self.id)
                event_database.commit()
                papi_database.commit()
        player.check_in = check_in
        player.clear_cache()
        self.clear_cache()

    def add_player(self, player: Player):
        """Adds a new player to the tournament, returns the player's ID."""
        ref = (max(p.ref_id for p in self.players) if self.players_by_id else 1) + 1
        with self.papi_write_database as papi_database:
            per_plugin_player_data = plugin_manager.hook.player_data_for_db_write(
                player=player
            )
            plugin_data = {
                key: value
                for data in per_plugin_player_data
                for key, value in data.items()
            }
            data: dict[str, Any] = {
                'Ref': ref,
                'Nom': player.last_name,
                'Prenom': player.first_name,
                'Sexe': player.gender.to_papi_value,
                'NeLe': PapiDatabase.date_to_papi_date(player.date_of_birth),
                'Cat': player.category.to_papi_value,
                'Elo': player.get_rating(TournamentRating.STANDARD).value,
                'Rapide': player.get_rating(TournamentRating.RAPID).value,
                'Blitz': player.get_rating(TournamentRating.BLITZ).value,
                'Federation': player.federation.name,
                'ClubRef': 0,
                'Club': player.club.name if player.club else None,
                'Fide': player.get_rating(TournamentRating.STANDARD).type.to_papi_value,
                'RapideFide': player.get_rating(
                    TournamentRating.RAPID
                ).type.to_papi_value,
                'BlitzFide': player.get_rating(
                    TournamentRating.BLITZ
                ).type.to_papi_value,
                'FideCode': player.fide_id if player.fide_id else None,
                'FideTitre': player.title.to_papi_value,
                'Pointe': player.check_in,
                'InscriptionRegle': player.paid,
                'InscriptionDu': player.owed,
                'Tel': player.phone,
                'EMail': player.mail,
                'Fixe': player.fixed or 0,
                'Flotteur': 'X' * 24,
                'Pts': 0,
                'PtA': 0,
            } | plugin_data
            for round_ in range(1, 25):
                data[f'Rd{round_:0>2}Adv'] = None
                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                data[f'Rd{round_:0>2}Cl'] = (
                    BYE_COLOR if round_ < self.current_round else UNPLAYED_COLOR
                )
            papi_database.write_player_dict(data)
            papi_database.commit()
        self.clear_cache(True)
        return ref

    def delete_player(
        self,
        player: Player,
    ):
        """Removes a player from the tournament, returns the deleted data as a dict if needed
        (used to move players from one tournament to another one)."""
        with self.papi_write_database as papi_database:
            papi_database.delete_player(player.ref_id)
            papi_database.commit()
        self.clear_cache(True)

    def update_player(
        self,
        player: Player,
    ):
        """Updates a player."""
        with self.papi_write_database as papi_database:
            papi_database.update_player(player)
            papi_database.commit()
        self.clear_cache(True)

    def create_round_pairing(
        self, round_nb: int, white_player_id: int, black_player_id: int | None
    ):
        """Creates a pairing for a round."""
        white_player = self.players_by_id[white_player_id]
        black_player = (
            self.players_by_id[black_player_id] if black_player_id is not None else None
        )
        white_pairing = white_player.pairings.get(round_nb, None)
        black_pairing = (
            black_player.pairings.get(round_nb, None) if black_player else None
        )

        if white_pairing and white_pairing.opponent_id:
            raise ValueError(
                f'White player {white_player.last_name} {white_player.first_name} already has an opponent for round {round_nb}.'
            )
        if black_player is not None and black_pairing and black_pairing.opponent_id:
            raise ValueError(
                f'Black player {black_player.last_name} {black_player.first_name} already has an opponent for round {round_nb}.'
            )

        with self.papi_write_database as papi_database:
            white_player.pairings[round_nb] = Pairing(
                BoardColor.WHITE,
                black_player.id if black_player else None,
                Result.NO_RESULT if black_player else Result.PAIRING_ALLOCATED_BYE,
            )
            papi_database.update_player_pairing(
                white_player, round_nb, white_player.pairings[round_nb]
            )
            if black_player:
                papi_database.remove_exempt_pairing(round_nb)
                black_player.pairings[round_nb] = Pairing(
                    BoardColor.BLACK, white_player.id, Result.NO_RESULT
                )
                papi_database.update_player_pairing(
                    black_player, round_nb, black_player.pairings[round_nb]
                )
            papi_database.commit()

    def unpair_boards(self, boards: list[Board], round_: int):
        with self.papi_write_database as database:
            for board in boards:
                for player in (board.white_player, board.black_player):
                    if not player:
                        continue
                    database.remove_player_pairing(player, round_)
                    self.players_by_id[player.id].pairings[round_] = Pairing()

                if board.result == Result.PAIRING_ALLOCATED_BYE:
                    database.remove_exempt_pairing(round_)
            database.commit()
        self.clear_cache()

    def permute_board_colors(self, board: Board, round_: int):
        assert board.white_player is not None
        assert board.black_player is not None
        with self.papi_write_database as database:
            pairing = Pairing(BoardColor.BLACK, board.black_player.id, board.result)
            database.update_player_pairing(board.white_player, round_, pairing)
            self.players_by_id[board.white_player.id].pairings[round_] = pairing
            pairing = Pairing(BoardColor.WHITE, board.white_player.id, board.result)
            database.update_player_pairing(board.black_player, round_, pairing)
            self.players_by_id[board.black_player.id].pairings[round_] = pairing
            database.commit()

    def update_round_pairings(self, round_nb: int):
        """Updates the pairings of all players for a round."""
        with self.papi_write_database as papi_database:
            for player in self.players:
                if round_nb in player.pairings:
                    papi_database.update_player_pairing(
                        player, round_nb, player.pairings[round_nb]
                    )
            papi_database.commit()
        self.clear_cache(True)

    def update_papi_database_from_stored_tournament(self):
        """Updates the papi database with all the
        values in common with the stored tournament."""
        from plugins.ffe.utils import PapiPairingSystem, PapiPairingVariation

        if not self.file_exists:
            return
        with self.papi_write_database as papi_database:
            papi_database.update_tie_breaks(
                [
                    tie_break
                    for tie_break in self.stored_tie_breaks or []
                    if tie_break.papi_id is not None
                ]
            )
            papi_info: dict[PapiVariable, str | int] = {
                PapiVariable.ROUNDS: self.stored_rounds,
                PapiVariable.RATING: self.stored_rating.to_papi_value,
            }
            if self.stored_pairing_variation:
                if variation := PapiPairingVariation.get_plugin_value(
                    self.stored_pairing_variation
                ):
                    system = PapiPairingSystem.get_plugin_value(
                        self.stored_pairing_variation.system()
                    )
                    assert system is not None
                    papi_info |= {
                        PapiVariable.PAIRING_VARIATION: variation,
                        PapiVariable.PAIRING_SYSTEM: system,
                    }
            papi_database.write_info(papi_info)
            papi_database.commit()
        self.clear_cache(True)

    def open_check_in(self):
        """Opens the check-in for the tournament and sets all the present players
        as not checked-in for the next round."""
        assert not self.finished, f'Tournament [{self.uniq_id}] is finished.'
        assert not self.playing, f'Games are played for tournament [{self.uniq_id}].'
        assert not self.check_in_open, (
            f'Check-in already open for tournament [{self.uniq_id}].'
        )
        assert self.stored_tournament.id is not None
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            with self.papi_write_database as papi_database:
                event_database.set_tournament_last_check_in_update(
                    self.stored_tournament.id
                )
                self.stored_tournament.check_in_open = True
                event_database.set_tournament_check_in(self.id, True)
                papi_database.open_check_in(self.current_round + 1)
                papi_database.commit()
            event_database.commit()
        self.clear_cache(True)

    def close_check_in(self, zpbs_last_rounds: bool):
        """Closes the check-in for the tournament and assigns a ZPB to all the players not checked-in
        for the next round (if zpbs_last_rounds, for the rest of the tournament)."""
        assert self.check_in_open, (
            f'Check-in already closed for tournament [{self.uniq_id}].'
        )
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            assert self.stored_tournament.id is not None
            event_database.set_tournament_last_check_in_update(
                self.stored_tournament.id
            )
            event_database.set_tournament_check_in(self.id, False)
            event_database.commit()
            self.stored_tournament.check_in_open = False
        with self.papi_write_database as papi_database:
            papi_database.close_check_in(
                self.current_round + 1,
                (self.rounds + 1) if zpbs_last_rounds else None,
            )
            papi_database.commit()
        self.clear_cache(True)

    def set_player_byes(self, player: Player, byes: dict[int, Result]):
        """Updates a player's pairings with ZPB, HPB, FPB or not-paired values."""
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            event_database.set_tournament_last_result_update(player.tournament_id)
            event_database.commit()
        with self.papi_write_database as papi_database:
            for round_, result in byes.items():
                papi_database.set_player_result(
                    player.ref_id,
                    round_,
                    result,
                    player.pairings[round_].opponent_id is not None,
                )
                player.pairings[round_].result = result
            papi_database.commit()
        self.clear_cache()
        player.clear_cache()

    def set_current_round(self, round_: int):
        with EventDatabase(self.event.uniq_id, True) as database:
            database.set_tournament_current_round(self.id, round_)
            database.commit()
        self.clear_cache()

    def update_pairing_settings(self, pairing_settings: dict[str, Any]):
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_tournament_pairing_settings(self.id, pairing_settings)
            database.commit()
        for setting in self.pairing_variation.settings:
            setting.save_to_papi_database(
                self.papi_write_database, pairing_settings[setting.id]
            )
        self.stored_tournament.pairing_settings = pairing_settings
        self.clear_cache(clear_papi_cache=True)
