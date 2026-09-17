"""Knock-out-specific views over a tournament, reached as ``tournament.knockout``.

A knock-out exposes a cluster of behaviours the templates and controllers need —
advancement resolution, the round-reached standings, the bracket tie-resolution
display and the manual-winner writers. They all delegate to the tournament's
pairing engine; grouping them here keeps them off the (system-agnostic)
:class:`~data.tournament.Tournament` class.

The engine-typed methods are valid only on a knock-out (callers gate on
``pairing_system.eliminates_participants``). The ``getattr``-based ones — the
board/team-match advancement display, the unresolved-match list, the manual
marker and the grouping preview — return an empty result for any system, so a
template may call them unconditionally.
"""

from functools import cached_property
from typing import TYPE_CHECKING, Any, Protocol, cast

from common.i18n import _
from data.pairings.knockout_helpers.common import seeded_players
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import set_stored_fields

if TYPE_CHECKING:
    from data.board import Board
    from data.pairings.knockout import KnockoutAdvancement
    from data.pairings.knockout_helpers.layout import BracketLayout
    from data.player import TournamentPlayer
    from data.teams.team_board import TeamBoard
    from data.tournament import Tournament

    class _KnockoutEngineProtocol(Protocol):
        """The knock-out-specific engine methods the delegators reach through
        ``pairing_variation.engine`` (a knock-out engine whenever these are
        called)."""

        def ranking_value(
            self,
            tournament: 'Tournament',
            player: 'TournamentPlayer',
            *,
            after_round: int,
        ) -> float: ...

        def standing_labels(
            self, tournament: 'Tournament', *, after_round: int | None = ...
        ) -> dict[int, str]: ...

        def team_ranking_values(
            self, tournament: 'Tournament', *, after_round: int
        ) -> dict[int, float]: ...

        def team_standing_labels(
            self, tournament: 'Tournament', *, after_round: int | None = ...
        ) -> dict[int, str]: ...

        def team_advancement(
            self, tournament: 'Tournament', team_board: 'TeamBoard'
        ) -> 'KnockoutAdvancement': ...

        def player_advancement(
            self, tournament: 'Tournament', board: 'Board'
        ) -> 'KnockoutAdvancement': ...


