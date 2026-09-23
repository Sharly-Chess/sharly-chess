from datetime import date, datetime
import weakref
from collections import Counter, defaultdict
from collections.abc import Collection
from functools import cached_property
from logging import Logger
from operator import attrgetter
from typing import TYPE_CHECKING, Any, cast
from _weakref import ReferenceType

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from common.logger import get_logger

from data.account import Account
from data.board import Board, compute_round_board_numbers
from data.board_operations import BoardOperations
from data.criteria.managers import TournamentCriterionManager
from data.screens.family import Family
from data.pairing_numbers import PairingNumbers
from data.player import Player, TournamentPlayer
from data.player_ranking import PlayerRanking
from data.player_categories import PlayerCategory
from data.point_adjustments import PointAdjustments
from data.point_system import PointSystem
from data.prize.assigned_prize import AssignedPrize
from data.prize.prize_category import PrizeCategory
from data.prize.prize_group import PrizeGroup
from data.prohibited_pairings import ProhibitedPairings
from data.screens.screen import Screen
from data.teams.team_board import TeamBoard
from data.teams.team_pairing_block import TeamPairingBlock
from data.tie_breaks.configuration import TieBreakConfiguration
from data.tie_breaks import (
    TieBreak,
    TieBreakPurpose,
)
from data.criteria.tournament_criteria import TournamentCriterion
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTournamentPlayer,
    StoredPairing,
)
from plugins.utils import PluginData
from plugins.manager import plugin_manager
from utils import Utils
from utils.date_time import format_date_range, format_date, format_datetime
from utils.enum import (
    BoardColor,
    PlayerGender,
    Result,
    ScoreType,
    TeamColourType,
    TeamSortMode,
    TournamentRating,
    PlayerRatingType,
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
        TrfProhibitedPairing,
        TrfTournament,
    )
    from data.rule_sets import RuleSet
    from data.pairing_dimensions import PairingDimension
    from data.pairings import PairingVariation, PairingSystem
    from data.pairings.keizer import KeizerScorer
    from data.pairings.knockout_helpers.view import KnockoutView
    from data.teams.team import Team
    from data.teams.team_scoring import TeamScoring, TeamStanding
    from data.tie_breaks.team_records import TeamRecord
    from data.tie_breaks.team_tie_breaks import TeamTieBreakContext

logger: Logger = get_logger()


