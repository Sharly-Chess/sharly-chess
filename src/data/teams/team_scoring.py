"""What the teams of a tournament have scored.

The standings, the per-team records the team tie-breaks read, and the
running totals a round starts from all tally the same team boards, so
they are worked out side by side, from one reading of the tournament.
"""

from dataclasses import replace
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from data.teams.team_board import TeamBoard
from data.tie_breaks import TeamTieBreak, TieBreak
from data.tie_breaks.team_records import TeamMatchRecord, TeamMatchType, TeamRecord
from data.tie_breaks.team_tie_breaks import TeamTieBreakContext
from utils.enum import Result, TeamByeType
from utils.types import TieBreakValue

if TYPE_CHECKING:
    from data.tournament import Tournament


class TeamScoring:
    """The scores of one tournament's teams, tallied from its team boards."""

    def __init__(self, tournament: 'Tournament') -> None:
        self.tournament = tournament

    def standings(self, *, after_round: int | None = None) -> list[dict[str, Any]]:
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

    def _empty_standings(self) -> dict[int, dict[str, Any]]:
        """One entry per team of the tournament, nothing scored yet."""
        tournament = self.tournament
        standings: dict[int, dict[str, Any]] = {}
        for team in tournament.event.sorted_teams:
            if team.tournament_id != tournament.id:
                continue
            standings[team.id] = {
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
        return standings

    def _tally_boards(
        self, standings: dict[int, dict[str, Any]], after_round: int | None
    ) -> None:
        """Flat fixed-table scoring (no team boards): each player's game
        points go straight into the team's total. ``team_game_points`` is
        used so the ``gp_*`` override applies to team scoring here too."""
        tournament = self.tournament
        team_game_points = tournament.team_game_points
        for board in tournament.boards_by_id.values():
            if after_round is not None and board.round > after_round:
                continue
            w_id = board.stored_board.white_player_id
            w_player = tournament.event.players_by_id.get(w_id) if w_id else None
            if w_player and w_player.team_id in standings:
                standings[w_player.team_id]['gp'] += board.white_pairing.result.points(
                    team_game_points
                )
                standings[w_player.team_id]['played'] += 1
            if board.stored_board.black_player_id is not None:
                b_player = tournament.event.players_by_id.get(
                    board.stored_board.black_player_id
                )
                if b_player and b_player.team_id in standings:
                    standings[b_player.team_id]['gp'] += (
                        board.black_pairing.result.points(team_game_points)
                    )
                    standings[b_player.team_id]['played'] += 1

    def _flat_ranking(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Flat fixed-table order: game points, then pairing number and
        name. The team tie-breaks are not computed in this mode, but every
        row still carries one zero per team tie-break so consumers that
        render a column each (ranking document / screen table) never
        index past the end."""
        tournament = self.tournament
        team_tie_breaks = [tb for tb in tournament.tie_breaks if tb.supports_team_mode]
        for row in rows:
            row['tie_break_values'] = self._wrap_tie_break_values(
                team_tie_breaks, [0.0] * len(team_tie_breaks)
            )
        rows.sort(
            key=lambda e: (
                -e['gp'],
                e['team'].pairing_number
                if e['team'].pairing_number is not None
                else float('inf'),
                e['team'].name.lower(),
            )
        )
        for rank, entry in enumerate(rows, 1):
            entry['rank'] = rank
        return rows

    def _tally_matches(
        self, standings: dict[int, dict[str, Any]], after_round: int | None
    ) -> None:
        """Score each team board through ``after_round``: byes at what
        their type is worth, matches at their effective game points."""
        tournament = self.tournament
        match_points = tournament.match_points
        win_mp = match_points.get(Result.WIN, 2.0)
        draw_mp = match_points.get(Result.DRAW, 1.0)
        loss_mp = match_points.get(Result.LOSS, 0.0)
        absent_mp = match_points.get(Result.ZERO_POINT_BYE, loss_mp)
        pab_mp = match_points.get(Result.PAIRING_ALLOCATED_BYE, win_mp)
        team_player_count = float(tournament.team_player_count or 0)
        win_gp_per_player = Result.WIN.point_value
        draw_gp_per_player = Result.DRAW.point_value
        absent_gp_per_player = tournament.team_game_points[Result.ZERO_POINT_BYE]
        excluded_team_ids = {
            team.id for team in tournament.teams if team.is_excluded_from_standings
        }
        for team_board in tournament.team_boards_by_id.values():
            if after_round is not None and team_board.round > after_round:
                continue
            stb = team_board.stored_team_board
            if stb.team_a_id in excluded_team_ids or stb.team_b_id in excluded_team_ids:
                continue
            a_gp, b_gp = team_board.game_points
            if stb.team_b_id is None:
                ent = standings.get(stb.team_a_id)
                if ent is None:
                    continue
                if (
                    stb.bye_type in (None, TeamByeType.PAB)
                    and tournament.team_bye_is_rest
                ):
                    # Round-robin rest game: not played, no points.
                    continue
                ent['played'] += 1
                # Distinguish bye types: PAB is the only one that
                # awards "as-if drew the match"; the manual byes mirror
                # individual byes scaled by team_player_count.
                match stb.bye_type:
                    case TeamByeType.ZPB:
                        ent['mp'] += absent_mp
                        # Team-level forfeit: every board counts as a
                        # forfeited game, scored at the absent-board game
                        # point value (the gp_zpb override, otherwise 0).
                        ent['gp'] += team_player_count * absent_gp_per_player
                        # An absent team is absent whether the round was
                        # paired before it went missing or not.
                        ent['forfeits'] += 1
                    case TeamByeType.HPB:
                        ent['mp'] += draw_mp
                        ent['gp'] += team_player_count * draw_gp_per_player
                        ent['draws'] += 1
                    case TeamByeType.FPB:
                        ent['mp'] += win_mp
                        ent['gp'] += team_player_count * win_gp_per_player
                        ent['wins'] += 1
                    case _:
                        # ``None`` / ``PAB`` → engine PAB.
                        ent['mp'] += pab_mp
                        ent['gp'] += tournament.team_pab_game_points
                        ent['wins'] += 1
                continue
            ent_a = standings.get(stb.team_a_id)
            ent_b = standings.get(stb.team_b_id)
            if ent_a:
                ent_a['played'] += 1
                ent_a['gp'] += a_gp
            if ent_b:
                ent_b['played'] += 1
                ent_b['gp'] += b_gp
            # Match result follows the effective game points (board + this
            # round's penalties/bonuses); the deltas are added to the totals
            # separately by _apply_point_adjustments.
            a_gp_effective, b_gp_effective = team_board.effective_game_points
            match_points_pair = team_board.match_points_pair(
                (a_gp_effective, b_gp_effective)
            )
            assert match_points_pair is not None
            a_mp, b_mp = match_points_pair
            if ent_a:
                ent_a['mp'] += a_mp
            if ent_b:
                ent_b['mp'] += b_mp
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
            if ent_a:
                ent_a[a_outcome] += 1
            if ent_b:
                ent_b[b_outcome] += 1

    def _apply_point_adjustments(
        self, standings: dict[int, dict[str, Any]], after_round: int | None
    ) -> None:
        tournament = self.tournament
        bound = tournament.point_adjustments.bound(after_round)
        for round_ in range(1, bound + 1):
            for team_id, entry in standings.items():
                mp_adj, gp_adj = tournament.point_adjustments.effective(team_id, round_)
                entry['mp'] += mp_adj
                entry['gp'] += gp_adj

    def _base_key(
        self, after_round: int | None
    ) -> Callable[[dict[str, Any]], tuple[float, ...]]:
        """What ranks ahead of the configured criteria: nothing.

        The primary score is one of them — the Points tie-break — rather
        than an implicit prefix, so that its position can be chosen
        (TRF26 record 212). The secondary score has never been implicit
        either: it is opted into with MPvGP. A tournament whose list
        holds neither ranks on its tie-breaks alone.

        A knock-out is the exception: it ranks by the round reached
        (bigger value, later exit, first), so that is the leading key."""
        tournament = self.tournament
        elimination_values: dict[int, float] = {}
        if tournament.pairing_system.eliminates_participants:
            elimination_values = tournament.knockout.team_ranking_values(
                after_round=(
                    after_round
                    if after_round is not None
                    else tournament.max_ranking_round
                )
            )

        def base_key(entry: dict[str, Any]) -> tuple[float, ...]:
            if elimination_values:
                return (-elimination_values.get(entry['team'].id, 0.0),)
            return ()

        return base_key

    def _add_tie_break_values(
        self,
        rows: list[dict[str, Any]],
        team_tie_breaks: list[TieBreak],
        base_key: Callable[[dict[str, Any]], tuple[float, ...]],
        after_round: int | None,
    ) -> None:
        """Append each team tie-break's raw value to every row, in
        tie-break order."""
        tournament = self.tournament
        for row in rows:
            row['tie_break_values'] = []
        if not team_tie_breaks:
            return
        if after_round is None:
            after_round = tournament.current_round
        records_by_id = {r.team_id: r for r in self.records(after_round=after_round)}
        context = self.tie_break_context()
        for tb in team_tie_breaks:
            if tb.display_rank_delta and isinstance(tb, TeamTieBreak):
                # Group-level resolution (EDE): cluster rows by the
                # sort key so far, then ask the tie-break to assign
                # rank-deltas within each still-tied group.
                rows.sort(
                    key=lambda e: base_key(e) + tuple(-v for v in e['tie_break_values'])
                )
                groups: list[list[dict[str, Any]]] = []
                current: list[dict[str, Any]] = []
                current_key: tuple[float, ...] | None = None
                for row in rows:
                    key = base_key(row) + tuple(-v for v in row['tie_break_values'])
                    if key != current_key:
                        if current:
                            groups.append(current)
                        current = [row]
                        current_key = key
                    else:
                        current.append(row)
                if current:
                    groups.append(current)
                tied = [
                    [
                        records_by_id[r['team'].id]
                        for r in g
                        if r['team'].id in records_by_id
                        and not r['team'].is_excluded_from_standings
                    ]
                    for g in groups
                    if len(g) > 1
                ]
                values_map: dict[int, float] = (
                    tb.compute_all_team_values(
                        tied,
                        records_by_id,
                        context,
                        after_round=after_round,
                    )
                    if tied
                    else {}
                )
                for row in rows:
                    row['tie_break_values'].append(
                        float(values_map.get(row['team'].id, 0.0))
                    )
            else:
                # Scalar tie-break — compute one value per team.
                for row in rows:
                    rec = records_by_id.get(row['team'].id)
                    if rec is None:
                        row['tie_break_values'].append(0.0)
                        continue
                    value = tb.compute_team_value(
                        rec,
                        records_by_id,
                        context,
                        after_round=after_round,
                    )
                    row['tie_break_values'].append(float(value))

    def _ranking(
        self,
        rows: list[dict[str, Any]],
        team_tie_breaks: list[TieBreak],
        base_key: Callable[[dict[str, Any]], tuple[float, ...]],
    ) -> list[dict[str, Any]]:
        """Sort the rows, number them, and wrap their tie-break values
        for display."""
        rows.sort(
            key=lambda e: (
                # Teams excluded from the standings (FIDE 6.6) rank last,
                # regardless of score, so the competitors keep a contiguous
                # ranking. They stay in the crosstable for the record.
                e['team'].is_excluded_from_standings,
                base_key(e)
                + tuple(-v for v in e['tie_break_values'])
                + (
                    e['team'].pairing_number
                    if e['team'].pairing_number is not None
                    else float('inf'),
                    e['team'].name.lower(),
                ),
            )
        )
        for rank, entry in enumerate(rows, 1):
            entry['rank'] = rank
        for row in rows:
            row['tie_break_values'] = self._wrap_tie_break_values(
                team_tie_breaks, row['tie_break_values']
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
            excluded_team_ids=frozenset(
                team.id for team in tournament.teams if team.is_excluded_from_standings
            ),
        )

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
        tournament = self.tournament
        ratings: list[int | None] = []
        for board in sorted(team_board.boards, key=lambda b: b.index):
            white_id = board.stored_board.white_player_id
            black_id = board.stored_board.black_player_id
            white_player = (
                tournament.tournament_players_by_id.get(white_id) if white_id else None
            )
            black_player = (
                tournament.tournament_players_by_id.get(black_id) if black_id else None
            )
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
        match_points = tournament.match_points
        win_mp = match_points.get(Result.WIN, 2.0)
        draw_mp = match_points.get(Result.DRAW, 1.0)
        loss_mp = match_points.get(Result.LOSS, 0.0)
        absent_mp = match_points.get(Result.ZERO_POINT_BYE, loss_mp)
        pab_mp = match_points.get(Result.PAIRING_ALLOCATED_BYE, win_mp)
        team_player_count = float(tournament.team_player_count or 0)
        absent_gp_per_player = tournament.team_game_points[Result.ZERO_POINT_BYE]

        totals_mp: dict[int, float] = {team.id: 0.0 for team in tournament.teams}
        totals_gp: dict[int, float] = {team.id: 0.0 for team in tournament.teams}
        matches_per_team: dict[int, list[TeamMatchRecord]] = {
            team.id: [] for team in tournament.teams
        }
        excluded_team_ids = {
            team.id for team in tournament.teams if team.is_excluded_from_standings
        }

        for team_board in tournament.team_boards_by_id.values():
            if team_board.round > after_round:
                continue
            stb = team_board.stored_team_board
            a_id = stb.team_a_id
            b_id = stb.team_b_id
            if a_id in excluded_team_ids or b_id in excluded_team_ids:
                continue
            a_gp, b_gp = team_board.game_points
            a_boards = self._board_scores_for(team_board, a_id)
            a_ratings = self._board_ratings_for(team_board, a_id)
            if b_id is None:
                if (
                    stb.bye_type in (None, TeamByeType.PAB)
                    and tournament.team_bye_is_rest
                ):
                    # Round-robin rest game: not a match — no record,
                    # no points, invisible to the tie-breaks.
                    continue
                # A PAB team still participates (it's present, just unpaired),
                # so OWN-ELO should reflect its strength. The bye envelope has
                # no boards, so take the round's lineup players' ratings.
                bye_team = tournament.event.teams_by_id.get(a_id)
                pab_ratings: tuple[int | None, ...]
                if bye_team is None:
                    pab_ratings = a_ratings
                else:
                    rating_list: list[int | None] = []
                    for player in bye_team.effective_round_slots(team_board.round):
                        tp = (
                            tournament.tournament_players_by_id.get(player.id)
                            if player is not None
                            else None
                        )
                        rating_list.append(tp.rating if tp and tp.rating else None)
                    pab_ratings = tuple(rating_list)
                # The bye types score as they do in the standings; the
                # match type is what Art. 16 reads to decide whether the
                # round was given up voluntarily.
                match stb.bye_type:
                    case TeamByeType.ZPB:
                        own_mp = absent_mp
                        own_gp = team_player_count * absent_gp_per_player
                        match_type = TeamMatchType.ZPB
                    case TeamByeType.HPB:
                        own_mp = draw_mp
                        own_gp = team_player_count * Result.DRAW.point_value
                        match_type = TeamMatchType.HPB
                    case TeamByeType.FPB:
                        own_mp = win_mp
                        own_gp = team_player_count * Result.WIN.point_value
                        # A full-point bye is awarded, not given up.
                        match_type = TeamMatchType.PAB
                    case _:
                        own_mp = pab_mp
                        own_gp = tournament.team_pab_game_points
                        match_type = TeamMatchType.PAB
                matches_per_team[a_id].append(
                    TeamMatchRecord(
                        round_=team_board.round,
                        opponent_id=None,
                        own_mp=own_mp,
                        own_gp=own_gp,
                        match_type=match_type,
                        board_scores=a_boards,
                        board_ratings=pab_ratings,
                    )
                )
                totals_mp[a_id] += own_mp
                totals_gp[a_id] += own_gp
                continue
            # Match result follows the effective game points (board + this
            # round's penalties/bonuses); the deltas are added to own_gp /
            # totals by the loop below — here they only tip the comparison.
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
            b_boards = self._board_scores_for(team_board, b_id)
            b_ratings = self._board_ratings_for(team_board, b_id)
            matches_per_team[a_id].append(
                TeamMatchRecord(
                    round_=team_board.round,
                    opponent_id=b_id,
                    own_mp=a_mp,
                    own_gp=a_gp,
                    match_type=a_type,
                    board_scores=a_boards,
                    board_ratings=a_ratings,
                )
            )
            matches_per_team[b_id].append(
                TeamMatchRecord(
                    round_=team_board.round,
                    opponent_id=a_id,
                    own_mp=b_mp,
                    own_gp=b_gp,
                    match_type=b_type,
                    board_scores=b_boards,
                    board_ratings=b_ratings,
                )
            )
            totals_mp[a_id] += a_mp
            totals_gp[a_id] += a_gp
            totals_mp[b_id] += b_mp
            totals_gp[b_id] += b_gp

        # Fold bonus/penalty points into totals (used by total-based
        # tie-breaks and the secondary score) and into each round's match
        # record (so MP/GP-sum tie-breaks like points-for / differential
        # see them; board- and rating-based tie-breaks read board data and
        # are unaffected).

        adjustment_bound = tournament.point_adjustments.bound(after_round)
        for team in tournament.teams:
            for round_ in range(1, adjustment_bound + 1):
                mp_adj, gp_adj = tournament.point_adjustments.effective(team.id, round_)
                if not mp_adj and not gp_adj:
                    continue
                totals_mp[team.id] += mp_adj
                totals_gp[team.id] += gp_adj
                team_matches = matches_per_team[team.id]
                for index, match in enumerate(team_matches):
                    if match.round_ == round_:
                        team_matches[index] = replace(
                            match,
                            own_mp=match.own_mp + mp_adj,
                            own_gp=match.own_gp + gp_adj,
                        )
                        break

        return [
            TeamRecord(
                team_id=team.id,
                name=team.name,
                total_mp=totals_mp[team.id],
                total_gp=totals_gp[team.id],
                matches=sorted(matches_per_team[team.id], key=lambda m: m.round_),
                pairing_number=team.pairing_number,
            )
            for team in tournament.teams
        ]

    def totals_after(self, after_round: int) -> dict[int, tuple[float, float]]:
        """Per-team ``(match_points, game_points)`` cumulative through
        ``after_round``, bonus / penalty points included. Returned dict
        is keyed by ``team.id``; teams with no team_board entries simply
        get ``(0.0, 0.0)``. PAB (team-level bye) awards the configured
        PAB match points and the tournament's PAB game points (default
        behaviour mirrors :meth:`standings`)."""
        tournament = self.tournament
        match_points = tournament.match_points
        win_mp = match_points.get(Result.WIN, 2.0)
        draw_mp = match_points.get(Result.DRAW, 1.0)
        loss_mp = match_points.get(Result.LOSS, 0.0)
        absent_mp = match_points.get(Result.ZERO_POINT_BYE, loss_mp)
        pab_mp = match_points.get(Result.PAIRING_ALLOCATED_BYE, draw_mp)
        team_player_count = float(tournament.team_player_count or 0)
        win_gp_per_player = Result.WIN.point_value
        draw_gp_per_player = Result.DRAW.point_value
        totals: dict[int, list[float]] = {}
        for team_board in tournament.team_boards_by_id.values():
            if team_board.round > after_round:
                continue
            stb = team_board.stored_team_board
            a_gp, b_gp = team_board.game_points
            a_entry = totals.setdefault(stb.team_a_id, [0.0, 0.0])
            if stb.team_b_id is None:
                match stb.bye_type:
                    case TeamByeType.ZPB:
                        a_entry[0] += absent_mp
                    case TeamByeType.HPB:
                        a_entry[0] += draw_mp
                        a_entry[1] += team_player_count * draw_gp_per_player
                    case TeamByeType.FPB:
                        a_entry[0] += win_mp
                        a_entry[1] += team_player_count * win_gp_per_player
                    case _ if tournament.team_bye_is_rest:
                        # Round-robin rest game: no points.
                        pass
                    case _:
                        a_entry[0] += pab_mp
                        a_entry[1] += tournament.team_pab_game_points
                continue
            b_entry = totals.setdefault(stb.team_b_id, [0.0, 0.0])
            a_entry[1] += a_gp
            b_entry[1] += b_gp
            # The played results alone here: the adjustments are folded in
            # below and reported separately in the 299 records.
            match_points_pair = team_board.match_points_pair((a_gp, b_gp))
            assert match_points_pair is not None
            a_entry[0] += match_points_pair[0]
            b_entry[0] += match_points_pair[1]
        # Bonus / penalty points count towards the standings, and the
        # 310 record carries the standings — the 299 records emitted
        # alongside say where the difference from the played results
        # came from. Without this the totals would contradict the rank
        # written on the same line, which does include them.
        for team in tournament.teams:
            for round_ in range(1, tournament.point_adjustments.bound(after_round) + 1):
                mp_adj, gp_adj = tournament.point_adjustments.effective(team.id, round_)
                if not mp_adj and not gp_adj:
                    continue
                entry = totals.setdefault(team.id, [0.0, 0.0])
                entry[0] += mp_adj
                entry[1] += gp_adj
        return {team_id: (mp, gp) for team_id, (mp, gp) in totals.items()}
