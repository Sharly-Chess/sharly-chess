"""FFE-specific rule sets — federation cups whose tournaments need
pre-configured scoring, tie-breaks, lineup constraints, etc.

The rule set is per-tournament: the arbiter creates one tournament for
each phase / group and picks its pairing system (Suisse / Molter /
round-robin) themselves. ``apply_defaults`` then writes the cup's
defaults into the freshly-built ``StoredTournament``.

Game-point scoring for these cups differs between Swiss / round-robin
("counts wins only", draws contribute 0 game points) and Molter (1 /
0.5 / 0). The Molter pairing systems live in a future plugin contribution;
until those land, ``apply_defaults`` treats every system as "Suisse-style"
because the plugin only ships Swiss / round-robin variations today.

Roster constraints (max size, Elo caps, parity) are applied at runtime
by the team-roster modal, not stored on the tournament — that lives in
future phases.
"""

from abc import ABC
from typing import override, TYPE_CHECKING

from common.i18n import _, ngettext
from data.pairings.fixed_table import FixedPairingTable, TablePairing as P
from data.rule_sets import RuleSet
from data.rule_sets.rule_sets import PointAdjustment
from utils.enum import (
    EventType,
    PlayerGender,
    Result,
    ScoreType,
    TeamColourType,
    TeamSortMode,
)

if TYPE_CHECKING:
    from data.team import Team
    from data.team_board import TeamBoard
    from database.sqlite.event.event_store import StoredTournament


# Both FFE cups use the same match-point scheme (3-2-1-0 with PAB
# treated as a win for the exempt team) and the same Suisse-style
# game-point scheme. Centralising the constants here so the two rule
# sets stay in sync.
_FFE_MATCH_POINTS: dict[int, float] = {
    Result.WIN.value: 3.0,
    Result.DRAW.value: 2.0,
    Result.LOSS.value: 1.0,
    Result.PAIRING_ALLOCATED_BYE.value: 3.0,
}

# Suisse / all-play-all: only wins count, draws are uncounted, losses
# are zero. Absence scores 0. (For finals, the FFE rules add a -1
# forfeit penalty; that needs a negative game point, deferred until it
# can be emitted via the TRF 299 field.)
_FFE_GAME_POINTS_SUISSE_STYLE: dict[int, float] = {
    Result.WIN.value: 1.0,
    Result.DRAW.value: 0.0,
    Result.LOSS.value: 0.0,
    Result.ZERO_POINT_BYE.value: 0.0,
    Result.PAIRING_ALLOCATED_BYE.value: 2.0,
}

# Molter: standard 1 / 0.5 / 0 game-points. Absence scores 0.
_FFE_GAME_POINTS_MOLTER: dict[int, float] = {
    Result.WIN.value: 1.0,
    Result.DRAW.value: 0.5,
    Result.LOSS.value: 0.0,
    Result.ZERO_POINT_BYE.value: 0.0,
    Result.PAIRING_ALLOCATED_BYE.value: 0.0,
}

# Tie-break order for the Swiss / round-robin phases of the two FFE
# team cups: match-point primary → game-points differential →
# game-points "pour" → lowest own avg Elo. Same list applies to
# ``TEAM_SWISS`` and ``TEAM_ROUND_ROBIN`` because the regulations
# bracket "Système Suisse ou toutes rondes" together.
_FFE_SUISSE_TIE_BREAKS: list[tuple[str, dict]] = [
    ('ffe-GP-DIFFERENTIAL', {}),
    ('ffe-GP-FOR', {}),
    ('ffe-OWN-AVG-ELO', {}),
]

# Molter phases: Berlin then lowest own avg Elo.
_FFE_MOLTER_TIE_BREAKS: list[tuple[str, dict]] = [
    ('ffe-BERLIN', {}),
    ('ffe-OWN-AVG-ELO', {}),
]

