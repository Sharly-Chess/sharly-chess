from datetime import datetime
from itertools import groupby
from math import floor
from time import time
from collections import Counter
from functools import cached_property
from logging import Logger
from operator import attrgetter
from pathlib import Path

from dateutil.relativedelta import relativedelta
from trf import Tournament as TrfTournament
from typing import TYPE_CHECKING, Any

from common import format_timestamp_date_time
from common.i18n import _
from common.papi_web_config import PapiWebConfig
from data.pairing import Pairing
from data.tie_break import PapiTieBreak, TieBreak
from data.util import TrfType, performance_bonus, round_fide

if TYPE_CHECKING:
    from data.event import Event

from common.logger import get_logger
from data.board import Board
from data.chessevent_tournament import ChessEventTournament
from data.family import Family
from data.player import Player, FederationTuple, LeagueTuple, ClubTuple
from data.screen import Screen
from data.util import (
    BoardColor,
    NeedsUpload,
    TournamentRating,
    PlayerFFELicence,
    PlayerGender,
)
from data.util import TournamentPairing, Result
from database.access.papi.papi_database import PapiDatabase
from database.sqlite.event_database import EventDatabase
from database.store import StoredTournament

logger: Logger = get_logger()


class Tournament:
    """A data wrapper around a stored tournament."""

    def __init__(
        self,
        event: 'Event',
        stored_tournament: StoredTournament,
    ):
        self.event: 'Event' = event
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
        if not self.stored_tournament.ffe_id or not self.stored_tournament.ffe_password:
            self.event.add_debug(
                _(
                    'Qualification number and FFE password not set, '
                    'operations on the FFE website will not be available.'
                ),
                tournament=self,
            )
        if not self.chessevent_user_id or not self.chessevent_password:
            self.event.add_debug(
                _('ChessEvent connection not defined.'), tournament=self
            )
        elif not self.chessevent_event_id:
            self.event.add_warning(_('ChessEvent event not set.'), tournament=self)
        elif not self.chessevent_tournament_name:
            self.event.add_warning(
                _('ChessEvent tournament name not set.'), tournament=self
            )
        self._rounds: int = 0
        self._pairing: TournamentPairing | None = None
        self._rating: TournamentRating | None = None
        self._players_by_id: dict[int, Player] = {}
        self._current_round: int = 0
        self._playing: bool = False
        self._rating_limit1: int = 0
        self._rating_limit2: int = 0
        self._location: str = ''
        self._start_date: str = ''
        self._end_date: str = ''
        self._arbiter: str = ''
        self._boards: list[Board] | None = None
        self._unpaired_players: list[Player] | None = None
        self._papi_tie_breaks: tuple[
            PapiTieBreak, PapiTieBreak, PapiTieBreak
        ] | None = None
        self._papi_read = False

    @property
    def id(self) -> int:
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
        if self.stored_tournament.ffe_id:
            return str(self.stored_tournament.ffe_id)
        return self.uniq_id

    @property
    def file(self) -> Path:
        return self.path / f'{self.filename}.{PapiWebConfig.papi_ext}'

    @property
    def file_exists(self) -> bool:
        return self.file.exists()

    @property
    def ffe_id(self) -> int | None:
        return self.stored_tournament.ffe_id

    @property
    def ffe_password(self) -> str | None:
        return self.stored_tournament.ffe_password if self.ffe_id else None

    @property
    def shadowed_ffe_password(self) -> str | None:
        return (
            f'{self.ffe_password[:4] + "*" * (len(self.ffe_password) - 4)}'
            if self.ffe_password
            else None
        )

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
    def chessevent_user_id(self) -> str | None:
        if self.stored_tournament.chessevent_user_id:
            return self.stored_tournament.chessevent_user_id
        return self.event.chessevent_user_id

    @property
    def chessevent_password(self) -> str | None:
        if self.stored_tournament.chessevent_password:
            return self.stored_tournament.chessevent_password
        return self.event.chessevent_password

    @property
    def chessevent_event_id(self) -> str | None:
        if self.stored_tournament.chessevent_event_id:
            return self.stored_tournament.chessevent_event_id
        return self.event.chessevent_event_id

    @property
    def chessevent_tournament_name(self) -> str | None:
        return self.stored_tournament.chessevent_tournament_name

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
        return self.stored_tournament.first_board_number or PapiWebConfig.default_first_board_number

    @property
    def paired_bye_points(self) -> Result:
        return Result(self.stored_tournament.paired_bye_points) or PapiWebConfig.default_paired_bye_points

    @property
    def max_byes(self) -> int:
        return self.stored_tournament.max_byes or PapiWebConfig.default_max_byes

    @property
    def last_rounds_no_byes(self) -> int:
        return self.stored_tournament.last_rounds_no_byes or PapiWebConfig.default_last_rounds_no_byes

    @cached_property
    def players_by_check_in_status(self) -> dict[bool | None, list[Player]]:
        if self.finished or self.playing or not self.check_in_open:
            return {
                None: self.players_by_id.values(),
                True: [],
                False: [],
            }
        else:
            result: dict[bool | None, list[Player]] = {
                None: [],
                True: [],
                False: [],
            }
            for player in self.players_by_id.values():
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
            for player in self.players_by_id.values():
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
    def last_ffe_upload(self) -> float:
        return self.stored_tournament.last_ffe_upload

    @property
    def last_ffe_rules_upload(self) -> float:
        return self.stored_tournament.last_ffe_rules_upload

    @property
    def last_chessevent_download_md5(self) -> str:
        return self.stored_tournament.last_chessevent_download_md5

    @property
    def stored_tie_breaks(self) -> list[TieBreak] | None:
        return self.stored_tournament.tie_breaks

    @property
    def download_allowed(self) -> bool:
        return self.file_exists

    @property
    def pairings_generation_allowed(self) -> bool:
        return not self.finished and not self.playing

    @property
    def handicap(self) -> bool:
        return bool(self.time_control_handicap_penalty_value)

    @property
    def rounds(self) -> int:
        self.read_papi()
        return self._rounds

    @property
    def pairing(self) -> TournamentPairing:
        self.read_papi()
        return self._pairing

    @property
    def rating(self) -> TournamentRating:
        self.read_papi()
        return self._rating

    @property
    def rating_limit1(self) -> int:
        self.read_papi()
        return self._rating_limit1

    @property
    def rating_limit2(self) -> int:
        self.read_papi()
        return self._rating_limit2

    @property
    def location(self) -> str:
        self.read_papi()
        return self._location

    @property
    def start_date(self) -> str:
        self.read_papi()
        return self._start_date

    @property
    def end_date(self) -> str:
        self.read_papi()
        return self._end_date

    @property
    def arbiter(self) -> str:
        self.read_papi()
        return self._arbiter

    @property
    def papi_tie_breaks(
        self
    ) -> tuple[PapiTieBreak, PapiTieBreak, PapiTieBreak]:
        self.read_papi()
        return self._papi_tie_breaks

    @property
    def players_by_id(self) -> dict[int, Player]:
        self.read_papi()
        return self._players_by_id

    @cached_property
    def players_by_ffe_licence_number(self) -> dict[str, Player]:
        return {
            player.ffe_licence_number: player
            for player in self.players_by_id.values()
            if player.ffe_licence_number
        }

    @cached_property
    def players_by_ffe_id(self) -> dict[int, Player]:
        return {
            player.ffe_id: player
            for player in self.players_by_id.values()
            if player.ffe_id
        }

    @cached_property
    def players_by_fide_id(self) -> dict[int, Player]:
        return {
            player.fide_id: player
            for player in self.players_by_id.values()
            if player.fide_id
        }

    @cached_property
    def players_by_trf_id(self) -> dict[int, Player]:
        ordered_players = sorted(
            self.players_by_id.values(),
            key=lambda player: player.starting_rank_sort_key,
        )
        return {
            trf_id: player for trf_id, player
            in enumerate(ordered_players, start=1)
        }

    @cached_property
    def players_by_name_with_unpaired(self) -> list[Player]:
        return sorted(
            list(self.players_by_id.values()),
            key=lambda player: (player.last_name, player.first_name),
        )

    @cached_property
    def players_by_name_without_unpaired(self) -> list[Player]:
        return sorted(
            [
                player
                for player in list(self.players_by_id.values())
                if not self.current_round or player.board_id
            ],
            key=lambda p: (p.last_name, p.first_name),
        )

    @cached_property
    def players_by_rank(self) -> dict[int, Player]:
        ranked_players = sorted(
            self.players_by_id.values(),
            key=lambda player: player.rank_sort_key,
        )
        return {
            rank: player for rank, player in
            enumerate(ranked_players, start=1)
        }

    @cached_property
    def ffe_licence_counts(self) -> Counter[PlayerFFELicence]:
        """Returns the number of players by FFE licence."""
        counter: Counter[PlayerFFELicence] = Counter[PlayerFFELicence]()
        for player in self.players_by_id.values():
            counter[player.ffe_licence] += 1
        return counter

    @cached_property
    def gender_counts(self) -> Counter[PlayerGender]:
        """Returns the number of players by gender."""
        counter: Counter[PlayerGender] = Counter[PlayerGender]()
        for player in self.players_by_id.values():
            counter[player.gender] += 1
        return counter

    @cached_property
    def federation_counts(self) -> Counter[FederationTuple]:
        """Returns the number of players by federation."""
        counter: Counter[FederationTuple] = Counter[FederationTuple]()
        for player in self.players_by_id.values():
            counter[player.federation_tuple] += 1
        return counter

    @cached_property
    def league_counts(self) -> Counter[LeagueTuple]:
        """Returns the number of players by league."""
        counter: Counter[LeagueTuple] = Counter[LeagueTuple]()
        for player in self.players_by_id.values():
            counter[player.league_tuple] += 1
        return counter

    @cached_property
    def club_counts(self) -> Counter[ClubTuple]:
        """Returns the number of players by club."""
        counter: Counter[ClubTuple] = Counter[ClubTuple]()
        for player in self.players_by_id.values():
            counter[player.club_tuple] += 1
        return counter

    @property
    def current_round(self) -> int | None:
        self.read_papi()
        return self._current_round

    @property
    def max_ranking_round(self) -> int | None:
        if not self.started:
            return 0
        if self.finished:
            return None
        if self.playing:
            return self.current_round - 1
        return self.current_round

    @property
    def started(self) -> bool:
        self.read_papi()
        return self.current_round != 0

    @property
    def playing(self) -> bool:
        self.read_papi()
        return self._playing

    @property
    def finished(self) -> bool:
        self.read_papi()
        return self.current_round == self.rounds and not self.playing

    @property
    def boards(self) -> list[Board] | None:
        self.read_papi()
        return self._boards

    @property
    def unpaired_players(self) -> list[Player] | None:
        self.read_papi()
        return self._unpaired_players

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
        match self._pairing:
            case _ if self._current_round is None:
                return False
            case TournamentPairing.HALEY | TournamentPairing.HALEY_SOFT:
                return self._current_round <= 2
            case TournamentPairing.SAD if self._rounds is not None:
                return self._current_round <= self._rounds - 2
            case _:
                return False
    
    @cached_property
    def point_values(self) -> dict[Result, float]:
        return {
            Result.from_trf(result_type): value 
            for result_type, value in self.stored_tournament.point_values.items()
        }

    @property
    def tie_breaks(self) -> list[TieBreak]:
        tie_breaks: list[TieBreak] = []
        for papi_tie_break in self.papi_tie_breaks:
            if tie_break := papi_tie_break.to_tie_break(self.rounds):
                tie_breaks.append(tie_break)
        return tie_breaks

    def to_trf(
        self,
        trf_type: TrfType,
        first_round_pairing: BoardColor = BoardColor.WHITE,
        papi_legacy: bool = True,
    ) -> TrfTournament:
        self.set_for_ranking(self.max_ranking_round, papi_legacy)
        return TrfTournament(
            name=self.name,
            city=self.location,
            startdate=self.start_date,
            enddate=self.end_date,
            numplayers=len(self.players_by_id),
            chiefarbiter=self.arbiter,
            players=[
                player.to_trf(
                    self._player_id_to_trf_id,
                    self._player_id_to_rank(player.id),
                    self.current_round + 1
                    if trf_type == TrfType.PAIRING
                    else self.rounds,
                )
                for player in self.players_by_trf_id.values()
            ],
            federation=self.event.federation,
            xx_fields=(
                self._trf_xx_fields(first_round_pairing)
                if trf_type == TrfType.PAIRING
                else {}
            ),
            bb_fields=(self._trf_bb_fields(point_values=self.point_values) if trf_type == TrfType.PAIRING else {}),
        )

    def _find_player_value_by_id(
        self, player_id: int, players_by_value: dict[Any, Player]
    ) -> any:
        for value, player in players_by_value.items():
            if player.id == player_id:
                return value
        raise KeyError(f'Id of unknown player: {player_id}')

    def _player_id_to_trf_id(self, player_id: int) -> int:
        return self._find_player_value_by_id(player_id, self.players_by_trf_id)

    def _player_id_to_rank(self, player_id: int) -> int:
        return self._find_player_value_by_id(player_id, self.players_by_rank)

    def _trf_xx_fields(self, first_round_pairing: BoardColor):
        next_round = self.current_round + 1
        fields: dict[str, str] = {
            'XXR': str(self.rounds),
            'XXC': first_round_pairing.to_trf_first_round_pairing,
            'XXZ': ' '.join(
                [
                    str(trf_id)
                    for trf_id, player in self.players_by_trf_id.items()
                    if next_round in player.pairings
                    and player.pairings[next_round].result.is_bye
                ]
            ),
        }
        for trf_id, player in self.players_by_trf_id.items():
            vpoints_history = [
                self._calculate_player_virtual_points(player, round_nb)
                for round_nb in range(1, next_round)
            ]
            if sum(vpoints_history) > 0:
                fields[f'XXA {trf_id:>4}'] = ' '.join(
                    [f'{vpoints:>4}' for vpoints in vpoints_history]
                )
        return fields

    @staticmethod
    def _trf_bb_fields(result_class: type[Result] = Result, point_values: dict[Result, float] | None = None) -> dict[str, str]:
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

    def read_papi(self, update: bool = False):
        """Fetch tournament information from the Papi database, as well
        as the player information."""
        if self._papi_read and not update:
            return
        if self.file_exists:
            with PapiDatabase(self.file) as papi_database:
                (
                    self._rounds,
                    self._pairing,
                    self._rating,
                    self._rating_limit1,
                    self._rating_limit2,
                    self._papi_tie_breaks,
                    self._location,
                    self._start_date,
                    self._end_date,
                    self._arbiter,
                ) = papi_database.read_info()
                self._players_by_id = papi_database.read_players(self.id, self._rounds)
            for player in self._players_by_id.values():
                player.tournament = self
        else:
            self._rounds = 0
            self._players_by_id = {}
            self._current_round = 0
            self._rating_limit1 = None
            self._rating_limit2 = None
            self._papi_tie_breaks = (PapiTieBreak.NONE,) * 3
            self._location = ''
            self._start_date = ''
            self._end_date = ''
            self._arbiter = ''
            self._boards = []
            self._unpaired_players = []
        self._papi_read = True
        self._calculate_current_round()
        self._set_players_illegal_moves()  # load illegal moves for the current round
        self._calculate_points()
        self._build_boards()
        self.estimate_players(papi_legacy=True)

    def _calculate_current_round(self):
        """Computes which round is the current round.
        Currently, the current round is the first paired round with missing
        results."""
        round_infos: dict[int, dict[str, bool]] = {}
        paired_rounds: list[int] = []
        for round_ in range(1, self._rounds + 1):
            round_infos[round_] = {
                'pairings_found': False,
                'results_missing': False,
            }
            for player in self._players_by_id.values():
                if player.ref_id != 1:
                    pairing: Pairing = player.pairings[round_]
                    if pairing.color in (
                        BoardColor.WHITE,
                        BoardColor.BLACK,
                    ):
                        round_infos[round_]['pairings_found'] = True
                        paired_rounds.append(round_)
                    if (
                        pairing.result == Result.NO_RESULT
                        and pairing.opponent_id is not None
                    ):
                        round_infos[round_]['results_missing'] = True
                    if (
                        round_infos[round_]['pairings_found']
                        and round_infos[round_]['results_missing']
                    ):
                        break
        # the current round is the first one with pairings and no missing result
        if paired_rounds:
            for round_ in paired_rounds:
                if round_infos[round_]['results_missing']:
                    self._current_round = round_
                    self._playing = True
                    break
            if self._current_round == 0:
                self._current_round = paired_rounds[-1]

    def _calculate_points(self):
        for player in self._players_by_id.values():
            if player.ref_id == 1:
                continue
            vpoints = self._calculate_player_virtual_points(player, self._current_round)
            player.compute_points(self._current_round)
            player.vpoints = player.points + vpoints

    def _calculate_player_virtual_points(
        self, player: Player, round_number: int
    ) -> float:
        vpoints = Result.LOSS.points(self.point_values)
        if self._pairing == TournamentPairing.HALEY:
            if round_number <= 2 and player.rating >= self._rating_limit1:
                vpoints = Result.GAIN.points(self.point_values)
        elif self._pairing == TournamentPairing.HALEY_SOFT:
            # Round 1: All players above rating_limit1 get 1 vpoint
            # Round 2: All players above rating_limit1 get 1 vpoint
            # Round 2: All other players get .5 vpoints
            # bottom of page #138 on
            # https://dna.ffechecs.fr/wp-content/uploads/sites/2/2023/10/Livre-arbitre-octobre-2023.pdf,
            # please remove if OK
            if round_number <= 2 and player.rating >= self.rating_limit1:
                vpoints = Result.GAIN.points(self.point_values)
            elif round_number == 2 and player.rating < self.rating_limit1:
                vpoints = Result.DRAW.points(self.point_values)
        elif self._pairing == TournamentPairing.SAD:
            # Before the second to last round, we remove the virtual
            # points, and use a simple Swiss Dutch system.
            if round_number <= self._rounds - 2:
                # Each 1.5 points earned, virtual points go up by 0.5
                # No player can have more than 2 points.
                # At the start, players are sorted in three groups
                # based on their rating.
                # Group A players start with 2 points
                # Group B players start with 1 point
                # Group C players start with 0 points.
                # If a player reaches more than half of the possible score,
                # their virtual points capital is raised to 2 points.

                # NOTE(Amaras): // is implemented on float as well, so it's
                # way simpler to implement than by applying the algorithm
                # step by step.
                points = player.points_before(round_number)
                draw_points = Result.DRAW.points(self.point_values)
                potential_vpoints = draw_points * (points // (3 * draw_points))
                if player.rating >= self.rating_limit1:
                    # Group A players get 2 virtual points
                    vpoints = 2 * Result.GAIN.points(self.point_values)
                elif player.rating >= self.rating_limit2:
                    # Group B players start with 1 point
                    # Players cannot have more than 2 points
                    vpoints = min(
                        2 * Result.GAIN.points(self.point_values),
                        Result.GAIN.points(self.point_values) + potential_vpoints
                    )
                else:
                    # Group C players start with 0 points
                    # Players cannot have more than 2 points
                    vpoints = min(
                        2 * Result.GAIN.points(self.point_values), potential_vpoints)
                if 2 * points >= self._rounds * Result.GAIN.points(self.point_values):
                    # If a player gets at least half the possible score,
                    # their capital is set at 2 points.
                    # Assumes a 0-0.5-1 scoring system.
                    vpoints = 2 * Result.GAIN.points(self.point_values)
        return vpoints
    
    def estimate_players(self, *, max_round: int | None = None, papi_legacy: bool = True, debug: bool = False):
        if max_round is None:
            max_round = self._current_round
        if self._current_round <= 1:
            return
        if not any(player.estimated for player in self.players_by_id.values()):
            return
        if papi_legacy:
            round_function = round
        else:
            round_function = round_fide
        
        max_possible_points = Result.GAIN.points(self.point_values) * max_round
        score_groups: list[float] = [0]
        if (step := Result.LOSS.points(self.point_values)) == 0:
            # NOTE(Amaras) only redefined if a loss gives 0 points
            step = Result.DRAW.points(self.point_values)
        assert step > 0, "Point values are too weird to consider"
        current_score = 0
        while current_score < max_possible_points:
            # NOTE(Amaras) this assumes that you can get all possible
            # scores starting with 0, and stepping up by a loss or a draw.
            # Exotic point values like W=3, D=1.5, L=1 will not work
            current_score += step
            score_groups.append(current_score)
        
        if debug:
            # breakpoint()
            pass

        players = sorted(self.players_by_id.values(), key=lambda player: player.points_after(max_round))
        players_by_points: dict[float, list[Player]] = {
            points: list(group)
            for points, group in groupby(players, key=lambda player: player.points_after(max_round))
        }
        point_keys = sorted(players_by_points.keys())
        level_estimations = {points: 0 for points in score_groups}
        for points, test_group in players_by_points.items():
            group_ratings = [
                player.estimation
                for player in test_group
                if not player.estimated
            ]
            if group_ratings:
                average_rating = round_function(sum(group_ratings) / len(group_ratings))
                level_estimations[points] = average_rating
        previous_estimation = previous_bonus = 0
        for points in reversed(score_groups):
            estimation = level_estimations[points]
            if estimation > 0:
                previous_bonus = round_function(performance_bonus(points / max_possible_points, papi_legacy=papi_legacy))
                previous_estimation = estimation
            elif previous_estimation > 0:
                bonus = round_function(performance_bonus(points / max_possible_points, papi_legacy=papi_legacy))
                level_estimations[points] = previous_estimation + previous_bonus - bonus
                previous_estimation = level_estimations[points]
                previous_bonus = bonus
        for points in score_groups:
            estimation = level_estimations[points]
            if estimation > 0:
                previous_bonus = round_function(performance_bonus(points / max_possible_points, papi_legacy=papi_legacy))
                previous_estimation = estimation
            elif previous_estimation > 0:
                bonus = round_function(performance_bonus(points / max_possible_points, papi_legacy=papi_legacy))
                level_estimations[points] = previous_estimation + previous_bonus - bonus
                previous_estimation = level_estimations[points]
                previous_bonus = bonus

        for points, test_group in players_by_points.items():
            estimation = level_estimations[points]
            for player in test_group:
                player.estimation = estimation


    def store_illegal_move(self, player: Player):
        """Store an illegal move for the given `player`, for the current
        round."""
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            event_database.add_stored_illegal_move(
                self.id, self.current_round, player.id
            )
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
            logger.info('An illegal move has been deleted for player [%s].', player.id)
        else:
            logger.info('No illegal move found for player [%s].', player.id)
        return deleted

    def get_illegal_moves(self) -> Counter[int]:
        """Retrieves all the illegal moves for the current round.
        Returns a Counter, ordered by player id."""
        with EventDatabase(self.event.uniq_id) as event_database:
            return event_database.get_stored_illegal_moves(self.id, self.current_round)

    def _set_players_illegal_moves(self):
        illegal_moves: Counter[int] = self.get_illegal_moves()
        for player in self._players_by_id.values():
            if player.id == 1:
                continue
            player.illegal_moves = illegal_moves[player.id]

    def set_for_ranking(
        self, max_round: int | None = None, papi_legacy: bool = True
    ):
        """Sets all the values required to compute the
        rankings after the round *max_round*. """
        if (
            max_round and self.max_ranking_round is not None
            and max_round > self.max_ranking_round
        ):
            raise ValueError(
                f'Impossible to generate rankings for round [{max_round}] '
                f'(last finished round: [{self.max_ranking_round}])'
            )
        max_round = max_round or self.max_ranking_round or self.rounds
        # Estimate pairings to ensure we have a defined rank for everyone
        self.estimate_players(max_round=max_round, papi_legacy=papi_legacy, debug=True)
        for player in self.players_by_id.values():
            player.points = (
                player.total_points() if max_round is None
                else player.points_after(max_round)
            )
            player.set_tie_break_values(self, max_round)
        for player in self.players_by_rank.values():
            player.set_ranking_pairings(max_round, self._player_id_to_rank)

    def _build_boards(self):
        if not self._current_round:
            return
        self._boards: list[Board] = []
        self._unpaired_players: list[Player] = []
        for player in self._players_by_id.values():
            opponent_id = player.pairings[self._current_round].opponent_id
            if opponent_id in self._players_by_id:
                player_board: Board | None = None
                for board in self._boards:
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
                    if player.pairings[self._current_round].color == BoardColor.WHITE:
                        self._boards.append(Board(white_player=player))
                    else:
                        self._boards.append(Board(black_player=player))
            else:
                if player.pairings[self._current_round].exempt:
                    self._boards.append(Board(white_player=player))
                else:
                    self._unpaired_players.append(player)

        self._boards = sorted(self._boards, reverse=True)
        for index, board in enumerate(self._boards, start=1):
            board.id = index
            number: int = (
                board.white_player.fixed
                or (board.black_player.fixed if board.black_player else None)
                or index
            )
            board.number = number
            board.white_player.set_board(index, number, BoardColor.WHITE)
            if board.black_player is not None:
                board.black_player.set_board(index, number, BoardColor.BLACK)
            board.result = board.white_player.pairings[self._current_round].result
            if self.handicap and board.black_player is not None:
                strong_player: Player
                weak_player: Player
                strong_player, weak_player = sorted(
                    (board.white_player, board.black_player),
                    key=attrgetter('rating'),
                    reverse=True,
                )
                weak_time = self.time_control_initial_time
                rating_diff = strong_player.rating - weak_player.rating
                penalties = rating_diff // self.time_control_handicap_penalty_step
                strong_time = max(
                    weak_time - penalties * self.time_control_handicap_penalty_value,
                    self.time_control_handicap_min_time,
                )
                strong_player.set_time_control(
                    strong_time, self.time_control_increment, penalties > 0
                )
                weak_player.set_time_control(
                    weak_time, self.time_control_increment, False
                )

    @property
    def ffe_upload_needed(self) -> NeedsUpload:
        try:
            if self.stored_tournament.last_ffe_upload > self.file.lstat().st_mtime:
                # last version already uploaded
                return NeedsUpload.NO_CHANGE
            if (
                time()
                < self.stored_tournament.last_ffe_upload
                + PapiWebConfig().ffe_upload_delay
            ):
                # last upload too recent
                return NeedsUpload.RECENT_CHANGE
            return NeedsUpload.YES
        except FileNotFoundError:
            return NeedsUpload.NO_CHANGE

    @property
    def ffe_rules_upload_needed(self) -> NeedsUpload:
        try:
            if (
                self.stored_tournament.last_ffe_rules_upload
                > Path(self.rules).lstat().st_mtime
            ):
                # last version already uploaded
                return NeedsUpload.NO_CHANGE
            return NeedsUpload.YES
        except FileNotFoundError:
            return NeedsUpload.NO_CHANGE

    def add_result(self, board: Board, white_result: Result):
        """Stores the given result for the given `board` in the current round.
        Stores the `white_result` directly, and uses the opposite result
        as the black's result.
        Assumes that no asymmetric result was entered."""
        black_result = white_result.opposite_result
        with PapiDatabase(self.file, write=True) as papi_database:
            papi_database.add_board_result(
                board.white_player.ref_id, self._current_round, white_result
            )
            papi_database.add_board_result(
                board.black_player.ref_id, self._current_round, black_result
            )
            papi_database.commit()
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            event_database.add_stored_result(
                self.id, self.current_round, board, white_result
            )
            event_database.commit()
        logger.info(
            'Added result: %s %s %d.%d %s %s %d %s %s %s %d.',
            self.event.uniq_id,
            self.uniq_id,
            self._current_round,
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
        with PapiDatabase(self.file, write=True) as papi_database:
            papi_database.remove_board_result(
                board.white_player.ref_id, self._current_round
            )
            papi_database.remove_board_result(
                board.black_player.ref_id, self._current_round
            )
            papi_database.commit()
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            event_database.delete_stored_result(self.id, self.current_round, board.id)
            event_database.commit()
        logger.info(
            'Removed result: %s %s %d.%d.',
            self.event.uniq_id,
            self.uniq_id,
            self._current_round,
            board.id,
        )

    def write_chessevent_info_to_database(
        self, chessevent_tournament: ChessEventTournament, chessevent_download_md5: str
    ) -> int:
        """Stores the information from the given `chessevent_tournament` in the event database.
        For comparison, also stores `chessevent_download_md5`, so that the tournament is not downloaded unnecessarily.
        Returns the number of players added."""
        players_added: int = 0
        with PapiDatabase(self.file, write=True) as papi_database:
            with EventDatabase(self.event.uniq_id, write=True) as event_database:
                papi_database.write_chessevent_info(chessevent_tournament)
                for player_papi_id, chessevent_player in enumerate(
                    chessevent_tournament.players, start=2
                ):
                    papi_database.add_chessevent_player(
                        player_papi_id,
                        chessevent_player,
                        chessevent_tournament.check_in_started,
                    )
                    players_added += 1
                event_database.set_tournament_check_in(self.id, True)
                papi_database.open_check_in(1)
                event_database.set_tournament_last_chessevent_download_md5(
                    self.id, chessevent_download_md5
                )
                event_database.commit()
                papi_database.commit()
        return players_added

    def check_in_player(self, player: Player, check_in: bool):
        """Stores the `check_in` status for the given `player`."""
        with PapiDatabase(self.file, write=True) as papi_database:
            with EventDatabase(self.event.uniq_id, write=True) as event_database:
                papi_database.check_in_player(player.id, check_in)
                event_database.set_tournament_last_check_in_update(
                    self.stored_tournament.id
                )
                event_database.commit()
                papi_database.commit()

    def read_player_dict(
        self,
        player_papi_id: int,
    ) -> dict[str, str | int | float | None]:
        """Reads a player from the Papi database and returns it as a dict
        (used to move players from one tournament to another one)."""
        with PapiDatabase(self.file, write=True) as papi_database:
            return papi_database.read_player_dict(player_papi_id)

    def add_player(
        self,
        player: Player,
    ):
        """Adds a new player to the tournament, returns the player's ID."""
        with PapiDatabase(self.file, write=True) as papi_database:
            data: dict[str, str | int | float | None] = {
                'Ref': (max(p.ref_id for p in self.players_by_id.values()) if self.players_by_id else 1) + 1,
                'RefFFE': player.ffe_id or (datetime.now() - relativedelta(years=30)),  # like Papi does :-(
                'NrFFE': player.ffe_licence_number
                if player.ffe_licence_number
                else None,
                'Nom': player.last_name,
                'Prenom': player.first_name,
                'Sexe': player.gender.to_papi_value,
                'NeLe': PapiDatabase.date_to_papi_date(player.date_of_birth),
                'Cat': player.category.to_papi_value,
                'AffType': player.ffe_licence.to_papi_value,
                'Elo': player.ratings[TournamentRating.STANDARD],
                'Rapide': player.ratings[TournamentRating.RAPID],
                'Blitz': player.ratings[TournamentRating.BLITZ],
                'Federation': player.federation,
                'ClubRef': 0,
                'Club': player.club,
                'Ligue': player.league,
                'Fide': player.rating_types[TournamentRating.STANDARD].to_papi_value,
                'RapideFide': player.rating_types[TournamentRating.RAPID].to_papi_value,
                'BlitzFide': player.rating_types[TournamentRating.BLITZ].to_papi_value,
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
            }
            for round_ in range(1, 25):
                data[f'Rd{round_:0>2}Adv'] = None
                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                data[f'Rd{round_:0>2}Cl'] = 'F' if round_ < self.current_round else 'R'
            papi_database.write_player_dict(data)
            papi_database.commit()

    def delete_player(
        self,
        player: Player,
    ):
        """Removes a player from the tournament, returns the deleted data as a dict if needed
        (used to move players from one tournament to another one)."""
        with PapiDatabase(self.file, write=True) as papi_database:
            papi_database.delete_player(player.ref_id)
            papi_database.commit()

    def update_player(
        self,
        player: Player,
    ):
        """Updates a player."""
        with PapiDatabase(self.file, write=True) as papi_database:
            papi_database.update_player(player)
            papi_database.commit()

    def update_round_pairings(self, round_nb: int):
        """Updates the pairings of all players for a round."""
        with PapiDatabase(self.file, write=True) as papi_database:
            for player in self.players_by_id.values():
                if round_nb in player.pairings:
                    papi_database.update_player_pairing(
                        player, round_nb, player.pairings[round_nb]
                    )
            papi_database.commit()

    def update_papi_database_from_stored_tournament(self):
        """Updates the papi database with all the
        values in common with the stored tournament."""
        if not self.file_exists:
            return
        with (PapiDatabase(self.file, write=True) as papi_database):
            if tie_breaks := self._update_papi_tie_breaks():
                papi_database.update_tie_breaks(tie_breaks)
            papi_database.commit()

    def _update_papi_tie_breaks(
        self
    ) -> tuple[PapiTieBreak, PapiTieBreak, PapiTieBreak] | None:
        if self.stored_tie_breaks is None:
            return None
        tie_breaks: list[PapiTieBreak] = [
            PapiTieBreak.from_tie_break(tie_break)
            for tie_break in self.stored_tie_breaks[:3]
        ] + [PapiTieBreak.NONE] * (3 - len(self.stored_tie_breaks))
        self._papi_tie_breaks = (tie_breaks[0], tie_breaks[1], tie_breaks[2])
        return self._papi_tie_breaks

    def open_check_in(self):
        """Opens the check-in for the tournament and sets all the present players
        as not checked-in for the next round."""
        assert not self.finished, f'Tournament [{self.uniq_id}] is finished.'
        assert not self.playing, f'Games are played for tournament [{self.uniq_id}].'
        assert not self.check_in_open, (
            f'Check-in already open for tournament [{self.uniq_id}].'
        )
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            with PapiDatabase(self.file, write=True) as papi_database:
                event_database.set_tournament_last_check_in_update(
                    self.stored_tournament.id
                )
                event_database.set_tournament_check_in(self.id, True)
                papi_database.open_check_in(self.current_round + 1)
                papi_database.commit()
            event_database.commit()

    def close_check_in(self, forfeit_last_rounds: bool):
        """Closes the check-in for the tournament and sets all the players not checked-in as forfeit
        for the next round (if forfeit_last_rounds, for the rest of the tournament)."""
        assert self.check_in_open, (
            f'Check-in already closed for tournament [{self.uniq_id}].'
        )
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            event_database.set_tournament_last_check_in_update(
                self.stored_tournament.id
            )
            event_database.set_tournament_check_in(self.id, False)
            event_database.commit()
        with PapiDatabase(self.file, write=True) as papi_database:
            papi_database.close_check_in(
                self.current_round + 1,
                (self.rounds + 1) if forfeit_last_rounds else None,
            )
            papi_database.commit()
