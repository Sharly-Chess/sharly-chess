from datetime import date, datetime
import weakref
from collections import Counter, defaultdict
from collections.abc import Collection
from functools import cached_property
from logging import Logger
from operator import attrgetter
from typing import TYPE_CHECKING, Any
from _weakref import ReferenceType

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from common.logger import get_logger

from data.account import Account
from data.board import Board
from data.criteria.managers import TournamentCriterionManager
from data.family import Family
from data.pairings.settings import ColorSeedSetting
from data.player import Player, TournamentPlayer
from data.player_categories import PlayerCategory
from data.prize.assigned_prize import AssignedPrize
from data.prize.prize_category import PrizeCategory
from data.prize.prize_group import PrizeGroup
from data.screen import Screen
from data.tie_breaks import (
    TieBreak,
    TieBreakOption,
    TieBreakManager,
    TieBreakOptionManager,
)
from data.criteria.tournament_criteria import TournamentCriterion
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredBoard,
    StoredTournamentPlayer,
    StoredPairing,
    StoredTieBreak,
)
from plugins.utils import PluginData
from plugins.manager import plugin_manager
from utils import Utils
from utils.date_time import format_date_range, format_date, format_datetime
from utils.enum import (
    BoardColor,
    PlayerGender,
    Result,
    TournamentRating,
    PlayerRatingType,
    ScreenType,
    RoleType,
    PlayerTitle,
    CheckInStatus,
    TitleNorm,
)