# Results that mean a game was actually contested over the board, as
# opposed to a forfeit, a bye, or an unplayed pairing.
_FFE_PLAYED_RESULTS = frozenset(
    {
        Result.WIN,
        Result.LOSS,
        Result.DRAW,
        Result.UNRATED_WIN,
        Result.UNRATED_LOSS,
        Result.UNRATED_DRAW,
    }
)

# Per-board results that count as a game lost by forfeit for the side
# that holds them.
_FFE_FORFEIT_LOSS_RESULTS = frozenset({Result.FORFEIT_LOSS, Result.DOUBLE_FORFEIT})


# 3 teams / 4 players — cup-specific Molter table used by both the
# Loubatière and Parité 3-team / 3-round phases. Not part of the
# standard FFE Molter registry (whose 3T×4P slot is a truncation of
# Tableau 1 that doesn't match the cup regulations).
_FFE_CUP_3T_4P_TABLE = FixedPairingTable(
    team_count=3,
    players_per_team=4,
    rounds=(
        (
            P('A', 1, 'B', 1),
            P('A', 2, 'C', 1),
            P('B', 2, 'C', 2),
            P('C', 3, 'B', 3),
            P('C', 4, 'A', 3),
            P('B', 4, 'A', 4),
        ),
        (
            P('B', 1, 'C', 1),
            P('B', 2, 'A', 1),
            P('C', 2, 'A', 2),
            P('A', 3, 'C', 3),
            P('A', 4, 'B', 3),
            P('C', 4, 'B', 4),
        ),
        (
            P('C', 1, 'A', 1),
            P('C', 2, 'B', 1),
            P('A', 2, 'B', 2),
            P('B', 3, 'A', 3),
            P('B', 4, 'C', 3),
            P('A', 4, 'C', 4),
        ),
    ),
    is_compromise=True,
)


def _fmt(value: float) -> str:
    """Render a points value the way the modal's number inputs accept
    it — integers without a trailing ``.0``."""
    return str(int(value)) if value == int(value) else str(value)


