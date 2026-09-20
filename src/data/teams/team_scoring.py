"""What the teams of a tournament have scored.

The standings, the per-team records the team tie-breaks read, and the
running totals a round starts from all tally the same team boards, so
they are worked out side by side, from one reading of what a bye and a
match are worth.
"""

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from data.teams.team_board import TeamBoard
from data.tie_breaks import TeamTieBreak, TieBreak
from data.tie_breaks.team_records import TeamMatchRecord, TeamMatchType, TeamRecord
from data.tie_breaks.team_tie_breaks import TeamTieBreakContext
from utils.enum import Result, TeamByeType
from utils.types import TieBreakValue

if TYPE_CHECKING:
    from data.tournament import Tournament

Row = dict[str, Any]
RankKey = Callable[[Row], tuple[float, ...]]

# What a bye counts as in the standings' tally of a team's rounds. A
# pairing-allocated bye is awarded, so it is a win, as is a full-point
# bye; a zero-point bye is the round the team was absent for.
_BYE_OUTCOME: dict[str, str] = {
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

    def _bye_score(self, bye_type: str | None) -> tuple[float, float] | None:
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

    def _excluded_team_ids(self) -> set[int]:
        return {
            team.id for team in self.tournament.teams if team.is_excluded_from_standings
        }

    # -------------------------------------------------------------------------
    # Standings
    # -------------------------------------------------------------------------

    def standings(self, *, after_round: int | None = None) -> list[Row]:
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
        if not tournament.team_boards_by_id:
            self._tally_boards(standings, after_round)
            self._apply_point_adjustments(standings, after_round)
            return self._flat_ranking(list(standings.values()))
        self._tally_matches(standings, after_round)
        self._apply_point_adjustments(standings, after_round)
        rows = list(standings.values())
        base_key = self._base_key(after_round)
        team_tie_breaks = [tb for tb in tournament.tie_breaks if tb.supports_team_mode]
        self._add_tie_break_values(rows, team_tie_breaks, base_key, after_round)
        return self._ranking(rows, team_tie_breaks, base_key)

    def _empty_standings(self) -> dict[int, Row]:
        """One entry per team of the tournament, nothing scored yet."""
        tournament = self.tournament
        return {
            team.id: {
                'team': team,
                'mp': 0.0,
                'gp': 0.0,
                'played': 0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                # A round the team was absent for counts here rather than
                # as a loss, so a loss is one taken over the board — a
                # match it forfeited outright, and a round it was left
                # unpaired as absent for.
                'forfeits': 0,
            }
            for team in tournament.event.sorted_teams
            if team.tournament_id == tournament.id
        }

    def _tally_boards(self, standings: dict[int, Row], after_round: int | None) -> None:
        """Flat fixed-table scoring (no team boards): each player's game
        points go straight into the team's total. ``team_game_points`` is
        used so the ``gp_*`` override applies to team scoring here too."""
        tournament = self.tournament
        team_game_points = tournament.team_game_points
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
                entry['gp'] += pairing.result.points(team_game_points)
                entry['played'] += 1

    def _flat_ranking(self, rows: list[Row]) -> list[Row]:
        """Flat fixed-table order: game points, then pairing number and
        name. The team tie-breaks are not computed in this mode, but every
        row still carries one zero per team tie-break so consumers that
        render a column each (ranking document / screen table) never
        index past the end."""
        team_tie_breaks = [
            tb for tb in self.tournament.tie_breaks if tb.supports_team_mode
        ]
        for row in rows:
            row['tie_break_values'] = self._wrap_tie_break_values(
                team_tie_breaks, [0.0] * len(team_tie_breaks)
            )
        rows.sort(key=lambda row: (-row['gp'], *self._team_order(row)))
        for rank, row in enumerate(rows, 1):
            row['rank'] = rank
        return rows

    def _tally_matches(
        self, standings: dict[int, Row], after_round: int | None
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
                score = self._bye_score(stb.bye_type)
                if entry is None or score is None:
                    continue
                mp, gp = score
                entry['played'] += 1
                entry['mp'] += mp
                entry['gp'] += gp
                entry[_BYE_OUTCOME.get(stb.bye_type or '', 'wins')] += 1
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
            if a_gp_effective > b_gp_effective:
                a_outcome, b_outcome = 'wins', 'losses'
            elif a_gp_effective < b_gp_effective:
                a_outcome, b_outcome = 'losses', 'wins'
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
                if entry is None:
                    continue
                entry['played'] += 1
                entry['mp'] += mp
                entry['gp'] += gp
                entry[outcome] += 1

    def _apply_point_adjustments(
        self, standings: dict[int, Row], after_round: int | None
    ) -> None:
        adjustments = self.tournament.point_adjustments
        for round_ in range(1, adjustments.bound(after_round) + 1):
            for team_id, entry in standings.items():
                mp_adj, gp_adj = adjustments.effective(team_id, round_)
                entry['mp'] += mp_adj
                entry['gp'] += gp_adj

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
        return lambda row: (-elimination_values.get(row['team'].id, 0.0),)

    def _add_tie_break_values(
        self,
        rows: list[Row],
        team_tie_breaks: list[TieBreak],
        base_key: RankKey,
        after_round: int | None,
    ) -> None:
        """Append each team tie-break's raw value to every row, in
        tie-break order."""
        for row in rows:
            row['tie_break_values'] = []
        if not team_tie_breaks:
            return
        if after_round is None:
            after_round = self.tournament.current_round
        records_by_id = {r.team_id: r for r in self.records(after_round=after_round)}
        context = self.tie_break_context()

        def key_so_far(row: Row) -> tuple[float, ...]:
            return base_key(row) + tuple(-v for v in row['tie_break_values'])

        for tb in team_tie_breaks:
            if tb.display_rank_delta and isinstance(tb, TeamTieBreak):
                # Group-level resolution (EDE): cluster rows by the
                # sort key so far, then ask the tie-break to assign
                # rank-deltas within each still-tied group.
                rows.sort(key=key_so_far)
                groups: list[list[Row]] = []
                current_key: tuple[float, ...] | None = None
                for row in rows:
                    key = key_so_far(row)
                    if key != current_key:
                        groups.append([])
                        current_key = key
                    groups[-1].append(row)
                tied = [
                    [
                        records_by_id[row['team'].id]
                        for row in group
                        if row['team'].id in records_by_id
                        and not row['team'].is_excluded_from_standings
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
                    row['tie_break_values'].append(
                        float(values_map.get(row['team'].id, 0.0))
                    )
                continue
            # Scalar tie-break — compute one value per team.
            for row in rows:
                record = records_by_id.get(row['team'].id)
                value = (
                    tb.compute_team_value(
                        record, records_by_id, context, after_round=after_round
                    )
                    if record is not None
                    else 0.0
                )
                row['tie_break_values'].append(float(value))

    def _ranking(
        self, rows: list[Row], team_tie_breaks: list[TieBreak], base_key: RankKey
    ) -> list[Row]:
        """Sort the rows, number them, and wrap their tie-break values
        for display."""
        rows.sort(
            key=lambda row: (
                # Teams excluded from the standings (FIDE 6.6) rank last,
                # regardless of score, so the competitors keep a contiguous
                # ranking. They stay in the crosstable for the record.
                row['team'].is_excluded_from_standings,
                base_key(row)
                + tuple(-v for v in row['tie_break_values'])
                + self._team_order(row),
            )
        )
        for rank, row in enumerate(rows, 1):
            row['rank'] = rank
        for row in rows:
            row['tie_break_values'] = self._wrap_tie_break_values(
                team_tie_breaks, row['tie_break_values']
            )
        return rows

    @staticmethod
    def _team_order(row: Row) -> tuple[float, str]:
        """The order of teams nothing else separates: pairing number,
        then name."""
        team = row['team']
        return (
            team.pairing_number if team.pairing_number is not None else float('inf'),
            team.name.lower(),
        )

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
        forfeit rather than over the board."""
        tournament = self.tournament
        if after_round is None:
            after_round = tournament.current_round
        matches_per_team: dict[int, list[TeamMatchRecord]] = {
            team.id: [] for team in tournament.teams
        }
        totals: dict[int, list[float]] = {
            team.id: [0.0, 0.0] for team in tournament.teams
        }
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
                totals[team_id][0] += record.own_mp
                totals[team_id][1] += record.own_gp
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

    def _bye_record(self, team_board: TeamBoard) -> TeamMatchRecord | None:
        """The record of a bye, or ``None`` for a rest game, which is not
        a match: no record, no points, invisible to the tie-breaks."""
        stb = team_board.stored_team_board
        score = self._bye_score(stb.bye_type)
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
        # A team is forfeit whether it fielded nobody or every one of
        # its players lost by forfeit: either way no game was played
        # on its side, and the round is not a played one for either
        # team.
        a_type = b_type = TeamMatchType.PLAYED
        if team_board.team_all_forfeit(a_id):
            a_type, b_type = TeamMatchType.FORFEIT_LOSS, TeamMatchType.FORFEIT_WIN
        if team_board.team_all_forfeit(b_id):
            b_type = TeamMatchType.FORFEIT_LOSS
            if a_type != TeamMatchType.FORFEIT_LOSS:
                a_type = TeamMatchType.FORFEIT_WIN
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
                score = self._bye_score(stb.bye_type)
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
