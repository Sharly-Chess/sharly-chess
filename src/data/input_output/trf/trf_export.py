"""The TRF26 records of a tournament.

Everything here reads the tournament and writes nothing back: the
export is a view of the standings, the pairings and the settings at a
given round, in the form bbpPairings and the federations' tools read.
"""

from collections import defaultdict
from typing import TYPE_CHECKING

from data.input_output.trf.trf_data import (
    TRF_DATE_FORMAT,
    TrfAbnormalPointsAssignment,
    TrfAcceleratedRound,
    TrfOOdOTeamPairing,
    TrfProhibitedPairing,
    TrfRoundBye,
    TrfTeam,
    TrfTeamForfeitedMatch,
    TrfTeamPABs,
    TrfTournament,
)
from data.input_output.trf.trf_mappers import TrfPointSystemResult
from data.pairings.engines import _team_ui_sort_key
from data.pairings.settings import ColorSeedSetting
from data.player import TournamentPlayer
from utils.enum import (
    BoardColor,
    PlayerRatingType,
    Result,
    ScoreType,
    TeamByeType,
    TeamColourType,
)

if TYPE_CHECKING:
    from data.tournament import Tournament


class TrfExport:
    """Builds the TRF of one tournament, as it stands after a round."""

    def __init__(self, tournament: 'Tournament') -> None:
        self.tournament = tournament

    def build(
        self,
        after_round: int | None = None,
        next_round_pairings_as_zpb: bool = False,
        prohibited_pairing_override: list[TrfProhibitedPairing] | None = None,
    ) -> TrfTournament:
        tournament = self.tournament
        if after_round is None:
            after_round = tournament.rounds
        tournament.compute_tournament_player_ranks(after_round=after_round)
        seed_setting = ColorSeedSetting()
        trf = TrfTournament(
            name=tournament.name,
            city=tournament.location or '',
            federation=tournament.event.federation,
            start_date=tournament.start_date.strftime(TRF_DATE_FORMAT),
            end_date=tournament.stop_date.strftime(TRF_DATE_FORMAT),
            num_players=len(tournament.tournament_players_by_id),
            num_rated_players=sum(
                bool(player.fide_rating_value) for player in tournament.players
            ),
            chief_arbiter=getattr(tournament.chief_arbiter, 'fide_arbiter_str', ''),
            deputy_arbiters=[
                arbiter.fide_arbiter_str for arbiter in tournament.deputy_arbiters
            ],
            round_dates=[
                dt.strftime('%y/%m/%d') if dt else ''
                for idx in range(1, after_round + 1)
                for dt in [tournament.round_datetimes.get(idx)]
            ],
            num_rounds=tournament.rounds,
            initial_color=seed_setting.get_value(tournament).value,
            individuals_point_system=self._individuals_point_system(),
            starting_rank_method=self._starting_rank_method(),
            starting_rank_federation=tournament.event.federation or '',
            pairing_controller_id='Sharly Chess',
            encoded_type=tournament.pairing_variation.trf_encoded_type,
            # Record 212 is the ordered list of criteria that define the
            # standings, PTS included — no longer prefixed here, since the
            # Points tie-break carries its own place in the list.
            standings_tie_breaks=[
                tie_break.trf_acronym for tie_break in tournament.tie_breaks
            ],
            time_control=tournament.time_control_trf25 or '',
            players=[
                player.to_trf(after_round, next_round_pairings_as_zpb)
                for player in tournament.tournament_players_by_pairing_number.values()
            ],
            accelerated_rounds=self.accelerated_rounds(),
            round_byes=self._round_byes(),
        )
        if tournament.is_team_tournament:
            self._populate_team(
                trf,
                after_round=after_round,
                next_round_pairings_as_zpb=next_round_pairings_as_zpb,
            )
        else:
            trf.abnormal_points_assignments = (
                self._individual_abnormal_points_assignments(after_round)
            )
        trf.prohibited_pairings = (
            prohibited_pairing_override
            if prohibited_pairing_override is not None
            else self._prohibited_pairings()
        )
        return trf

    def _prohibited_pairings(self) -> list[TrfProhibitedPairing]:
        """TRF26 260 records regenerated from the per-round snapshots: the
        frozen hard/soft groups plus the round's ``protect_rank`` reproduce
        the *exact* effective set bbpPairings enforced (hard groups kept
        whole, soft groups relaxed at the stored cutoff) — so the export is
        the truth, not the configured-before-relaxation set. Snapshots with
        no cutoff (a hard-only round, or an imported 260 set) emit every
        group whole."""
        tournament = self.tournament
        result: list[TrfProhibitedPairing] = []
        groups_by_round: dict[int, list] = {}
        protect_by_round: dict[int, int] = {}
        for group in tournament.stored_tournament.stored_prohibited_pairing_groups:
            if group.round_ is None:
                continue
            groups_by_round.setdefault(group.round_, []).append(group)
            if group.protect_rank is not None:
                protect_by_round[group.round_] = group.protect_rank
        for round_ in sorted(groups_by_round):
            groups = groups_by_round[round_]
            protect_rank = protect_by_round.get(round_)
            if protect_rank is None:
                # No relaxation recorded — every stored group is enforced
                # whole (hard-only round, or an imported 260 set).
                whole = [list(group.member_ids) for group in groups]
                result.extend(
                    tournament.prohibited_pairings.applied_lines(
                        whole, [], 0, {}, round_
                    )
                )
                continue
            hard_groups = [list(g.member_ids) for g in groups if g.is_hard]
            soft_groups = [list(g.member_ids) for g in groups if not g.is_hard]
            rank_by_member = tournament.prohibited_pairings.member_weakness_ranks(
                after_round=round_ - 1
            )
            result.extend(
                tournament.prohibited_pairings.applied_lines(
                    hard_groups, soft_groups, protect_rank, rank_by_member, round_
                )
            )
        return result

    def _populate_team(
        self,
        trf: TrfTournament,
        *,
        after_round: int,
        next_round_pairings_as_zpb: bool = False,
    ) -> None:
        """TRF26 team-mode records (310 rosters, 192 team code, 362
        match-point system, 352 board-colour sequence). Built on top
        of the individual TRF (001 player rows + 162 game points)
        produced by :meth:`build` — bbpPairings' ``--team`` mode
        aggregates the per-player games into team match data."""
        tournament = self.tournament
        match_points = tournament.match_points
        trf.teams_point_system = {
            'TW': float(match_points.get(Result.WIN, 2.0)),
            'TD': float(match_points.get(Result.DRAW, 1.0)),
            'TL': float(match_points.get(Result.LOSS, 0.0)),
        }
        tpn_map = self._team_tpn_map()
        trf.team_pabs = self._team_pabs_record(
            after_round=after_round, tpn_by_team_id=tpn_map
        )
        trf.oodo_team_pairings = self._team_oodo_records(
            after_round=after_round, tpn_by_team_id=tpn_map
        )
        (
            trf.informative_team_pairings_records,
            trf.informative_team_results_records,
        ) = self._team_informative_records(
            after_round=after_round, tpn_by_team_id=tpn_map
        )

        team_player_count = tournament.team_player_count or 0
        pattern = tournament.color_pattern or ''
        if not pattern and team_player_count:
            pattern = ''.join(
                BoardColor.WHITE.value if i % 2 == 0 else BoardColor.BLACK.value
                for i in range(team_player_count)
            )
        trf.board_color_sequence = pattern

        # 240 records in team mode are interpreted by bbpPairings as
        # *team* byes — its team-TRF reader strips them from the
        # member stream and uses the TPN values (not player numbers).
        # We therefore overwrite whatever individual-bye 240s were
        # populated by :meth:`build` and emit only team byes for the
        # round being paired.
        trf.round_byes = self._team_round_byes(
            after_round=after_round,
            tpn_by_team_id=tpn_map,
            next_round_pairings_as_zpb=next_round_pairings_as_zpb,
        )
        trf.team_forfeited_matches = self._team_forfeited_matches(
            after_round=after_round, tpn_by_team_id=tpn_map
        )

        teams = sorted(tournament.teams, key=_team_ui_sort_key)
        tpn_by_team_id = tpn_map
        tp_by_player_id = {tp.id: tp for tp in tournament.tournament_players}
        team_totals = tournament.team_totals_after(after_round)
        # Team rank from the tournament's own standings — primary
        # score + secondary + (eventually) team tie-breaks. Falls back
        # to the team-UI order for teams ``team_standings`` doesn't
        # return.
        rank_by_team_id: dict[int, int] = {}
        # Rank must match ``team_totals`` (bounded to ``after_round``) —
        # otherwise the in-progress round leaks into the TRF rank fed to
        # bbpPairings (e.g. during complementary pairing).
        for row in tournament.team_standings(after_round=after_round):
            rank_by_team_id[row['team'].id] = row['rank']
        nickname_by_team_id = self._team_nickname_map(tpn_by_team_id)
        trf_teams: list[TrfTeam] = []
        for team in teams:
            tpn = tpn_by_team_id[team.id]
            # 310 lists the whole roster: the round's board order first
            # (capped at the board count), then the remaining roster
            # members as substitutes, so a never-fielded player still
            # round-trips through the team record on re-import.
            lineup = team.effective_round_lineup(after_round + 1)[:team_player_count]
            ordered_members = list(lineup)
            seen_ids = {member.id for member in lineup}
            for member in team.players:
                if member.id not in seen_ids:
                    ordered_members.append(member)
                    seen_ids.add(member.id)
            player_ids: list[int] = []
            for member in ordered_members:
                tp = tp_by_player_id.get(member.id)
                if tp is None or tp.pairing_number is None:
                    continue
                player_ids.append(tp.pairing_number)
            mp, gp = team_totals.get(team.id, (0.0, 0.0))
            trf_teams.append(
                TrfTeam(
                    id=tpn,
                    name=team.name[:32],
                    nickname=nickname_by_team_id[team.id],
                    match_points=mp,
                    game_points=gp,
                    rank=rank_by_team_id.get(team.id),
                    player_ids=player_ids,
                )
            )
        trf_teams.sort(key=lambda t: t.id)
        trf.teams = trf_teams
        trf.num_teams = len(trf_teams)
        # Only the team-Swiss system gets the score/colour-derived FIDE
        # team-Swiss code; round-robin, two-game-match and flat fixed-table
        # systems keep their own variation code (set from
        # ``pairing_variation.trf_encoded_type`` when the TRF was built).
        if tournament.pairing_system.fide_team_swiss_code:
            trf.encoded_type = self._team_encoded_type()
        trf.abnormal_points_assignments = self._team_abnormal_points_assignments(
            after_round=after_round, tpn_by_team_id=tpn_map
        )

    def _individual_abnormal_points_assignments(
        self, after_round: int
    ) -> list[TrfAbnormalPointsAssignment]:
        """TRF26 299 records for an individual tournament: one blank-type
        line per (player, round) carrying a bonus / penalty, keyed on the
        pairing number. Only the game-points field applies — 8-11 is for
        teams — and the 001 points already include the delta, which is
        what a reader recomputing the score from the results expects."""
        tournament = self.tournament
        assignments: list[TrfAbnormalPointsAssignment] = []
        for player in tournament.tournament_players_by_pairing_number.values():
            if player.pairing_number is None:
                continue
            for round_ in range(1, after_round + 1):
                delta = tournament.player_point_adjustment(player.id, round_)
                if not delta:
                    continue
                assignments.append(
                    TrfAbnormalPointsAssignment(
                        type=' ',
                        match_points=None,
                        game_points=delta,
                        round=round_,
                        pairing_numbers=[player.pairing_number],
                    )
                )
        return assignments

    def _team_abnormal_points_assignments(
        self, *, after_round: int, tpn_by_team_id: dict[int, int]
    ) -> list[TrfAbnormalPointsAssignment]:
        """TRF26 299 records — the team bonus / penalty points actually
        applied, one line per (team, round) carrying a non-zero
        effective (MP, GP) delta (manual entry + rule-set). The single
        pairing number is the team's TPN. On import the value is stored
        as a manual adjustment (the rule set isn't carried by the TRF,
        so nothing re-derives the automatic part)."""
        tournament = self.tournament
        assignments: list[TrfAbnormalPointsAssignment] = []
        for team in tournament.teams:
            tpn = tpn_by_team_id.get(team.id)
            if tpn is None:
                continue
            for round_ in range(1, after_round + 1):
                mp, gp = tournament.effective_point_adjustment(team.id, round_)
                if not mp and not gp:
                    continue
                assignments.append(
                    TrfAbnormalPointsAssignment(
                        type=' ',
                        match_points=mp,
                        game_points=gp,
                        round=round_,
                        pairing_numbers=[tpn],
                    )
                )
        return assignments

    def _starting_rank_method(self) -> str:
        """TRF26 172 — how the participants were ranked. Derived from the
        ratings actually used rather than from the tournament setting:
        the setting only states a preference, and which fallback fired
        is what the receiver needs in order to reproduce the ranking.

        Estimated ratings (and the floors a rule set may supply) have no
        place in the format, so a tournament that used any of them is
        ranked by a method the TRF cannot express — which is what
        ``OTHER`` is for."""
        tournament = self.tournament
        used = {player.rating_type for player in tournament.players}
        if not used:
            # Nothing to describe yet; state the preference.
            return (
                'FIDE'
                if tournament.player_rating_type == PlayerRatingType.FIDE
                else 'NRO'
            )
        if PlayerRatingType.ESTIMATED in used:
            return 'OTHER'
        if used == {PlayerRatingType.FIDE}:
            return 'FIDE'
        if used == {PlayerRatingType.NATIONAL}:
            return 'NRO'
        # Both were used, so a fallback fired: say which way round.
        return (
            'FIDON'
            if tournament.player_rating_type == PlayerRatingType.FIDE
            else 'NIDOF'
        )

    def _individuals_point_system(self) -> dict[str, float]:
        """TRF26 162 record — game-point values per result symbol.
        Only emits values that have been overridden vs the FIDE
        defaults; readers fall back to W=1 / D=0.5 / L=0 / ZPB=LOSS /
        PAB=WIN when a symbol is absent. bbpPairings ``--team``
        accepts the full W / D / L / A (ZPB) / P (PAB) alphabet."""
        tournament = self.tournament
        raw = tournament.stored_tournament.game_points or {}
        result: dict[str, float] = {}
        for outcome_value, value in raw.items():
            try:
                outcome = Result(outcome_value)
            except ValueError:
                continue
            symbol = TrfPointSystemResult.get_outer_value(outcome) or ''
            if not symbol:
                continue
            result[symbol] = float(value)
        return result

    def _team_oodo_records(
        self,
        *,
        after_round: int,
        tpn_by_team_id: dict[int, int],
    ) -> list[TrfOOdOTeamPairing]:
        """TRF26 300 records — per-round team lineups in board order.
        Emitted twice per real (non-PAB) team match: once from team_a's
        view, once from team_b's. Carries the historical lineup so a
        re-import can recover round-by-round board ordering when it
        differs from the current 310 roster."""
        tournament = self.tournament
        team_player_count = tournament.team_player_count or 0
        team_id_by_player_id = {
            tp.id: tp.team_id
            for tp in tournament.tournament_players
            if tp.team_id is not None
        }
        records: list[TrfOOdOTeamPairing] = []
        team_boards = sorted(
            (
                tb
                for tb in tournament.team_boards_by_id.values()
                if 1 <= tb.round <= after_round
                and tb.stored_team_board.team_b_id is not None
            ),
            key=lambda tb: (tb.round, tb.index or 0),
        )
        for tb in team_boards:
            stb = tb.stored_team_board
            a_tpn = tpn_by_team_id.get(stb.team_a_id)
            b_tpn = (
                tpn_by_team_id.get(stb.team_b_id) if stb.team_b_id is not None else None
            )
            if a_tpn is None or b_tpn is None:
                continue
            a_lineup: list[int | None] = [None] * team_player_count
            b_lineup: list[int | None] = [None] * team_player_count
            for board in tb.boards:
                slot = board.index
                if slot < 0 or slot >= team_player_count:
                    continue
                white_tp = board.optional_white_tournament_player
                black_tp = board.black_tournament_player
                for tp in (white_tp, black_tp):
                    if tp is None or tp.pairing_number is None:
                        continue
                    team_id = team_id_by_player_id.get(tp.id)
                    if team_id == stb.team_a_id:
                        a_lineup[slot] = tp.pairing_number
                    elif team_id == stb.team_b_id:
                        b_lineup[slot] = tp.pairing_number
            records.append(
                TrfOOdOTeamPairing(
                    round=tb.round,
                    team_id=a_tpn,
                    opponent_team_id=b_tpn,
                    boards=a_lineup,
                )
            )
            records.append(
                TrfOOdOTeamPairing(
                    round=tb.round,
                    team_id=b_tpn,
                    opponent_team_id=a_tpn,
                    boards=b_lineup,
                )
            )
        return records

    def _team_informative_records(
        self,
        *,
        after_round: int,
        tpn_by_team_id: dict[int, int],
    ) -> tuple[list[str], list[str]]:
        """TRF26 801 (team pairings) and 802 (team results) — one row
        per team summarising every played round. Both are informative
        records; the spec says they "duplicate some information that
        already exists" but recommends emitting them for human
        readability. Export-only — the importer ignores these fields.

        801 per-round block: ``<opp_tpn> <colour> <board-results>
        <team-RID-string>`` where each RID is the player's position on
        the 310 roster (1-9, then A-Z for 10-35, then ``*``).

        802 per-round block: ``<opp_tpn|bye> <colour> <GP> <forfeit>``
        with fixed widths (opp/bye = 3 chars, GP = 4 chars "11.5"
        format)."""
        tournament = self.tournament

        def _rid_char(position_1based: int) -> str:
            """Encode a roster position as a single character per the
            spec's VNC scheme: 1-9 → '1'-'9', 10-35 → 'A'-'Z', 36+ →
            '*'."""
            if 1 <= position_1based <= 9:
                return str(position_1based)
            if 10 <= position_1based <= 35:
                return chr(ord('A') + position_1based - 10)
            return '*'

        pairings: list[str] = []
        results: list[str] = []
        team_player_count = tournament.team_player_count or 0
        teams_by_tpn = sorted(
            (
                (tpn_by_team_id[team.id], team)
                for team in tournament.teams
                if team.id in tpn_by_team_id
            ),
            key=lambda item: item[0],
        )

        # Pre-compute each player's RID character (position on their
        # team's 310 roster + 1 → spec-encoded char).
        rid_by_player_id: dict[int, str] = {}
        for tp in tournament.tournament_players:
            if tp.team_index is None:
                continue
            rid_by_player_id[tp.id] = _rid_char(tp.team_index + 1)

        # Round → team_id → (opp_tpn, colour, board_results, rid_string,
        # match_gp, is_forfeit, bye_acronym_or_none).
        per_round: dict[
            int,
            dict[
                int,
                tuple[int | None, str, str, str, float, bool, str | None],
            ],
        ] = {}
        for team_board in tournament.team_boards_by_id.values():
            if not (1 <= team_board.round <= after_round):
                continue
            stb = team_board.stored_team_board
            round_data = per_round.setdefault(team_board.round, {})
            a_gp, b_gp = team_board.game_points
            if stb.team_b_id is None:
                # Team-level PAB.
                round_data[stb.team_a_id] = (
                    None,
                    ' ',
                    ' ' * team_player_count,
                    ' ' * team_player_count,
                    tournament.team_pab_game_points,
                    False,
                    TeamByeType.PAB,
                )
                continue

            symbols_a: list[str] = []
            symbols_b: list[str] = []
            rid_a: list[str] = []
            rid_b: list[str] = []
            for board in sorted(team_board.boards, key=lambda b: b.index):
                white_tp = board.optional_white_tournament_player
                black_tp = board.black_tournament_player
                wtp_team = white_tp.team_id if white_tp is not None else None
                a_player: TournamentPlayer | None
                b_player: TournamentPlayer | None
                if wtp_team == stb.team_a_id:
                    a_player, b_player = white_tp, black_tp
                else:
                    a_player, b_player = black_tp, white_tp
                rid_a.append(
                    rid_by_player_id.get(a_player.id, ' ')
                    if a_player is not None
                    else ' '
                )
                rid_b.append(
                    rid_by_player_id.get(b_player.id, ' ')
                    if b_player is not None
                    else ' '
                )
                result = board.result
                a_is_white = (
                    a_player is not None
                    and white_tp is not None
                    and white_tp.id == a_player.id
                )
                if result == Result.WIN:
                    a_sym, b_sym = ('1', '0') if a_is_white else ('0', '1')
                elif result == Result.LOSS:
                    a_sym, b_sym = ('0', '1') if a_is_white else ('1', '0')
                elif result == Result.DRAW:
                    a_sym, b_sym = '=', '='
                else:
                    a_sym, b_sym = ' ', ' '
                symbols_a.append(a_sym)
                symbols_b.append(b_sym)
            # Pad to team_player_count.
            while len(symbols_a) < team_player_count:
                symbols_a.append(' ')
                symbols_b.append(' ')
                rid_a.append(' ')
                rid_b.append(' ')
            # Colour of team_a on board 0 → team_a's match colour.
            color_a = ' '
            color_b = ' '
            for board in team_board.boards:
                if board.index != 0:
                    continue
                white_team_id, _black_team_id = team_board.board_team_ids(board)
                if white_team_id == stb.team_a_id:
                    color_a, color_b = 'w', 'b'
                else:
                    color_a, color_b = 'b', 'w'
                break
            round_data[stb.team_a_id] = (
                tpn_by_team_id.get(stb.team_b_id),
                color_a,
                ''.join(symbols_a),
                ''.join(rid_a),
                a_gp,
                False,
                None,
            )
            round_data[stb.team_b_id] = (
                tpn_by_team_id.get(stb.team_a_id),
                color_b,
                ''.join(symbols_b),
                ''.join(rid_b),
                b_gp,
                False,
                None,
            )

        team_totals = tournament.team_totals_after(after_round)
        nickname_by_team_id = self._team_nickname_map(tpn_by_team_id)
        max_tpn = max(tpn_by_team_id.values(), default=0)
        tpn_width = max(2, len(str(max_tpn)))
        results_width = max(team_player_count, 4)
        rid_width = results_width
        for tpn, team in teams_by_tpn:
            mp, gp = team_totals.get(team.id, (0.0, 0.0))
            nickname = nickname_by_team_id[team.id]
            header_801 = f'{tpn:>{tpn_width}} {nickname:<5} {mp:>4.1f} {gp:>4.1f}'
            header_802 = f'{tpn:>{tpn_width}} {nickname:<5} {mp:>6.1f} {gp:>6.1f}'
            blocks_801: list[str] = []
            blocks_802: list[str] = []
            for round_ in range(1, after_round + 1):
                entry = per_round.get(round_, {}).get(team.id)
                if entry is None:
                    blocks_801.append(
                        f'  {"":>{tpn_width}} {"":1}'
                        f' {"":<{results_width}} {"":<{rid_width}}'
                    )
                    blocks_802.append(f'  {"":>{tpn_width}} {"":1} {"":>4} {"":1}')
                    continue
                opp_tpn, colour, board_str, rid_str, team_gp, _, bye = entry
                # 801: per the spec, an opponent-less round (bye) is
                # represented by leaving the opponent / colour / board
                # results columns blank — keep block width constant.
                if bye is not None:
                    opp_801 = ' ' * tpn_width
                    colour_801 = ' '
                    opp_802 = f'{bye:>3}'
                    colour_802 = ' '
                else:
                    opp_801 = (
                        f'{opp_tpn:>{tpn_width}}'
                        if opp_tpn is not None
                        else ' ' * tpn_width
                    )
                    colour_801 = colour
                    opp_802 = f'{opp_tpn:>3}' if opp_tpn is not None else '   '
                    colour_802 = colour
                blocks_801.append(
                    f'  {opp_801} {colour_801:1}'
                    f' {board_str:<{results_width}}'
                    f' {rid_str:<{rid_width}}'
                )
                blocks_802.append(f'  {opp_802} {colour_802:1} {team_gp:>4.1f}  ')
            pairings.append(header_801 + ''.join(blocks_801))
            results.append(header_802 + ''.join(blocks_802))
        return pairings, results

    def _team_tpn_map(self) -> dict[int, int]:
        """``team.id`` → unique TRF26 team pairing number (TPN).
        ``team.pairing_number`` is a user-editable hint and may
        collide across teams of the same tournament in malformed
        databases; TRF26 requires unique TPNs, so collisions are
        pushed to the next free slot, in team-UI order."""
        tournament = self.tournament
        teams = sorted(tournament.teams, key=_team_ui_sort_key)
        tpn_by_team_id: dict[int, int] = {}
        used: set[int] = set()
        next_tpn = 1
        for team in teams:
            if team.pairing_number is not None and team.pairing_number not in used:
                tpn_by_team_id[team.id] = team.pairing_number
                used.add(team.pairing_number)
                next_tpn = max(next_tpn, team.pairing_number + 1)
        for team in teams:
            if team.id in tpn_by_team_id:
                continue
            while next_tpn in used:
                next_tpn += 1
            tpn_by_team_id[team.id] = next_tpn
            used.add(next_tpn)
            next_tpn += 1
        return tpn_by_team_id

    def _team_nickname_map(self, tpn_by_team_id: dict[int, int]) -> dict[int, str]:
        """``team.id`` → unique 5-char TRF26 310 nickname. Derived from
        the team name; same-club teams (e.g. ``Rennes Paul Bert A/B/C``)
        all reduce to the same prefix, so on a collision the trailing
        characters are replaced with a counter until unique (TRF26
        requires distinct nicknames). Assigned in TPN order for
        determinism. Shared by the 310 and 801/802 records so a team's
        nickname is identical across them."""
        tournament = self.tournament
        nicknames: dict[int, str] = {}
        used: set[str] = set()
        teams_by_id = tournament.event.teams_by_id
        for team_id in sorted(tpn_by_team_id, key=lambda t: tpn_by_team_id[t]):
            team = teams_by_id.get(team_id)
            base = ((team.name[:5] if team is not None else '') or 'T').upper()
            nickname = base
            seq = 0
            while nickname in used:
                seq += 1
                tag = str(seq)
                nickname = (base[: max(1, 5 - len(tag))] + tag)[:5]
            used.add(nickname)
            nicknames[team_id] = nickname
        return nicknames

    def _team_pabs_record(
        self, *, after_round: int, tpn_by_team_id: dict[int, int]
    ) -> TrfTeamPABs | None:
        """TRF26 320 record: team-PAB match / game points + per-round
        team that received the PAB. Built when the team-PAB scores
        differ from defaults (draw match-points, draw game-points per
        FIDE C.04.6 §1.4) or when at least one team has actually
        received a PAB so far."""
        tournament = self.tournament
        match_points = tournament.match_points
        draw_mp = match_points.get(Result.DRAW, 1.0)
        pab_mp = match_points.get(Result.PAIRING_ALLOCATED_BYE, draw_mp)
        pab_gp = tournament.team_pab_game_points
        team_id_by_round: dict[int, int] = {}
        for team_board in tournament.team_boards_by_id.values():
            if team_board.round > after_round:
                continue
            stb = team_board.stored_team_board
            if stb.team_b_id is not None or stb.bye_type not in (
                None,
                TeamByeType.PAB,
            ):
                continue
            tpn = tpn_by_team_id.get(stb.team_a_id)
            if tpn is not None:
                team_id_by_round[team_board.round] = tpn
        default_gp = float(tournament.team_player_count or 0) * Result.DRAW.point_value
        non_default = pab_mp != draw_mp or pab_gp != default_gp
        if not team_id_by_round and not non_default:
            return None
        return TrfTeamPABs(
            match_points=pab_mp,
            game_points=pab_gp,
            team_id_by_round=team_id_by_round,
        )

    def _team_encoded_type(self) -> str:
        """``FIDE_TEAM_TYPE<X>_<primary>[_<secondary>]`` per TRF26 §7
        codes table. ``X`` is the colour-preference rule (A or B);
        when ``TeamColourType.NONE`` is selected the ``TYPE<X>_``
        infix is dropped, matching the FIDE convention for events that
        opt out of colour preferences. The primary-only code is what
        "the secondary score is not used for colour allocation" looks
        like on the wire."""
        tournament = self.tournament
        primary = 'MP' if tournament.primary_score == ScoreType.MATCH_POINTS else 'GP'
        colour_type = tournament.team_colour_type
        infix = (
            f'TYPE{colour_type.value}_' if colour_type != TeamColourType.NONE else ''
        )
        if not tournament.secondary_score_for_colours:
            return f'FIDE_TEAM_{infix}{primary}'
        secondary = (
            'MP' if tournament.secondary_score == ScoreType.MATCH_POINTS else 'GP'
        )
        return f'FIDE_TEAM_{infix}{primary}_{secondary}'

    def _round_byes(self) -> list[TrfRoundBye]:
        tournament = self.tournament
        round_byes: list[TrfRoundBye] = []
        for round_ in range(1, tournament.rounds + 1):
            pairing_numbers_by_bye: dict[Result, list[int]] = defaultdict(list)
            for (
                pairing_number,
                player,
            ) in tournament.tournament_players_by_pairing_number.items():
                result = player.pairings[round_].result
                if result.is_next_round_bye:
                    pairing_numbers_by_bye[result].append(pairing_number)
            for bye, pairing_numbers in pairing_numbers_by_bye.items():
                round_bye = TrfRoundBye(
                    type=bye.to_trf.upper(),
                    round=round_,
                    pairing_numbers=pairing_numbers,
                )
                round_byes.append(round_bye)
        return round_byes

    def _team_round_byes(
        self,
        *,
        after_round: int,
        tpn_by_team_id: dict[int, int],
        next_round_pairings_as_zpb: bool = False,
    ) -> list[TrfRoundBye]:
        """TRF26 240 records (team-mode interpretation): one entry per
        (round, bye type) listing the team TPNs flagged with
        ``HPB`` / ``FPB`` / ``ZPB`` envelopes. Emits records for every
        round through ``after_round + 1`` so the round-trip preserves
        past manual byes too — bbpPairings only consults the entry
        for the round it's pairing, but ignores the rest harmlessly.

        When *next_round_pairings_as_zpb* is set, teams already on
        any envelope for round ``after_round + 1`` (real matches,
        PAB envelopes) are additionally emitted as ``Z`` byes so
        bbpPairings excludes them when generating complementary
        pairings."""
        tournament = self.tournament
        type_map: dict[str, str] = {
            TeamByeType.FPB: 'F',
            TeamByeType.HPB: 'H',
            TeamByeType.ZPB: 'Z',
        }
        last_round = min(after_round + 1, tournament.rounds)
        next_round = after_round + 1
        records: list[TrfRoundBye] = []
        for round_ in range(1, last_round + 1):
            tpns_by_type: dict[str, list[int]] = defaultdict(list)
            for tb in tournament.get_round_team_boards(round_):
                stb = tb.stored_team_board
                if stb.team_b_id is None:
                    mapped = type_map.get(stb.bye_type or '')
                    if mapped is None:
                        if next_round_pairings_as_zpb and round_ == next_round:
                            tpn = tpn_by_team_id.get(stb.team_a_id)
                            if tpn is not None:
                                tpns_by_type['Z'].append(tpn)
                        continue
                    tpn = tpn_by_team_id.get(stb.team_a_id)
                    if tpn is not None:
                        tpns_by_type[mapped].append(tpn)
                elif next_round_pairings_as_zpb and round_ == next_round:
                    for tid in (stb.team_a_id, stb.team_b_id):
                        tpn = tpn_by_team_id.get(tid)
                        if tpn is not None:
                            tpns_by_type['Z'].append(tpn)
            if round_ == next_round:
                # Absent teams (check_in=False) are excluded from
                # pairing — emit a Z bye for each one not already in
                # another envelope this round.
                already_enveloped: set[int] = {
                    stb.team_a_id
                    for tb in tournament.get_round_team_boards(round_)
                    for stb in [tb.stored_team_board]
                } | {
                    stb.team_b_id
                    for tb in tournament.get_round_team_boards(round_)
                    for stb in [tb.stored_team_board]
                    if stb.team_b_id is not None
                }
                for team in tournament.teams:
                    if team.check_in:
                        continue
                    if team.id in already_enveloped:
                        continue
                    tpn = tpn_by_team_id.get(team.id)
                    if tpn is not None and tpn not in tpns_by_type['Z']:
                        tpns_by_type['Z'].append(tpn)
            for t, tpns in tpns_by_type.items():
                records.append(
                    TrfRoundBye(type=t, round=round_, pairing_numbers=sorted(tpns))
                )
        return records

    def _team_forfeited_matches(
        self,
        *,
        after_round: int,
        tpn_by_team_id: dict[int, int],
    ) -> list[TrfTeamForfeitedMatch]:
        """TRF26 330 records — one entry per played team match where
        one (or both) teams forfeited by failing to field any player.
        Type ``W`` = white team won by forfeit (black team forfeited),
        ``B`` = black team won, ``D`` = double forfeit. The colour each
        team plays at slot 0 of the match (driven by ``color_pattern``)
        decides which team is "white" for this encoding."""
        tournament = self.tournament
        pattern = tournament.color_pattern or ''
        team_a_board0_white = pattern[:1].upper() != BoardColor.BLACK.value
        records: list[TrfTeamForfeitedMatch] = []
        for round_ in range(1, after_round + 1):
            for tb in tournament.get_round_team_boards(round_):
                stb = tb.stored_team_board
                if stb.team_b_id is None:
                    continue
                team_a = tournament.event.teams_by_id.get(stb.team_a_id)
                team_b = tournament.event.teams_by_id.get(stb.team_b_id)
                if team_a is None or team_b is None:
                    continue
                a_empty = all(p is None for p in team_a.effective_round_slots(round_))
                b_empty = all(p is None for p in team_b.effective_round_slots(round_))
                if not (a_empty or b_empty):
                    continue
                a_tpn = tpn_by_team_id.get(team_a.id)
                b_tpn = tpn_by_team_id.get(team_b.id)
                if a_tpn is None or b_tpn is None:
                    continue
                if team_a_board0_white:
                    white_tpn, black_tpn = a_tpn, b_tpn
                    white_empty, black_empty = a_empty, b_empty
                else:
                    white_tpn, black_tpn = b_tpn, a_tpn
                    white_empty, black_empty = b_empty, a_empty
                # TRF26 330 type is two chars: white-side, black-side.
                # ``+`` = forfeit win, ``-`` = forfeit loss.
                if white_empty and black_empty:
                    forfeit_type = '--'
                elif black_empty:
                    forfeit_type = '+-'
                else:
                    forfeit_type = '-+'
                records.append(
                    TrfTeamForfeitedMatch(
                        type=forfeit_type,
                        round=round_,
                        white_team_id=white_tpn,
                        black_team_id=black_tpn,
                    )
                )
        return records

    def accelerated_rounds(self) -> list[TrfAcceleratedRound]:
        tournament = self.tournament
        variation = tournament.pairing_variation
        if not variation.include_accelerated_rules_in_trf:
            return []
        rounds = tournament.rounds
        acceleration_rules = variation.get_tournament_accelerated_rules(tournament)
        tpn_range_by_group = variation.get_acceleration_number_range_by_group(
            tournament
        )
        accelerated_rounds: list[TrfAcceleratedRound] = [
            TrfAcceleratedRound(
                match_points=None,
                game_points=rule.vpoints,
                first_round=rule.resolved_round_range(tournament)[0],
                last_round=rule.resolved_round_range(tournament)[1],
                first_id=number_range[0],
                last_id=number_range[1],
            )
            for rule in acceleration_rules
            if (number_range := rule.resolved_number_range(tournament)) is not None
        ]
        players_by_tpn = tournament.tournament_players_by_pairing_number
        for group, (min_tpn, max_tpn) in tpn_range_by_group.items():
            group_rules = [
                rule
                for rule in acceleration_rules
                if rule.number_range is None and rule.group == group
            ]
            if not any(rule.points_threshold for rule in group_rules):
                accelerated_rounds += [
                    TrfAcceleratedRound(
                        match_points=None,
                        game_points=rule.vpoints,
                        first_round=rule.resolved_round_range(tournament)[0],
                        last_round=rule.resolved_round_range(tournament)[1],
                        first_id=min_tpn,
                        last_id=max_tpn,
                    )
                    for rule in group_rules
                ]
                continue

            for tpn, player in players_by_tpn.items():
                if not min_tpn <= tpn <= max_tpn:
                    continue
                vpoints_history = [
                    tournament.player_virtual_points(player, at_round=round_)
                    for round_ in range(1, rounds + 1)
                ]
                first_round = 1
                previous_vpoints = vpoints_history[0]
                for index in range(1, rounds):
                    vpoints = vpoints_history[index]
                    if vpoints == previous_vpoints:
                        continue
                    if previous_vpoints != 0:
                        accelerated_rounds.append(
                            TrfAcceleratedRound(
                                match_points=None,
                                game_points=previous_vpoints,
                                first_round=first_round,
                                last_round=index,
                                first_id=tpn,
                                last_id=tpn,
                            )
                        )
                    first_round = index + 1
                    previous_vpoints = vpoints
                if previous_vpoints != 0:
                    accelerated_rounds.append(
                        TrfAcceleratedRound(
                            match_points=None,
                            game_points=previous_vpoints,
                            first_round=first_round,
                            last_round=rounds,
                            first_id=tpn,
                            last_id=tpn,
                        )
                    )
        return accelerated_rounds