class _FfeTeamCupRuleSet(RuleSet, ABC):
    """Shared scaffold for the two FFE team cups. Both share the
    4-board team format, MP / GP scoring and colour rule; only roster
    constraints (max size, Elo caps, parity) differ — those land in a
    later phase."""

    @property
    @override
    def event_type(self) -> EventType:
        return EventType.TEAM

    @property
    @override
    def forced_team_sort_mode(self) -> str | None:
        # FFE cups order teams by the round-1 lineup's average Elo.
        return TeamSortMode.LINEUP_AVERAGE_RATING.value

    @property
    @override
    def forced_prohibited_pairing(self) -> tuple[str, bool] | None:
        # The cups keep teams of the same affiliation apart when the
        # pairing allows it (soft constraint on the team group).
        return ('team-group', False)

    @property
    def round3_winner_protection(self) -> bool:
        """Two teams that have won both of their first two matches are not
        paired together in round 3 (FFE cup regulations). On by default; the
        explicit no-protection variant turns it off, for the case where there
        is a single qualifying place for the N1F."""
        return True

    @property
    @override
    def managed_fields(self) -> set[str]:
        return {
            'rounds',
            'team_player_count',
            'primary_score',
            'team_colour_type',
            'enforce_roster_order',
            'mp_win',
            'mp_draw',
            'mp_loss',
            'mp_pab',
            'gp_win',
            'gp_draw',
            'gp_loss',
            'gp_zpb',
            'gp_pab',
        }

    @override
    def apply_defaults(
        self,
        stored_tournament: 'StoredTournament',
        pairing_system_id: str | None = None,
    ) -> None:
        stored_tournament.team_player_count = 4
        stored_tournament.team_colour_type = TeamColourType.A.value
        stored_tournament.enforce_roster_order = True
        stored_tournament.match_points = dict(_FFE_MATCH_POINTS)
        stored_tournament.primary_score = self._primary_score_for(pairing_system_id)
        # Overlay only the game-point fields the rule set manages
        # (win/draw/loss/zpb), preserving any the user set that it does not —
        # notably gp_pab — instead of replacing the whole mapping.
        game_points = dict(stored_tournament.game_points or {})
        game_points.update(self._game_points_for(pairing_system_id))
        stored_tournament.game_points = game_points
        if pairing_system_id is not None:
            rounds = self.rounds_for_pairing(pairing_system_id)
            if rounds is not None:
                stored_tournament.rounds = rounds

    @staticmethod
    def _primary_score_for(pairing_system_id: str | None) -> str:
        # Suisse / toutes rondes: match points. Molter: game points.
        # A two-game match isn't mentioned in the cup regs — treat it like
        # a head-to-head 2-game match where the result hinges on game
        # points.
        if pairing_system_id in ('MOLTER', 'TEAM_TWO_GAME_MATCH'):
            return ScoreType.GAME_POINTS.value
        return ScoreType.MATCH_POINTS.value

    @staticmethod
    def _game_points_for(pairing_system_id: str | None) -> dict[int, float]:
        # Suisse / round-robin: wins-only (1 / 0 / 0) — draws are
        # uncounted "X". Molter and the 2-team two-game match count
        # every game (1 / 0.5 / 0), the standard chess convention for
        # a head-to-head match.
        if pairing_system_id in ('MOLTER', 'TEAM_TWO_GAME_MATCH'):
            return _FFE_GAME_POINTS_MOLTER
        return _FFE_GAME_POINTS_SUISSE_STYLE

    @property
    @override
    def tie_break_overrides_by_pairing(self) -> dict[str, list[tuple[str, dict]]]:
        return {
            'TEAM_SWISS': _FFE_SUISSE_TIE_BREAKS,
            'TEAM_ROUND_ROBIN': _FFE_SUISSE_TIE_BREAKS,
            'TEAM_TWO_GAME_MATCH': _FFE_SUISSE_TIE_BREAKS,
            'MOLTER': _FFE_MOLTER_TIE_BREAKS,
        }

    @override
    def rounds_for_pairing(self, pairing_system_id: str) -> int | None:
        # Phase rounds per pairing system (Loubatière / Parité):
        # Swiss / Molter / single RR: 3 rounds; 2-team two-game match: 2.
        return {
            'TEAM_SWISS': 3,
            'MOLTER': 3,
            'TEAM_ROUND_ROBIN': 3,
            'TEAM_TWO_GAME_MATCH': 2,
        }.get(pairing_system_id)

    @override
    def molter_table_overrides(self) -> dict[tuple[int, int], FixedPairingTable]:
        return {(3, 4): _FFE_CUP_3T_4P_TABLE}

    # Subclass attribute: per-player rating ceiling. None = skip.
    PLAYER_RATING_CAP: int | None = None

    @override
    def roster_warnings(self, team: 'Team') -> list[str]:
        msgs: list[str] = []
        if (cap := self.PLAYER_RATING_CAP) is not None:
            over = [
                p
                for p in team.players
                if p.event_default_rating and p.event_default_rating > cap
            ]
            if over:
                names = ', '.join(
                    f'{p.full_name} ({p.event_default_rating})' for p in over
                )
                msgs.append(
                    _('Player rating above {cap}: {names}.').format(
                        cap=cap, names=names
                    )
                )
        msgs.extend(self._lineup_sum_warnings(team))
        return msgs

    def _lineup_sum_warnings(self, team: 'Team') -> list[str]:
        """Lineup-rating-sum cap warnings. Subclasses override when
        their regulations cap the fielded lineup's total rating.
        Default: no constraint."""
        return []

    @staticmethod
    def _team_round_match(team: 'Team', round_: int) -> 'TeamBoard | None':
        """The team's real (non-bye) team-match for ``round_``, or
        ``None`` when the team sat out / wasn't paired that round."""
        tournament = team.tournament
        if tournament is None:
            return None
        for team_board in tournament.get_round_team_boards(round_):
            stored = team_board.stored_team_board
            if (
                team.id in (stored.team_a_id, stored.team_b_id)
                and not team_board.is_bye
            ):
                return team_board
        return None

    @staticmethod
    def _team_board_breakdown(
        team_board: 'TeamBoard', team_id: int
    ) -> list[tuple[int, bool, bool]]:
        """Per individual board, in board order, a tuple of
        ``(index, team_forfeited, game_played)``:

        - ``team_forfeited`` — the team didn't field a player on the
          board, or its player there lost by forfeit.
        - ``game_played`` — both teams fielded a player and the board
          carries a real, contested result.
        """
        rows: list[tuple[int, bool, bool]] = []
        for board in team_board.boards:
            white_team, black_team = team_board.board_team_ids(board)
            if team_id not in (white_team, black_team):
                continue
            team_is_white = white_team == team_id
            if team_is_white:
                team_player = board.optional_white_tournament_player
                team_pairing = board.optional_white_pairing
            else:
                team_player = board.black_tournament_player
                team_pairing = board.optional_black_pairing
            team_result = team_pairing.result if team_pairing else Result.NO_RESULT
            forfeited = team_player is None or team_result in _FFE_FORFEIT_LOSS_RESULTS
            played = (
                board.optional_white_tournament_player is not None
                and board.black_tournament_player is not None
                and board.result in _FFE_PLAYED_RESULTS
            )
            rows.append((board.index, forfeited, played))
        return rows

    def _round_breakdown(
        self, team: 'Team', round_: int
    ) -> list[tuple[int, bool, bool]]:
        """``(index, forfeited, played)`` per board for the team this round,
        for either pairing model: a team-vs-team match (Suisse / round-robin)
        or a flat fixed-table round (Molter), which has no team_board."""
        team_board = self._team_round_match(team, round_)
        if team_board is not None:
            return self._team_board_breakdown(team_board, team.id)
        return self._flat_round_breakdown(team, round_)

    @staticmethod
    def _flat_round_breakdown(
        team: 'Team', round_: int
    ) -> list[tuple[int, bool, bool]]:
        """Flat fixed-table (Molter) counterpart of
        :meth:`_team_board_breakdown`: one row per team seat, holes
        included. Empty when the team isn't playing this round."""
        tournament = team.tournament
        if tournament is None:
            return []
        slots = team.effective_round_slots(round_)
        players_by_id = tournament.tournament_players_by_id
        engaged = any(
            player is not None
            and (tp := players_by_id.get(player.id)) is not None
            and round_ in tp.pairings_by_round
            for player in slots
        )
        if not engaged:
            return []
        rows: list[tuple[int, bool, bool]] = []
        for index, player in enumerate(slots):
            if player is None:
                # No player fielded on this board ⇒ forfeited, not played.
                rows.append((index, True, False))
                continue
            tp = players_by_id.get(player.id)
            pairing = tp.pairings_by_round.get(round_) if tp else None
            result = pairing.result if pairing else Result.NO_RESULT
            board = pairing.board if pairing else None
            forfeited = result in _FFE_FORFEIT_LOSS_RESULTS
            played = (
                board is not None
                and board.optional_white_tournament_player is not None
                and board.black_tournament_player is not None
                and board.result in _FFE_PLAYED_RESULTS
            )
            rows.append((index, forfeited, played))
        return rows

    def _forfeit_loss_penalty(
        self, team: 'Team', round_: int
    ) -> 'PointAdjustment | None':
        """A game lost by forfeit counts −1 game point ("Une partie perdue
        par forfait sportif est comptée -1"). Applies to every pairing
        system, Molter included."""
        if team.tournament is None:
            return None
        count = sum(
            1
            for _index, forfeited, _played in self._round_breakdown(team, round_)
            if forfeited
        )
        if not count:
            return None
        return PointAdjustment(
            gp=-float(count),
            explanation=ngettext(
                '{n} game lost by forfeit, counted as -1.',
                '{n} games lost by forfeit, counted as -1 each.',
                count,
            ).format(n=count),
        )

    def _following_board_played_penalty(
        self, team: 'Team', round_: int
    ) -> 'PointAdjustment | None':
        """−1 for each board the team forfeited while a game was actually
        played on a following (lower) board — i.e. a hole above a board it
        did field (FFE 4.1.c, "pour les deux systèmes"). Works for Molter
        too via the flat breakdown."""
        rows = self._round_breakdown(team, round_)
        played_indexes = [index for index, _f, played in rows if played]
        if not played_indexes:
            return None
        last_played = max(played_indexes)
        count = sum(
            1 for index, forfeited, _p in rows if forfeited and index < last_played
        )
        if not count:
            return None
        return PointAdjustment(
            gp=-float(count),
            explanation=ngettext(
                '{n} forfeited board above a board on which a game was '
                'played, counted as -1.',
                '{n} forfeited boards above a board on which a game was '
                'played, counted as -1 each.',
                count,
            ).format(n=count),
        )

    def _match_forfeit_mp_penalty(
        self, team: 'Team', round_: int
    ) -> 'PointAdjustment | None':
        """A match lost by forfeit scores 0 match points instead of the
        normal 1 ("un match perdu par forfait 0 point"). Applied as a -1
        match-point adjustment when the team forfeited its whole match, and
        only where match points rank the teams (Suisse / round-robin)."""
        tournament = team.tournament
        if tournament is None:
            return None
        if tournament.primary_score != ScoreType.MATCH_POINTS:
            return None
        rows = self._round_breakdown(team, round_)
        if rows and all(forfeited for _index, forfeited, _played in rows):
            return PointAdjustment(
                mp=-1.0,
                explanation=_('Match lost by forfeit, counted as 0 match points.'),
            )
        return None

    @staticmethod
    def _combine(
        *adjustments: 'PointAdjustment | None',
    ) -> 'PointAdjustment | None':
        """Sum several point adjustments into one, joining their
        explanations. Returns ``None`` when none apply."""
        parts = [adjustment for adjustment in adjustments if adjustment is not None]
        if not parts:
            return None
        return PointAdjustment(
            mp=sum(part.mp for part in parts),
            gp=sum(part.gp for part in parts),
            explanation=' '.join(
                part.explanation for part in parts if part.explanation
            ),
        )

    @override
    def form_defaults(self, pairing_system_id: str | None = None) -> dict[str, str]:
        gp = self._game_points_for(pairing_system_id)
        defaults: dict[str, str] = {
            'team_player_count': '4',
            'primary_score': self._primary_score_for(pairing_system_id),
            'team_colour_type': TeamColourType.A.value,
            'enforce_roster_order': 'on',
            'mp_win': _fmt(_FFE_MATCH_POINTS[Result.WIN.value]),
            'mp_draw': _fmt(_FFE_MATCH_POINTS[Result.DRAW.value]),
            'mp_loss': _fmt(_FFE_MATCH_POINTS[Result.LOSS.value]),
            'mp_pab': _fmt(_FFE_MATCH_POINTS[Result.PAIRING_ALLOCATED_BYE.value]),
            'gp_win': _fmt(gp[Result.WIN.value]),
            'gp_draw': _fmt(gp[Result.DRAW.value]),
            'gp_loss': _fmt(gp[Result.LOSS.value]),
            'gp_zpb': _fmt(gp[Result.ZERO_POINT_BYE.value]),
            'gp_pab': _fmt(gp[Result.PAIRING_ALLOCATED_BYE.value]),
        }
        if pairing_system_id is not None:
            rounds = self.rounds_for_pairing(pairing_system_id)
            if rounds is not None:
                defaults['rounds'] = str(rounds)
        return defaults