from utils.types import BigTournamentExemption
from data.norms import (
    compute_big_tournament_exemption,
    compute_high_level_tournament,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament, StoredPrizeGroup

if TYPE_CHECKING:
    from data.event import Event
    from data.input_output.trf.trf_data import (
        TrfTournament,
        TrfRoundBye,
        TrfAcceleratedRound,
    )
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
        self._tournament_players_by_rank: dict[int, TournamentPlayer] | None = None

    # -------------------------------------------------------------------------
    # Plugin
    # -------------------------------------------------------------------------

    @staticmethod
    def plugin_data_class_by_plugin_id() -> dict[str, type[PluginData]]:
        return {
            plugin_id: plugin_data_class
            for plugin_id, plugin_data_class in plugin_manager.hook.get_tournament_plugin_data_class()
        }

    @cached_property
    def plugin_data(self) -> dict[str, PluginData]:
        return {
            plugin_id: plugin_data_class.from_stored_value(
                self.stored_tournament.plugin_data.get(plugin_id, {})
            )
            for plugin_id, plugin_data_class in self.plugin_data_class_by_plugin_id().items()
        }

    # -------------------------------------------------------------------------
    # Stored properties
    # -------------------------------------------------------------------------

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
    def index(self) -> int:
        return self.stored_tournament.index

    @property
    def name(self) -> str:
        return self.stored_tournament.name

    @property
    def sanitized_name(self) -> str:
        return Utils.name_to_uniq_id(self.name)

    @property
    def full_name(self) -> str:
        return (
            f'{self.event.name} - {self.name}'
            if len(self.event.tournaments_by_id.values()) > 1
            else self.event.name
        )

    @property
    def log_prefix(self) -> str:
        return f'Event [{self.event.uniq_id}] - Tournament [{self.name}] - '

    @property
    def start_date(self) -> date:
        return self.stored_tournament.start_date

    @property
    def stop_date(self) -> date:
        return self.stored_tournament.stop_date

    @property
    def date_range_str(self) -> str:
        return format_date_range(self.start_date, self.stop_date)

    @property
    def start_date_str(self) -> str:
        return format_date(self.start_date)

    @property
    def stop_date_str(self) -> str:
        return format_date(self.stop_date)

    # Round schedule

    @property
    def round_datetimes(self) -> dict[int, datetime | None]:
        """Return the per-round scheduled datetimes: {round_number: datetime | None}."""
        return self.stored_tournament.round_datetimes

    @property
    def has_schedule(self) -> bool:
        """True if at least one round has a scheduled datetime."""
        return any(v is not None for v in self.round_datetimes.values())

    @property
    def schedule_first_datetime(self) -> datetime | None:
        """Return the earliest scheduled round datetime, or None if no schedule."""
        datetimes = [v for v in self.round_datetimes.values() if v is not None]
        return min(datetimes) if datetimes else None

    @property
    def schedule_last_datetime(self) -> datetime | None:
        """Return the latest scheduled round datetime, or None if no schedule."""
        datetimes = [v for v in self.round_datetimes.values() if v is not None]
        return max(datetimes) if datetimes else None

    @property
    def round_schedule_tooltip_str(self) -> str:
        """Return a multi-line string listing each round with its scheduled time, grouped by date."""
        from collections import defaultdict
        from utils.date_time import format_time

        rounds_by_date = defaultdict(list)
        for round_num in sorted(self.round_datetimes.keys()):
            dt = self.round_datetimes[round_num]
            if dt is not None:
                rounds_by_date[format_date(dt.date())].append((round_num, dt))

        lines: list[str] = ['<div class="text-start text-nowrap d-flex flex-column">']
        for date_str, rounds in rounds_by_date.items():
            if len(rounds) == 1:
                round_num, dt = rounds[0]
                round_str = _('Round #{round}').format(round=round_num)
                lines.append(f'<div><b>{format_datetime(dt)}</b> {round_str}</div>')
            else:
                lines.append(f'<div><b>{date_str}</b></div>')
                for round_num, dt in rounds:
                    round_str = _('Round #{round}').format(round=round_num)
                    lines.append(
                        f'<div class="d-flex gap-2 ms-2"><b class="text-end" style="min-width: 45px">{format_time(dt)}</b><span>{round_str}</span></div>'
                    )
        lines.append('</div>')
        return ''.join(lines)

    @property
    def multiple_fide_periods(self) -> bool:
        """Returns True if the tournament lasts more than one month, False otherwise."""
        return (self.stop_date - self.start_date).days > 30

    @property
    def location(self) -> str | None:
        return self.stored_tournament.location or self.event.location

    @property
    def time_control_trf25(self) -> str:
        return self.stored_tournament.time_control_trf25 or ''

    @property
    def record_illegal_moves(self) -> int:
        if self.stored_tournament.record_illegal_moves is not None:
            return self.stored_tournament.record_illegal_moves
        return SharlyChessConfig.default_record_illegal_moves

    @property
    def check_in_open(self) -> bool:
        return self.stored_tournament.check_in_open

    @property
    def default_player_check_in(self) -> bool:
        return self.started

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
        if self.stored_tournament.max_byes is None:
            return SharlyChessConfig.default_max_byes
        else:
            return self.stored_tournament.max_byes

    @property
    def last_rounds_no_byes(self) -> int:
        if self.stored_tournament.last_rounds_no_byes is None:
            return SharlyChessConfig.default_last_rounds_no_byes
        else:
            return self.stored_tournament.last_rounds_no_byes

    @property
    def last_update(self) -> datetime:
        return self.stored_tournament.last_update

    @property
    def last_player_update(self) -> datetime:
        return self.stored_tournament.last_player_update or self.last_update

    @property
    def last_pairing_update(self) -> datetime:
        return self.stored_tournament.last_pairing_update or self.last_update

    @property
    def rounds(self) -> int:
        return self.stored_tournament.rounds

    @property
    def pairing_variation(self) -> 'PairingVariation':
        from data.pairings import PairingVariationManager

        return PairingVariationManager(self.event).get_object(
            self.stored_tournament.pairing
        )

    @property
    def pairing_system(self) -> 'PairingSystem':
        return self.pairing_variation.system()

    @cached_property
    def rating(self) -> TournamentRating:
        return TournamentRating(self.stored_tournament.rating)

    @cached_property
    def player_rating_type(self) -> PlayerRatingType:
        return (
            PlayerRatingType(self.stored_tournament.player_rating_type)
            if self.stored_tournament.player_rating_type is not None
            else self.event.player_rating_type
        )

    @property
    def override_unrated_rapid_blitz(self) -> bool:
        return self.stored_tournament.override_unrated_rapid_blitz

    @property
    def three_points_for_a_win(self) -> bool:
        return self.stored_tournament.three_points_for_a_win

    @property
    def pab_value(self) -> Result:
        return Result(self.stored_tournament.pab_value)

    # -------------------------------------------------------------------------
    # Pairing settings
    # -------------------------------------------------------------------------

    @property
    def stored_pairing_settings(self) -> dict[str, Any]:
        return self.stored_tournament.pairing_settings

    @cached_property
    def pairing_settings(self) -> dict[str, Any]:
        return {
            setting.id: setting.get_value(self)
            for setting in self.pairing_variation.settings
        }

    @property
    def pairing_warning_message(self) -> str | None:
        """Warning to display at global pairing level."""
        plugin_warning = plugin_manager.hook_for_event(
            self.event, 'get_tournament_pairing_warning_message'
        )(tournament=self)
        if plugin_warning:
            return plugin_warning
        return None

    def set_valid_pairing_settings(self):
        modified_settings: dict[str, Any] = {}
        for setting in self.pairing_variation.settings:
            if setting.is_valid(self):
                continue
            modified_settings[setting.id] = setting.to_stored_value(
                setting.default_value(self)
            )
        if modified_settings:
            self.update_pairing_settings(
                self.stored_pairing_settings | modified_settings
            )

    def update_pairing_settings(self, pairing_settings: dict[str, Any]):
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_tournament_pairing_settings(self.id, pairing_settings)
        self.stored_tournament.pairing_settings = pairing_settings
        Utils.reset_cached_properties(self, 'pairing_settings')

    def get_pairing_settings_data_errors(self, data: dict[str, str]) -> dict[str, Any]:
        return self.pairing_variation.get_settings_data_errors(self, data)

    # -------------------------------------------------------------------------
    # Tie-breaks
    # -------------------------------------------------------------------------

    def _tie_break_from_stored_tie_break(
        self, stored_tie_break: StoredTieBreak
    ) -> TieBreak | None:
        try:
            tie_break_type = TieBreakManager(self.event).get_type(stored_tie_break.type)
        except KeyError:
            logger.warning(
                'Tie-break [%s] not found for tournament [%s].',
                stored_tie_break.type,
                self.name,
            )
            return None
        options: list[TieBreakOption] = []
        manager = TieBreakOptionManager(self.event)
        for option_id, option_value in stored_tie_break.options.items():
            try:
                option_type = manager.get_type(option_id)
                options.append(option_type(option_value))
            except KeyError:
                logger.warning(
                    'Unknown tie-break option [%s] for tie-break [%d].',
                    option_id,
                    stored_tie_break.id,
                )
        return tie_break_type(options)

    @cached_property
    def tie_breaks_by_id(self) -> dict[int, TieBreak]:
        tie_breaks_by_id: dict[int, TieBreak] = {}
        for stored_tie_break in self.stored_tournament.stored_tie_breaks:
            if not (
                tie_break := (self._tie_break_from_stored_tie_break(stored_tie_break))
            ):
                continue
            id_ = stored_tie_break.id
            assert id_ is not None
            tie_breaks_by_id[id_] = tie_break
        return tie_breaks_by_id

    @property
    def tie_breaks(self) -> list[TieBreak]:
        invalid_tie_break_ids = self.tie_breaks_invalid_messages.keys()
        return [
            tie_break
            for stored_id, tie_break in self.tie_breaks_by_id.items()
            if stored_id not in invalid_tie_break_ids
        ]

    @property
    def team_ranking_tie_breaks(self) -> list[TieBreak]:
        return [
            tie_break
            for tie_break in self.tie_breaks
            if tie_break.is_used_for_team_ranking
        ]

    @property
    def tie_breaks_with_invalid(self) -> Collection[TieBreak]:
        return self.tie_breaks_by_id.values()

    @property
    def tie_breaks_invalid_messages(self) -> dict[int, str]:
        """Get all the messages invalidating the tie-breaks, including the order errors."""
        invalid_messages_by_id: dict[int, str] = {}
        valid_tie_breaks: list[TieBreak] = []
        for stored_id, tie_break in self.tie_breaks_by_id.items():
            if message := self.tie_break_invalid_message(tie_break):
                invalid_messages_by_id[stored_id] = message
            elif not tie_break.allow_multiple and tie_break in valid_tie_breaks:
                # Untranslated, should not happen
                invalid_messages_by_id[stored_id] = (
                    'This tie-break is already used with the same modifiers'
                )
            elif (
                valid_tie_breaks
                and tie_break.allow_multiple
                and tie_break.id == valid_tie_breaks[-1].id
            ):
                invalid_messages_by_id[stored_id] = _(
                    "This tie-break can't be used twice in a row (ignored)."
                )
            else:
                valid_tie_breaks.append(tie_break)
        return invalid_messages_by_id

    def tie_break_invalid_message(self, tie_break: TieBreak) -> str | None:
        """Get a message explaining why a tie-break is invalid in the context of the tournament.
        Return or None if it is valid."""
        if self.pairing_system in tie_break.forbidden_pairing_systems:
            return _(
                'This tie-break is not compatible with '
                'the pairing system [{pairing_system}] (ignored).'
            ).format(pairing_system=self.pairing_system.name)
        if not tie_break.allow_unrated_players and self.unrated_count:
            return _(
                'This tie-break is disabled when there are unrated players '
                'without estimated ratings ({count} in the tournament).'
            ).format(count=self.unrated_count)
        if not tie_break.allow_estimated_players and self.estimated_count:
            return _(
                'By default, this tie-break is disabled when there '
                'are unrated players ({count} in the tournament). '
                'You must specify that the player estimation is explained '
                'in the rules.'
            ).format(count=self.estimated_count)
        return None

    @property
    def tie_breaks_warning_message(self) -> str | None:
        """Warning to display at global tie-break level."""
        plugin_warning = plugin_manager.hook_for_event(
            self.event, 'get_tournament_tie_breaks_warning_message'
        )(tournament=self)
        if plugin_warning:
            return plugin_warning
        return None

    def reorder_tie_breaks(self, ordered_ids: list[int]):
        if len(ordered_ids) != len(self.tie_breaks_by_id):
            raise ValueError(f'{ordered_ids=}')
        for object_id, tie_break in self.tie_breaks_by_id.items():
            if object_id not in ordered_ids:
                raise ValueError(
                    f'Tie break [{object_id}] not part of tournament [{self.name}].'
                )
        with EventDatabase(self.event.uniq_id, True) as database:
            self._set_tie_break_indexes(database, ordered_ids)
        self.tie_breaks_by_id = {
            object_id: self.tie_breaks_by_id[object_id] for object_id in ordered_ids
        }

    def _set_tie_break_indexes(self, database: EventDatabase, ordered_ids: list[int]):
        for index, object_id in enumerate(ordered_ids):
            stored_tie_break = self.tie_breaks_by_id[object_id].to_stored_value()
            stored_tie_break.id = object_id
            stored_tie_break.tournament_id = self.id
            stored_tie_break.index = index
            database.update_stored_tie_break(stored_tie_break)

    def add_tie_break(self, tie_break: TieBreak):
        stored_tie_break = tie_break.to_stored_value()
        stored_tie_break.tournament_id = self.id
        stored_tie_break.index = len(self.tie_breaks_by_id)
        with EventDatabase(self.event.uniq_id, write=True) as database:
            object_id = database.add_stored_tie_break(stored_tie_break)
        self.tie_breaks_by_id[object_id] = tie_break
        return tie_break

    def update_tie_break(self, tie_break_id: int, new_tie_break: TieBreak):
        if tie_break_id not in self.tie_breaks_by_id:
            raise ValueError(
                f'Tie-break [{tie_break_id}] not part of tournament [{self.name}].'
            )
        stored_tie_break = new_tie_break.to_stored_value()
        stored_tie_break.id = tie_break_id
        stored_tie_break.tournament_id = self.id
        stored_tie_break.index = list(self.tie_breaks_by_id).index(tie_break_id)
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.update_stored_tie_break(stored_tie_break)
        self.tie_breaks_by_id[tie_break_id] = new_tie_break

    def delete_tie_break(self, tie_break_id: int):
        if tie_break_id not in self.tie_breaks_by_id:
            raise ValueError(
                f'Tie-break [{tie_break_id}] not part of tournament [{self.name}].'
            )
        with EventDatabase(self.event.uniq_id, True) as database:
            if self.tie_breaks_by_id[tie_break_id].is_manual:
                self.delete_manual_tie_break_values(database)
            database.delete_stored_tie_break(tie_break_id)
            del self.tie_breaks_by_id[tie_break_id]
            self._set_tie_break_indexes(database, list(self.tie_breaks_by_id))

    def delete_manual_tie_break_values(self, database: EventDatabase):
        manual_updates: dict[int, int | None] = {}
        for tournament_player in self.tournament_players:
            if tournament_player.manual_tiebreak is not None:
                tournament_player.stored_tournament_player.manual_tiebreak = None
                manual_updates[tournament_player.id] = None
        database.set_tournament_players_manual_tiebreak(self.id, manual_updates)

    @property
    def has_manual_tie_break_values(self) -> bool:
        return any(tie_break.is_manual for tie_break in self.tie_breaks) and any(
            player.manual_tiebreak is not None for player in self.tournament_players
        )

    # -------------------------------------------------------------------------
    # Criteria
    # -------------------------------------------------------------------------

    @cached_property
    def criteria(self) -> list[TournamentCriterion]:
        criteria: list[TournamentCriterion] = []
        for criteria_id, stored_value in self.stored_tournament.criteria.items():
            try:
                criterion = TournamentCriterionManager(self.event).get_object(
                    criteria_id
                )
                value = criterion.value_from_stored_value(stored_value)
                criterion.set_value(value)
                criteria.append(criterion)
            except KeyError:
                logger.exception(f'Unknown criterion [{criteria_id}].')
        return criteria

    @cached_property
    def num_players_not_matching_criteria(self) -> int:
        """Return the number of players matching all criteria of this tournament."""
        return sum(
            not player.matches_tournament_criteria for player in self.tournament_players
        )

    @property
    def sorted_criteria(self) -> list[TournamentCriterion]:
        return sorted(self.criteria, key=lambda criteria: criteria.id)

    @property
    def criteria_string(self) -> str:
        return ', '.join(criterion.full_name for criterion in self.criteria)

    # -------------------------------------------------------------------------
    # Prize groups
    # -------------------------------------------------------------------------

    @property
    def prize_groups(self) -> Collection[PrizeGroup]:
        return self.prize_groups_by_id.values()

    @property
    def sorted_prize_groups(self) -> list[PrizeGroup]:
        return sorted(
            self.prize_groups,
            key=lambda group: (
                group.main_category is None,
                -len(group.categories),
                group.id,
            ),
        )

    def get_prizes_assigned_to_players_by_group_id_by_category_id(
        self,
        monetary_only: bool,
    ) -> dict[int, dict[int, list[AssignedPrize]]]:
        result: dict[int, dict[int, list[AssignedPrize]]] = {}
        for prize_group in self.sorted_prize_groups:
            prizes_assigned_to_players_by_category_id: dict[
                int, list[AssignedPrize]
            ] = prize_group.get_prizes_assigned_to_players_by_category_id(monetary_only)
            if prizes_assigned_to_players_by_category_id:
                result[prize_group.id] = prizes_assigned_to_players_by_category_id
        return result

    @property
    def main_prize_category(self) -> PrizeCategory | None:
        return next(
            (
                prize_group.main_category
                for prize_group in self.prize_groups
                if prize_group.main_category
            ),
            None,
        )

    @cached_property
    def prize_groups_by_id(self) -> dict[int, PrizeGroup]:
        prize_groups_by_id = {}
        for stored_prize_group in self.stored_tournament.stored_prize_groups:
            assert stored_prize_group.id is not None
            prize_groups_by_id[stored_prize_group.id] = PrizeGroup(
                self, stored_prize_group
            )
        return prize_groups_by_id

    def add_prize_group(self, stored_prize_group: StoredPrizeGroup) -> PrizeGroup:
        with EventDatabase(self.event.uniq_id, True) as database:
            object_id = database.add_stored_prize_group(stored_prize_group)
        stored_prize_group.id = object_id
        prize_group = PrizeGroup(self, stored_prize_group)
        self.prize_groups_by_id[object_id] = prize_group
        return prize_group

    def delete_prize_group(self, prize_group_id: int):
        with EventDatabase(self.event.uniq_id, True) as database:
            database.delete_stored_prize_group(prize_group_id)

        if prize_group_id in self.prize_groups_by_id:
            del self.prize_groups_by_id[prize_group_id]

    def get_unused_prize_group_name(self, base_name: str | None = None) -> str:
        return Utils.get_unused_item_name(
            base_name or _('New group'),
            (group.name for group in self.prize_groups),
        )

    # -------------------------------------------------------------------------
    # Players
    # -------------------------------------------------------------------------

    @property
    def tournament_players(self) -> Collection[TournamentPlayer]:
        return self.tournament_players_by_id.values()

    @cached_property
    def player_count(self) -> int:
        return len(self.tournament_players_by_id)

    @cached_property
    def tournament_players_by_fide_id(self) -> dict[int, TournamentPlayer]:
        return {
            tournament_player.fide_id: tournament_player
            for tournament_player in self.tournament_players
            if tournament_player.fide_id
        }

    @cached_property
    def tournament_players_by_starting_rank(self) -> dict[int, TournamentPlayer]:
        ordered_players = sorted(
            self.tournament_players,
            key=lambda player: player.starting_rank_sort_key,
        )
        return {
            trf_id: player for trf_id, player in enumerate(ordered_players, start=1)
        }

    @cached_property
    def tournament_players_by_pairing_number(self) -> dict[int, TournamentPlayer]:
        self._set_tournament_players_pairing_numbers()
        return {
            tournament_player.pairing_number or 0: tournament_player
            for tournament_player in sorted(
                self.tournament_players, key=attrgetter('pairing_number')
            )
        }

    @cached_property
    def sorted_tournament_players(self) -> list[TournamentPlayer]:
        return sorted(
            self.tournament_players,
            key=attrgetter('name_sort_key'),
        )

    @cached_property
    def sorted_tournament_players_without_unpaired(self) -> list[TournamentPlayer]:
        unpaired_ids = [
            tournament_player.id
            for tournament_player in self.get_unpaired_tournament_players(self.boards)
        ]
        return [
            player
            for player in self.sorted_tournament_players
            if player.id not in unpaired_ids
        ]

    @cached_property
    def ex_aequo_rank_by_player_id(self) -> dict[int, int]:
        rank_by_player_id: dict[int, int] = {}
        previous_rank_key: tuple | None = None
        previous_rank: int = 0
        for rank, player in self.tournament_players_by_rank.items():
            rank_key = player.rank_sort_key_without_pairing_number
            if rank_key != previous_rank_key:
                previous_rank_key = rank_key
                previous_rank = player.rank
            rank_by_player_id[player.id] = previous_rank
        return rank_by_player_id

    @property
    def min_player_rating(self) -> int | None:
        if not self.tournament_players:
            return None
        return min(player.rating for player in self.tournament_players)

    @property
    def max_player_rating(self) -> int | None:
        if not self.tournament_players:
            return None
        return max(player.rating for player in self.tournament_players)

    @property
    def average_player_rating(self) -> float:
        if not self.tournament_players:
            return 0
        return sum(player.rating for player in self.tournament_players) / len(
            self.tournament_players
        )

    # -------------------------------------------------------------------------
    # Counters
    # -------------------------------------------------------------------------

    @cached_property
    def gender_counts(self) -> Counter[PlayerGender]:
        """Returns the number of players by gender."""
        counter: Counter[PlayerGender] = Counter[PlayerGender]()
        for player in self.tournament_players:
            counter[player.gender] += 1
        return counter

    @cached_property
    def federation_counts(self) -> Counter[str]:
        """Returns the number of players by federation."""
        counter: Counter[str] = Counter[str]()
        for player in self.tournament_players:
            counter[player.federation.name] += 1
        return counter

    @cached_property
    def club_counts(self) -> Counter[str]:
        """Returns the number of players by club."""
        counter: Counter[str] = Counter[str]()
        for player in self.tournament_players:
            counter[player.club.name] += 1
        return counter

    @cached_property
    def category_counts(self) -> Counter[PlayerCategory]:
        counter = Counter[PlayerCategory]()
        for player in self.tournament_players:
            counter[player.category] += 1
        return counter

    @cached_property
    def rating_type_counts(self) -> Counter[PlayerRatingType]:
        counter = Counter[PlayerRatingType]()
        for player in self.tournament_players:
            counter[player.rating_type] += 1
        return counter

    @cached_property
    def check_in_status_grouped_counts(self) -> Counter[CheckInStatus]:
        return self.check_in_status_grouped_counts_for_round(self.current_round + 1)

    def check_in_status_grouped_counts_for_round(
        self, round_: int
    ) -> Counter[CheckInStatus]:
        counter = Counter[CheckInStatus]()
        for player in self.tournament_players:
            status = player.check_in_status_for_round(round_)
            if status not in (CheckInStatus.ABSENT, CheckInStatus.PRESENT):
                status = CheckInStatus.NEXT_ROUND_BYE
            counter[status] += 1
        return counter

    @cached_property
    def unrated_count(self) -> int:
        return sum(player.rating == 0 for player in self.tournament_players)

    @cached_property
    def estimated_count(self) -> int:
        return sum(player.estimated for player in self.tournament_players)

    # -------------------------------------------------------------------------
    # Misc
    # -------------------------------------------------------------------------

    @property
    def chief_arbiter(self) -> Account | None:
        for account in self.event.accounts_by_id.values():
            role = account.get_role(RoleType.CHIEF_ARBITER)
            if role and role.tournament_ids and self.id in role.tournament_ids:
                return account
        return None

    @property
    def deputy_arbiters(self) -> list[Account]:
        return [
            account
            for account in self.event.accounts_by_id.values()
            if (
                (role := account.get_role(RoleType.DEPUTY_ARBITER))
                and role.tournament_ids
                and self.id in role.tournament_ids
            )
        ]

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

    @property
    def boards(self) -> list[Board]:
        return self.get_round_boards(self.current_round)

    def boards_without_result(self, at_round: int) -> list[Board]:
        boards = self.get_round_boards(at_round)
        return [board for board in boards if board.result == Result.NO_RESULT]

    @property
    def dependent_families(self) -> list[Family]:
        return [
            family
            for family in self.event.families_by_id.values()
            if family.tournament.id == self.id
        ]

    @property
    def dependent_screens(self) -> list[Screen]:
        dependent_screens = []
        for screen in self.event.basic_screens_by_id.values():
            match screen.type:
                case (
                    ScreenType.INPUT
                    | ScreenType.BOARDS
                    | ScreenType.PLAYERS
                    | ScreenType.RANKING
                    | ScreenType.CHECK_IN
                ):
                    if all(
                        screen_set.tournament.id == self.id
                        for screen_set in screen.screen_sets
                    ):
                        dependent_screens.append(screen)
                case ScreenType.RESULTS:
                    if screen.results_tournament_ids == [self.id]:
                        dependent_screens.append(screen)
                case ScreenType.IMAGE:
                    pass
                case _:
                    raise ValueError(f'{screen.type=}')

        return dependent_screens

    @property
    def related_screens(self) -> list[Screen]:
        related_screens = []
        for screen in self.event.basic_screens_by_id.values():
            match screen.type:
                case (
                    ScreenType.INPUT
                    | ScreenType.BOARDS
                    | ScreenType.PLAYERS
                    | ScreenType.RANKING
                    | ScreenType.CHECK_IN
                ):
                    for screen_set in screen.sorted_screen_sets:
                        if screen_set.tournament.id == self.id:
                            related_screens.append(screen)
                case ScreenType.RESULTS:
                    if (
                        not screen.results_tournament_ids
                        or self.id in screen.results_tournament_ids
                    ):
                        related_screens.append(screen)
                case ScreenType.IMAGE:
                    pass
                case _:
                    raise ValueError(f'{screen.type=}')

        return related_screens

    def print_real_points(self, round_: int | None = None) -> bool:
        if round_ is None:
            round_ = self.current_round
        return self.pairing_variation.print_real_points(round_, self.rounds)

    @cached_property
    def point_values(self) -> dict[Result, float]:
        values: dict[Result, float] = {}
        if self.three_points_for_a_win:
            values = {Result.WIN: 3, Result.DRAW: 1, Result.LOSS: 0}
        if self.pab_value != Result.WIN:
            values[Result.PAIRING_ALLOCATED_BYE] = values[self.pab_value]
        return values

    @property
    def is_standard_point_system_used(self) -> bool:
        return self.pab_value == Result.WIN and not self.three_points_for_a_win

    @cached_property
    def win_points(self) -> float:
        return Result.WIN.points(self.point_values)

    @cached_property
    def draw_points(self) -> float:
        return Result.DRAW.points(self.point_values)

    @cached_property
    def loss_points(self) -> float:
        return Result.LOSS.points(self.point_values)

    @cached_property
    def current_round(self) -> int:
        return (
            self.stored_tournament.current_round
            or self.pairing_system.default_current_round(self)
        )

    @property
    def is_last_round(self) -> bool:
        return self.current_round == self.rounds

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

    @property
    def has_titled_players(self) -> bool:
        return any(
            player.title != PlayerTitle.NONE for player in self.tournament_players
        )

    @property
    def has_norm_eligible_titled_players(self) -> bool:
        return any(
            player.title in TitleNorm.TITLE_HOLDERS
            for player in self.tournament_players
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
        return not self.finished and (
            not self.has_pairings
            or self.pairing_system.allow_player_addition_once_paired
        )

    @cached_property
    def playing(self) -> bool:
        return self.is_round_in_tournament(
            self.current_round
        ) and not self.is_round_finished(self.current_round)

    @cached_property
    def tournament_players_by_id(self) -> dict[int, TournamentPlayer]:
        players_by_id: dict[int, TournamentPlayer] = {}
        for (
            stored_tournament_player
        ) in self.stored_tournament.stored_tournament_players:
            tournament_player = TournamentPlayer(self, stored_tournament_player)
            players_by_id[tournament_player.id] = tournament_player
        return players_by_id

    @property
    def players_by_id(self) -> dict[int, TournamentPlayer]:
        return self.tournament_players_by_id

    @property
    def players(self) -> Collection[TournamentPlayer]:
        return self.tournament_players

    @cached_property
    def boards_by_id(self) -> dict[int, Board]:
        boards_by_id: dict[int, Board] = {}
        for (
            round_,
            stored_boards,
        ) in self.stored_tournament.stored_boards_by_round.items():
            for stored_board in stored_boards:
                board = Board(self, round_, stored_board)
                boards_by_id[board.identifier] = board
        return boards_by_id

    def get_round_boards(self, round_: int) -> list[Board]:
        return sorted(
            (board for board in self.boards_by_id.values() if board.round == round_),
            key=lambda board: board.index,
        )

    def get_round_pab_board(self, round_: int) -> Board | None:
        return next(
            (
                board
                for board in self.boards_by_id.values()
                if board.round == round_ and not board.black_tournament_player
            ),
            None,
        )

    def get_unpaired_tournament_players(
        self, boards: list[Board]
    ) -> list[TournamentPlayer]:
        paired_player_ids: list[int] = []
        for board in boards:
            paired_player_ids.append(board.white_tournament_player.id)
            if board.black_tournament_player:
                paired_player_ids.append(board.black_tournament_player.id)
        return [
            tournament_player
            for tournament_player in self.tournament_players
            if tournament_player.id not in paired_player_ids
        ]

    @property
    def has_never_paired_players(self) -> bool:
        return any(not player.has_real_pairings for player in self.tournament_players)

    def set_for_round(self, round_: int | None = None):
        """Set the tournament for the given round (defaults to the current round)"""
        if round_ is None:
            round_ = self.current_round
        for player in self.tournament_players:
            self.set_tournament_player_points(player, before_round=round_)
        for board in self.get_round_boards(round_):
            board.white_tournament_player.set_board(
                board.index, board.number, BoardColor.WHITE
            )
            if board.black_tournament_player:
                board.black_tournament_player.set_board(
                    board.index, board.number, BoardColor.BLACK
                )
        plugin_manager.hook_for_event(self.event, 'set_for_round')(
            tournament=self, round_=round_
        )

    def generate_round_pairings(
        self, at_round: int, partial_pairings: bool = False
    ) -> str:
        return self.pairing_variation.engine.generate_pairings(
            self, at_round, partial_pairings
        )

    def pairings_generation_disabled_message(self, at_round: int) -> str | None:
        return self.pairing_variation.engine.pairings_generation_disabled_message(
            self, at_round
        )

    def is_round_finished(self, round_: int) -> bool:
        return all(
            player.pairings[round_].result != Result.NO_RESULT
            for player in self.tournament_players
        )

    def is_round_paired(self, round_: int) -> bool:
        return all(
            player.pairings[round_].opponent_id is not None
            or player.pairings[round_].result.is_bye
            for player in self.tournament_players
        )

    def is_round_partially_paired(self, round_: int) -> bool:
        return self.round_has_pairings(round_) and not self.is_round_paired(round_)

    def round_has_result(self, round_: int) -> bool:
        return any(
            player.pairings[round_].result != Result.NO_RESULT
            and player.pairings[round_].opponent_id is not None
            for player in self.tournament_players
        )

    def round_has_played_result(self, round_: int) -> bool:
        return any(player.pairings[round_].played for player in self.tournament_players)

    def round_has_pairings(self, round_: int) -> bool:
        return any(
            player.pairings[round_].opponent_id is not None
            or player.pairings[round_].exempt
            for player in self.tournament_players
        )

    def round_has_pab(self, round_: int) -> bool:
        return any(player.pairings[round_].exempt for player in self.tournament_players)

    def is_round_in_tournament(self, round_: int) -> bool:
        return 1 <= round_ <= self.rounds

    @cached_property
    def big_tournament_exemption(self) -> BigTournamentExemption:
        """1.4.3d Swiss exception — see data.norms for the calculation.

        Cached on the Tournament instance so the per-applicant searcher
        can read it cheaply for every player.
        """
        return compute_big_tournament_exemption(self)

    @cached_property
    def high_level_tournament(self) -> bool:
        """1.5.6a — see data.norms for the calculation.

        Cached on the Tournament instance for per-applicant lookup.
        """
        return compute_high_level_tournament(self)

    def to_trf(
        self,
        after_round: int | None = None,
        next_round_pairings_as_zpb: bool = False,
    ) -> 'TrfTournament':
        from data.input_output.trf.trf_data import TrfTournament
        from data.input_output.trf.trf_importer import TRF_DATE_FORMAT
        from data.input_output.trf.trf_mappers import TrfPointSystemResult

        if after_round is None:
            after_round = self.rounds
        self.compute_tournament_player_ranks(after_round=after_round)
        seed_setting = ColorSeedSetting()
        return TrfTournament(
            name=self.name,
            city=self.location or '',
            federation=self.event.federation,
            start_date=self.start_date.strftime(TRF_DATE_FORMAT),
            end_date=self.stop_date.strftime(TRF_DATE_FORMAT),
            num_players=len(self.tournament_players_by_id),
            num_rated_players=sum(
                bool(player.fide_rating_value) for player in self.players
            ),
            chief_arbiter=getattr(self.chief_arbiter, 'fide_arbiter_str', ''),
            deputy_arbiters=[
                arbiter.fide_arbiter_str for arbiter in self.deputy_arbiters
            ],
            round_dates=[
                dt.strftime('%y/%m/%d') if dt else ''
                for idx in range(1, after_round + 1)
                for dt in [self.round_datetimes.get(idx)]
            ],
            num_rounds=self.rounds,
            initial_color=seed_setting.get_value(self).value,
            individuals_point_system={
                TrfPointSystemResult.get_outer_value(result) or '': value
                for result, value in self.point_values.items()
            },
            starting_rank_method=(
                'FIDON' if self.player_rating_type == PlayerRatingType.FIDE else 'NIDOF'
            ),
            pairing_controller_id='Sharly Chess',
            encoded_type=self.pairing_variation.trf_encoded_type,
            standings_tie_breaks=['PTS']
            + [tie_break.trf_acronym for tie_break in self.tie_breaks],
            time_control=self.time_control_trf25 or '',
            players=[
                player.to_trf(after_round, next_round_pairings_as_zpb)
                for player in self.tournament_players_by_pairing_number.values()
            ],
            accelerated_rounds=self._trf_accelerated_rounds(),
            round_byes=self._trf_round_byes(),
        )

    def _trf_round_byes(self) -> list['TrfRoundBye']:
        from data.input_output.trf.trf_data import TrfRoundBye

        round_byes: list[TrfRoundBye] = []
        for round_ in range(1, self.rounds + 1):
            pairing_numbers_by_bye: dict[Result, list[int]] = defaultdict(list)
            for (
                pairing_number,
                player,
            ) in self.tournament_players_by_pairing_number.items():
                result = player.pairings[round_].result
                if result.is_next_round_bye:
                    pairing_numbers_by_bye[result].append(pairing_number)
            for bye, pairing_numbers in pairing_numbers_by_bye.items():
                round_bye = TrfRoundBye(
                    type=bye.to_trf.upper(),
                    round=round_,
                    pairing_numbers=pairing_numbers,
                )
                round_byes.append(round_bye)
        return round_byes

    def _trf_accelerated_rounds(self) -> list['TrfAcceleratedRound']:
        from data.input_output.trf.trf_data import TrfAcceleratedRound

        variation = self.pairing_variation
        if not variation.include_accelerated_rules_in_trf:
            return []
        rounds = self.rounds
        acceleration_rules = variation.get_tournament_accelerated_rules(
            rounds, self.draw_points, self.win_points
        )
        tpn_range_by_group = variation.get_acceleration_number_range_by_group(self)
        accelerated_rounds: list[TrfAcceleratedRound] = []
        players_by_tpn = self.tournament_players_by_pairing_number
        for group, (min_tpn, max_tpn) in tpn_range_by_group.items():
            group_rules = [rule for rule in acceleration_rules if rule.group == group]
            if not any(rule.points_threshold for rule in group_rules):
                accelerated_rounds += [
                    TrfAcceleratedRound(
                        match_points=None,
                        game_points=rule.vpoints,
                        first_round=rule.first_round,
                        last_round=rule.last_round,
                        first_id=min_tpn,
                        last_id=max_tpn,
                    )
                    for rule in group_rules
                ]
                continue

            for tpn, player in players_by_tpn.items():
                if not min_tpn <= tpn <= max_tpn:
                    continue
                vpoints_history = [
                    self._calculate_player_virtual_points(player, at_round=round_)
                    for round_ in range(1, rounds + 1)
                ]
                first_round = 1
                previous_vpoints = vpoints_history[0]
                for index in range(1, rounds):
                    vpoints = vpoints_history[index]
                    if vpoints == previous_vpoints:
                        continue
                    if previous_vpoints != 0:
                        accelerated_rounds.append(
                            TrfAcceleratedRound(
                                match_points=None,
                                game_points=previous_vpoints,
                                first_round=first_round,
                                last_round=index,
                                first_id=tpn,
                                last_id=tpn,
                            )
                        )
                    first_round = index + 1
                    previous_vpoints = vpoints
                if previous_vpoints != 0:
                    accelerated_rounds.append(
                        TrfAcceleratedRound(
                            match_points=None,
                            game_points=previous_vpoints,
                            first_round=first_round,
                            last_round=rounds,
                            first_id=tpn,
                            last_id=tpn,
                        )
                    )
        return accelerated_rounds

    def set_tournament_player_points(
        self, tournament_player: TournamentPlayer, *, before_round: int
    ):
        """Sets the points of a player before round *before_round*."""
        vpoints = self._calculate_player_virtual_points(
            tournament_player, at_round=before_round
        )
        tournament_player.compute_points(before_round=before_round)
        assert tournament_player.points is not None
        tournament_player.vpoints = tournament_player.points + vpoints

    def _calculate_player_virtual_points(
        self, tournament_player: TournamentPlayer, *, at_round: int
    ) -> float:
        if self.pairing_variation.vpoints_use_pairing_numbers:
            self.set_tournament_players_pairing_numbers()
        return self.pairing_variation.compute_virtual_points(
            self, tournament_player, at_round
        )

    def store_illegal_move(self, tournament_player: TournamentPlayer):
        """Store an illegal move for the given `tournament_player`, for the current
        round."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            tournament_player.pairings[self.current_round].add_illegal_move(database)

    def delete_illegal_move(self, tournament_player: TournamentPlayer) -> bool:
        """Deletes one illegal move for the given `tournament_player` for the current round."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            deleted = tournament_player.pairings[
                self.current_round
            ].delete_illegal_move(database)
        return deleted

    def correct_ranking_round(self, ranking_round: int | None = None) -> int:
        """Returns a correct round number that corresponds the best to a given round number."""
        if ranking_round is None:
            return self.max_ranking_round
        else:
            return max(0, min(ranking_round, self.max_ranking_round))

    def compute_tournament_player_ranks(
        self, *, after_round: int | None = None
    ) -> dict[int, TournamentPlayer]:
        """compute and return the ranks of all the players after round *after_round*."""
        if after_round is None:
            after_round = self.max_ranking_round

        self.set_tournament_players_pairing_numbers()
        for tie_break in self.tie_breaks:
            for player_id, variable in tie_break.get_player_variables(
                self, after_round
            ).items():
                player = self.tournament_players_by_id[player_id]
                player.tie_break_variables[tie_break.id] = variable
        for player in self.tournament_players:
            player.points = player.points_after(after_round)
            player.compute_tie_break_values(after_round=after_round)

        for index, tie_break in enumerate(self.tie_breaks):
            if tie_break.is_computed_per_player:
                continue
            value_by_player_id = tie_break.compute_all_player_values(
                self,
                tie_break_index=index,
                after_round=after_round,
            )
            for player_id, tie_break_value in value_by_player_id.items():
                player = self.tournament_players_by_id[player_id]
                player.tie_break_values[index].value = tie_break_value

        sorted_tournament_players = sorted(
            self.tournament_players, key=lambda p: p.rank_sort_key
        )
        self._tournament_players_by_rank = {
            rank: tournament_player
            for rank, tournament_player in enumerate(sorted_tournament_players, start=1)
        }
        for rank, player in self._tournament_players_by_rank.items():
            player.rank = rank
        for tie_break_index, tie_break in enumerate(self.tie_breaks):
            if not tie_break.display_rank_delta:
                continue
            players_ranked_without_tie_break = sorted(
                self.tournament_players,
                key=lambda p: p.rank_sort_key_without_tie_break(tie_break_index),
            )
            for rank_without_tie_break, player in enumerate(
                players_ranked_without_tie_break, start=1
            ):
                player.tie_break_values[tie_break_index].rank_progress = (
                    rank_without_tie_break - player.rank
                )

        return self._tournament_players_by_rank

    @property
    def tournament_players_by_rank(self) -> dict[int, TournamentPlayer]:
        assert self._tournament_players_by_rank is not None, (
            'Tournament._tournament_players_by_rank is not set, call Tournament.compute_player_ranks() before.'
        )
        return self._tournament_players_by_rank

    def add_result(self, board: Board, white_result: Result):
        """Stores the given result for the given `board` in the current round.
        Stores the `white_result` directly, and uses the opposite result
        as the black's result.
        Assumes that no asymmetric result was entered."""
        assert board.black_tournament_player is not None

        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            board.white_pairing.update_result(event_database, white_result)
            board.black_pairing.update_result(
                event_database, white_result.opposite_result
            )

            board.set_last_result_update(board.white_pairing.result, event_database)

        logger.info(
            'Added result: %s %s %d.%d %s %s %d %s %s %s %d.',
            self.event.uniq_id,
            self.name,
            board.round,
            board.id,
            board.white_tournament_player.last_name,
            board.white_tournament_player.first_name or '',
            board.white_tournament_player.rating,
            white_result,
            board.black_tournament_player.last_name,
            board.black_tournament_player.first_name or '',
            board.black_tournament_player.rating,
        )

        # Remove the cached 'playing' value so that the pairing tab updates correctly
        self.__dict__.pop('playing', None)

    def delete_result(self, board: Board):
        """Deletes the result for the given `board`."""
        assert board.black_tournament_player is not None
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            board.white_pairing.update_result(event_database, Result.NO_RESULT)
            board.black_pairing.update_result(event_database, Result.NO_RESULT)
            board.set_last_result_update(board.white_pairing.result, event_database)
        logger.info(
            'Removed result: %s %s %d.%d.',
            self.event.uniq_id,
            self.name,
            board.round,
            board.id,
        )

        # Remove the cached 'playing' value so that the pairing tab updates correctly
        self.__dict__.pop('playing', None)

    def check_in_player(self, player: Player, check_in: bool):
        """Stores the `check_in` status for the given `player`."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_player_check_in(player.id, check_in)
        player.stored_player.check_in = check_in
        player.__dict__.pop('check_in_status', None)

    def check_in_all_players(self, check_in: bool):
        player_ids = []
        for player in self.players:
            if player.check_in != check_in:
                player_ids.append(player.id)
                player.stored_player.check_in = check_in
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_players_check_in(player_ids, check_in)

    def add_player_to_tournament(
        self,
        stored_player: StoredPlayer,
        event_database: EventDatabase | None = None,
    ):
        assert stored_player.id is not None
        current_round = self.current_round
        last_zpb_round = (
            current_round
            if current_round == 0 or self.is_round_finished(current_round)
            else current_round - 1
        )
        stored_tournament_player = StoredTournamentPlayer(
            tournament_id=self.id,
            player_id=stored_player.id,
            pairing_number=None,
            manual_tiebreak=None,
            stored_pairings=[
                StoredPairing(
                    tournament_id=self.id,
                    player_id=stored_player.id,
                    round_=round_,
                    result=Result.ZERO_POINT_BYE,
                    board_id=None,
                )
                for round_ in range(1, last_zpb_round + 1)
            ],
        )
        if event_database:
            event_database.add_stored_tournament_player(stored_tournament_player)
        else:
            with EventDatabase(self.event.uniq_id, True) as database:
                database.add_stored_tournament_player(stored_tournament_player)
        self.tournament_players_by_id[stored_player.id] = TournamentPlayer(
            self, stored_tournament_player
        )

    def get_available_board_indexes(self, round_: int) -> list[int]:
        board_indexes = [
            board.index for board in self.get_round_boards(round_) if not board.exempt
        ]
        max_board_count = (
            len(self.tournament_players) // 2 + len(self.tournament_players) % 2
        )
        return [
            index for index in range(0, max_board_count) if index not in board_indexes
        ]

    def get_pab_board_index(
        self,
        round_: int,
        new_indexes: list[int] | None = None,
    ) -> int:
        board_indexes = [
            board.index for board in self.get_round_boards(round_) if not board.exempt
        ] + (new_indexes or [])
        if not board_indexes:
            return 0
        return max(board_indexes) + 1

    def set_tournament_players_pairing_numbers(self):
        # Set up the cached property, which makes sure the
        # pairing number checking process is not executed twice
        __ = self.tournament_players_by_pairing_number

    def _set_tournament_players_pairing_numbers(self):
        """Set the pairing numbers of all the players in the tournament.
        Returns a list of players sorted by pairing number."""
        inserted_tournament_players: list[TournamentPlayer] = []
        current_tournament_players: list[TournamentPlayer] = []
        current_pairing_numbers: set[int] = set()
        for tournament_player in self.tournament_players:
            if tournament_player.pairing_number is None:
                inserted_tournament_players.append(tournament_player)
            else:
                current_tournament_players.append(tournament_player)
                current_pairing_numbers.add(tournament_player.pairing_number)
        deleted_pairing_numbers = set(range(1, self.player_count + 1)).difference(
            current_pairing_numbers
        )
        settings_updated = (
            self.pairing_variation.update_settings_from_deleted_pairing_numbers(
                self, deleted_pairing_numbers
            )
        )
        if self.current_round >= 4:
            # FIDE Handbook C.04.2.B.3: No modification of a pairing number
            # is allowed after the fourth round has been paired.
            # --> We keep the numbering only to inserted / deleted players
            if (
                not inserted_tournament_players
                and not deleted_pairing_numbers
                and not settings_updated
            ):
                return
            sorted_tournament_players = sorted(
                current_tournament_players, key=attrgetter('pairing_number')
            )
        else:
            sorted_tournament_players = sorted(
                current_tournament_players, key=attrgetter('starting_rank_sort_key')
            )
        for tournament_player in inserted_tournament_players:
            tournament_player_index = next(
                (
                    index
                    for index, player_ in enumerate(sorted_tournament_players)
                    if player_.starting_rank_sort_key
                    > tournament_player.starting_rank_sort_key
                ),
                len(sorted_tournament_players),
            )
            sorted_tournament_players.insert(tournament_player_index, tournament_player)
            settings_updated |= (
                self.pairing_variation.update_settings_from_added_pairing_number(
                    self, tournament_player_index + 1
                )
            )

        tournament_players_by_updated_pairing_number = {
            pairing_number: player
            for pairing_number, player in enumerate(sorted_tournament_players, start=1)
            if pairing_number != player.pairing_number
        }
        if not tournament_players_by_updated_pairing_number:
            return
        with EventDatabase(self.event.uniq_id, True) as database:
            for (
                pairing_number,
                tournament_player,
            ) in tournament_players_by_updated_pairing_number.items():
                tournament_player.stored_tournament_player.pairing_number = (
                    pairing_number
                )
                database.set_tournament_player_pairing_number(
                    tournament_player.stored_tournament_player
                )
            if settings_updated:
                database.set_tournament_pairing_settings(
                    self.id, self.stored_pairing_settings
                )

    def create_round_pairing(
        self, round_nb: int, white_player_id: int, black_player_id: int | None
    ) -> Board:
        """Creates a pairing for a round."""
        white_tournament_player = self.tournament_players_by_id[white_player_id]
        black_tournament_player = (
            self.tournament_players_by_id[black_player_id] if black_player_id else None
        )
        white_pairing = white_tournament_player.pairings[round_nb]
        black_pairing = (
            black_tournament_player.pairings[round_nb]
            if black_tournament_player
            else None
        )

        if white_pairing.opponent_id:
            raise ValueError(
                f'White player {white_tournament_player.full_name} already has an '
                f'opponent (id: {white_pairing.opponent_id}) for round {round_nb}.'
            )
        if black_tournament_player and black_pairing and black_pairing.opponent_id:
            raise ValueError(
                f'Black player {black_tournament_player.full_name} already has an '
                f'opponent (id: {black_pairing.opponent_id}) for round {round_nb}.'
            )
        with EventDatabase(self.event.uniq_id, True) as database:
            if black_tournament_player and black_pairing:
                result = Result.NO_RESULT
                board = self.get_round_pab_board(round_nb)
                assert board is not None
                board_id = board.identifier
                board.stored_board.index = self.get_available_board_indexes(round_nb)[0]
                board.replace_player(black_tournament_player, 'black')
                black_pairing.stored_pairing.result = result.value
                black_pairing.stored_pairing.board_id = board_id
                black_pairing.update(database)
                database.update_stored_board(board.stored_board)
            else:
                result = Result.PAIRING_ALLOCATED_BYE
                round_boards = self.get_round_boards(round_nb)
                stored_board = StoredBoard(
                    id=None,
                    white_player_id=white_tournament_player.id,
                    black_player_id=None,
                    index=round_boards[-1].index + 1 if round_boards else 0,
                )
                board_id = database.add_stored_board(stored_board)
                stored_board.id = board_id
                board = Board(self, round_nb, stored_board)
                self.boards_by_id[board_id] = board
            white_pairing.stored_pairing.result = result.value
            white_pairing.stored_pairing.board_id = board_id
            white_pairing.update(database)
        return board

    def unpair_boards(self, boards: list[Board]):
        rounds: set[int] = set()
        with EventDatabase(self.event.uniq_id, True) as database:
            for board in boards:
                rounds.add(board.round)
                board.white_tournament_player.delete_pairing(board.round, database)
                board.white_tournament_player.reset_board()
                if board.black_tournament_player:
                    board.black_tournament_player.delete_pairing(board.round, database)
                    board.black_tournament_player.reset_board()
                database.delete_stored_board(board.identifier)
                if board.identifier in self.boards_by_id:
                    del self.boards_by_id[board.identifier]
            for round_ in rounds:
                if pab_board := self.get_round_pab_board(round_):
                    pab_board.stored_board.index = self.get_pab_board_index(round_)
                    database.update_stored_board(pab_board.stored_board)

    def create_boards(
        self, stored_boards: list[StoredBoard], round_: int, pab_result: Result
    ):
        with EventDatabase(self.event.uniq_id, True) as database:
            if pab_board := self.get_round_pab_board(round_):
                pab_board.stored_board.index = self.get_pab_board_index(
                    round_, [board.index for board in stored_boards]
                )
                database.update_stored_board(pab_board.stored_board)
            for stored_board in stored_boards:
                id_ = database.add_stored_board(stored_board)
                stored_board.id = id_
                board = Board(self, round_, stored_board)
                self.boards_by_id[id_] = board
                white_stored_pairing = board.white_pairing.stored_pairing
                white_stored_pairing.board_id = id_
                if board.black_tournament_player:
                    board.black_pairing.stored_pairing.board_id = id_
                    board.black_pairing.update(database)
                else:
                    white_stored_pairing.result = pab_result.value
                board.white_pairing.update(database)

    def toggle_check_in_open(self):
        check_in_open = not self.check_in_open
        with EventDatabase(self.event.uniq_id, True) as database:
            database.set_tournament_check_in_open(self.id, check_in_open)
        self.stored_tournament.check_in_open = check_in_open

    def set_player_participation(
        self, player: TournamentPlayer, withdraw: bool = False
    ):
        # If there aren't any pairings, then the round for the bye is the first round
        round_for_participation = self.current_round or 1
        if not withdraw and self.round_has_pairings(round_for_participation):
            # If returning to tournament and pairings for this round, then start setting removing ZPBs from the next round only
            round_for_participation += 1
        result = Result.ZERO_POINT_BYE if withdraw else Result.NO_RESULT
        new_byes = {
            round_: result
            for round_ in range(
                round_for_participation,
                self.rounds + 1,
            )
            if player.pairings[round_].unpaired
        }
        self.set_player_byes(player, new_byes)
        self.check_in_player(player, not withdraw)
        player.__dict__.pop('has_withdrawn', None)
        player.__dict__.pop('check_in_status', None)

    def set_player_byes(self, player: TournamentPlayer, byes: dict[int, Result]):
        """Updates a player's pairings with ZPB, HPB, FPB or not-paired values."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            for round_, result in byes.items():
                pairing = player.pairings_by_round[round_]
                if pairing.unpaired:
                    pairing.update_result(database, result)

    def set_current_round(self, round_: int):
        with EventDatabase(self.event.uniq_id, True) as database:
            database.set_tournament_current_round(self.id, round_)
