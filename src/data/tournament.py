from datetime import datetime
import weakref
from babel.lists import format_list
from common.i18n import get_locale
from collections import Counter
from collections.abc import Collection
from functools import cached_property
from logging import Logger
from operator import attrgetter
from typing import TYPE_CHECKING, Any
from _weakref import ReferenceType

from common.i18n.utils import by
from trf import Tournament as TrfTournament

from common import format_timestamp
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from common.logger import get_logger

from data.account import Account
from data.board import Board
from data.criteria.managers import PlayerFilter
from data.family import Family
from data.player import Player, Federation, Club
from data.prize.prize_category import PrizeCategory
from data.prize.prize_group import PrizeGroup
from data.screen import Screen
from data.tie_breaks import (
    TieBreak,
    TieBreakOption,
    TieBreakManager,
    TieBreakOptionManager,
)
from data.tournament_criterion import TournamentCriterion
from database.sqlite.event.event_store import (
    RoleKind,
    StoredPlayer,
    StoredBoard,
    StoredTournamentCriterion,
    StoredTournamentPlayer,
    StoredPairing,
    StoredTieBreak,
)
from plugins.utils import PluginData
from plugins.manager import plugin_manager
from utils import Utils
from utils.enum import (
    BoardColor,
    PlayerGender,
    Result,
    TournamentRating,
    TrfType,
    PlayerCategory,
    PlayerRatingType,
    ScreenType,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament, StoredPrizeGroup
from utils.time_control import parse_time_control_trf25

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
        self.players_by_id = self._get_players_by_id()
        self.boards_by_id = self._get_boards_by_id()
        self.prize_groups_by_id = self._get_prize_groups_by_id()
        self._players_by_rank: dict[int, Player] | None = None
        self.criteria_by_id = self._get_criteria_by_id()
        self.tie_breaks_by_id = self._get_tie_breaks_by_id()
        self.plugin_data = self._get_plugin_data()

    # -------------------------------------------------------------------------
    # Plugin
    # -------------------------------------------------------------------------

    @staticmethod
    def plugin_data_class_by_plugin_id() -> dict[str, type[PluginData]]:
        return {
            plugin_id: plugin_data_class
            for plugin_id, plugin_data_class in plugin_manager.hook.get_tournament_plugin_data_class()
        }

    def _get_plugin_data(self) -> dict[str, PluginData]:
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
    def uniq_id(self) -> str:
        # TODO (Molrn) replace all the uniq_id usages by the name
        return self.name

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
        return f'Event [{self.event.uniq_id}] - Tournament [{self.uniq_id}] - '

    @property
    def start_timestamp(self) -> float:
        return self.stored_tournament.start or self.event.start

    @property
    def stop_timestamp(self) -> float:
        return self.stored_tournament.stop or self.event.stop

    @property
    def start_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.start_timestamp)

    @property
    def stop_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.stop_timestamp)

    @property
    def location(self) -> str | None:
        return self.stored_tournament.location or self.event.location

    @property
    def time_control_trf25(self) -> str:
        return self.stored_tournament.time_control_trf25 or ''

    @property
    def time_control_initial_time(self) -> int:
        """Parse initial time from TRF25 format. Returns 0 for invalid formats."""
        return parse_time_control_trf25(self.stored_tournament.time_control_trf25)[0]

    @property
    def time_control_increment(self) -> int:
        """Parse increment from TRF25 format. Returns 0 for invalid formats."""
        return parse_time_control_trf25(self.stored_tournament.time_control_trf25)[1]

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
    def last_update(self) -> float:
        return self.stored_tournament.last_update

    @property
    def last_player_update(self) -> float:
        return self.stored_tournament.last_player_update

    @property
    def last_pairing_update(self) -> float:
        return self.stored_tournament.last_pairing_update

    @property
    def handicap(self) -> bool:
        return bool(self.time_control_handicap_penalty_value)

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
        if self.stored_tournament.override_unrated_rapid_blitz is not None:
            return self.stored_tournament.override_unrated_rapid_blitz
        return self.event.override_unrated_rapid_blitz

    @property
    def three_points_for_a_win(self) -> bool:
        if self.stored_tournament.three_points_for_a_win is not None:
            return self.stored_tournament.three_points_for_a_win
        return self.event.three_points_for_a_win

    @property
    def pab_value(self) -> Result:
        if self.stored_tournament.pab_value is not None:
            return Result(self.stored_tournament.pab_value)
        return self.event.pab_value

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
        property_name = 'pairing_settings'
        if property_name in self.__dict__:
            del self.__dict__[property_name]

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

    def _get_tie_breaks_by_id(self) -> dict[int, TieBreak]:
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
        for player in self.players:
            if player.manual_tiebreak is not None:
                player.stored_tournament_player.manual_tiebreak = None
                manual_updates[player.id] = None
        database.set_tournament_players_manual_tiebreak(self.id, manual_updates)

    @property
    def has_manual_tie_break_values(self) -> bool:
        return any(tie_break.is_manual for tie_break in self.tie_breaks) and any(
            player.manual_tiebreak is not None for player in self.players
        )

    # -------------------------------------------------------------------------
    # Criteria
    # -------------------------------------------------------------------------

    def _get_criteria_by_id(self) -> dict[int, TournamentCriterion]:
        criteria_by_id = {}
        for stored_criterion in self.stored_tournament.stored_criteria:
            assert stored_criterion.id is not None
            try:
                criteria_by_id[stored_criterion.id] = TournamentCriterion(
                    self, stored_criterion
                )
            except KeyError as e:
                # This can happen when the plugin that defined the criteria is not enabled
                logger.warning(
                    'Criterion [%s] not found for tournament [%s]: %s',
                    stored_criterion.id,
                    self.uniq_id,
                    e,
                )
                pass
        return criteria_by_id

    @property
    def criteria(self) -> Collection[TournamentCriterion]:
        return self.criteria_by_id.values()

    def player_matches_criteria(self, player: Player) -> bool:
        """Check if the player matches all criteria of this tournament."""
        return all(
            criterion.player_filter.is_player_included_function(player)
            for criterion in self.criteria
        )

    def failing_criteria(self, player: Player) -> list[PlayerFilter]:
        """Return the list of criteria that the player does not match."""
        return [
            criterion.player_filter
            for criterion in self.criteria
            if not criterion.player_filter.is_player_included_function(player)
        ]

    def failing_criteria_message(self, player: Player) -> str:
        """Return the list of criteria that the player does not match."""
        locale = get_locale()
        return format_list(
            [criteria.name for criteria in self.failing_criteria(player)], locale=locale
        )

    @cached_property
    def num_players_not_matching_criteria(self) -> int:
        """Return the number of players matching all criteria of this tournament."""
        return sum(
            1
            for player in self.players_by_id.values()
            if not self.player_matches_criteria(player)
        )

    @property
    def sorted_criteria(self) -> list[TournamentCriterion]:
        return sorted(self.criteria, key=lambda criteria: criteria.id)

    @property
    def criteria_string(self) -> str:
        return ', '.join(criterion.name for criterion in self.criteria)

    def add_criterion(
        self, stored_criterion: StoredTournamentCriterion
    ) -> TournamentCriterion:
        with EventDatabase(self.event.uniq_id, write=True) as database:
            object_id = database.add_stored_tournament_criterion(stored_criterion)
        stored_criterion.id = object_id
        tournament_criterion = TournamentCriterion(self, stored_criterion)
        self.criteria_by_id[object_id] = tournament_criterion
        return tournament_criterion

    def delete_criterion(self, criterion_id: int):
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.delete_stored_tournament_criterion(criterion_id)
        if criterion_id in self.criteria_by_id:
            del self.criteria_by_id[criterion_id]

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

    def _get_prize_groups_by_id(self) -> dict[int, PrizeGroup]:
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
    def players(self) -> Collection[Player]:
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
    def players_by_pairing_number(self) -> dict[int, Player]:
        self._set_players_pairing_numbers()
        return {
            player.pairing_number or 0: player
            for player in sorted(self.players, key=attrgetter('pairing_number'))
        }

    @cached_property
    def players_by_name_with_unpaired(self) -> list[Player]:
        return sorted(
            self.players,
            key=by('last_name', 'first_name'),
        )

    @cached_property
    def players_by_name_without_unpaired(self) -> list[Player]:
        return sorted(
            [player for player in self.players if player not in self.unpaired_players],
            key=by('last_name', 'first_name'),
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

    @property
    def min_player_rating(self) -> int | None:
        if not self.players:
            return None
        return min(player.rating for player in self.players)

    @property
    def max_player_rating(self) -> int | None:
        if not self.players:
            return None
        return max(player.rating for player in self.players)

    @property
    def average_player_rating(self) -> float:
        if not self.players:
            return 0
        return sum(player.rating for player in self.players) / len(self.players)

    # -------------------------------------------------------------------------
    # Counters
    # -------------------------------------------------------------------------

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

    @cached_property
    def category_counts(self) -> Counter[PlayerCategory]:
        counter = Counter[PlayerCategory]()
        for player in self.players:
            counter[player.category] += 1
        return counter

    @cached_property
    def rating_type_counts(self) -> Counter[PlayerRatingType]:
        counter = Counter[PlayerRatingType]()
        for player in self.players:
            counter[player.rating_type] += 1
        return counter

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

    @cached_property
    def unrated_count(self) -> int:
        return sum(player.rating == 0 for player in self.players)

    @cached_property
    def estimated_count(self) -> int:
        return sum(player.estimated for player in self.players)

    # -------------------------------------------------------------------------
    # Misc
    # -------------------------------------------------------------------------

    @property
    def chief_arbiter(self) -> Account | None:
        for account in self.event.accounts_by_id.values():
            role = account.get_role(RoleKind.CHIEF_ARBITER)
            if role and role.tournament_ids and self.id in role.tournament_ids:
                return account
        return None

    @property
    def deputy_arbiters(self) -> list[Account]:
        return [
            account
            for account in self.event.accounts_by_id.values()
            if (
                (role := account.get_role(RoleKind.DEPUTY_ARBITER))
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

    @cached_property
    def unpaired_players(self) -> list[Player]:
        return self.get_unpaired_players(self.boards)

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
                ):
                    if all(
                        screen_set.tournament.id == self.id
                        for screen_set in screen.screen_sets_by_id.values()
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
                ):
                    for screen_set in screen.screen_sets_sorted_by_order:
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

    @property
    def point_values(self) -> dict[Result, float]:
        values: dict[Result, float]
        if self.three_points_for_a_win:
            values = {Result.WIN: 3, Result.DRAW: 1, Result.LOSS: 0}
        else:
            values = {Result.WIN: 1, Result.DRAW: 0.5, Result.LOSS: 0}

        values[Result.PAIRING_ALLOCATED_BYE] = values[self.pab_value]
        return values

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
        return not self.finished and (
            not self.has_pairings
            or self.pairing_system.allow_player_addition_once_paired
        )

    @cached_property
    def playing(self) -> bool:
        return self.is_round_in_tournament(
            self.current_round
        ) and not self.is_round_finished(self.current_round)

    def _get_players_by_id(self) -> dict[int, Player]:
        players_by_id: dict[int, Player] = {}
        for stored_player in self.stored_tournament.stored_players:
            player = Player(self, stored_player)
            players_by_id[player.id] = player
        return players_by_id

    def _get_boards_by_id(self) -> dict[int, Board]:
        boards_by_id: dict[int, Board] = {}
        for (
            round_,
            stored_boards,
        ) in self.stored_tournament.stored_boards_by_round.items():
            for stored_board in stored_boards:
                board = Board(self, round_, stored_board)
                boards_by_id[board.identifier] = board
        return boards_by_id

    def _set_handicap(self, round_: int):
        for board in self.get_round_boards(round_):
            if not board.black_player:
                continue
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
                weak_time - penalties * (self.time_control_handicap_penalty_value or 0),
                self.time_control_handicap_min_time or 0,
            )
            strong_player.set_time_control(
                strong_time, self.time_control_increment or 0, penalties > 0
            )
            weak_player.set_time_control(
                weak_time, self.time_control_increment or 0, False
            )

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
                if board.round == round_ and not board.black_player
            ),
            None,
        )

    def get_unpaired_players(self, boards: list[Board]) -> list[Player]:
        paired_player_ids: list[int] = []
        for board in boards:
            paired_player_ids.append(board.white_player.id)
            if board.black_player:
                paired_player_ids.append(board.black_player.id)
        return [player for player in self.players if player.id not in paired_player_ids]

    def set_for_round(self, round_: int | None = None):
        """Set the tournament for the given round (defaults to the current round)"""
        if round_ is None:
            round_ = self.current_round
        for player in self.players:
            self.set_player_points(player, before_round=round_)
        if self.handicap:
            self._set_handicap(round_)
        for board in self.get_round_boards(round_):
            board.white_player.set_board(board.index, board.number, BoardColor.WHITE)
            if board.black_player:
                board.black_player.set_board(
                    board.index, board.number, BoardColor.BLACK
                )

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

    def is_round_partially_paired(self, round_: int) -> bool:
        return self.round_has_pairings(round_) and not self.is_round_paired(round_)

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
        self,
        trf_type: TrfType,
        after_round: int | None = None,
        next_round_pairings_as_zpb: bool = False,
    ) -> TrfTournament:
        if after_round is None:
            after_round = self.rounds
        self.compute_player_ranks(after_round=after_round)
        return TrfTournament(
            name=self.name,
            city=self.location,
            startdate=format_timestamp(self.start_timestamp, '%Y/%m/%d'),
            enddate=format_timestamp(self.stop_timestamp, '%Y/%m/%d'),
            numplayers=len(self.players_by_id),
            chiefarbiter=self.chief_arbiter.full_name_and_id
            if self.chief_arbiter
            else '',
            players=[
                player.to_trf(
                    after_round,
                    next_round_pairings_as_zpb,
                    include_next_round_bye=trf_type == TrfType.TRF_BX,
                )
                for player in self.players_by_pairing_number.values()
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

    def _player_id_to_rank(self, player_id: int) -> int:
        return self.players_by_id[player_id].rank

    def _trf_xx_fields(self, next_round: int):
        from data.input_output.trf_mappers import TrfSeedColor
        from data.pairings.settings import ColorSeedSetting

        fields: dict[str, str] = {
            'XXR': str(self.rounds),
            'XXC': TrfSeedColor.get_outer_value(ColorSeedSetting.get_value(self)) or '',
            'XXZ': ' '.join(
                [
                    str(trf_id)
                    for trf_id, player in self.players_by_pairing_number.items()
                    if next_round in player.pairings
                    and player.pairings[next_round].next_round_bye
                ]
            ),
        }
        for trf_id, player in self.players_by_pairing_number.items():
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
            result_class.WIN,
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
        if self.pairing_variation.vpoints_use_pairing_numbers:
            self.set_players_pairing_numbers()
        return self.pairing_variation.compute_virtual_points(self, player, at_round)

    def store_illegal_move(self, player: Player):
        """Store an illegal move for the given `player`, for the current
        round."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            player.pairings[self.current_round].add_illegal_move(database)

    def delete_illegal_move(self, player: Player) -> bool:
        """Deletes one illegal move for the given `player` for the current round."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            deleted = player.pairings[self.current_round].delete_illegal_move(database)
        return deleted

    def correct_ranking_round(self, ranking_round: int | None = None) -> int:
        """Returns a correct round number that corresponds the best to a given round number."""
        if ranking_round is None:
            return self.max_ranking_round
        else:
            return max(0, min(ranking_round, self.max_ranking_round))

    def compute_player_ranks(
        self, *, after_round: int | None = None
    ) -> dict[int, Player]:
        """compute and return the ranks of all the players after round *after_round*."""
        if after_round is None:
            after_round = self.max_ranking_round

        self.set_players_pairing_numbers()
        for tie_break in self.tie_breaks:
            for player_id, variable in tie_break.get_player_variables(
                self, after_round
            ).items():
                player = self.players_by_id[player_id]
                player.tie_break_variables[tie_break.id] = variable
        for player in self.players:
            player.points = player.points_after(after_round)
            player.compute_tie_break_values(after_round=after_round)

        for index, tie_break in enumerate(self.tie_breaks):
            if tie_break.is_computed_per_player:
                continue
            value_by_player_id = tie_break.compute_all_player_values(
                self, tie_break_index=index, after_round=after_round
            )
            for player_id, tie_break_value in value_by_player_id.items():
                player = self.players_by_id[player_id]
                player.tie_break_values[index].value = tie_break_value

        sorted_players = sorted(self.players, key=lambda p: p.rank_sort_key)
        self._players_by_rank = {
            rank: player for rank, player in enumerate(sorted_players, start=1)
        }
        for rank, player in self._players_by_rank.items():
            player.rank = rank
        for tie_break_index, tie_break in enumerate(self.tie_breaks):
            if not tie_break.display_rank_delta:
                continue
            players_ranked_without_tie_break = sorted(
                self.players,
                key=lambda p: p.rank_sort_key_without_tie_break(tie_break_index),
            )
            for rank_without_tie_break, player in enumerate(
                players_ranked_without_tie_break, start=1
            ):
                player.tie_break_values[tie_break_index].rank_progress = (
                    rank_without_tie_break - player.rank
                )

        return self._players_by_rank

    @property
    def players_by_rank(self) -> dict[int, Player]:
        assert self._players_by_rank is not None, (
            'Tournament._players_by_rank is not set, call Tournament.compute_player_ranks() before.'
        )
        return self._players_by_rank

    def add_result(self, board: Board, white_result: Result):
        """Stores the given result for the given `board` in the current round.
        Stores the `white_result` directly, and uses the opposite result
        as the black's result.
        Assumes that no asymmetric result was entered."""
        assert board.black_player is not None

        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            board.white_pairing.update_result(event_database, white_result)
            board.black_pairing.update_result(
                event_database, white_result.opposite_result
            )

            board.set_last_result_update(board.white_pairing.result, event_database)

        logger.info(
            'Added result: %s %s %d.%d %s %s %d %s %s %s %d.',
            self.event.uniq_id,
            self.uniq_id,
            board.round,
            board.id,
            board.white_player.last_name,
            board.white_player.first_name or '',
            board.white_player.rating,
            white_result,
            board.black_player.last_name,
            board.black_player.first_name or '',
            board.black_player.rating,
        )

        # Remove the cached 'playing' value so that the pairing tab updates correctly
        self.__dict__.pop('playing', None)

    def delete_result(self, board: Board):
        """Deletes the result for the given `board`."""
        assert board.black_player is not None
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            board.white_pairing.update_result(event_database, Result.NO_RESULT)
            board.black_pairing.update_result(event_database, Result.NO_RESULT)
            board.set_last_result_update(board.white_pairing.result, event_database)
        logger.info(
            'Removed result: %s %s %d.%d.',
            self.event.uniq_id,
            self.uniq_id,
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

    def add_player_to_tournament(
        self,
        stored_player: StoredPlayer,
        event_database: EventDatabase | None = None,
    ):
        assert stored_player.id is not None
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
                for round_ in range(1, self.current_round)
            ],
        )
        stored_player.stored_tournament_player = stored_tournament_player
        if event_database:
            event_database.add_stored_tournament_player(stored_tournament_player)
        else:
            with EventDatabase(self.event.uniq_id, True) as database:
                database.add_stored_tournament_player(stored_tournament_player)
        self.players_by_id[stored_player.id] = Player(self, stored_player)

    def delete_player_from_tournament(self, player_id: int):
        with EventDatabase(self.event.uniq_id, True) as database:
            database.delete_stored_tournament_player(self.id, player_id)
        if player_id in self.players_by_id:
            del self.players_by_id[player_id]

    def get_available_board_indexes(self, round_: int) -> list[int]:
        board_indexes = [
            board.index for board in self.get_round_boards(round_) if not board.exempt
        ]
        max_board_count = len(self.players) // 2 + len(self.players) % 2
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

    def set_players_pairing_numbers(self):
        # Set up the cached property, which makes sure the
        # pairing number checking process is not executed twice
        __ = self.players_by_pairing_number

    def _set_players_pairing_numbers(self):
        """Set the pairing numbers of all the players in the tournament.
        Returns a list of players sorted by pairing number."""
        inserted_players: list[Player] = []
        current_players: list[Player] = []
        current_pairing_numbers: set[int] = set()
        for player in self.players:
            if player.pairing_number is None:
                inserted_players.append(player)
            else:
                current_players.append(player)
                current_pairing_numbers.add(player.pairing_number)
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
                not inserted_players
                and not deleted_pairing_numbers
                and not settings_updated
            ):
                return
            sorted_players = sorted(current_players, key=attrgetter('pairing_number'))
        else:
            sorted_players = sorted(
                current_players, key=attrgetter('starting_rank_sort_key')
            )
        for player in inserted_players:
            player_index = next(
                (
                    index
                    for index, player_ in enumerate(sorted_players)
                    if player_.starting_rank_sort_key > player.starting_rank_sort_key
                ),
                len(sorted_players),
            )
            sorted_players.insert(player_index, player)
            settings_updated |= (
                self.pairing_variation.update_settings_from_added_pairing_number(
                    self, player_index + 1
                )
            )

        players_by_updated_pairing_number = {
            pairing_number: player
            for pairing_number, player in enumerate(sorted_players, start=1)
            if pairing_number != player.pairing_number
        }
        if not players_by_updated_pairing_number:
            return
        with EventDatabase(self.event.uniq_id, True) as database:
            for pairing_number, player in players_by_updated_pairing_number.items():
                player.stored_tournament_player.pairing_number = pairing_number
                database.set_tournament_player_pairing_number(
                    player.stored_tournament_player
                )
            if settings_updated:
                database.set_tournament_pairing_settings(
                    self.id, self.stored_pairing_settings
                )

    def create_round_pairing(
        self, round_nb: int, white_player_id: int, black_player_id: int | None
    ) -> Board:
        """Creates a pairing for a round."""
        white_player = self.players_by_id[white_player_id]
        black_player = self.players_by_id[black_player_id] if black_player_id else None
        white_pairing = white_player.pairings[round_nb]
        black_pairing = black_player.pairings[round_nb] if black_player else None

        if white_pairing.opponent_id:
            raise ValueError(
                f'White player {white_player.full_name} already has an '
                f'opponent (id: {white_pairing.opponent_id}) for round {round_nb}.'
            )
        if black_player and black_pairing and black_pairing.opponent_id:
            raise ValueError(
                f'Black player {black_player.full_name} already has an '
                f'opponent (id: {black_pairing.opponent_id}) for round {round_nb}.'
            )
        with EventDatabase(self.event.uniq_id, True) as database:
            if black_player and black_pairing:
                result = Result.NO_RESULT
                board = self.get_round_pab_board(round_nb)
                assert board is not None
                board_id = board.identifier
                board.replace_player(black_player, 'black')
                board.stored_board.index = self.get_available_board_indexes(round_nb)[0]
                black_pairing.stored_pairing.result = result.value
                black_pairing.stored_pairing.board_id = board_id
                black_pairing.update(database)
                database.update_stored_board(board.stored_board)
            else:
                result = Result.PAIRING_ALLOCATED_BYE
                round_boards = self.get_round_boards(round_nb)
                stored_board = StoredBoard(
                    id=None,
                    white_player_id=white_player.id,
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
                board.white_player.delete_pairing(board.round, database)
                board.white_player.reset_board()
                if board.black_player:
                    board.black_player.delete_pairing(board.round, database)
                    board.black_player.reset_board()
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
                if board.black_player:
                    board.black_pairing.stored_pairing.board_id = id_
                    board.black_pairing.update(database)
                else:
                    white_stored_pairing.result = pab_result.value
                board.white_pairing.update(database)

    def open_check_in(self):
        """Opens the check-in for the tournament and sets all the present players
        as not checked-in for the next round."""
        assert not self.finished, f'Tournament [{self.uniq_id}] is finished.'
        assert not self.playing, f'Games are played for tournament [{self.uniq_id}].'
        assert not self.check_in_open, (
            f'Check-in already open for tournament [{self.uniq_id}].'
        )
        self.stored_tournament.check_in_open = True
        present_player_ids: list[int] = []
        for player in self.players:
            pairing = player.pairings_by_round.get(self.current_round + 1, None)
            if not pairing or not pairing.result.is_bye:
                present_player_ids.append(player.id)
                player.stored_player.check_in = False

        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_tournament_check_in(self.id, True)
            database.set_players_check_in(present_player_ids, False)

    def close_check_in(self, zpbs_next_round: bool, zpbs_last_rounds: bool):
        """Closes the check-in for the tournament and assigns a ZPB to all the players not checked-in
        for the next round (if zpbs_last_rounds, for the rest of the tournament)."""
        assert self.check_in_open, (
            f'Check-in already closed for tournament [{self.uniq_id}].'
        )
        self.stored_tournament.check_in_open = False

        zpb_rounds: list[int] = []
        if zpbs_last_rounds:
            zpb_rounds = list(range(self.current_round + 1, self.rounds + 1))
        elif zpbs_next_round:
            zpb_rounds = [self.current_round + 1]

        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_tournament_check_in(self.id, False)
            if zpb_rounds:
                for player in self.players:
                    if player.check_in:
                        continue
                    pairing = player.pairings_by_round.get(self.current_round + 1, None)
                    if pairing and pairing.result.is_bye:
                        continue
                    for round_ in zpb_rounds:
                        player.pairings_by_round[round_].update_result(
                            database, Result.ZERO_POINT_BYE
                        )

    def set_player_byes(self, player: Player, byes: dict[int, Result]):
        """Updates a player's pairings with ZPB, HPB, FPB or not-paired values."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            for round_, result in byes.items():
                if player.pairings_by_round[round_].needs_pairing_or_has_bye:
                    player.pairings_by_round[round_].update_result(database, result)

    def set_current_round(self, round_: int):
        with EventDatabase(self.event.uniq_id, True) as database:
            database.set_tournament_current_round(self.id, round_)