class CoupeJeanClaudeLoubatiereRuleSet(_FfeTeamCupRuleSet):
    """FFE *Coupe Jean-Claude Loubatière* (C03) — 4-board team cup."""

    # Players ≤1800 Elo for phase 1; later phases let phase-1 alumni
    # back in regardless of rating. Surfaced as a warning so the
    # arbiter judges case by case.
    PLAYER_RATING_CAP = 1800

    @override
    def team_point_adjustment(
        self, team: 'Team', round_: int
    ) -> 'PointAdjustment | None':
        # A game lost by forfeit counts -1 game point; a match lost by
        # forfeit scores 0 match points.
        return self._combine(
            self._forfeit_loss_penalty(team, round_),
            self._match_forfeit_mp_penalty(team, round_),
        )

    @property
    @override
    def roster_max_size(self) -> int | None:
        return 5

    @staticmethod
    @override
    def static_id() -> str:
        return 'ffe-coupe-jean-claude-loubatiere'

    @staticmethod
    @override
    def static_name() -> str:
        return _('Jean-Claude Loubatière Cup')

    @property
    @override
    def description(self) -> str:
        return _(
            'FFE 4-board team cup. 5-player roster cap, max Elo 1800 '
            'per player, mixed-system schedule (Swiss / Molter / round-robin).'
        )