class BoardsById(dict[int, Board]):
    """Board mapping with a version counter for numbering caches."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.version: int = 0

    def __setitem__(self, key: int, value: Board) -> None:
        super().__setitem__(key, value)
        self.version += 1

    def __delitem__(self, key: int) -> None:
        super().__delitem__(key)
        self.version += 1

    def pop(self, *args: Any) -> Any:
        result = super().pop(*args)
        self.version += 1
        return result

    def clear(self) -> None:
        super().clear()
        self.version += 1


class Tournament:
    """A data wrapper around a stored tournament."""

    def __init__(
        self,
        event: 'Event',
        stored_tournament: StoredTournament,
    ):
        self._event_ref: ReferenceType[Event] = weakref.ref(event)
        self.stored_tournament: StoredTournament = stored_tournament
        # Per-player caches are valid only while pairings are stable.
        self._compute_caching_enabled: bool = False
        self._round_board_numbers_cache: dict[tuple[int, int], dict[int, int]] = {}
        # Whole-table Keizer scorer, rebuilt whenever the per-player caches
        # are cleared (see ``set_for_round`` / ``_compute_tournament_player_ranks``).
        self._keizer_scorer: KeizerScorer | None = None

    # -------------------------------------------------------------------------
    # Plugin
    # -------------------------------------------------------------------------

    @staticmethod
    def plugin_data_class_by_plugin_id() -> dict[str, type[PluginData]]:
        return dict(plugin_manager.hook.get_tournament_plugin_data_class())

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
        return Result(self.stored_tournament.paired_bye_result)

    @property
    def max_byes(self) -> int:
        if self.stored_tournament.max_byes is None:
            return SharlyChessConfig.default_max_byes
        return self.stored_tournament.max_byes

    @property
    def last_rounds_no_byes(self) -> int:
        if self.stored_tournament.last_rounds_no_byes is None:
            return SharlyChessConfig.default_last_rounds_no_byes
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
        """The number of rounds this tournament is played over.
        A stored 0 means the pairing system works it out from its entrants"""
        stored_rounds = self.stored_tournament.rounds
        if self.pairing_variation.sets_its_own_round_count:
            # The system's answer wins over whatever is stored. A
            # tournament saved before it could work this out — or before
            # its boards or its entrants changed — would otherwise be
            # stuck with a count that no longer describes it, and could
            # not be paired at all.
            return self.automatic_rounds or stored_rounds or 1
        return stored_rounds or 1

    @property
    def rounds_are_automatic(self) -> bool:
        """Whether the pairing system settles the round count itself."""
        return self.pairing_variation.automatic_round_count(self) is not None or (
            not self.stored_tournament.rounds
        )

    @property
    def automatic_rounds(self) -> int | None:
        if getattr(self, '_computing_automatic_rounds', False):
            return None
        self._computing_automatic_rounds = True
        try:
            return self.pairing_variation.automatic_round_count(self)
        finally:
            self._computing_automatic_rounds = False

    @cached_property
    def pairing_variation(self) -> 'PairingVariation':
        """The stored variation, or until the tournament is paired, the
        one its rule set picks for the teams entered."""
        from data.pairings import PairingVariationManager

        manager = PairingVariationManager(self.event)
        variation = manager.get_object(self.stored_tournament.pairing)
        if self.rule_set is not None and not self._has_stored_pairings:
            variation_id = self.rule_set.pairing_variation_for(
                variation.system().id, self.team_count
            )
            if variation_id is not None:
                return manager.get_object(variation_id)
        return variation

    @property
    def pairing_variation_is_automatic(self) -> bool:
        """Whether the rule set still picks the variation: until the
        tournament is paired."""
        return (
            self.rule_set is not None
            and not self._has_stored_pairings
            and self.rule_set.pairing_variation_for(
                self.pairing_system.id, self.team_count
            )
            is not None
        )

    @property
    def rounds_are_unsettled(self) -> bool:
        """Whether the pairing system will still work the round count
        out: until the tournament is paired."""
        return (
            self.pairing_variation.sets_its_own_round_count
            and not self._has_stored_pairings
        )

    @cached_property
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

    # -------------------------------------------------------------------------
    # Team tournament settings
    # -------------------------------------------------------------------------

    @property
    def is_team_tournament(self) -> bool:
        return self.stored_tournament.team_player_count is not None

    @property
    def team_player_count(self) -> int | None:
        return self.stored_tournament.team_player_count

    @property
    def rule_set_id(self) -> str | None:
        return self.stored_tournament.rule_set

    @cached_property
    def rule_set(self) -> 'RuleSet | None':
        """Resolved :class:`RuleSet` object for this tournament, or
        ``None`` when no rule set is set or the stored id no longer
        maps to a registered rule set (plugin disabled, etc.)."""
        from data.rule_sets import RuleSetManager

        rule_set_id = self.stored_tournament.rule_set
        if not rule_set_id:
            return None
        try:
            rule_set_type = RuleSetManager(self.event).get_type(rule_set_id)
        except KeyError:
            return None
        return rule_set_type(self.stored_tournament.rule_set_config)

    @property
    def roster_max_size(self) -> int | None:
        """Maximum team-roster size, or ``None`` for no cap. Set on the
        tournament directly; a rule set writes (and locks) it via
        ``apply_defaults`` when attached."""
        return self.stored_tournament.roster_max_size

    @property
    def warn_lineup_order(self) -> bool:
        """True iff the lineup editor warns when a round's board order
        differs from the team roster order. Lineups can still be
        reordered freely. Set manually on the tournament, or forced on
        by a rule set."""
        return bool(self.stored_tournament.enforce_roster_order)

    @property
    def rule_set_forced_team_sort_mode(self) -> str | None:
        """The team-sort mode the rule set imposes for the tournament's
        pairing system, or ``None`` when it leaves the choice free."""
        rule_set = self.rule_set
        if rule_set is None:
            return None
        try:
            system_id = self.pairing_system.id
        except KeyError:
            system_id = None
        return rule_set.forced_team_sort_mode(system_id)

    @property
    def team_sort_mode(self) -> TeamSortMode:
        """Effective team-ordering mode. A rule set may force a value
        (locking the choice); otherwise the stored mode applies."""
        forced = self.rule_set_forced_team_sort_mode
        if forced is not None:
            try:
                return TeamSortMode(forced)
            except ValueError:
                pass
        try:
            return TeamSortMode(self.stored_tournament.team_sort_mode)
        except ValueError:
            return TeamSortMode.MANUAL

    @property
    def _has_stored_pairings(self) -> bool:
        """Cheap, shape-agnostic "already paired?" check read straight
        from the stored board collections — no Board objects built
        (so it can't trip over a mid-rebuild player cache). Covers both
        team-board envelopes (Swiss / Berger) and flat fixed-table
        boards (Molter).

        Bye-only envelopes (``team_b_id`` ``None`` — manual HPB / FPB /
        ZPB / PAB pre-marks set before pairing) don't count: a team
        parked on a bye must not freeze team ordering or the sort mode.
        Only a real match (opponent present) or flat boards mean the
        round was actually paired."""
        stored = self.stored_tournament
        if any(
            stb.team_b_id is not None
            for boards in stored.stored_team_boards_by_round.values()
            for stb in boards
        ):
            return True
        return bool(stored.stored_boards_by_round)

    @property
    def team_sort_mode_locked(self) -> bool:
        """True iff a rule set forces the team-sort mode (UI read-only),
        or the tournament is already paired (mode can no longer change)."""
        return (
            self.rule_set_forced_team_sort_mode is not None or self._has_stored_pairings
        )

    def resort_teams(self, database: 'EventDatabase') -> None:
        """Re-assign team pairing numbers per the effective sort mode.
        No-op once any round is paired. MANUAL keeps the existing order and
        only fills in sequential numbers — appending teams that have none yet
        (e.g. just created) at the end — so every assigned team always has a
        pairing number. RANDOM keeps the existing relative order and drops
        newly-added teams into random positions; the rating modes fully
        re-sort."""
        if self._has_stored_pairings:
            return
        teams = list(self.teams)
        if not teams:
            return
        mode = self.team_sort_mode
        if mode == TeamSortMode.MANUAL:
            # Preserve the current order; unnumbered (new) teams sort last.
            ordered = sorted(
                teams,
                key=lambda t: (
                    t.pairing_number if t.pairing_number is not None else float('inf'),
                    t.name.lower(),
                ),
            )
        elif mode == TeamSortMode.TEAM_AVERAGE_RATING:
            ordered = sorted(
                teams,
                key=lambda t: (-(t.average_rating or 0), t.name.lower()),
            )
        elif mode == TeamSortMode.LINEUP_AVERAGE_RATING:
            ordered = sorted(
                teams,
                key=lambda t: (
                    -(t.lineup_average_rating(1) or 0),
                    t.name.lower(),
                ),
            )
        else:  # RANDOM
            ordered = self._random_team_order(teams)
        for index, team in enumerate(ordered, start=1):
            if team.pairing_number != index:
                team.set_pairing_number(index, database)

    @staticmethod
    def _random_team_order(teams: list['Team']) -> list['Team']:
        import random

        placed = sorted(
            (t for t in teams if t.pairing_number is not None),
            key=lambda t: t.pairing_number or 0,
        )
        newcomers = [t for t in teams if t.pairing_number is None]
        if not placed:
            # Fresh shuffle (mode just switched to random).
            order = list(teams)
            random.shuffle(order)
            return order
        # Insert each newcomer at a random position among the existing
        # order; existing teams keep their relative order.
        order = list(placed)
        for team in newcomers:
            order.insert(random.randint(0, len(order)), team)
        return order

    @property
    def rule_set_managed_tie_breaks(self) -> bool:
        """True iff the tournament has a rule set that imposes a
        tie-break list for the current pairing system. The tie-break
        editor renders read-only in that case."""
        rule_set = self.rule_set
        if rule_set is None:
            return False
        try:
            system_id = self.pairing_system.id
        except KeyError:
            return False
        return bool(rule_set.tie_breaks_for_pairing(system_id))

    @cached_property
    def point_system(self) -> PointSystem:
        """What the results are worth, once the defaults are filled in."""
        from data.pairings.systems import TeamSwissPairingSystem

        return PointSystem(
            game_point_overrides=self.stored_tournament.game_points or {},
            match_point_overrides=self.stored_tournament.match_points or {},
            is_team=self.is_team_tournament,
            boards=self.team_player_count or 0,
            pab_is_draw=self.pairing_system == TeamSwissPairingSystem(),
            bye_is_rest=self.pairing_variation.engine.pab_result == Result.REST_GAME,
            primary_score=self._primary_score,
        )

    @property
    def _primary_score(self) -> ScoreType:
        """The score the teams rank on: game points where the system has
        no match points (a flat fixed table), otherwise whichever the
        tournament stores, match points by default."""
        if not self.pairing_system.supports_match_points:
            return ScoreType.GAME_POINTS
        if self.stored_tournament.primary_score:
            return ScoreType(self.stored_tournament.primary_score)
        return ScoreType.MATCH_POINTS

    @property
    def match_points(self) -> dict[Result, float]:
        return self.point_system.match_points

    @property
    def primary_score(self) -> 'ScoreType':
        """Score basis used as primary (FIDE 1.2.1). Default: match points
        for team tournaments; not used for individual tournaments."""
        return self.point_system.primary_score

    @property
    def secondary_score(self) -> 'ScoreType':
        return self.point_system.secondary_score

    @property
    def round_robin_participation_rule(self) -> bool:
        """FIDE 6.6: whether round-robin participants who completed less than
        50% of their games are dropped from the final standings and their
        games annulled (not counted in the opponents' scores and
        tie-breaks). Set by the arbiter in the tournament form, and off for
        tournaments created before the rule existed so their standings stay
        unchanged."""
        return bool(self.stored_tournament.round_robin_participation_rule)

    @property
    def secondary_score_for_colours(self) -> bool:
        """Whether the secondary score breaks ties when deciding which
        team is the "first team" for colour allocation (§1.2.1, §4.3).
        Default: on, per §1.2.2."""
        return bool(self.stored_tournament.secondary_score_for_colours)

    @property
    def team_colour_type(self) -> TeamColourType:
        """FIDE C.04.6 §1.7 colour-allocation rule. Default: Type A
        (board-by-board flip)."""
        raw = self.stored_tournament.team_colour_type
        if raw:
            return TeamColourType(raw)
        return TeamColourType.A

    @property
    def color_pattern(self) -> str | None:
        return self.stored_tournament.color_pattern

    @cached_property
    def point_adjustments(self) -> PointAdjustments:
        return PointAdjustments(self)

    @cached_property
    def team_scoring(self) -> 'TeamScoring':
        from data.teams.team_scoring import TeamScoring

        return TeamScoring(self)

    def team_standings(self, *, after_round: int | None = None) -> list['TeamStanding']:
        return self.team_scoring.standings(after_round=after_round)

    def team_records(self, *, after_round: int | None = None) -> list['TeamRecord']:
        return self.team_scoring.records(after_round=after_round)

    def team_tie_break_context(self) -> 'TeamTieBreakContext':
        return self.team_scoring.tie_break_context()

    def team_totals_after(self, after_round: int) -> dict[int, tuple[float, float]]:
        return self.team_scoring.totals_after(after_round)

    @cached_property
    def teams_by_id(self) -> dict[int, 'Team']:
        return {
            team.id: team
            for team in self.event.teams_by_id.values()
            if team.tournament_id == self.id
        }

    @property
    def teams(self) -> Collection['Team']:
        return self.teams_by_id.values()

    @cached_property
    def team_count(self) -> int:
        return len(self.teams_by_id)

    @cached_property
    def sorted_teams(self) -> list['Team']:
        return sorted(self.teams, key=attrgetter('name'))

    @property
    def teams_in_pairing_order(self) -> list['Team']:
        """Teams ordered by pairing number then id — the same order the
        fixed-table letters (A, B, …) follow, so a letter-labelled list
        reads in sequence."""
        return sorted(
            self.teams,
            key=lambda team: (
                team.pairing_number
                if team.pairing_number is not None
                else float('inf'),
                team.id,
            ),
        )

    @cached_property
    def teams_by_pairing_number(self) -> dict[int, 'Team']:
        return {
            team.pairing_number: team
            for team in self.teams
            if team.pairing_number is not None
        }

    # -------------------------------------------------------------------------
    # Prohibited pairings
    # -------------------------------------------------------------------------

    @cached_property
    def prohibited_pairings(self) -> ProhibitedPairings:
        return ProhibitedPairings(self)

    def pairing_dimensions(self) -> 'list[PairingDimension]':
        """All grouping dimensions applicable to this tournament: the
        core ones plus any contributed by enabled plugins, filtered to
        match this tournament's individual/team nature."""
        from data.pairing_dimensions import core_pairing_dimensions
        from plugins.manager import plugin_manager

        dimensions = list(core_pairing_dimensions())
        for plugin_result in plugin_manager.hook_for_event(
            self.event, 'get_prohibited_pairing_dimensions'
        )():
            if plugin_result:
                dimensions.extend(plugin_result)
        return [d for d in dimensions if d.is_team == self.is_team_tournament]

    # -------------------------------------------------------------------------
    # Team boards and records
    # -------------------------------------------------------------------------

    def clear_team_cache(self) -> None:
        Utils.reset_cached_properties(
            self,
            'teams_by_id',
            'sorted_teams',
            'teams_by_pairing_number',
            'team_boards_by_id',
            'team_boards_by_round',
            'team_match_by_team_and_round',
            'team_pairing_blocks',
        )

    @cached_property
    def team_boards_by_id(self) -> dict[int, TeamBoard]:
        return {
            stored_team_board.id: TeamBoard(self, stored_team_board)
            for stored_team_boards in (
                self.stored_tournament.stored_team_boards_by_round.values()
            )
            for stored_team_board in stored_team_boards
            if stored_team_board.id is not None
        }

    @cached_property
    def team_boards_by_round(self) -> dict[int, list[TeamBoard]]:
        result: dict[int, list[TeamBoard]] = {}
        for team_board in self.team_boards_by_id.values():
            result.setdefault(team_board.round, []).append(team_board)
        for round_team_boards in result.values():
            round_team_boards.sort(key=lambda tb: (tb.index is None, tb.index or 0))
        return result

    def get_round_team_boards(self, round_: int) -> list[TeamBoard]:
        return self.team_boards_by_round.get(round_, [])

    @cached_property
    def team_match_by_team_and_round(self) -> dict[tuple[int, int], TeamBoard]:
        """``(team_id, round)`` → the team's match that round, byes left
        out: a bye envelope has no opponent and no boards to read a
        lineup from. Both of a match's teams are keyed to it.

        Looking a team's match up runs on every lineup read, so it is an
        index rather than a scan of the round's matches. What it keys on
        is fixed when a match is created, and the paths that pair, unpair
        or bye a team all clear the team cache."""
        matches: dict[tuple[int, int], TeamBoard] = {}
        for team_board in self.team_boards_by_id.values():
            stb = team_board.stored_team_board
            if stb.team_b_id is None:
                continue
            matches.setdefault((stb.team_a_id, team_board.round), team_board)
            matches.setdefault((stb.team_b_id, team_board.round), team_board)
        return matches

    @cached_property
    def team_pairing_blocks(self) -> list[TeamPairingBlock]:
        return [
            TeamPairingBlock(self, stored_block)
            for stored_block in self.stored_tournament.stored_team_pairing_blocks
        ]

    def get_round_team_pairing_blocks(self, round_: int) -> list[TeamPairingBlock]:
        return [
            block
            for block in self.team_pairing_blocks
            if block.applies_to_round(round_)
        ]

    def is_team_pair_blocked(self, team_a_id: int, team_b_id: int, round_: int) -> bool:
        return any(
            block.involves(team_a_id, team_b_id)
            for block in self.get_round_team_pairing_blocks(round_)
        )

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
            return cast(str | None, plugin_warning)
        return None

    def set_valid_pairing_settings(self) -> None:
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

    def update_pairing_settings(self, pairing_settings: dict[str, Any]) -> None:
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_tournament_pairing_settings(self.id, pairing_settings)
        self.stored_tournament.pairing_settings = pairing_settings
        Utils.reset_cached_properties(self, 'pairing_settings')

    def get_pairing_settings_data_errors(self, data: dict[str, str]) -> dict[str, Any]:
        return self.pairing_variation.get_settings_data_errors(self, data)

    # -------------------------------------------------------------------------
    # Tie-breaks
    # -------------------------------------------------------------------------

    @cached_property
    def tie_break_configuration(self) -> TieBreakConfiguration:
        return TieBreakConfiguration(self)

    @property
    def tie_breaks(self) -> list[TieBreak]:
        """The ranking criteria in force, in order."""
        return self.tie_break_configuration.ranking

    @property
    def tie_breaks_by_id(self) -> dict[int, TieBreak]:
        """Every stored tie-break, keyed by id, in order."""
        return self.tie_break_configuration.by_id

    @property
    def team_tie_breaks(self) -> list[TieBreak]:
        return self.tie_break_configuration.team

    @property
    def team_ranking_tie_breaks(self) -> list[TieBreak]:
        return self.tie_break_configuration.team_ranking

    @property
    def advancement_tie_breaks(self) -> list[TieBreak]:
        return self.tie_break_configuration.advancement

    @property
    def leading_tie_break(self) -> TieBreak:
        return self.tie_break_configuration.leading

    @property
    def tie_break_config_purpose(self) -> TieBreakPurpose:
        return self.tie_break_configuration.purpose

    def tie_break_acronym(self, tie_break: TieBreak) -> str:
        return self.tie_break_configuration.acronym(tie_break)

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

    def player_matches_criteria(self, tournament_player: TournamentPlayer) -> bool:
        """Check if the player matches all criteria of this tournament."""
        return all(
            criterion.is_player_included_function(tournament_player)
            for criterion in self.criteria
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

    def delete_prize_group(self, prize_group_id: int) -> None:
        with EventDatabase(self.event.uniq_id, True) as database:
            database.delete_stored_prize_group(prize_group_id)

        if prize_group_id in self.prize_groups_by_id:
            del self.prize_groups_by_id[prize_group_id]

    def get_unused_prize_group_name(self, base_name: str | None = None) -> str:
        return Utils.get_unused_item_name(
            base_name or _('New group'),
            (group.name for group in self.prize_groups),
        )

    @property
    def total_monetary_prize_value(self) -> float:
        return sum(group.total_monetary_value for group in self.prize_groups)

    @property
    def total_non_monetary_prize_value(self) -> float:
        return sum(group.total_non_monetary_value for group in self.prize_groups)

    def format_total_monetary_prize_value(self, currency: str) -> str:
        return Utils.currency_value_str(self.total_monetary_prize_value, currency)

    def format_total_non_monetary_prize_value(self, currency: str) -> str:
        return Utils.currency_value_str(self.total_non_monetary_prize_value, currency)

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
    def exclusive_player_ids(self) -> set[int]:
        """The players this tournament would take with it if deleted:
        those it holds and no other tournament of the event does. Players
        are event-level, so one entered in several tournaments stays.

        Team rosters count: a team tournament stores no
        ``tournament_player`` rows, but the loader synthesises them from
        team membership, so ``tournament_players_by_id`` holds them all.
        """
        other_player_ids: set[int] = set()
        for tournament in self.event.tournaments_by_id.values():
            if tournament.id != self.id:
                other_player_ids |= set(tournament.tournament_players_by_id)
        return set(self.tournament_players_by_id) - other_player_ids

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
        return dict(enumerate(ordered_players, start=1))

    @cached_property
    def pairing_numbers(self) -> PairingNumbers:
        return PairingNumbers(self)

    @property
    def tournament_players_by_pairing_number(self) -> dict[int, TournamentPlayer]:
        return self.pairing_numbers.by_number

    def set_tournament_players_pairing_numbers(self) -> None:
        self.pairing_numbers.assign()

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
        for player in self.tournament_players_by_rank.values():
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
    # Arbiters
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
    def arbiters(self) -> list[Account]:
        return [
            account
            for account in self.event.accounts_by_id.values()
            if (
                (role := account.get_role(RoleType.ARBITER))
                and role.tournament_ids
                and self.id in role.tournament_ids
            )
        ]

    # -------------------------------------------------------------------------
    # Points
    # -------------------------------------------------------------------------

    @property
    def point_values(self) -> dict[Result, float]:
        return self.point_system.game_points

    @property
    def team_game_points(self) -> dict[Result, float]:
        return self.point_system.team_game_points

    @property
    def is_standard_point_system_used(self) -> bool:
        return self.point_system.is_standard

    @property
    def pab_equivalent_result(self) -> Result:
        return self.point_system.pab_equivalent_result

    @property
    def win_points(self) -> float:
        return self.point_system.win

    @property
    def draw_points(self) -> float:
        return self.point_system.draw

    @property
    def loss_points(self) -> float:
        return self.point_system.loss

    @property
    def pab_points(self) -> float:
        return self.point_system.pab

    @property
    def zpb_points(self) -> float:
        return self.point_system.zpb

    @property
    def team_bye_is_rest(self) -> bool:
        return self.point_system.bye_is_rest

    @property
    def team_pab_game_points(self) -> float:
        return self.point_system.team_pab_game_points

    def print_real_points(self, round_: int | None = None) -> bool:
        if round_ is None:
            round_ = self.current_round
        return self.pairing_variation.print_real_points(self, round_)

    @property
    def hide_pairing_points(self) -> bool:
        """Whether the pairing table hides the running points columns. Team
        systems that pair whole teams keep points on the team block, not the
        board rows; and a knock-out ranks by the round reached, not points, so
        its pairing table has no points to show for players or teams."""
        return (
            self.event.is_team_event and self.pairing_system.paired_by_team
        ) or self.pairing_system.eliminates_participants

    @property
    def hide_team_block_points(self) -> bool:
        """Whether the team blocks of the pairing table hide the running score
        of each team. A knock-out ranks by the round reached, not points, so it
        has no score to show; every other team system does."""
        return self.pairing_system.eliminates_participants

    def set_tournament_player_points(
        self, tournament_player: TournamentPlayer, *, before_round: int
    ) -> None:
        """Sets the points of a player before round *before_round*."""
        if self.pairing_system.id == 'KEIZER':
            # A Keizer total is not a game-point count; it comes from the
            # whole-table scorer. Points and board-ordering points are the
            # same figure — board 1 is the leader.
            total = self.keizer_scorer.total(
                tournament_player, after_round=before_round - 1
            )
            tournament_player.points = total
            tournament_player.vpoints = total
            return
        vpoints = self.player_virtual_points(tournament_player, at_round=before_round)
        tournament_player.compute_points(before_round=before_round)
        assert tournament_player.points is not None
        tournament_player.vpoints = tournament_player.points + vpoints

    @property
    def keizer_scorer(self) -> 'KeizerScorer':
        """The whole-table Keizer scorer, rebuilt after the per-player
        compute caches are cleared so it always reflects current results."""
        if self._keizer_scorer is None:
            from data.pairings.keizer import KeizerScorer

            self._keizer_scorer = KeizerScorer(self)
        return self._keizer_scorer

    def reset_keizer_scorer(self) -> None:
        """Forget the Keizer scorer, so the next read rebuilds it from the
        current results."""
        self._keizer_scorer = None

    def player_virtual_points(
        self, tournament_player: TournamentPlayer, *, at_round: int
    ) -> float:
        if self.pairing_variation.vpoints_use_pairing_numbers:
            self.set_tournament_players_pairing_numbers()
        return self.pairing_variation.compute_virtual_points(
            self, tournament_player, at_round
        )

    def team_primary_score_before_round(self, team_id: int, round_: int) -> float:
        """The team's cumulative primary score (match points or game
        points, per :attr:`primary_score`) at the start of ``round_``
        — i.e. after rounds 1..``round_``−1 have been accounted for.
        Returns ``0.0`` for teams with no prior team_board entries."""
        totals = self.team_totals_after(round_ - 1)
        mp, gp = totals.get(team_id, (0.0, 0.0))
        return mp if self.primary_score == ScoreType.MATCH_POINTS else gp

    # -------------------------------------------------------------------------
    # Progress
    # -------------------------------------------------------------------------

    @cached_property
    def current_round(self) -> int:
        return (
            self.stored_tournament.current_round
            or self.pairing_system.default_current_round(self)
        )

    def set_current_round(self, round_: int) -> None:
        with EventDatabase(self.event.uniq_id, True) as database:
            database.set_tournament_current_round(self.id, round_)

    @property
    def max_ranking_round(self) -> int:
        if not self.started:
            return 0
        if self.finished:
            # A tournament that ends before its last reserved round (a double
            # elimination whose grand final needs no reset) still ranks as of
            # that last round — it is finished, just never paired, so its
            # standings are the final ones.
            return self.rounds
        if self.playing:
            return self.current_round - 1
        return self.current_round

    @property
    def started(self) -> bool:
        return self.current_round != 0

    @property
    def finished(self) -> bool:
        if self.current_round == self.rounds and not self.playing:
            return True
        # A system may end early: a double elimination whose grand final the
        # winners' champion wins skips its reserved reset round, so the last
        # round is played but never reached. The pairing system decides.
        return self.pairing_system.tournament_is_over(self)

    @property
    def is_last_round(self) -> bool:
        return self.current_round == self.rounds

    def is_round_in_tournament(self, round_: int) -> bool:
        return 1 <= round_ <= self.rounds

    def round_label(self, round_: int) -> str | None:
        """The name of a whole round for the round navigation — a knock-out's
        stage ('Semifinals', 'Upper Bracket Final', …). ``None`` for a system
        whose rounds have no name of their own."""
        label = getattr(self.pairing_variation.engine, 'round_label', None)
        return label(self, round_) if label is not None else None

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
    def is_fully_paired(self) -> bool:
        return all(self.is_round_paired(round_) for round_ in range(1, self.rounds + 1))

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
    def playing(self) -> bool:
        return self.is_round_in_tournament(
            self.current_round
        ) and not self.is_round_finished(self.current_round)

    @cached_property
    def knockout(self) -> 'KnockoutView':
        """The knock-out-specific facet of this tournament — advancement, the
        round-reached standings, the bracket tie-resolution display and the
        manual-winner writers. See
        :class:`~data.pairings.knockout_helpers.view.KnockoutView`."""
        from data.pairings.knockout_helpers.view import KnockoutView

        return KnockoutView(self)

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

    @property
    def has_titled_players(self) -> bool:
        return any(
            player.strongest_title != PlayerTitle.NONE
            for player in self.tournament_players
        )

    @property
    def has_norm_eligible_titled_players(self) -> bool:
        return any(
            not player.held_titles.isdisjoint(TitleNorm.TITLE_HOLDERS)
            for player in self.tournament_players
        )

    # -------------------------------------------------------------------------
    # Rounds
    # -------------------------------------------------------------------------

    def set_for_round(
        self,
        round_: int | None = None,
        *,
        only_players: 'list[TournamentPlayer] | None' = None,
    ) -> None:
        """Prepare a round, optionally limiting point calculation to *only_players*.

        A full-page render must recompute the full field after a limited pass.
        """
        if round_ is None:
            round_ = self.current_round
        self._compute_caching_enabled = True
        try:
            self.reset_keizer_scorer()
            for player in self.tournament_players:
                player.clear_compute_caches()
            players_to_compute = (
                self.tournament_players if only_players is None else only_players
            )
            for player in players_to_compute:
                self.set_tournament_player_points(player, before_round=round_)
            board_numbers = self._round_board_numbers(round_)
            for board in self.get_round_boards(round_):
                if board.stored_board.id is not None:
                    number = board_numbers[board.identifier]
                else:
                    number = board.fixed_number or board.standard_number
                white_tp = board.optional_white_tournament_player
                if white_tp is not None:
                    white_tp.set_board(board.index, number, BoardColor.WHITE)
                if board.black_tournament_player:
                    board.black_tournament_player.set_board(
                        board.index, number, BoardColor.BLACK
                    )
            plugin_manager.hook_for_event(self.event, 'set_for_round')(
                tournament=self, round_=round_
            )
        finally:
            self._compute_caching_enabled = False

    def generate_round_pairings(
        self, at_round: int, partial_pairings: bool = False
    ) -> str:
        if not partial_pairings and self.round_has_pairings(at_round):
            return _(
                'Round {round} is already paired. Unpair it before pairing it again.'
            ).format(round=at_round)
        self.persist_pairing_variation()
        self.persist_automatic_rounds()
        return self.pairing_variation.engine.generate_pairings(
            self, at_round, partial_pairings
        )

    def persist_pairing_variation(self) -> None:
        """Write down the variation the rule set picked, which the
        tournament keeps once paired whatever its teams become."""
        if self.pairing_variation.id == self.stored_tournament.pairing:
            return
        self.stored_tournament.pairing = self.pairing_variation.id
        with EventDatabase(self.event.uniq_id, True) as database:
            database.update_stored_tournament(self.stored_tournament)

    def persist_automatic_rounds(self) -> None:
        """Write down the round count a system works out for itself.

        ``rounds`` already answers with it, but the stored value is what
        the schedule, the exports and every other reader of the record
        see. Settling it as the pairings are generated keeps them in
        step — including after an unpairing, when the field may have
        changed size and the count with it.
        """
        if not self.pairing_variation.sets_its_own_round_count:
            return
        automatic_rounds = self.automatic_rounds
        if automatic_rounds is None or automatic_rounds == (
            self.stored_tournament.rounds
        ):
            return
        self.stored_tournament.rounds = automatic_rounds
        with EventDatabase(self.event.uniq_id, True) as database:
            database.update_stored_tournament(self.stored_tournament)

    def pairings_generation_disabled_message(self, at_round: int) -> str | None:
        return self.pairing_variation.engine.pairings_generation_disabled_message(
            self, at_round
        )

    def is_round_finished(self, round_: int) -> bool:
        # In team events, reserve players (not in the round's lineup)
        # have no pairing for this round; players punched out of the
        # lineup mid-round retain a row but with ``board_id = None``.
        # Both cases mean "no game to finish". In team-paired systems
        # the round additionally isn't finished until every team has an
        # envelope (real match or any bye) — a team with no envelope is
        # still waiting. Flat systems pair boards without envelopes.
        if self.event.is_team_event:
            if (
                self.pairing_system.paired_by_team
                and not self.pairing_system.eliminates_participants
            ):
                # A knocked-out team plays no more matches, so it has no
                # envelope this round and must not hold it open — only a
                # non-elimination system waits on every team being paired.
                envelope_team_ids: set[int] = set()
                for tb in self.get_round_team_boards(round_):
                    stb = tb.stored_team_board
                    envelope_team_ids.add(stb.team_a_id)
                    if stb.team_b_id is not None:
                        envelope_team_ids.add(stb.team_b_id)
                if any(team.id not in envelope_team_ids for team in self.teams):
                    return False
            return self.team_round_results_complete(round_)
        if self.pairing_system.eliminates_participants:
            # Knock-out: a knocked-out player has no board and no result
            # this round, and must not hold it open. Only the players
            # still boarded this round have a game to finish. A drawn game
            # is still "finished" — an unresolved final simply ends in a
            # shared title until the arbiter designates a winner, and a
            # mid-bracket tie is caught separately by the pairing gate.
            return all(
                player.pairings[round_].result != Result.NO_RESULT
                for player in self.tournament_players
                if player.pairings[round_].exists
                and player.pairings[round_].stored_pairing.board_id is not None
            )
        return all(
            player.pairings[round_].result != Result.NO_RESULT
            for player in self.tournament_players
        )

    def round_sections(self, boards: list) -> list[tuple[str | None, list]]:
        """Group a round's *boards* (individual boards or team matches) into
        the sections the pairing tab heads with a title — for a knock-out the
        round names ('Upper Bracket Semifinals' / 'Final' / 'Grand Final' /
        …), the engine deciding each board's section. Returns
        ``[(name, boards)]`` in board order. A system with no sections (Swiss,
        round-robin, …) returns a single ``(None, boards)`` group, so the
        caller renders as before."""
        section_label = getattr(
            self.pairing_variation.engine, 'board_section_label', None
        )
        if section_label is None or not boards:
            return [(None, boards)]
        grouped: dict[str | None, list] = {}
        order: list[str | None] = []
        for board in boards:
            label = section_label(self, board)
            if label not in grouped:
                grouped[label] = []
                order.append(label)
            grouped[label].append(board)
        return [(label, grouped[label]) for label in order]

    def round_is_locked(self, round_: int) -> bool:
        """Whether a round's results are read-only. The pairing system owns
        the rule (a knock-out locks a round once the next is paired from it);
        most systems never lock."""
        return self.pairing_system.round_is_locked(self, round_)

    def team_round_results_complete(self, round_: int) -> bool:
        """All entered results for the round's real boards (team events).
        Unlike :meth:`is_round_finished`, doesn't require every team to
        have an envelope — used to decide how far a late-joining team's
        zero-point byes extend."""
        return all(
            player.pairings[round_].result != Result.NO_RESULT
            for player in self.tournament_players
            if player.pairings[round_].exists
            and player.pairings[round_].stored_pairing.board_id is not None
            # A board whose opponent slot is a hole has no game to
            # play (it's a forfeit), so it never holds up the round.
            and player.pairings[round_].opponent_id is not None
        )

    def is_round_paired(self, round_: int) -> bool:
        return all(
            player.pairings[round_].opponent_id is not None
            or player.pairings[round_].result.is_bye
            for player in self.tournament_players
        )

    def is_round_partially_paired(self, round_: int) -> bool:
        if self.event.is_team_event and self.pairing_system.paired_by_team:
            # Team mode: there's something to complement if at least
            # one team has no envelope (real match / manual bye / PAB)
            # for the round.
            envelope_team_ids: set[int] = set()
            for tb in self.get_round_team_boards(round_):
                stb = tb.stored_team_board
                envelope_team_ids.add(stb.team_a_id)
                if stb.team_b_id is not None:
                    envelope_team_ids.add(stb.team_b_id)
            # "Partially" paired means some teams are paired and some aren't —
            # a fully unpaired round (no envelopes at all) is not partial, so
            # the complementary-pairing button stays hidden.
            return bool(envelope_team_ids) and any(
                team.id not in envelope_team_ids for team in self.teams
            )
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
        # Team matches are stored as team-board envelopes; the per-player
        # pairings are derived from the lineups. A round with team
        # matches but empty/partial rosters may have no seated players at
        # all, so the envelope is the source of truth for team modes —
        # otherwise the round wrongly reads as unpaired (pair button
        # stays, no unpair button).
        if self.get_round_team_boards(round_):
            return True
        # A round beyond the current count (e.g. after a double elimination's
        # reset round is toggled off) has no pairing entry, so read defensively.
        return any(
            (pairing := player.pairings.get(round_)) is not None
            and (pairing.opponent_id is not None or pairing.exempt)
            for player in self.tournament_players
        )

    def round_has_pab(self, round_: int) -> bool:
        return any(
            (pairing := player.pairings.get(round_)) is not None and pairing.exempt
            for player in self.tournament_players
        )

    def has_acceleration_beyond_last_round(self) -> bool:
        """Whether an acceleration entry would reach past the final round.

        bbpPairings stores one acceleration entry per round up to the entry's
        last round and rejects a player holding more entries than the
        tournament has rounds. This happens when a rule's last round outlives
        a later reduction of the round count (the settings form only validates
        the range at save time)."""
        from data.input_output.trf.trf_export import TrfExport

        return any(
            accelerated_round.last_round > self.rounds
            for accelerated_round in TrfExport(self).accelerated_rounds()
        )

    # -------------------------------------------------------------------------
    # Boards
    # -------------------------------------------------------------------------

    @property
    def boards(self) -> list[Board]:
        return self.get_round_boards(self.current_round)

    @cached_property
    def boards_by_id(self) -> BoardsById:
        boards_by_id: BoardsById = BoardsById()
        for (
            round_,
            stored_boards,
        ) in self.stored_tournament.stored_boards_by_round.items():
            for stored_board in stored_boards:
                board = Board(self, round_, stored_board)
                boards_by_id[board.identifier] = board
        return boards_by_id

    def boards_without_result(self, at_round: int) -> list[Board]:
        boards = self.get_round_boards(at_round)
        return [
            board
            for board in boards
            if board.result == Result.NO_RESULT
            and (
                board.stored_board.white_player_id is not None
                or board.stored_board.black_player_id is not None
            )
        ]

    def get_round_boards(self, round_: int) -> list[Board]:
        return sorted(
            (board for board in self.boards_by_id.values() if board.round == round_),
            key=lambda board: board.index,
        )

    def invalidate_board_layout(self) -> None:
        """Invalidate board-number caches after an in-place board change."""
        if 'boards_by_id' in self.__dict__:
            self.boards_by_id.version += 1

    @cached_property
    def leave_fixed_board_holes(self) -> bool:
        """Whether a fixed board number leaves the table it displaces empty
        and duplicates the number it lands on, reproducing the numbering of
        the reference file format. When false the round is numbered compactly:
        fixed players keep their number and every other board fills the
        remaining numbers in order."""
        return bool(
            plugin_manager.hook_for_event(self.event, 'leave_fixed_board_holes')(
                tournament=self
            )
        )

    def _round_board_numbers(self, round_: int) -> dict[int, int]:
        cache_key = (round_, self.boards_by_id.version)
        cached = self._round_board_numbers_cache.get(cache_key)
        if cached is not None:
            return cached
        entries = [
            (board.identifier, board.fixed_number, board.standard_number)
            for board in self.get_round_boards(round_)
        ]
        board_numbers = compute_round_board_numbers(
            entries, self.first_board_number, self.leave_fixed_board_holes
        )
        self._round_board_numbers_cache[cache_key] = board_numbers
        return board_numbers

    def board_number(self, board: Board) -> int:
        if board.stored_board.id is None:
            return board.fixed_number or board.standard_number
        return self._round_board_numbers(board.round)[board.identifier]

    @cached_property
    def board_operations(self) -> BoardOperations:
        return BoardOperations(self)

    def get_unpaired_tournament_players(
        self, boards: list[Board]
    ) -> list[TournamentPlayer]:
        # Knock-out: the bracket seats every player still in, so an
        # unboarded player is knocked out, not waiting to be paired. There
        # is nothing to hand-pair, so the "to pair" list stays empty.
        if self.pairing_system.eliminates_participants:
            return []
        paired_player_ids: list[int] = []
        for board in boards:
            if board.optional_white_tournament_player:
                paired_player_ids.append(board.optional_white_tournament_player.id)
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

    # -------------------------------------------------------------------------
    # Results
    # -------------------------------------------------------------------------

    def add_result(self, board: Board, white_result: Result) -> None:
        """Stores the given result for the given `board` in the current round.
        Stores the `white_result` directly, and uses the opposite result
        as the black's result.
        Assumes that no asymmetric result was entered."""
        if board.optional_white_tournament_player is None:
            raise ValueError(
                f'Board [{board.stored_board.id}] has a forfeit hole, '
                'its result cannot be changed.'
            )
        assert board.black_tournament_player is not None

        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            board.white_pairing.update_result(event_database, white_result)
            board.black_pairing.update_result(
                event_database, white_result.opposite_result
            )

            board.set_last_result_update(board.white_pairing.result, event_database)

        self.knockout.forget_settled_winners(board)

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

    def delete_result(self, board: Board) -> None:
        """Deletes the result for the given `board`."""
        assert board.black_tournament_player is not None
        with EventDatabase(self.event.uniq_id, write=True) as event_database:
            board.white_pairing.update_result(event_database, Result.NO_RESULT)
            board.black_pairing.update_result(event_database, Result.NO_RESULT)
            board.set_last_result_update(board.white_pairing.result, event_database)

        self.knockout.forget_settled_winners(board)

        logger.info(
            'Removed result: %s %s %d.%d.',
            self.event.uniq_id,
            self.name,
            board.round,
            board.id,
        )

        # Remove the cached 'playing' value so that the pairing tab updates correctly
        self.__dict__.pop('playing', None)

    def store_illegal_move(self, tournament_player: TournamentPlayer) -> None:
        """Store an illegal move for the given `tournament_player`, for the current
        round."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            tournament_player.pairings[self.current_round].add_illegal_move(database)

    def delete_illegal_move(self, tournament_player: TournamentPlayer) -> bool:
        """Deletes one illegal move for the given `tournament_player` for the current round."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            return tournament_player.pairings[self.current_round].delete_illegal_move(
                database
            )

    # -------------------------------------------------------------------------
    # Ranking
    # -------------------------------------------------------------------------

    @cached_property
    def ranking(self) -> PlayerRanking:
        return PlayerRanking(self)

    def compute_tournament_player_ranks(
        self, *, after_round: int | None = None
    ) -> dict[int, TournamentPlayer]:
        """Compute and return the ranks of all the players after round
        *after_round*."""
        return self.ranking.compute(after_round=after_round)

    @property
    def tournament_players_by_rank(self) -> dict[int, TournamentPlayer]:
        return self.ranking.players_by_rank

    def ensure_tournament_player_ranks_computed(self) -> None:
        self.ranking.ensure_computed()

    # -------------------------------------------------------------------------
    # Roster and check-in
    # -------------------------------------------------------------------------

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
    def can_add_players(self) -> bool:
        """Determines if players can be added to the tournament."""
        return not self.finished and (
            not self.has_pairings
            or self.pairing_system.allow_player_addition_once_paired
        )

    @cached_property
    def can_add_teams(self) -> bool:
        """Determines if teams can be added to the tournament."""
        return not self.finished and (
            not self.has_pairings or self.pairing_system.allow_team_addition_once_paired
        )

    def add_player_to_tournament(
        self,
        stored_player: StoredPlayer,
        event_database: EventDatabase | None = None,
    ) -> None:
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

    def register_rostered_player(self, player_id: int) -> None:
        """Take note that a player has joined a team of this tournament.

        A team tournament stores no ``tournament_player`` rows — the
        loader synthesises them from team membership (see
        ``load_stored_tournament_players``) — so a player added to a team
        after the event was loaded is absent from this tournament until
        the next reload, and the players tab shows them with no
        tournament of their own.
        """
        if player_id in self.tournament_players_by_id:
            return
        stored_tournament_player = StoredTournamentPlayer(
            tournament_id=self.id,
            player_id=player_id,
            pairing_number=None,
            manual_tiebreak=None,
            stored_pairings=[],
        )
        self.stored_tournament.stored_tournament_players.append(
            stored_tournament_player
        )
        self.tournament_players_by_id[player_id] = TournamentPlayer(
            self, stored_tournament_player
        )
        self._reset_player_derived_cache()

    def unregister_rostered_player(self, player_id: int) -> None:
        """The reverse: a player has left a team of this tournament."""
        if player_id not in self.tournament_players_by_id:
            return
        del self.tournament_players_by_id[player_id]
        self.stored_tournament.stored_tournament_players = [
            stored_tournament_player
            for stored_tournament_player in (
                self.stored_tournament.stored_tournament_players
            )
            if stored_tournament_player.player_id != player_id
        ]
        self._reset_player_derived_cache()

    def _reset_player_derived_cache(self) -> None:
        """Drop what is computed from the tournament's player list."""
        Utils.reset_cached_properties(
            self,
            'player_count',
            'exclusive_player_ids',
            'tournament_players_by_fide_id',
            'tournament_players_by_starting_rank',
            'pairing_numbers',
            'sorted_tournament_players',
            'sorted_tournament_players_without_unpaired',
        )
        # A knock-out resolves its whole match graph from the field's size
        # and holds on to it.
        self.knockout.invalidate_engine_cache()

    def set_player_participation(
        self, player: TournamentPlayer, withdraw: bool = False
    ) -> None:
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

    def set_player_byes(
        self, player: TournamentPlayer, byes: dict[int, Result]
    ) -> None:
        """Updates a player's pairings with ZPB, HPB, FPB or not-paired values."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            for round_, result in byes.items():
                pairing = player.pairings_by_round[round_]
                if pairing.unpaired:
                    pairing.update_result(database, result)

    def check_in_player(self, player: Player, check_in: bool) -> None:
        """Stores the `check_in` status for the given `player`."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_player_check_in(player.id, check_in)
        player.stored_player.check_in = check_in
        player.__dict__.pop('check_in_status', None)

    def check_in_team(self, team: 'Team', check_in: bool) -> None:
        """Stores the per-team check-in status."""
        with EventDatabase(self.event.uniq_id, write=True) as database:
            team.set_check_in(check_in, database)

    def check_in_all_teams(self, check_in: bool) -> None:
        teams = [team for team in self.teams if team.check_in != check_in]
        if not teams:
            return
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_team_check_in_for_tournament(self.id, check_in)
            for team in teams:
                team.stored_team.check_in = check_in

    def check_in_all_players(self, check_in: bool) -> None:
        player_ids = []
        for player in self.players:
            if player.check_in != check_in:
                player_ids.append(player.id)
                player.stored_player.check_in = check_in
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.set_players_check_in(player_ids, check_in)

    @property
    def absent_teams(self) -> list['Team']:
        return [team for team in self.teams if not team.check_in]

    @property
    def team_check_in_status_grouped_counts(self) -> 'Counter[CheckInStatus]':
        counter: Counter[CheckInStatus] = Counter()
        for team in self.teams:
            counter[
                CheckInStatus.PRESENT if team.check_in else CheckInStatus.ABSENT
            ] += 1
        return counter

    def toggle_check_in_open(self) -> None:
        check_in_open = not self.check_in_open
        with EventDatabase(self.event.uniq_id, True) as database:
            database.set_tournament_check_in_open(self.id, check_in_open)
        self.stored_tournament.check_in_open = check_in_open

    # -------------------------------------------------------------------------
    # Exports and dependants
    # -------------------------------------------------------------------------

    def to_trf(
        self,
        after_round: int | None = None,
        next_round_pairings_as_zpb: bool = False,
        prohibited_pairing_override: list['TrfProhibitedPairing'] | None = None,
    ) -> 'TrfTournament':
        from data.input_output.trf.trf_export import TrfExport

        return TrfExport(self).build(
            after_round=after_round,
            next_round_pairings_as_zpb=next_round_pairings_as_zpb,
            prohibited_pairing_override=prohibited_pairing_override,
        )

    @property
    def dependent_families(self) -> list[Family]:
        return [
            family
            for family in self.event.families_by_id.values()
            if family.tournament.id == self.id
        ]

    @property
    def dependent_screens(self) -> list[Screen]:
        return [
            screen
            for screen in self.event.basic_screens_by_id.values()
            if screen.screen_type.depends_on_tournament(screen, self)
        ]

    @property
    def related_screens(self) -> list[Screen]:
        return [
            screen
            for screen in self.event.basic_screens_by_id.values()
            if screen.screen_type.relates_to_tournament(screen, self)
        ]