class KnockoutView:
    """The knock-out-specific facet of a tournament (see the module docstring)."""

    def __init__(self, tournament: 'Tournament') -> None:
        self._t = tournament

    @cached_property
    def engine_cache(self) -> dict:
        """Scratch space the engines memoise per-tournament derivations in — a
        double elimination resolves its whole match graph to answer a single
        player's placement, and the standings ask once per player. Lives as long
        as the tournament object; the writers below drop it."""
        return {}

    def invalidate_engine_cache(self) -> None:
        """Drop the memoised derivations after a result they depend on moved."""
        self.__dict__.pop('engine_cache', None)

    @property
    def _engine(self) -> '_KnockoutEngineProtocol':
        """The pairing engine typed as a knock-out engine. Only reached from
        methods that run on a knock-out, where the engine really carries them."""
        return cast('_KnockoutEngineProtocol', self._t.pairing_variation.engine)

    # -- Advancement resolution (knock-out only) ----------------------------

    def team_advancement(self, team_board: 'TeamBoard') -> 'KnockoutAdvancement':
        """Who advances from a level team match and why; see
        :meth:`KnockoutEngine.team_advancement`."""
        return self._engine.team_advancement(self._t, team_board)

    def advancement_winner(self, team_board: 'TeamBoard') -> int | None:
        return self.team_advancement(team_board).winner_id

    def player_advancement(self, board: 'Board') -> 'KnockoutAdvancement':
        """Who advances from a drawn individual game and why; see
        :meth:`KnockoutEngine.player_advancement`."""
        return self._engine.player_advancement(self._t, board)

    def advancement_winner_player(self, board: 'Board') -> int | None:
        return self.player_advancement(board).winner_id

    # -- Advancement display (empty for any non-knock-out system) -----------

    def board_advancement(self, board: 'Board') -> 'KnockoutAdvancement | None':
        """The advancement detail to show on an individual board — only for a
        knock-out game drawn between two players, else ``None``."""
        method = getattr(self._t.pairing_variation.engine, 'board_advancement', None)
        return method(self._t, board) if method is not None else None

    def team_board_advancement(
        self, team_board: 'TeamBoard'
    ) -> 'KnockoutAdvancement | None':
        """The advancement detail to show on a team match — only for a finished
        knock-out match level on game points, else ``None``."""
        method = getattr(
            self._t.pairing_variation.engine, 'team_board_advancement', None
        )
        return method(self._t, team_board) if method is not None else None

    @property
    def advancement_has_manual(self) -> bool:
        """Whether the advancement list contains the play-off (manual) marker,
        so the pairing tab may offer to designate a winner. False for
        non-knock-outs."""
        method = getattr(
            self._t.pairing_variation.engine, 'advancement_has_manual', None
        )
        return method(self._t) if method is not None else False

    def unresolved_matches(self, round_: int) -> list[dict[str, Any]]:
        """The round's played matches that no advancement tie-break can settle —
        awaiting a play-off designation. Empty unless this is a knock-out."""
        method = getattr(self._t.pairing_variation.engine, 'unresolved_matches', None)
        return method(self._t, round_) if method is not None else []

    # -- Standings (round reached, knock-out only) --------------------------

    def ranking_value(self, player: 'TournamentPlayer', *, after_round: int) -> float:
        """A knock-out's standing value for *player* — the round reached
        (bigger = better); see :meth:`KnockoutEngine.ranking_value`."""
        return self._engine.ranking_value(self._t, player, after_round=after_round)

    def standing_labels(self, *, after_round: int | None = None) -> dict[int, str]:
        """Plain-language knock-out standings per player id ('Winner' /
        'Runner-up' / 'Out — round N' / 'Still in')."""
        return self._engine.standing_labels(self._t, after_round=after_round)

    def team_ranking_values(self, *, after_round: int) -> dict[int, float]:
        """Ranking value per team id (round reached)."""
        return self._engine.team_ranking_values(self._t, after_round=after_round)

    def team_standing_labels(self, *, after_round: int | None = None) -> dict[int, str]:
        """Plain-language knock-out standings per team id."""
        return self._engine.team_standing_labels(self._t, after_round=after_round)

    # -- Bracket render / grouping preview ----------------------------------

    def layout(self) -> 'BracketLayout | None':
        """A render-ready bracket diagram, or ``None`` for a system with no
        bracket to draw."""
        build = getattr(self._t.pairing_variation.engine, 'bracket_layout', None)
        return build(self._t) if build is not None else None

    def grouping_preview(self, dimension_id: str) -> 'dict | None':
        """Preview of seeding a knock-out bracket by *dimension_id* (the groups
        and the bracket consequence). ``None`` for a non-knock-out or an unknown
        dimension."""
        method = getattr(self._t.pairing_variation.engine, 'grouping_preview', None)
        if method is None:
            return None
        for dimension in self._t.prohibited_pairing_dimensions():
            if dimension.id == dimension_id:
                return method(self._t, dimension)
        return None

    def team_last_round(self, team_id: int) -> int | None:
        """The last round a knocked-out team plays, or ``None`` while it is
        still in and may yet reach the final."""
        values = self._engine.team_ranking_values(self._t, after_round=self._t.rounds)
        value = values.get(team_id)
        rounds = self._t.rounds
        if value is None or value >= rounds + 1:
            return None
        # A third-place play-off is played in the final round.
        return rounds if value >= rounds - 0.5 else int(value)

    def side_sections(self, round_: int) -> list[dict[str, Any]]:
        """The side column of a knock-out at *round_*: who is still in, by
        bracket, and who is out.

        Each section is ``{'label', 'ids', 'collapsed'}``. Whoever the
        round seats is left out — the boards show them. What remains is a
        double elimination's bracket sitting the round out, named with the
        round it plays instead, and last of all the eliminated, folded away.
        Before the draw nothing is seated, so the whole field is there.
        """
        method = getattr(self._t.pairing_variation.engine, 'still_in_groups', None)
        if method is None:
            return []
        seated = self._seated_ids(round_)
        sections: list[dict[str, Any]] = []
        for label, ids in method(self._t, round_):
            # Whoever has a board this round is on it; the column is for the
            # rest — the bracket sitting the round out, and the eliminated.
            waiting = [id_ for id_ in ids if id_ not in seated]
            if waiting:
                sections.append({'label': label, 'ids': waiting, 'collapsed': False})
        eliminated = self._eliminated_ids(
            seated | {id_ for section in sections for id_ in section['ids']}
        )
        if eliminated:
            sections.append(
                {'label': _('Eliminated'), 'ids': eliminated, 'collapsed': True}
            )
        return sections

    def _seated_ids(self, round_: int) -> set[int]:
        """Who the round has a board for."""
        seated: set[int] = set()
        if self._t.pairing_system.paired_by_team:
            for team_board in self._t.get_round_team_boards(round_):
                stb = team_board.stored_team_board
                seated.add(stb.team_a_id)
                if stb.team_b_id is not None:
                    seated.add(stb.team_b_id)
            return seated
        for board in self._t.get_round_boards(round_):
            for player in (
                board.optional_white_tournament_player,
                board.black_tournament_player,
            ):
                if player is not None:
                    seated.add(player.id)
        return seated

    def _eliminated_ids(self, still_in: set[int]) -> list[int]:
        """Everyone the bracket has no further match for, in seed order."""
        if self._t.pairing_system.paired_by_team:
            participants: list[Any] = sorted(
                self._t.teams,
                key=lambda team: (
                    team.pairing_number
                    if team.pairing_number is not None
                    else float('inf'),
                    team.id,
                ),
            )
        else:
            by_seed = seeded_players(self._t)
            participants = [by_seed[seed] for seed in sorted(by_seed)]
        return [
            participant.id
            for participant in participants
            if participant.id not in still_in
        ]

    # -- Manual winner designation ------------------------------------------

    def match_rounds(self, round_: int) -> tuple[int, ...]:
        """The rounds a match is played over — one, or the games of a
        two-game match."""
        method = getattr(self._t.pairing_variation.engine, 'match_rounds', None)
        return method(self._t, round_) if method is not None else (round_,)

    def forget_settled_winners(self, board: 'Board') -> None:
        """Drop the designations a result has settled. A match that is no
        longer level decides who advances by itself, and a cleared result
        leaves nothing to advance from — a designation kept either way would
        come back the next time the match fell level."""
        if not self._t.pairing_system.eliminates_participants:
            return
        for round_ in self.match_rounds(board.round):
            for match_board in self._t.get_round_boards(round_):
                if match_board.stored_board.knockout_winner_player_id is None:
                    continue
                if self.board_advancement(match_board) is not None:
                    continue
                self.set_player_match_winner(match_board.identifier, None)
        team_board = board.team_board
        if (
            team_board is not None
            and team_board.stored_team_board.knockout_winner_team_id is not None
            and self.team_board_advancement(team_board) is None
        ):
            self.set_team_match_winner(team_board.id, None)

    def set_team_match_winner(self, team_board_id: int, team_id: int | None) -> None:
        """Designate (or clear, with ``None``) the team that advances from a
        level team match the tie-breaks could not settle."""
        team_board = self._t.team_boards_by_id[team_board_id]
        stb = team_board.stored_team_board
        if team_id is not None and team_id not in (stb.team_a_id, stb.team_b_id):
            raise ValueError(
                f'Team [{team_id}] is not in team match [{team_board_id}].'
            )
        stb.knockout_winner_team_id = team_id
        with EventDatabase(self._t.event.uniq_id, write=True) as database:
            database.update_stored_team_board(stb)
        self.invalidate_engine_cache()
        self._t.clear_team_cache()

    def set_player_match_winner(self, board_id: int, player_id: int | None) -> None:
        """Designate (or clear, with ``None``) the player that advances from a
        drawn game the tie-breaks could not settle."""
        board = self._t.boards_by_id[board_id]
        stored_board = board.stored_board
        if player_id is not None and player_id not in (
            stored_board.white_player_id,
            stored_board.black_player_id,
        ):
            raise ValueError(f'Player [{player_id}] is not on board [{board_id}].')
        # StoredBoard is frozen; use the field-setting helper.
        set_stored_fields(stored_board, knockout_winner_player_id=player_id)
        with EventDatabase(self._t.event.uniq_id, write=True) as database:
            database.update_stored_board(stored_board)
        self.invalidate_engine_cache()