class ChampionnatFemininN1N2RuleSet(_FfeTeamCupRuleSet):
    """FFE *Championnat de France Féminin des Clubs*, divisions
    Nationale 1 (N1F) and Nationale 2 (N2F).

    Same 4-board team-cup chassis as Loubatière (MP/GP scoring,
    Molter tie-breaks, 5-player roster, lineup follows the roster
    order). The cup-specific 1800 Elo cap doesn't apply; in its
    place the roster must consist entirely of women players —
    enforced as a soft warning so the arbiter can override.

    No Suisse / round-robin tie-breaks are imposed: the official
    departage (differential → points pour → per-board differential)
    is defined for the *whole competition* across multiple phases,
    which Sharly Chess doesn't aggregate — the arbiter picks per-phase
    tie-breaks if they need any.
    """

    @property
    @override
    def roster_max_size(self) -> int | None:
        return 5

    @property
    @override
    def tie_break_overrides_by_pairing(self) -> dict[str, list[tuple[str, dict]]]:
        return {'MOLTER': _FFE_MOLTER_TIE_BREAKS}

    @override
    def team_point_adjustment(
        self, team: 'Team', round_: int
    ) -> 'PointAdjustment | None':
        # -1 when a game was played on a board below a forfeited one; a
        # match lost by forfeit scores 0 match points.
        return self._combine(
            self._following_board_played_penalty(team, round_),
            self._match_forfeit_mp_penalty(team, round_),
        )

    @staticmethod
    @override
    def static_id() -> str:
        return 'ffe-championnat-feminin-n1-n2'

    @staticmethod
    @override
    def static_name() -> str:
        return _('FFE Women championship (N1F / N2F)')

    @property
    @override
    def description(self) -> str:
        return _(
            'FFE Nationale 1 / Nationale 2 Féminine. 5-player roster, '
            '4-board team matches, mixed Suisse / Molter / round-robin schedule. '
            'Roster must consist of women players only.'
        )

    @override
    def roster_warnings(self, team: 'Team') -> list[str]:
        # No per-player Elo cap on the Féminine divisions, so skip
        # the parent's rating check and only flag non-women rosters.
        non_women = [p for p in team.players if p.gender != PlayerGender.WOMAN]
        if not non_women:
            return []
        names = ', '.join(p.full_name for p in non_women)
        return [
            _('Roster must consist of women players only: {names}.').format(names=names)
        ]


