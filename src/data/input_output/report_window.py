"""The period of a tournament that one report covers.

A tournament of more than 30 days is reported to FIDE period by period. The
file of a period is the tournament's own file with the other rounds left
empty: the same dates, the same round count, the same players under the
same numbers, and only the games of the period filled in. What belongs to
the period alone is what the games are worth — points counted from those
games, the standings they make, and the ratings and titles the period was
played on (FIDE B.01 1.1.4).

That is the shape Swiss Manager writes when asked for the rounds of one
period: the 001 records keep every round's column and fill in the period's,
while the header records go on describing the tournament entire.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from data.player import TournamentPlayer
from data.tournament_period import TournamentPeriod

if TYPE_CHECKING:
    from data.tournament import Tournament


@dataclass(frozen=True)
class ReportWindow:
    """The rounds a report fills in, and the standings they make."""

    period: TournamentPeriod
    rank_by_player_id: dict[int, int]

    @property
    def rounds(self) -> range:
        return self.period.rounds

    @property
    def first_round(self) -> int:
        return self.period.first_round

    @property
    def last_round(self) -> int:
        return self.period.last_round

    def covers(self, round_: int) -> bool:
        return round_ in self.rounds

    def rank(self, player: TournamentPlayer) -> int:
        return self.rank_by_player_id[player.id]

    def points(self, player: TournamentPlayer) -> float:
        return (
            player.team_trf_standard_points_in(self.rounds)
            if player.tournament.is_team_tournament
            else player.points_in(self.rounds)
        )


def build_window(tournament: 'Tournament', period: TournamentPeriod) -> ReportWindow:
    """The window of a period, ranking the field on the games it holds."""
    window = ReportWindow(period=period, rank_by_player_id={})
    # The standings the file states are its own: ranked on the points of
    # the games it fills in, ties sharing a place.
    players = sorted(tournament.tournament_players, key=lambda p: -window.points(p))
    previous_points: float | None = None
    previous_rank = 0
    for position, player in enumerate(players, start=1):
        points = window.points(player)
        if points != previous_points:
            previous_rank, previous_points = position, points
        window.rank_by_player_id[player.id] = previous_rank
    return window
