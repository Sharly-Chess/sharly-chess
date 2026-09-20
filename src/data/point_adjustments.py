"""Bonus and penalty points.

A team's adjustment for a round is what the arbiter entered plus what
the rule set imposes; a player's, in an individual tournament, is the
arbiter's alone. Both are folded into the standings, the tie-break
records, the screens and the TRF export.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from database.sqlite.event.event_store import (
    StoredPlayerPointAdjustment,
    StoredTeamPointAdjustment,
)

if TYPE_CHECKING:
    from data.rule_sets.rule_sets import PointAdjustment
    from data.tournament import Tournament
    from database.sqlite.event.event_database import EventDatabase


def _replace[T](rows: list[T], is_the_one: Callable[[T], bool], row: T | None) -> None:
    """Keep the loaded rows in step with the database: the row for the
    key goes, and ``row`` takes its place unless there is nothing left
    to store."""
    rows[:] = [existing for existing in rows if not is_the_one(existing)]
    if row is not None:
        rows.append(row)


class PointAdjustments:
    """The bonus and penalty points of one tournament."""

    def __init__(self, tournament: 'Tournament') -> None:
        self.tournament = tournament

    def stored(self, team_id: int, round_: int) -> StoredTeamPointAdjustment | None:
        """The stored manual adjustment row for (team, round), or None."""
        for adj in self.tournament.stored_tournament.stored_team_point_adjustments:
            if adj.team_id == team_id and adj.round_ == round_:
                return adj
        return None

    def manual(self, team_id: int, round_: int) -> tuple[float, float]:
        """Stored manual (MP, GP) bonus/penalty for (team, round)."""
        adj = self.stored(team_id, round_)
        return (adj.mp_delta, adj.gp_delta) if adj else (0.0, 0.0)

    def from_rule_set(self, team_id: int, round_: int) -> 'PointAdjustment | None':
        """Rule-set-imposed adjustment for (team, round), or None."""
        rule_set = self.tournament.rule_set
        if rule_set is None:
            return None
        team = self.tournament.event.teams_by_id.get(team_id)
        if team is None:
            return None
        return rule_set.team_point_adjustment(team, round_)

    def effective(self, team_id: int, round_: int) -> tuple[float, float]:
        """Combined manual + rule-set (MP, GP) adjustment for the team's
        round. Folded into standings, tie-break records, screens and the
        TRF 299 export."""
        mp, gp = self.manual(team_id, round_)
        rule_set_adjustment = self.from_rule_set(team_id, round_)
        if rule_set_adjustment is not None:
            mp += rule_set_adjustment.mp
            gp += rule_set_adjustment.gp
        return mp, gp

    def set_manual(
        self,
        team_id: int,
        round_: int,
        mp_delta: float,
        gp_delta: float,
        reason: str | None,
        database: 'EventDatabase',
    ) -> None:
        """Upsert the manual (MP, GP) adjustment for (team, round) and
        keep the in-memory stored list in sync."""
        tournament = self.tournament
        database.set_stored_team_point_adjustment(
            tournament.id, team_id, round_, mp_delta, gp_delta, reason
        )
        _replace(
            tournament.stored_tournament.stored_team_point_adjustments,
            lambda adjustment: (
                adjustment.team_id == team_id and adjustment.round_ == round_
            ),
            StoredTeamPointAdjustment(
                id=None,
                tournament_id=tournament.id,
                team_id=team_id,
                round_=round_,
                mp_delta=mp_delta,
                gp_delta=gp_delta,
                reason=reason,
            )
            if mp_delta or gp_delta or reason
            else None,
        )

    def stored_for_player(
        self, player_id: int, round_: int
    ) -> StoredPlayerPointAdjustment | None:
        """The stored manual adjustment row for (player, round), or None."""
        for (
            adjustment
        ) in self.tournament.stored_tournament.stored_player_point_adjustments:
            if adjustment.player_id == player_id and adjustment.round_ == round_:
                return adjustment
        return None

    def for_player(self, player_id: int, round_: int) -> float:
        """Manual bonus / penalty points for (player, round) in an
        individual tournament. Team events adjust whole teams instead, so
        this is always zero there.

        Unlike the team counterpart there is no rule-set contribution:
        rule sets award match points, which individual tournaments don't
        have."""
        if self.tournament.is_team_tournament:
            return 0.0
        adjustment = self.stored_for_player(player_id, round_)
        return adjustment.delta if adjustment else 0.0

    def player_total(self, player_id: int, after_round: int) -> float:
        """Every adjustment for the player through ``after_round``."""
        if self.tournament.is_team_tournament:
            return 0.0
        return sum(
            adjustment.delta
            for adjustment in self.tournament.stored_tournament.stored_player_point_adjustments
            if adjustment.player_id == player_id and adjustment.round_ <= after_round
        )

    def set_manual_for_player(
        self,
        player_id: int,
        round_: int,
        delta: float,
        reason: str | None,
        database: 'EventDatabase',
    ) -> None:
        """Upsert the manual adjustment for (player, round) and keep the
        in-memory stored list in sync."""
        tournament = self.tournament
        database.set_stored_player_point_adjustment(
            tournament.id, player_id, round_, delta, reason
        )
        _replace(
            tournament.stored_tournament.stored_player_point_adjustments,
            lambda adjustment: (
                adjustment.player_id == player_id and adjustment.round_ == round_
            ),
            StoredPlayerPointAdjustment(
                id=None,
                tournament_id=tournament.id,
                player_id=player_id,
                round_=round_,
                delta=delta,
                reason=reason,
            )
            if delta or reason
            else None,
        )

    def bound(self, after_round: int | None) -> int:
        """Highest round whose adjustments count: the explicit bound, or
        the current round for live views."""
        bound = (
            after_round if after_round is not None else self.tournament.current_round
        )
        return bound or 0
