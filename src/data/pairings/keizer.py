"""The Keizer pairing system for individual tournaments.

Unlike a Swiss or round-robin, a Keizer score is not a running count of
game points: each player carries a *ranking value* derived from their
current standing, and a game is worth the opponent's ranking value (a
draw, half of it). Because the values follow the standings, every past
round is re-scored with the opponents' current values after each round —
a win over a player who later collapses is worth less than a win over one
who climbs. That whole-table, iterative recomputation is what
:class:`KeizerScorer` implements; the system, variation and engine below
wire it into the pairing framework.
"""

from functools import cached_property
from typing import TYPE_CHECKING, override

from common.i18n import _
from data.pairings.engines import PairingEngine
from data.pairings.settings import (
    KeizerAbsenceFractionSetting,
    KeizerRematchGapSetting,
    KeizerRounding,
    KeizerRoundingSetting,
    KeizerStartAttributionSetting,
    PairingSetting,
)
from data.pairings.systems import PairingSystem, SwissPairingSystem
from data.pairings.variations import PairingVariation
from data.safety_mode import PairingAction, PermissionHandler
from database.sqlite.event.event_store import StoredBoard
from utils.entity import EntityManager, EventBoundEntityManager
from utils.enum import BoardColor, Result

if TYPE_CHECKING:
    from data.event import Event
    from data.pairing import Pairing
    from data.player import TournamentPlayer
    from data.tournament import Tournament


# The results that earn the opponent's current ranking value (a full share
# for a win, half for a draw).
_WIN_RESULTS = (Result.WIN, Result.UNRATED_WIN, Result.FORFEIT_WIN)
# The byes that count as an excused absence, earning the configured share
# of the player's own current ranking value.
_ABSENCE_RESULTS = (
    Result.HALF_POINT_BYE,
    Result.FULL_POINT_BYE,
    Result.PAIRING_ALLOCATED_BYE,
    Result.REST_GAME,
)


class KeizerScorer:
    """Computes Keizer totals and ranking values for a tournament.

    All results come from one recurrence, memoised per target round:

    - ``values_after(0)`` are the start values, by rating rank: the top
      player gets about three times the lowest, each next rank one less
      (see :meth:`_top_value`).
    - ``values_after(k)`` ranks the totals computed with
      ``values_after(k-1)`` and reassigns values by position.
    - a total after round ``R`` sums every played round ``r <= R`` using
      the opponents' values from ``values_after(R-1)`` — so past rounds
      are re-scored as the standings move.

    A player only contributes rounds they actually have a pairing for, so
    late entries and withdrawals need no special handling.
    """

    def __init__(self, tournament: 'Tournament'):
        self.tournament = tournament
        self._values_cache: dict[int, dict[int, float]] = {}
        self._start_attribution = KeizerStartAttributionSetting.get_value(tournament)
        self._rounding = KeizerRoundingSetting.get_value(tournament)
        self._absence_fraction = KeizerAbsenceFractionSetting.get_value(tournament)
        self._start_values_cache: dict[int, float] | None = None

    # -- public API ---------------------------------------------------------

    def total(self, player: 'TournamentPlayer', after_round: int) -> float:
        """The player's Keizer total after round *after_round* (0 before
        the first round)."""
        return self.totals_after(after_round).get(player.id, 0.0)

    def totals_after(self, after_round: int) -> dict[int, float]:
        """Every player's Keizer total after round *after_round*."""
        after_round = max(0, after_round)
        values = (
            self._start_values()
            if after_round == 0
            else self._values_after(after_round - 1)
        )
        return self._totals_with_values(values, up_to_round=after_round)

    # -- recurrence ---------------------------------------------------------

    def _top_value(self) -> int:
        """The value of the top-ranked player. The values step down by one
        per rank to a lowest of ``(N-1)//2``, so the top is about three
        times the lowest — the spread used by the common implementations
        (a 6-player field runs 7, 6, 5, 4, 3, 2)."""
        n = self.tournament.player_count
        return (n - 1) // 2 + (n - 1)

    def _start_values(self) -> dict[int, float]:
        if self._start_values_cache is None:
            top = self._top_value()
            self._start_values_cache = {
                player.id: float(top - (rank - 1))
                for rank, player in (
                    self.tournament.tournament_players_by_starting_rank.items()
                )
            }
        return self._start_values_cache

    def _values_after(self, k: int) -> dict[int, float]:
        if k <= 0:
            return self._start_values()
        if k not in self._values_cache:
            totals = self._totals_with_values(self._values_after(k - 1), up_to_round=k)
            self._values_cache[k] = self._assign_values_by_rank(totals)
        return self._values_cache[k]

    def _assign_values_by_rank(self, totals: dict[int, float]) -> dict[int, float]:
        """Position players by total (ties broken by rating rank) and hand
        out ranking values from :meth:`_top_value` downwards."""
        top = self._top_value()
        start_rank = {
            player.id: rank
            for rank, player in (
                self.tournament.tournament_players_by_starting_rank.items()
            )
        }
        ordered = sorted(
            totals,
            key=lambda player_id: (-totals[player_id], start_rank.get(player_id, 0)),
        )
        return {player_id: float(top - i) for i, player_id in enumerate(ordered)}

    def _totals_with_values(
        self, values: dict[int, float], *, up_to_round: int
    ) -> dict[int, float]:
        totals: dict[int, float] = {}
        for player in self.tournament.tournament_players:
            total = self._start_values()[player.id] if self._start_attribution else 0.0
            for round_, pairing in player.pairings.items():
                if round_ > up_to_round:
                    continue
                total += self._game_points(player, pairing, values)
            totals[player.id] = self._round(total)
        return totals

    def _game_points(
        self,
        player: 'TournamentPlayer',
        pairing: 'Pairing',
        values: dict[int, float],
    ) -> float:
        result = pairing.result
        if result in _WIN_RESULTS:
            opponent_id = pairing.opponent_id
            return values.get(opponent_id, 0.0) if opponent_id else 0.0
        if result.is_draw:
            opponent_id = pairing.opponent_id
            return (values.get(opponent_id, 0.0) if opponent_id else 0.0) / 2
        if result in _ABSENCE_RESULTS:
            return self._absence_fraction * values.get(player.id, 0.0)
        # Losses, zero-point byes, forfeits and unplayed games earn nothing.
        return 0.0

    def _round(self, value: float) -> float:
        if self._rounding == KeizerRounding.FULL:
            return float(round(value))
        if self._rounding == KeizerRounding.HALF:
            return round(value * 2) / 2
        return value


