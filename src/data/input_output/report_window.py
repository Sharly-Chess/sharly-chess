"""The slice of a tournament that one report covers.

A tournament of more than 30 days is reported to FIDE slice by slice,
and a slice's file is a tournament in its own right: it holds that
slice's rounds numbered from 1, the players who played in them, the
ratings and titles they held then (FIDE B.01 1.1.4), and points counted
from those games alone — "the number of points in the tournament
standings" of TRF-25 001, the tournament being the file's own.

Two accepted submissions of one Italian tournament show the shape:
<https://ratings.fide.com/tournament_src_report.phtml?code=286873> holds
its rounds 1-4, and
<https://ratings.fide.com/tournament_src_report.phtml?code=286875> the
same tournament's rounds 5-6 — numbered 1-2, eleven of the fourteen
players, and both players' ratings moved between the two.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from data.player import TournamentPlayer
from data.tournament_period import TournamentPeriod

if TYPE_CHECKING:
    from data.tournament import Tournament


@dataclass(frozen=True)
class ReportWindow:
    """The rounds a report covers and the numbering it gives its
    players."""

    period: TournamentPeriod
    players: list[TournamentPlayer]
    number_by_player_id: dict[int, int]
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

    def rebase(self, round_: int) -> int:
        """The round's number in the report, counted from 1."""
        return round_ - self.first_round + 1

    def number(self, player: TournamentPlayer) -> int:
        return self.number_by_player_id[player.id]

    def optional_number(self, player: TournamentPlayer) -> int | None:
        """The player's number in the report, or None when the report
        does not hold them — a team member who played none of its
        rounds."""
        return self.number_by_player_id.get(player.id)

    def rank(self, player: TournamentPlayer) -> int:
        return self.rank_by_player_id[player.id]

    def points(self, player: TournamentPlayer) -> float:
        return (
            player.team_trf_standard_points_in(self.rounds)
            if player.tournament.is_team_tournament
            else player.points_in(self.rounds)
        )


def build_window(tournament: 'Tournament', period: TournamentPeriod) -> ReportWindow:
    """The window of a period: the players with a game in it, ranked on
    the ratings they held then."""
    players = [
        player
        for player in tournament.tournament_players
        if any(
            player.pairings[round_].exists
            for round_ in period.rounds
            if round_ in player.pairings
        )
    ]
    players.sort(
        key=lambda player: (
            -player.rating_and_type_in(period).value,
            *player.name_sort_key,
        )
    )
    window = ReportWindow(
        period=period,
        players=players,
        number_by_player_id={
            player.id: number for number, player in enumerate(players, start=1)
        },
        rank_by_player_id={},
    )
    # The standings the file states are its own: ranked on the points of
    # the games it holds, ties sharing a place.
    by_points = sorted(players, key=lambda player: -window.points(player))
    previous_points: float | None = None
    previous_rank = 0
    for position, player in enumerate(by_points, start=1):
        points = window.points(player)
        if points != previous_points:
            previous_rank, previous_points = position, points
        window.rank_by_player_id[player.id] = previous_rank
    return window
