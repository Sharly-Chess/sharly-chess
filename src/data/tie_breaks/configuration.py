"""The ranking criteria a tournament is configured with.

The stored list is what the arbiter chose; what is in force leaves out
the criteria the pairing system or the field make unusable, and falls
back to the points when nothing usable is left.
"""

from collections.abc import Collection
from functools import cached_property
from typing import TYPE_CHECKING, cast

from common.i18n import _, pgettext
from common.logger import get_logger
from data.tie_breaks import TieBreak, TieBreakManager, TieBreakOption
from data.tie_breaks.managers import TieBreakOptionManager
from data.tie_breaks.tie_breaks import PointsTieBreak, TieBreakPurpose
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTieBreak
from plugins.manager import plugin_manager
from utils.enum import ScoreType

if TYPE_CHECKING:
    from data.tournament import Tournament

logger = get_logger()


class TieBreakConfiguration:
    """The ranking criteria of one tournament: those stored, those in
    force, and the changes the arbiter makes to them."""

    def __init__(self, tournament: 'Tournament') -> None:
        self.tournament = tournament

    def _from_stored(self, stored_tie_break: StoredTieBreak) -> TieBreak | None:
        tournament = self.tournament
        try:
            tie_break_type = TieBreakManager(tournament.event).get_type(
                stored_tie_break.type
            )
        except KeyError:
            logger.warning(
                'Tie-break [%s] not found for tournament [%s].',
                stored_tie_break.type,
                tournament.name,
            )
            return None
        options: list[TieBreakOption] = []
        manager = TieBreakOptionManager(tournament.event)
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
    def by_id(self) -> dict[int, TieBreak]:
        """Every stored tie-break for this tournament, keyed by id, in order.
        What they decide depends on the pairing system: a knock-out's are its
        advancement (FIDE Art. 12) tie-breaks; every other system's are the
        standings criteria (a knock-out's standings are fixed to the round
        reached, so it configures advancement here instead)."""
        tie_breaks_by_id: dict[int, TieBreak] = {}
        for stored_tie_break in self.tournament.stored_tournament.stored_tie_breaks:
            if not (tie_break := (self._from_stored(stored_tie_break))):
                continue
            id_ = stored_tie_break.id
            assert id_ is not None
            tie_breaks_by_id[id_] = tie_break
        return tie_breaks_by_id

    @property
    def advancement(self) -> list[TieBreak]:
        """A knock-out's advancement tie-breaks, in order — the stored
        tie-breaks that can decide a level match. Only read on a knock-out,
        where the stored list *is* the advancement list."""
        return [
            tie_break
            for tie_break in self.by_id.values()
            if tie_break.usable_as_knockout_advancement
        ]

    @property
    def advancement_after_manual(self) -> bool:
        """Whether a tie-break is listed after the play-off (manual)
        marker. A play-off settles the match outright, so anything below it
        can never apply — worth flagging so the arbiter reorders."""
        seen_manual = False
        for tie_break in self.by_id.values():
            if tie_break.is_manual:
                seen_manual = True
            elif seen_manual:
                return True
        return False

    @property
    def purpose(self) -> TieBreakPurpose:
        """Whether the tie-break configuration UI edits *advancement* (a
        knock-out) or *standings* (every other system) tie-breaks. Derived from
        the pairing system, not stored — a tournament only ever configures one."""
        if self.tournament.pairing_system.eliminates_participants:
            return TieBreakPurpose.ADVANCEMENT
        return TieBreakPurpose.STANDINGS

    @property
    def ranking(self) -> list[TieBreak]:
        """The ranking criteria, in order.

        A tournament that has none falls back to the points alone: the
        criteria decide the standings outright — the score is one of them
        rather than an implicit first key — so an empty list would
        otherwise rank nobody. Removing the Points tie-break from a list
        that holds others is a deliberate act and is honoured.
        """
        if self.tournament.pairing_system.eliminates_participants:
            # A knock-out is ranked by the round reached, carried by the
            # points themselves; it has no configurable standings
            # tie-breaks (its Art. 12 tie-breaks are for advancement).
            return self._default
        invalid_tie_break_ids = self.invalid_messages.keys()
        configured = [
            tie_break
            for stored_id, tie_break in self.by_id.items()
            if stored_id not in invalid_tie_break_ids
        ]
        return configured or self._default

    @cached_property
    def _default(self) -> list[TieBreak]:
        """Cached so the instance outlives the call: a
        :class:`TieBreakValue` keeps only a weak reference to its
        tie-break, so a freshly built one would be collected at once."""
        return [PointsTieBreak()]

    @property
    def leads_on_points(self) -> bool:
        """Whether the standings rank on the points before anything else
        — the usual layout, and the only one Papi can express."""
        tie_breaks = self.ranking
        return bool(tie_breaks) and isinstance(tie_breaks[0], PointsTieBreak)

    @property
    def ranks_on_points(self) -> bool:
        """Whether the points are among the ranking criteria at all.

        They need not come first — another criterion may outrank them —
        but leaving them out altogether ranks the field on tie-breaks
        alone, which is almost never intended.
        """
        return any(isinstance(tie_break, PointsTieBreak) for tie_break in self.ranking)

    @property
    def only_points(self) -> bool:
        """Whether nothing has been chosen to break ties — the standings
        rank on the score and stop there. The state a tournament starts
        in, and the one a tie-break set may be applied to."""
        return len(self.by_id) == 0 or (len(self.by_id) == 1 and self.leads_on_points)

    def acronym(self, tie_break: TieBreak) -> str:
        """The label for a criterion's column in the standings.

        The Points tie-break stands for the primary score, which in a
        team tournament is either the match points or the game points —
        the column says which rather than showing a generic label.
        """
        if isinstance(tie_break, PointsTieBreak) and self.tournament.is_team_tournament:
            if self.tournament.primary_score == ScoreType.MATCH_POINTS:
                return pgettext('team ranking header match points', 'MP')
            return pgettext('team ranking header game points', 'GP')
        return tie_break.acronym

    @property
    def leading(self) -> TieBreak:
        """The criterion the standings rank on first — the points in the
        usual layout. Prize categories that rank by final standing are
        decided on it, so it is what they display."""
        return self.ranking[0]

    @property
    def team(self) -> list[TieBreak]:
        """The ranking criteria that yield a per-team value — the list
        :meth:`team_standings` computes values for, in the same order."""
        return [tie_break for tie_break in self.ranking if tie_break.supports_team_mode]

    @property
    def team_ranking(self) -> list[TieBreak]:
        return [
            tie_break
            for tie_break in self.ranking
            if tie_break.is_used_for_team_ranking
        ]

    @property
    def all(self) -> Collection[TieBreak]:
        return self.by_id.values()

    @property
    def invalid_messages(self) -> dict[int, str]:
        """Get all the messages invalidating the tie-breaks, including the order errors."""
        invalid_messages_by_id: dict[int, str] = {}
        valid_tie_breaks: list[TieBreak] = []
        for stored_id, tie_break in self.by_id.items():
            if message := self.invalid_message(tie_break):
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

    def invalid_message(self, tie_break: TieBreak) -> str | None:
        """Get a message explaining why a tie-break is invalid in the context of the tournament.
        Return or None if it is valid."""
        tournament = self.tournament
        if not tie_break.is_compatible_with(tournament.pairing_system):
            return _(
                'This tie-break is not compatible with '
                'the pairing system [{pairing_system}] (ignored).'
            ).format(pairing_system=tournament.pairing_system.name)
        if not tie_break.allow_unrated_players and tournament.unrated_count:
            return _(
                'This tie-break is disabled when there are unrated players '
                'without estimated ratings ({count} in the tournament).'
            ).format(count=tournament.unrated_count)
        if not tie_break.allow_estimated_players and tournament.estimated_count:
            return _(
                'By default, this tie-break is disabled when there '
                'are unrated players ({count} in the tournament). '
                'You must specify that the player estimation is explained '
                'in the rules.'
            ).format(count=tournament.estimated_count)
        return None

    @property
    def warning_message(self) -> str | None:
        """Warning to display at global tie-break level."""
        plugin_warning = plugin_manager.hook_for_event(
            self.tournament.event, 'get_tournament_tie_breaks_warning_message'
        )(tournament=self.tournament)
        if plugin_warning:
            return cast(str | None, plugin_warning)
        return None

    def reorder(self, ordered_ids: list[int]) -> None:
        if len(ordered_ids) != len(self.by_id):
            raise ValueError(f'{ordered_ids=}')
        for object_id in self.by_id:
            if object_id not in ordered_ids:
                raise ValueError(
                    f'Tie break [{object_id}] not part of tournament [{self.tournament.name}].'
                )
        with EventDatabase(self.tournament.event.uniq_id, True) as database:
            self._set_indexes(database, ordered_ids)
        self.by_id = {object_id: self.by_id[object_id] for object_id in ordered_ids}

    def _set_indexes(self, database: EventDatabase, ordered_ids: list[int]) -> None:
        for index, object_id in enumerate(ordered_ids):
            stored_tie_break = self.by_id[object_id].to_stored_value()
            stored_tie_break.id = object_id
            stored_tie_break.tournament_id = self.tournament.id
            stored_tie_break.index = index
            database.update_stored_tie_break(stored_tie_break)

    def add(self, tie_break: TieBreak) -> TieBreak:
        stored_tie_break = tie_break.to_stored_value()
        stored_tie_break.tournament_id = self.tournament.id
        stored_tie_break.index = len(self.by_id)
        with EventDatabase(self.tournament.event.uniq_id, write=True) as database:
            object_id = database.add_stored_tie_break(stored_tie_break)
        self.by_id[object_id] = tie_break
        return tie_break

    def update(self, tie_break_id: int, new_tie_break: TieBreak) -> None:
        tournament = self.tournament
        if tie_break_id not in self.by_id:
            raise ValueError(
                f'Tie-break [{tie_break_id}] not part of tournament [{tournament.name}].'
            )
        stored_tie_break = new_tie_break.to_stored_value()
        stored_tie_break.id = tie_break_id
        stored_tie_break.tournament_id = tournament.id
        stored_tie_break.index = list(self.by_id).index(tie_break_id)
        with EventDatabase(tournament.event.uniq_id, write=True) as database:
            database.update_stored_tie_break(stored_tie_break)
        self.by_id[tie_break_id] = new_tie_break

    def delete(self, tie_break_id: int) -> None:
        tournament = self.tournament
        if tie_break_id not in self.by_id:
            raise ValueError(
                f'Tie-break [{tie_break_id}] not part of tournament [{tournament.name}].'
            )
        if self.purpose == TieBreakPurpose.STANDINGS and len(self.by_id) == 1:
            # The standings rank on the criteria listed and nothing else, so
            # the last one cannot go — there would be nothing to rank on. A
            # knock-out's advancement list may be emptied (a play-off decides).
            raise ValueError(
                f'Tie-break [{tie_break_id}] is the only ranking criterion '
                f'of tournament [{tournament.name}].'
            )
        with EventDatabase(tournament.event.uniq_id, True) as database:
            if self.by_id[tie_break_id].is_manual:
                self.delete_manual_values(database)
            database.delete_stored_tie_break(tie_break_id)
            del self.by_id[tie_break_id]
            self._set_indexes(database, list(self.by_id))

    def delete_manual_values(self, database: EventDatabase) -> None:
        manual_updates: dict[int, int | None] = {}
        for tournament_player in self.tournament.tournament_players:
            if tournament_player.manual_tiebreak is not None:
                tournament_player.stored_tournament_player.manual_tiebreak = None
                manual_updates[tournament_player.id] = None
        database.set_tournament_players_manual_tiebreak(
            self.tournament.id, manual_updates
        )

    @property
    def has_manual_values(self) -> bool:
        return any(tie_break.is_manual for tie_break in self.ranking) and any(
            player.manual_tiebreak is not None
            for player in self.tournament.tournament_players
        )