class KeizerPairingSystem(PairingSystem['KeizerVariation']):
    @staticmethod
    def static_id() -> str:
        return 'KEIZER'

    @staticmethod
    def static_name() -> str:
        return _('Keizer')

    @override
    def variation_manager(self, event: 'Event') -> EntityManager['KeizerVariation']:
        return KeizerVariationManager(event)

    @property
    def pairing_buttons_template(self) -> str:
        return '/admin/pairings/swiss_pairing_buttons.html'

    @property
    @override
    def uses_result_points(self) -> bool:
        # A Keizer score comes from the ranking values, not a count of
        # win / draw / loss points, so the game-point values and any
        # rating-body report built on them do not apply.
        return False

    @property
    @override
    def lock_settings_after_first_pairing(self) -> bool:
        # A Keizer recomputes every score from the whole field on each
        # render, so no round holds a frozen copy of the settings; they
        # can be edited at any point and simply re-derive the standings.
        return False

    @cached_property
    def permission_handler(self) -> PermissionHandler[PairingAction]:
        # Pairs round by round like a Swiss, so the Swiss permission set
        # (results enterable on the current round, pairing on the next)
        # fits.
        return SwissPairingSystem().permission_handler

    def default_current_round(self, tournament: 'Tournament') -> int:
        return tournament.last_paired_round


class KeizerVariation(PairingVariation):
    @staticmethod
    def variation_id() -> str:
        return 'STANDARD'

    @staticmethod
    def static_name() -> str:
        return _('Keizer')

    @staticmethod
    def system() -> PairingSystem:
        return KeizerPairingSystem()

    @property
    def engine(self) -> PairingEngine:
        return KeizerPairingEngine()

    @property
    def settings(self) -> list[PairingSetting]:
        return [
            KeizerStartAttributionSetting(),
            KeizerRoundingSetting(),
            KeizerRematchGapSetting(),
            KeizerAbsenceFractionSetting(),
        ]

    @property
    def trf_encoded_type(self) -> str:
        # No FIDE TRF26 code describes a Keizer: its score is not a game-
        # point count. Export is not offered for Keizer tournaments.
        return 'CUSTOM_KEIZER'


