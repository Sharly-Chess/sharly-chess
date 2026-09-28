"""What the teams of a tournament have scored.

The standings, the per-team records the team tie-breaks read, and the
running totals a round starts from all tally the same team boards, so
they are worked out side by side, from one reading of what a bye and a
match are worth.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from data.teams.team_board import TeamBoard
from data.tie_breaks import TeamTieBreak, TieBreak
from data.tie_breaks.team_records import TeamMatchRecord, TeamMatchType, TeamRecord
from data.tie_breaks.team_tie_breaks import TeamTieBreakContext
from utils.enum import Result, ScoreType, TeamByeType
from utils.types import TieBreakValue

if TYPE_CHECKING:
    from data.teams.team import Team
    from data.tournament import Tournament

Outcome = Literal['wins', 'draws', 'losses', 'forfeits']
RankKey = Callable[['TeamStanding'], tuple[float, ...]]


@dataclass
class TeamStanding:
    """One team's line in the standings."""

    team: 'Team'
    mp: float = 0.0
    gp: float = 0.0
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    # A round the team was absent for counts here rather than as a loss,
    # so a loss is one taken over the board — a match it forfeited
    # outright, and a round it was left unpaired as absent for.
    forfeits: int = 0
    tie_break_values: list[TieBreakValue] = field(default_factory=list)
    rank: int = 0
    # Everything the standings rank on, short of the tie_order of last
    # resort: teams sharing it are level, and share a rank wherever a rank
    # is reported rather than a position (C.07 Art. 4.2).
    rank_key: tuple[float, ...] = ()

    def score(self, score_type: ScoreType) -> float:
        """The team's match or game points, whichever ``score_type`` is."""
        return self.mp if score_type == ScoreType.MATCH_POINTS else self.gp

    def add(self, mp: float, gp: float, outcome: Outcome) -> None:
        """Count one more round, scored ``mp`` / ``gp`` and ending in
        ``outcome``."""
        self.played += 1
        self.mp += mp
        self.gp += gp
        setattr(self, outcome, getattr(self, outcome) + 1)

    @property
    def tie_order(self) -> tuple[float, str]:
        """The order of teams nothing else separates: pairing number,
        then name."""
        team = self.team
        return (
            team.pairing_number if team.pairing_number is not None else float('inf'),
            team.name.lower(),
        )


# What a bye counts as in the standings' tally of a team's rounds. A
# pairing-allocated bye is awarded, so it is a win, as is a full-point
# bye; a zero-point bye is the round the team was absent for.
_BYE_OUTCOME: dict[str, Outcome] = {
    TeamByeType.ZPB: 'forfeits',
    TeamByeType.HPB: 'draws',
    TeamByeType.FPB: 'wins',
}
# What a bye is to the tie-breaks' unplayed-rounds handling (Art. 16).
# A full-point bye is awarded, not given up, so it reads as a PAB.
_BYE_MATCH_TYPE: dict[str, TeamMatchType] = {
    TeamByeType.ZPB: TeamMatchType.ZPB,
    TeamByeType.HPB: TeamMatchType.HPB,
    TeamByeType.FPB: TeamMatchType.PAB,
}


