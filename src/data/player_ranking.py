"""The standings of a tournament's players.

Ranking the field after a round scores every player, evaluates every
ranking criterion, sorts, and notes how far each criterion moved each
player; the result is kept until the next computation, and the round
it was made for with it.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.player import TournamentPlayer
    from data.tournament import Tournament


class PlayerRanking:
    """The players of one tournament by rank, as last computed."""

    def __init__(self, tournament: 'Tournament') -> None:
        self.tournament = tournament
        self.by_rank: dict[int, TournamentPlayer] | None = None
        #: The round the standings were last computed for.
        self.after_round: int | None = None

    @property
    def ranked_after_round(self) -> int:
        """The round the standings on this tournament were last computed for.
        A label read beside those rows (a knock-out result, say) must describe
        the same round, not the latest one played."""
        if self.after_round is None:
            return self.tournament.max_ranking_round
        return self.after_round

    def correct_round(self, ranking_round: int | None = None) -> int:
        """The round closest to the one asked for that the standings can
        be computed for."""
        max_ranking_round = self.tournament.max_ranking_round
        if ranking_round is None:
            return max_ranking_round
        return max(0, min(ranking_round, max_ranking_round))

    def compute(
        self, *, after_round: int | None = None
    ) -> dict[int, 'TournamentPlayer']:
        """Rank every player after ``after_round``, the last ranking round
        by default, and return them by rank."""
        tournament = self.tournament
        if after_round is None:
            after_round = tournament.max_ranking_round
        tournament._compute_caching_enabled = True
        try:
            self._compute(after_round)
        finally:
            tournament._compute_caching_enabled = False
        assert self.by_rank is not None
        return self.by_rank

    def ensure_computed(self) -> None:
        """Compute the ranks when they have not been yet, so rank-dependent
        derivations (e.g. a ranking screen's default name) work without the
        caller having to precompute them."""
        if self.by_rank is None:
            self.compute()

    @property
    def players_by_rank(self) -> dict[int, 'TournamentPlayer']:
        assert self.by_rank is not None, (
            'The ranks are not computed; call compute() first.'
        )
        return self.by_rank

    def _compute(self, after_round: int) -> None:
        tournament = self.tournament
        self.after_round = after_round
        tournament.reset_keizer_scorer()
        for player in tournament.tournament_players:
            player.clear_compute_caches()
        tournament.set_tournament_players_pairing_numbers()
        tie_breaks = tournament.tie_breaks
        for tie_break in tie_breaks:
            for player_id, variable in tie_break.get_player_variables(
                tournament, after_round
            ).items():
                player = tournament.tournament_players_by_id[player_id]
                player.tie_break_variables[tie_break.id] = variable
        keizer = tournament.pairing_system.id == 'KEIZER'
        knockout = tournament.pairing_system.eliminates_participants
        for player in tournament.tournament_players:
            if keizer:
                player.points = tournament.keizer_scorer.total(
                    player, after_round=after_round
                )
            elif knockout:
                player.points = tournament.knockout.ranking_value(
                    player, after_round=after_round
                )
            else:
                player.points = player.standings_points(after_round)
            player.compute_tie_break_values(
                after_round=after_round, tie_breaks=tie_breaks
            )

        for index, tie_break in enumerate(tie_breaks):
            if tie_break.is_computed_per_player:
                continue
            value_by_player_id = tie_break.compute_all_player_values(
                tournament,
                tie_break_index=index,
                after_round=after_round,
            )
            for player_id, tie_break_value in value_by_player_id.items():
                player = tournament.tournament_players_by_id[player_id]
                player.tie_break_values[index].value = tie_break_value

        # Players excluded from the standings (FIDE 6.6 round-robin rule) are
        # ranked last regardless of their score, so the competitors keep a
        # contiguous ranking. They stay in the crosstable for the record.
        sorted_tournament_players = sorted(
            tournament.tournament_players,
            key=lambda p: (p.is_excluded_from_standings, p.rank_sort_key),
        )
        self.by_rank = dict(enumerate(sorted_tournament_players, start=1))
        for rank, player in self.by_rank.items():
            player.rank = rank
        for tie_break_index, tie_break in enumerate(tie_breaks):
            if not tie_break.display_rank_delta:
                continue
            players_ranked_without_tie_break = sorted(
                tournament.tournament_players,
                key=lambda p: p.rank_sort_key_without_tie_break(tie_break_index),
            )
            for rank_without_tie_break, player in enumerate(
                players_ranked_without_tie_break, start=1
            ):
                player.tie_break_values[tie_break_index].rank_progress = (
                    rank_without_tie_break - player.rank
                )