class CoupeDeLaPariteRuleSet(_FfeTeamCupRuleSet):
    """FFE *Coupe de la Parité* (C04) — 2 men + 2 women per match."""

    @property
    @override
    def roster_max_size(self) -> int | None:
        return 6

    @override
    def roster_warnings(self, team: 'Team') -> list[str]:
        msgs = super().roster_warnings(team)
        msgs.extend(self._gender_balance_warnings(team))
        return msgs

    @override
    def team_point_adjustment(
        self, team: 'Team', round_: int
    ) -> 'PointAdjustment | None':
        # -1 when a game was played on a board below a forfeited one; a
        # match lost by forfeit scores 0 match points.
        return self._combine(
            self._following_board_played_penalty(team, round_),
            self._match_forfeit_mp_penalty(team, round_),
        )

    @staticmethod
    def _gender_balance_warnings(team: 'Team') -> list[str]:
        # The roster holds at most 3 men and 3 women,
        # and each match fields 2 men + 2 women — so a roster needs at
        # least 2 of each gender to field a legal lineup, and no more
        # than 3 of either.
        men = sum(1 for p in team.players if p.gender == PlayerGender.MAN)
        women = sum(1 for p in team.players if p.gender == PlayerGender.WOMAN)
        msgs: list[str] = []
        if men < 2:
            msgs.append(
                _('Need at least 2 men on the roster ({n} listed).').format(n=men)
            )
        elif men > 3:
            msgs.append(
                _('At most 3 men allowed on the roster ({n} listed).').format(n=men)
            )
        if women < 2:
            msgs.append(
                _('Need at least 2 women on the roster ({n} listed).').format(n=women)
            )
        elif women > 3:
            msgs.append(
                _('At most 3 women allowed on the roster ({n} listed).').format(n=women)
            )
        return msgs

    @override
    def _lineup_sum_warnings(self, team: 'Team') -> list[str]:
        tournament = team.tournament
        if tournament is None or not tournament.team_player_count:
            return []
        roster_size = len(team.players)
        if roster_size == 0:
            return []
        lineup_size = min(tournament.team_player_count, roster_size)
        # Lineup of 4 ≤ 8000 ; lineup of 3 < 6000.
        if lineup_size >= 4:
            cap = 8000
        elif lineup_size == 3:
            cap = 5999
        else:
            return []
        bottom_ratings = sorted(p.event_default_rating or 0 for p in team.players)[
            :lineup_size
        ]
        bottom_sum = sum(bottom_ratings)
        if bottom_sum <= cap:
            return []
        return [
            _('No legal {n}-player lineup: cheapest sum {sum} > {cap} cap.').format(
                n=lineup_size, sum=bottom_sum, cap=cap
            )
        ]

    @staticmethod
    @override
    def static_id() -> str:
        return 'ffe-coupe-de-la-parite'

    @staticmethod
    @override
    def static_name() -> str:
        return _('Mixed Cup')

    @property
    @override
    def description(self) -> str:
        return _(
            'FFE mixed team cup. 6-player roster (3M + 3W), per-match '
            'lineup must field 2 men and 2 women, team Elo capped at 8000.'
        )