class TeamScoring:
    """The scores of one tournament's teams, tallied from its team boards."""

    def __init__(self, tournament: 'Tournament') -> None:
        self.tournament = tournament

    # -------------------------------------------------------------------------
    # What a bye is worth
    # -------------------------------------------------------------------------

    def bye_score(self, bye_type: str | None) -> tuple[float, float] | None:
        """The ``(match points, game points)`` a team takes for a bye of
        that type, or ``None`` for a rest game — the bye a round robin or a
        two-game-match system allocates, which is not played and scores
        nothing.

        A pairing-allocated bye (``None`` or ``PAB``) is worth what the
        tournament says a PAB is; the manual byes mirror the individual
        ones, scaled by the board count. A zero-point bye is a team-level
        forfeit: every board counts as a forfeited game, scored at the
        absent-board game point value (the ``gp_zpb`` override, otherwise
        0)."""
        tournament = self.tournament
        match_points = tournament.match_points
        boards = float(tournament.team_player_count or 0)
        match bye_type:
            case TeamByeType.ZPB:
                return (
                    match_points[Result.ZERO_POINT_BYE],
                    boards * tournament.team_game_points[Result.ZERO_POINT_BYE],
                )
            case TeamByeType.HPB:
                return match_points[Result.DRAW], boards * Result.DRAW.point_value
            case TeamByeType.FPB:
                return match_points[Result.WIN], boards * Result.WIN.point_value
            case _:
                if tournament.team_bye_is_rest:
                    return None
                return (
                    match_points[Result.PAIRING_ALLOCATED_BYE],
                    tournament.team_pab_game_points,
                )

    def _team_boards_through(self, after_round: int | None) -> list[TeamBoard]:
        """The team boards of the rounds up to ``after_round``, every round
        when it is ``None``, in id order."""
        return [
            team_board
            for team_board in self.tournament.team_boards_by_id.values()
            if after_round is None or team_board.round <= after_round
        ]

    @property
    def _flat(self) -> bool:
        """Whether the players are paired straight across teams, with no
        team board around a round's games (a fixed-table system such as
        Molter), so that a team's round is what its lineup scored on each
        board rather than one match against one opponent."""
        return not self.tournament.pairing_system.paired_by_team

    def _excluded_team_ids(self) -> set[int]:
        return {
            team.id for team in self.tournament.teams if team.is_excluded_from_standings
        }

    # -------------------------------------------------------------------------
    # Standings
    # -------------------------------------------------------------------------

    def standings(self, *, after_round: int | None = None) -> list[TeamStanding]:
        """The team standings, sorted by the configured ranking criteria
        in order. The primary score is one of them — the Points tie-break
        — rather than an implicit first key, so that its position can be
        chosen; the secondary score is opted into with MPvGP.
        Each entry: {team, mp, gp, played, wins, draws, losses, forfeits,
        tie_break_values, rank}.

        ``after_round`` bounds which rounds count: only matches up to
        and including it are tallied. ``None`` (default) counts every
        stored match — the live standings. A ranking document passes
        the finished round it's printing for, so a paired-but-unfinished
        round isn't counted (played / points stay at the prior round).

        For ``paired_by_team`` systems (team-vs-team blocks), match
        points and game points come from the ``team_board`` records.
        For flat fixed-table systems (e.g. FFE Molter — players from
        different teams paired directly with no team_board envelope),
        a team's points are the sum of its players' individual game
        points across all boards in the tournament. Match-point and
        win/draw/loss tallies aren't meaningful in that mode."""
        tournament = self.tournament
        standings = self._empty_standings()
        if self._flat:
            self._tally_boards(standings, after_round)
        else:
            self._tally_matches(standings, after_round)
        self._apply_point_adjustments(standings, after_round)
        rows = list(standings.values())
        base_key = self._base_key(after_round)
        team_tie_breaks = [tb for tb in tournament.tie_breaks if tb.supports_team_mode]
        values = self._tie_break_values(rows, team_tie_breaks, base_key, after_round)
        return self._ranking(rows, team_tie_breaks, values, base_key)

    def _empty_standings(self) -> dict[int, TeamStanding]:
        """One line per team of the tournament, nothing scored yet."""
        tournament = self.tournament
        return {
            team.id: TeamStanding(team)
            for team in tournament.event.sorted_teams
            if team.tournament_id == tournament.id
        }

    def _tally_boards(
        self, standings: dict[int, TeamStanding], after_round: int | None
    ) -> None:
        """Flat fixed-table scoring (no team boards): each player's game
        points go straight into the team's total, and a round any of
        them was paired in is a round the team played. ``team_game_points``
        is used so the ``gp_*`` override applies to team scoring here
        too."""
        tournament = self.tournament
        team_game_points = tournament.team_game_points
        rounds_played: set[tuple[int, int]] = set()
        for board in tournament.boards_by_id.values():
            if after_round is not None and board.round > after_round:
                continue
            for player_id, pairing in (
                (board.stored_board.white_player_id, board.white_pairing),
                (board.stored_board.black_player_id, board.black_pairing),
            ):
                if player_id is None:
                    continue
                player = tournament.event.players_by_id.get(player_id)
                if player is None or player.team_id not in standings:
                    continue
                entry = standings[player.team_id]
                entry.gp += pairing.result.points(team_game_points)
                rounds_played.add((player.team_id, board.round))
        for team_id, _round in rounds_played:
            standings[team_id].played += 1

    def _tally_matches(
        self, standings: dict[int, TeamStanding], after_round: int | None
    ) -> None:
        """Score each team board through ``after_round``: byes at what
        their type is worth, matches at their effective game points."""
        excluded_team_ids = self._excluded_team_ids()
        for team_board in self._team_boards_through(after_round):
            stb = team_board.stored_team_board
            if stb.team_a_id in excluded_team_ids or stb.team_b_id in excluded_team_ids:
                continue
            if stb.team_b_id is None:
                entry = standings.get(stb.team_a_id)
                score = self.bye_score(stb.bye_type)
                if entry is None or score is None:
                    continue
                mp, gp = score
                entry.add(mp, gp, _BYE_OUTCOME.get(stb.bye_type or '', 'wins'))
                continue
            a_gp, b_gp = team_board.game_points
            # Match result follows the effective game points (board + this
            # round's penalties/bonuses); the deltas are added to the totals
            # separately by _apply_point_adjustments.
            a_gp_effective, b_gp_effective = team_board.effective_game_points
            match_points_pair = team_board.match_points_pair(
                (a_gp_effective, b_gp_effective)
            )
            assert match_points_pair is not None
            a_mp, b_mp = match_points_pair
            a_outcome: Outcome
            b_outcome: Outcome
            if a_gp_effective > b_gp_effective:
                a_outcome, b_outcome = 'wins', 'losses'
            elif a_gp_effective < b_gp_effective:
                a_outcome, b_outcome = 'losses', 'wins'
            elif team_board.lost_by_both((a_gp_effective, b_gp_effective)):
                a_outcome = b_outcome = 'losses'
            else:
                a_outcome = b_outcome = 'draws'
            # A side that forfeited the whole match is tallied as a
            # forfeit, not as the result its boards add up to.
            if team_board.team_all_forfeit(stb.team_a_id):
                a_outcome = 'forfeits'
            if team_board.team_all_forfeit(stb.team_b_id):
                b_outcome = 'forfeits'
            for team_id, mp, gp, outcome in (
                (stb.team_a_id, a_mp, a_gp, a_outcome),
                (stb.team_b_id, b_mp, b_gp, b_outcome),
            ):
                entry = standings.get(team_id)
                if entry is not None:
                    entry.add(mp, gp, outcome)

    def _apply_point_adjustments(
        self, standings: dict[int, TeamStanding], after_round: int | None
    ) -> None:
        adjustments = self.tournament.point_adjustments
        for round_ in range(1, adjustments.bound(after_round) + 1):
            for team_id, entry in standings.items():
                mp_adj, gp_adj = adjustments.effective(team_id, round_)
                entry.mp += mp_adj
                entry.gp += gp_adj

    def _base_key(self, after_round: int | None) -> RankKey:
        """What ranks ahead of the configured criteria: nothing.

        The primary score is one of them — the Points tie-break — rather
        than an implicit prefix, so that its position can be chosen
        (TRF26 record 212). The secondary score has never been implicit
        either: it is opted into with MPvGP. A tournament whose list
        holds neither ranks on its tie-breaks alone.

        A knock-out is the exception: it ranks by the round reached
        (bigger value, later exit, first), so that is the leading key."""
        tournament = self.tournament
        if not tournament.pairing_system.eliminates_participants:
            return lambda row: ()
        elimination_values = tournament.knockout.team_ranking_values(
            after_round=(
                after_round if after_round is not None else tournament.max_ranking_round
            )
        )
        return lambda row: (-elimination_values.get(row.team.id, 0.0),)

    def _tie_break_values(
        self,
        rows: list[TeamStanding],
        team_tie_breaks: list[TieBreak],
        base_key: RankKey,
        after_round: int | None,
    ) -> dict[int, list[float]]:
        """Each team's raw value for each team tie-break, in tie-break
        order, keyed by team id."""
        values: dict[int, list[float]] = {row.team.id: [] for row in rows}
        if not team_tie_breaks:
            return values
        if after_round is None:
            after_round = self.tournament.current_round
        records_by_id = {r.team_id: r for r in self.records(after_round=after_round)}
        context = self.tie_break_context()

        def key_so_far(row: TeamStanding) -> tuple[float, ...]:
            return base_key(row) + tuple(-v for v in values[row.team.id])

        for tb in team_tie_breaks:
            if tb.display_rank_delta and isinstance(tb, TeamTieBreak):
                # Group-level resolution (EDE): cluster rows by the
                # sort key so far, then ask the tie-break to assign
                # rank-deltas within each still-tied group.
                rows.sort(key=key_so_far)
                groups: list[list[TeamStanding]] = []
                current_key: tuple[float, ...] | None = None
                for row in rows:
                    key = key_so_far(row)
                    if key != current_key:
                        groups.append([])
                        current_key = key
                    groups[-1].append(row)
                tied = [
                    [
                        records_by_id[row.team.id]
                        for row in group
                        if row.team.id in records_by_id
                        and not row.team.is_excluded_from_standings
                    ]
                    for group in groups
                    if len(group) > 1
                ]
                values_map: dict[int, float] = (
                    tb.compute_all_team_values(
                        tied, records_by_id, context, after_round=after_round
                    )
                    if tied
                    else {}
                )
                for row in rows:
                    values[row.team.id].append(float(values_map.get(row.team.id, 0.0)))
                continue
            # Scalar tie-break — compute one value per team.
            for row in rows:
                record = records_by_id.get(row.team.id)
                value = (
                    tb.compute_team_value(
                        record, records_by_id, context, after_round=after_round
                    )
                    if record is not None
                    else 0.0
                )
                values[row.team.id].append(float(value))
        return values

    def _ranking(
        self,
        rows: list[TeamStanding],
        team_tie_breaks: list[TieBreak],
        values: dict[int, list[float]],
        base_key: RankKey,
    ) -> list[TeamStanding]:
        """Sort the rows, number them, and give them their tie-break
        values, wrapped for display."""
        rows.sort(
            key=lambda row: (
                # Teams excluded from the standings (FIDE 6.6) rank last,
                # regardless of score, so the competitors keep a contiguous
                # ranking. They stay in the crosstable for the record.
                row.team.is_excluded_from_standings,
                base_key(row) + tuple(-v for v in values[row.team.id]) + row.tie_order,
            )
        )
        for rank, row in enumerate(rows, 1):
            row.rank = rank
            row.rank_key = base_key(row) + tuple(-v for v in values[row.team.id])
            row.tie_break_values = self._wrap_tie_break_values(
                team_tie_breaks, values[row.team.id]
            )
        return rows

    @staticmethod
    def _wrap_tie_break_values(
        tbs: list[TieBreak], values: list[float]
    ) -> list[TieBreakValue]:
        """Wrap raw tie-break floats as ``TieBreakValue`` so consumers
        share one display path (absolute-value flag, rank-delta arrows)
        instead of each re-implementing it."""
        wrapped: list[TieBreakValue] = []
        for tb, value in zip(tbs, values, strict=True):
            tbv = TieBreakValue(tb, value)
            if tb.display_rank_delta:
                tbv.rank_progress = round(value)
            wrapped.append(tbv)
        return wrapped

    # -------------------------------------------------------------------------
    # Records for the team tie-breaks
    # -------------------------------------------------------------------------

    def tie_break_context(self) -> TeamTieBreakContext:
        """Snapshot the tournament parameters team tie-breaks need."""
        tournament = self.tournament
        match_points = tournament.match_points
        team_size = tournament.team_player_count or 0
        return TeamTieBreakContext(
            primary_score=tournament.primary_score,
            secondary_score=tournament.secondary_score,
            rounds=tournament.rounds,
            win_mp=match_points.get(Result.WIN, 2.0),
            draw_mp=match_points.get(Result.DRAW, 1.0),
            loss_mp=match_points.get(Result.LOSS, 0.0),
            team_player_count=team_size,
            draw_gp=team_size * tournament.draw_points,
            predetermined_pairings=tournament.pairing_system.predetermined_pairings,
            excluded_team_ids=frozenset(self._excluded_team_ids()),
        )

    def records(self, *, after_round: int | None = None) -> list[TeamRecord]:
        """Build :class:`TeamRecord` instances for every team in this
        tournament, suitable as input to the team tie-break compute API.

        A round carries the score the standings give it and the match
        type Art. 16 handling reads. A team marked absent is a
        zero-point bye whose contribution is cut first, not a
        pairing-allocated bye scored as a win; a team that fielded
        nobody, or every one of whose players lost by forfeit, forfeited
        the match rather than playing it, and its opponent won by
        forfeit rather than over the board.

        In a flat tournament a team's round is the games its lineup
        played on each board, against no one opponent, and it scores
        game points only."""
        tournament = self.tournament
        if after_round is None:
            after_round = tournament.current_round
        matches_per_team: dict[int, list[TeamMatchRecord]] = {
            team.id: [] for team in tournament.teams
        }
        if self._flat:
            for team in tournament.teams:
                matches_per_team[team.id] = self._flat_records(team, after_round)
        else:
            self._collect_match_records(matches_per_team, after_round)
        totals: dict[int, list[float]] = {
            team_id: [
                sum(record.own_mp for record in records),
                sum(record.own_gp for record in records),
            ]
            for team_id, records in matches_per_team.items()
        }
        self._fold_adjustments_into(matches_per_team, totals, after_round)
        return [
            TeamRecord(
                team_id=team.id,
                name=team.name,
                total_mp=totals[team.id][0],
                total_gp=totals[team.id][1],
                matches=sorted(matches_per_team[team.id], key=lambda m: m.round_),
                pairing_number=team.pairing_number,
            )
            for team in tournament.teams
        ]

    def _collect_match_records(
        self, matches_per_team: dict[int, list[TeamMatchRecord]], after_round: int
    ) -> None:
        """Add each team's record of every team board through
        ``after_round``."""
        excluded_team_ids = self._excluded_team_ids()
        for team_board in self._team_boards_through(after_round):
            stb = team_board.stored_team_board
            if stb.team_a_id in excluded_team_ids or stb.team_b_id in excluded_team_ids:
                continue
            records = (
                self._match_records(team_board)
                if stb.team_b_id is not None
                else (self._bye_record(team_board),)
            )
            for team_id, record in zip(
                (stb.team_a_id, stb.team_b_id), records, strict=False
            ):
                if record is None:
                    continue
                assert team_id is not None
                matches_per_team[team_id].append(record)

    def _flat_records(self, team: 'Team', after_round: int) -> list[TeamMatchRecord]:
        """One record per round the team's lineup was paired in, with a
        score and a rating per board slot: a slot left empty, or whose
        player sat the round out, scores nothing."""
        tournament = self.tournament
        players_by_id = tournament.tournament_players_by_id
        team_game_points = tournament.team_game_points
        records: list[TeamMatchRecord] = []
        for round_ in range(1, after_round + 1):
            scores: list[float] = []
            ratings: list[int | None] = []
            paired = False
            for player in team.effective_round_slots(round_):
                tournament_player = (
                    players_by_id.get(player.id) if player is not None else None
                )
                pairing = (
                    tournament_player.pairings.get(round_)
                    if tournament_player is not None
                    else None
                )
                if tournament_player is None or pairing is None:
                    scores.append(0.0)
                    ratings.append(None)
                    continue
                paired = True
                scores.append(pairing.result.points(team_game_points))
                ratings.append(tournament_player.rating or None)
            if not paired:
                continue
            records.append(
                TeamMatchRecord(
                    round_=round_,
                    opponent_id=None,
                    own_mp=0.0,
                    own_gp=sum(scores),
                    match_type=TeamMatchType.PLAYED,
                    board_scores=tuple(scores),
                    board_ratings=tuple(ratings),
                )
            )
        return records

    def _bye_record(self, team_board: TeamBoard) -> TeamMatchRecord | None:
        """The record of a bye, or ``None`` for a rest game, which is not
        a match: no record, no points, invisible to the tie-breaks."""
        stb = team_board.stored_team_board
        score = self.bye_score(stb.bye_type)
        if score is None:
            return None
        own_mp, own_gp = score
        return TeamMatchRecord(
            round_=team_board.round,
            opponent_id=None,
            own_mp=own_mp,
            own_gp=own_gp,
            match_type=_BYE_MATCH_TYPE.get(stb.bye_type or '', TeamMatchType.PAB),
            board_scores=self._board_scores_for(team_board, stb.team_a_id),
            board_ratings=self._bye_ratings(team_board),
        )

    def _bye_ratings(self, team_board: TeamBoard) -> tuple[int | None, ...]:
        """A team on a bye still takes part (it is present, just unpaired),
        so OWN-ELO should reflect its strength. The bye envelope has no
        boards, so the round's lineup players' ratings stand in."""
        tournament = self.tournament
        stb = team_board.stored_team_board
        team = tournament.event.teams_by_id.get(stb.team_a_id)
        if team is None:
            return self._board_ratings_for(team_board, stb.team_a_id)
        ratings: list[int | None] = []
        for player in team.effective_round_slots(team_board.round):
            tp = (
                tournament.tournament_players_by_id.get(player.id)
                if player is not None
                else None
            )
            ratings.append(tp.rating if tp and tp.rating else None)
        return tuple(ratings)

    def _match_records(
        self, team_board: TeamBoard
    ) -> tuple[TeamMatchRecord, TeamMatchRecord]:
        """The two teams' records of one match, team A's first."""
        stb = team_board.stored_team_board
        a_id, b_id = stb.team_a_id, stb.team_b_id
        assert b_id is not None
        a_gp, b_gp = team_board.game_points
        # Match result follows the effective game points (board + this
        # round's penalties/bonuses); the deltas are added to own_gp and
        # the totals by _fold_adjustments_into — here they only tip the
        # comparison.
        match_points_pair = team_board.match_points_pair()
        assert match_points_pair is not None
        a_mp, b_mp = match_points_pair
        # A match is played when a game was played on any of its boards.
        # Otherwise its result stands and it is a forfeit for the team that
        # lost it, or for both teams when neither scored.
        a_type = b_type = TeamMatchType.PLAYED
        if team_board.no_board_played():
            if a_mp > b_mp:
                a_type, b_type = TeamMatchType.FORFEIT_WIN, TeamMatchType.FORFEIT_LOSS
            elif a_mp < b_mp:
                a_type, b_type = TeamMatchType.FORFEIT_LOSS, TeamMatchType.FORFEIT_WIN
            elif a_gp > 0 or b_gp > 0:
                a_type = b_type = TeamMatchType.UNPLAYED_DRAW
            else:
                a_type = b_type = TeamMatchType.FORFEIT_LOSS
        return (
            TeamMatchRecord(
                round_=team_board.round,
                opponent_id=b_id,
                own_mp=a_mp,
                own_gp=a_gp,
                match_type=a_type,
                board_scores=self._board_scores_for(team_board, a_id),
                board_ratings=self._board_ratings_for(team_board, a_id),
            ),
            TeamMatchRecord(
                round_=team_board.round,
                opponent_id=a_id,
                own_mp=b_mp,
                own_gp=b_gp,
                match_type=b_type,
                board_scores=self._board_scores_for(team_board, b_id),
                board_ratings=self._board_ratings_for(team_board, b_id),
            ),
        )

    def _fold_adjustments_into(
        self,
        matches_per_team: dict[int, list[TeamMatchRecord]],
        totals: dict[int, list[float]],
        after_round: int,
    ) -> None:
        """Fold each round's bonus / penalty points into the totals (used
        by total-based tie-breaks and the secondary score) and into that
        round's match record, so MP/GP-sum tie-breaks like points-for and
        differential see them (board- and rating-based tie-breaks read
        board data and are unaffected)."""
        adjustments = self.tournament.point_adjustments
        for team_id, matches in matches_per_team.items():
            for round_ in range(1, adjustments.bound(after_round) + 1):
                mp_adj, gp_adj = adjustments.effective(team_id, round_)
                if not mp_adj and not gp_adj:
                    continue
                totals[team_id][0] += mp_adj
                totals[team_id][1] += gp_adj
                for index, match in enumerate(matches):
                    if match.round_ == round_:
                        matches[index] = replace(
                            match,
                            own_mp=match.own_mp + mp_adj,
                            own_gp=match.own_gp + gp_adj,
                        )
                        break

    def _board_scores_for(
        self, team_board: TeamBoard, team_id: int
    ) -> tuple[float, ...]:
        """Per-board own scores for ``team_id`` in this match, ordered
        by board index. Required by board-weighted tie-breaks (FFE
        Berlin, knockout BC/TBR/BBE)."""
        scores: list[float] = []
        for board in sorted(team_board.boards, key=lambda b: b.index):
            white_team_id, _black_team_id = team_board.board_team_ids(board)
            white_pairing = board.optional_white_pairing
            white_pts = white_pairing.points if white_pairing is not None else 0.0
            black_pairing = board.optional_black_pairing
            black_pts = black_pairing.points if black_pairing is not None else 0.0
            scores.append(white_pts if white_team_id == team_id else black_pts)
        return tuple(scores)

    def _board_ratings_for(
        self, team_board: TeamBoard, team_id: int
    ) -> tuple[int | None, ...]:
        """Per-board own player ratings for ``team_id`` in this match,
        ordered by board index. Mirrors :meth:`_board_scores_for`
        for tie-breaks that weigh team standings by own-player rating.
        ``None`` for unrated players."""
        players_by_id = self.tournament.tournament_players_by_id
        ratings: list[int | None] = []
        for board in sorted(team_board.boards, key=lambda b: b.index):
            white_id = board.stored_board.white_player_id
            black_id = board.stored_board.black_player_id
            white_player = players_by_id.get(white_id) if white_id else None
            black_player = players_by_id.get(black_id) if black_id else None
            own_player = (
                white_player
                if white_player and white_player.team_id == team_id
                else black_player
                if black_player and black_player.team_id == team_id
                else None
            )
            ratings.append(
                own_player.rating if own_player and own_player.rating else None
            )
        return tuple(ratings)

    # -------------------------------------------------------------------------
    # Totals
    # -------------------------------------------------------------------------

    def totals_after(self, after_round: int) -> dict[int, tuple[float, float]]:
        """Per-team ``(match_points, game_points)`` cumulative through
        ``after_round``, bonus / penalty points included. Returned dict
        is keyed by ``team.id``; teams with no team_board entries simply
        get ``(0.0, 0.0)``."""
        totals: dict[int, list[float]] = {}
        for team_board in self._team_boards_through(after_round):
            stb = team_board.stored_team_board
            a_entry = totals.setdefault(stb.team_a_id, [0.0, 0.0])
            if stb.team_b_id is None:
                score = self.bye_score(stb.bye_type)
                if score is not None:
                    a_entry[0] += score[0]
                    a_entry[1] += score[1]
                continue
            b_entry = totals.setdefault(stb.team_b_id, [0.0, 0.0])
            a_gp, b_gp = team_board.game_points
            # The played results alone here: the adjustments are folded in
            # below and reported separately in the 299 records.
            match_points_pair = team_board.match_points_pair((a_gp, b_gp))
            assert match_points_pair is not None
            a_entry[0] += match_points_pair[0]
            a_entry[1] += a_gp
            b_entry[0] += match_points_pair[1]
            b_entry[1] += b_gp
        # Bonus / penalty points count towards the standings, and the
        # 310 record carries the standings — the 299 records emitted
        # alongside say where the difference from the played results
        # came from. Without this the totals would contradict the rank
        # written on the same line, which does include them.
        adjustments = self.tournament.point_adjustments
        for team in self.tournament.teams:
            for round_ in range(1, adjustments.bound(after_round) + 1):
                mp_adj, gp_adj = adjustments.effective(team.id, round_)
                if not mp_adj and not gp_adj:
                    continue
                entry = totals.setdefault(team.id, [0.0, 0.0])
                entry[0] += mp_adj
                entry[1] += gp_adj
        return {team_id: (mp, gp) for team_id, (mp, gp) in totals.items()}