class KeizerVariationManager(EventBoundEntityManager[KeizerVariation]):
    @override
    def entity_types(self) -> list[type[KeizerVariation]]:
        return [KeizerVariation]


class KeizerPairingEngine(PairingEngine):
    MIN_PLAYERS = 2

    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        if tournament.player_count < self.MIN_PLAYERS:
            return _(
                'Too few players to generate the pairings (minimum: {min}).'
            ).format(min=self.MIN_PLAYERS)
        return None

    def _generate_stored_boards(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
        prohibited_pairing_override: 'list | None' = None,
    ) -> list[StoredBoard]:
        players = self._players_to_pair(tournament, round_)
        pairs, bye_player = self._pair(tournament, players, round_)
        stored_boards: list[StoredBoard] = []
        for index, (white, black) in enumerate(pairs):
            stored_boards.append(
                StoredBoard(
                    id=None,
                    white_player_id=white.id,
                    black_player_id=black.id,
                    index=index,
                )
            )
        if bye_player is not None:
            stored_boards.append(
                StoredBoard(
                    id=None,
                    white_player_id=bye_player.id,
                    black_player_id=None,
                    index=len(stored_boards),
                )
            )
        return stored_boards

    def _players_to_pair(
        self, tournament: 'Tournament', round_: int
    ) -> list['TournamentPlayer']:
        """Present players still needing a board this round, ordered by
        their current Keizer standing.

        A bye or an already-boarded pairing takes a player out; so does
        being absent when check-in is in use — Keizer pairs only the
        players actually there for the round. An absent player with no
        bye simply earns nothing for the round."""
        scorer = tournament.keizer_scorer
        totals = scorer.totals_after(round_ - 1)
        start_rank = {
            player.id: rank
            for rank, player in tournament.tournament_players_by_starting_rank.items()
        }
        players = [
            player
            for player in tournament.tournament_players
            if player.pairings[round_].needs_pairing
            and self._is_present(tournament, player)
        ]
        return sorted(
            players,
            key=lambda player: (
                -totals.get(player.id, 0.0),
                start_rank.get(player.id, 0),
            ),
        )

    @staticmethod
    def _is_present(tournament: 'Tournament', player: 'TournamentPlayer') -> bool:
        """Whether the player counts as present for pairing. Check-in only
        gates when the arbiter has opened it; otherwise everyone entered is
        paired."""
        if not tournament.check_in_open:
            return True
        return player.check_in

    # Cost weights for the matching. Ranking distance dominates so nearby
    # players are strongly preferred; a rematch inside the gap is a large
    # soft penalty (allowed only when nothing else can be paired); colour
    # is a light tie-breaker, deliberately below distance so a good
    # ranking pairing is never sacrificed for colour alone.
    _REMATCH_PENALTY = 1_000_000
    _DISTANCE_WEIGHT = 10

    def _pair(
        self,
        tournament: 'Tournament',
        players: list['TournamentPlayer'],
        round_: int,
    ) -> tuple[
        list[tuple['TournamentPlayer', 'TournamentPlayer']], 'TournamentPlayer | None'
    ]:
        bye_player: 'TournamentPlayer | None' = None
        if len(players) % 2 == 1:
            bye_player = self._select_bye_player(players)
            players = [player for player in players if player is not bye_player]
        gap = KeizerRematchGapSetting.get_value(tournament)
        matched = self._match(players, round_, gap)
        pairs = [self._order_colors(a, b, round_) for a, b in matched]
        return pairs, bye_player

    def _match(
        self,
        players: list['TournamentPlayer'],
        round_: int,
        gap: int,
    ) -> list[tuple['TournamentPlayer', 'TournamentPlayer']]:
        """Exact minimum-cost perfect matching over the standings-ordered
        *players* (even count), by branch-and-bound.

        The first unpaired player is matched against every remaining
        candidate cheapest-first, so a near-adjacent solution is found
        early and bounds the search; branches that already cost more than
        the best complete solution are pruned. Small present counts make
        this fast in practice."""
        n = len(players)
        if n == 0:
            return []
        position = {player.id: index for index, player in enumerate(players)}
        best_cost = float('inf')
        best_pairs: list[tuple[TournamentPlayer, TournamentPlayer]] | None = None
        used = [False] * n
        current: list[tuple[TournamentPlayer, TournamentPlayer]] = []

        def backtrack(accumulated: float) -> None:
            nonlocal best_cost, best_pairs
            if accumulated >= best_cost:
                return
            first = next((k for k in range(n) if not used[k]), None)
            if first is None:
                best_cost = accumulated
                best_pairs = list(current)
                return
            used[first] = True
            candidates = sorted(
                (k for k in range(n) if not used[k]),
                key=lambda k: self._pair_cost(
                    players[first], players[k], position, round_, gap
                ),
            )
            for k in candidates:
                used[k] = True
                cost = self._pair_cost(
                    players[first], players[k], position, round_, gap
                )
                current.append((players[first], players[k]))
                backtrack(accumulated + cost)
                current.pop()
                used[k] = False
            used[first] = False

        backtrack(0.0)
        assert best_pairs is not None
        return best_pairs

    def _pair_cost(
        self,
        a: 'TournamentPlayer',
        b: 'TournamentPlayer',
        position: dict[int, int],
        round_: int,
        gap: int,
    ) -> float:
        distance = abs(position[a.id] - position[b.id])
        cost = self._DISTANCE_WEIGHT * (distance - 1) ** 2
        if self._met_recently(a, b, round_, gap):
            cost += self._REMATCH_PENALTY
        cost += self._colour_residual(a, b, round_)
        return cost

    def _colour_residual(
        self, a: 'TournamentPlayer', b: 'TournamentPlayer', round_: int
    ) -> int:
        """Light colour cost: the smaller total colour imbalance the pair
        is left with once White is handed to whichever player it helps
        most."""
        if round_ <= 1:
            return 0
        ba = self._color_balance(a, round_)
        bb = self._color_balance(b, round_)
        white_to_a = abs(ba + 1) + abs(bb - 1)
        white_to_b = abs(ba - 1) + abs(bb + 1)
        return min(white_to_a, white_to_b)

    @staticmethod
    def _select_bye_player(
        players: list['TournamentPlayer'],
    ) -> 'TournamentPlayer':
        """Give the bye to the lowest-ranked present player who has not had
        one yet, falling back to the lowest-ranked player.

        *players* is standings-ordered, so the later entries are the
        lower-ranked ones."""
        for player in reversed(players):
            if not any(pairing.result.is_bye for pairing in player.pairings.values()):
                return player
        return players[-1]

    @staticmethod
    def _met_recently(
        player: 'TournamentPlayer',
        opponent: 'TournamentPlayer',
        round_: int,
        gap: int,
    ) -> bool:
        for past_round, pairing in player.pairings.items():
            if past_round >= round_:
                continue
            if pairing.opponent_id != opponent.id:
                continue
            if round_ - past_round <= gap:
                return True
        return False

    @staticmethod
    def _order_colors(
        higher: 'TournamentPlayer',
        lower: 'TournamentPlayer',
        round_: int,
    ) -> tuple['TournamentPlayer', 'TournamentPlayer']:
        """Return ``(white_player, black_player)``.

        The first round gives White to the lower-ranked player; later
        rounds give it to whoever has had White less, the lower-ranked
        player breaking a tie."""
        if round_ <= 1:
            return lower, higher
        higher_balance = KeizerPairingEngine._color_balance(higher, round_)
        lower_balance = KeizerPairingEngine._color_balance(lower, round_)
        if higher_balance > lower_balance:
            # The higher-ranked player has had more White; give it away.
            return lower, higher
        if lower_balance > higher_balance:
            return higher, lower
        # Tie: the lower-ranked player takes White.
        return lower, higher

    @staticmethod
    def _color_balance(player: 'TournamentPlayer', round_: int) -> int:
        """Whites minus Blacks over the player's played rounds so far."""
        balance = 0
        for past_round, pairing in player.pairings.items():
            if past_round >= round_ or not pairing.played:
                continue
            if pairing.color == BoardColor.WHITE:
                balance += 1
            elif pairing.color == BoardColor.BLACK:
                balance -= 1
        return balance