# Each cup ships a second variant that drops the round-3 winner-protection
# rule — used when a single qualifying place for the N1F means the two
# leaders *should* meet in round 3.
class _NoRound3ProtectionMixin:
    @property
    def round3_winner_protection(self) -> bool:
        return False


class CoupeJeanClaudeLoubatiereNoR3RuleSet(
    _NoRound3ProtectionMixin, CoupeJeanClaudeLoubatiereRuleSet
):
    @staticmethod
    @override
    def static_id() -> str:
        return 'ffe-coupe-jean-claude-loubatiere-no-r3'

    @staticmethod
    @override
    def static_name() -> str:
        return _('Jean-Claude Loubatière Cup (no round-3 protection)')


class ChampionnatFemininN1N2NoR3RuleSet(
    _NoRound3ProtectionMixin, ChampionnatFemininN1N2RuleSet
):
    @staticmethod
    @override
    def static_id() -> str:
        return 'ffe-championnat-feminin-n1-n2-no-r3'

    @staticmethod
    @override
    def static_name() -> str:
        return _('FFE Women championship (N1F / N2F) (no round-3 protection)')


class CoupeDeLaPariteNoR3RuleSet(_NoRound3ProtectionMixin, CoupeDeLaPariteRuleSet):
    @staticmethod
    @override
    def static_id() -> str:
        return 'ffe-coupe-de-la-parite-no-r3'

    @staticmethod
    @override
    def static_name() -> str:
        return _('Mixed Cup (no round-3 protection)')
