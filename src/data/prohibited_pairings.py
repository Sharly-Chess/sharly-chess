"""Prohibited pairings for Swiss — members that must not meet.

The grouping keys come from :class:`~data.pairing_dimensions.PairingDimension`
(``club`` / ``federation`` / affiliation, plus plugin dimensions). This module
turns those buckets into forbidden pairs and picks the soft-relaxation cutoff for
a round. A knock-out reuses the same dimensions for a different purpose (seeding
groups), so the dimension type itself lives in :mod:`data.pairing_dimensions`.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from data.input_output.trf.trf_data import TrfProhibitedPairing
from plugins.manager import plugin_manager

if TYPE_CHECKING:
    from data.pairing_dimensions import PairingDimension
    from data.tournament import Tournament
    from database.sqlite.event.event_database import EventDatabase
    from database.sqlite.event.event_store import StoredProhibitedPairingGroup


@dataclass(frozen=True)
class RoundProhibitedPairingGroup:
    """A prohibited-pairing group a plugin contributes for a specific round
    (typically results-based). ``name`` is the human label shown in the
    prohibited-pairings modal; ``member_ids`` are team ids in a team
    tournament, player ids otherwise."""

    name: str
    is_hard: bool
    member_ids: list[int]


# A prohibited pair is the unordered pair of the two members (player ids
# or team ids) that must not meet. ``Pair = frozenset({a, b})``.
Pair = frozenset


def resolve_soft_protect_rank(
    thresholds: list[int],
    feasible: Callable[[int], bool],
) -> tuple[int | None, bool]:
    """Pick the soft-relaxation cutoff ``N`` for this round — *protect the
    top N members*.

    Hard prohibitions are always enforced (baked into ``feasible``, which
    the caller closes over). A member whose standing rank is ``<= N`` is
    protected: it keeps *all* its soft separations. A soft separation is
    relaxed only when **both** its members rank below ``N`` — so any
    unavoidable club/league clash lands on two bottom-of-the-table
    members, on a low board, never on a strong one.

    ``thresholds`` are the distinct candidate cutoffs (the standing ranks
    of the members that appear in soft groups, sorted ascending; 1 = top).
    ``feasible(N)`` answers "can bbpPairings pair the field with the top N
    protected?" — monotone *decreasing* in ``N`` (a larger protected set
    only adds constraints), so we **bisect for the largest feasible N**.

    - Protecting everyone feasible → protect everyone (no clash forced).
    - Even protecting none infeasible → the hard constraints alone can't be
      paired → ``hard_infeasible`` (caller surfaces an error, never
      silently violates a hard prohibition).
    - No soft members at all → ``(None, False)``.

    Returns ``(protect_rank, hard_infeasible)``. ``protect_rank`` is the
    chosen cutoff, ``0`` to protect no one (all soft relaxed), or ``None``
    when there are no soft members to relax.
    """
    if not thresholds:
        return None, False
    if feasible(thresholds[-1]):
        return thresholds[-1], False
    if not feasible(0):
        return None, True
    best = 0
    low, high = 0, len(thresholds) - 1
    while low <= high:
        mid = (low + high) // 2
        if feasible(thresholds[mid]):
            best = thresholds[mid]
            low = mid + 1
        else:
            high = mid - 1
    return best, False


def expand_groups_to_pairs(
    member_ids: Iterable[int],
) -> list['frozenset[int]']:
    """Every unordered pair within a prohibited group (a group of N members
    forbids all N·(N−1)/2 internal pairings)."""
    members = list(member_ids)
    return [
        frozenset((members[i], members[j]))
        for i in range(len(members))
        for j in range(i + 1, len(members))
    ]


class ProhibitedPairings:
    """The prohibited pairings of one tournament: the configured
    dimension and manual groups, the snapshot frozen for each paired
    round, and the 260 lines that snapshot regenerates."""

    def __init__(self, tournament: 'Tournament') -> None:
        self.tournament = tournament

    @property
    def forced_by_rule_set(self) -> tuple[str, bool] | None:
        """The ``(dimension_id, is_hard)`` the tournament's rule set
        imposes, or ``None`` when the configuration is free."""
        rule_set = self.tournament.rule_set
        return rule_set.forced_prohibited_pairing if rule_set else None

    @property
    def dimension_id(self) -> str | None:
        forced = self.forced_by_rule_set
        if forced is not None:
            return forced[0]
        return self.tournament.stored_tournament.prohibited_pairing_dimension

    @property
    def dimension_is_hard(self) -> bool:
        forced = self.forced_by_rule_set
        if forced is not None:
            return forced[1]
        return self.tournament.stored_tournament.prohibited_pairing_dimension_is_hard

    def dimension(self) -> 'PairingDimension | None':
        dimension_id = self.dimension_id
        if dimension_id is None:
            return None
        for dimension in self.tournament.pairing_dimensions():
            if dimension.id == dimension_id:
                return dimension
        return None

    def set_config(
        self,
        dimension_id: str | None,
        dimension_is_hard: bool,
        database: 'EventDatabase',
    ) -> None:
        tournament = self.tournament
        tournament.stored_tournament.prohibited_pairing_dimension = dimension_id or None
        tournament.stored_tournament.prohibited_pairing_dimension_is_hard = (
            dimension_is_hard
        )
        database.update_stored_tournament(tournament.stored_tournament)

    @property
    def _members(self) -> list:
        """The members the dimension buckets — players for an individual
        tournament, teams for a team one."""
        tournament = self.tournament
        if tournament.is_team_tournament:
            return list(tournament.teams)
        return list(tournament.tournament_players)

    def manual_groups(
        self,
    ) -> 'list[StoredProhibitedPairingGroup]':
        return [
            group
            for group in self.tournament.stored_tournament.stored_prohibited_pairing_groups
            if group.round_ is None
        ]

    def set_manual_groups(
        self,
        groups: list[tuple[bool, list[int]]],
        database: 'EventDatabase',
    ) -> None:
        tournament = self.tournament
        database.replace_manual_prohibited_pairing_groups(tournament.id, groups)
        tournament.stored_tournament.stored_prohibited_pairing_groups = (
            database.load_tournament_stored_prohibited_pairing_groups(tournament.id)
        )

    def dimension_buckets(self) -> list[tuple[str, list[int]]]:
        """Live dimension buckets of ≥2 members, each ``(key, member_ids)``
        where ``key`` is the shared affiliation value (club / federation
        / … name). Empty when no dimension is selected."""
        dimension = self.dimension()
        if dimension is None:
            return []
        buckets: dict[str, list[int]] = {}
        for member in self._members:
            key = dimension.group_key(member)
            if key is None:
                continue
            buckets.setdefault(key, []).append(cast(int, member.id))
        return [
            (key, member_ids)
            for key, member_ids in buckets.items()
            if len(member_ids) >= 2
        ]

    def dimension_groups(self) -> list[tuple[bool, list[int]]]:
        """Live dimension-derived groups for the current config, each
        ``(is_hard, member_ids)``. Empty when no dimension is selected."""
        is_hard = self.dimension_is_hard
        return [(is_hard, member_ids) for _key, member_ids in self.dimension_buckets()]

    def computed_groups(
        self, round_: int | None = None
    ) -> list[tuple[bool, list[int]]]:
        """The live groups for the current config — dimension-derived
        plus the manual template groups. Each is ``(is_hard,
        member_ids)``. This is what a full pairing snapshots.

        When ``round_`` is given, plugin-contributed dynamic groups for
        that round (the ``get_round_prohibited_pairing_groups`` hook —
        e.g. results-based protections) are merged in too."""
        groups: list[tuple[bool, list[int]]] = list(self.dimension_groups())
        groups.extend(
            (group.is_hard, list(group.member_ids))
            for group in self.manual_groups()
            if len(group.member_ids) >= 2
        )
        if round_ is not None:
            groups.extend(
                (rule_group.is_hard, list(rule_group.member_ids))
                for rule_group in self.round_rule_groups(round_)
            )
        return groups

    def round_rule_groups(self, round_: int) -> list[RoundProhibitedPairingGroup]:
        """Named prohibited-pairing groups contributed by plugins for
        ``round_`` (the ``get_round_prohibited_pairing_groups`` hook). Kept
        named (unlike :meth:`computed_groups`) so the
        prohibited-pairings modal can label them before the round is paired.
        Groups of fewer than two members are dropped."""
        groups: list[RoundProhibitedPairingGroup] = []
        for plugin_result in plugin_manager.hook_for_event(
            self.tournament.event, 'get_round_prohibited_pairing_groups'
        )(tournament=self.tournament, round_=round_):
            groups.extend(
                group for group in plugin_result or [] if len(group.member_ids) >= 2
            )
        return groups

    def snapshot(self, round_: int) -> 'list[StoredProhibitedPairingGroup]':
        return [
            group
            for group in self.tournament.stored_tournament.stored_prohibited_pairing_groups
            if group.round_ == round_
        ]

    def count_for_round(self, round_: int) -> int:
        """Number of prohibition groups in effect for ``round_``: the frozen
        snapshot once the round is paired, otherwise the live configured
        groups. Drives the round's prohibited-pairings button indicator."""
        snapshot = self.snapshot(round_)
        if snapshot:
            return sum(1 for group in snapshot if len(group.member_ids) >= 2)
        return len(self.computed_groups(round_))

    def _member_pairing_number(self, member_id: int) -> int | None:
        """The TRF pairing number used in 260 records — a team TPN in
        team mode, a player pairing number otherwise."""
        tournament = self.tournament
        if tournament.is_team_tournament:
            team = tournament.teams_by_id.get(member_id)
            return team.pairing_number if team else None
        tp = tournament.tournament_players_by_id.get(member_id)
        return tp.pairing_number if tp else None

    def member_weakness_ranks(self, after_round: int) -> dict[int, int]:
        """Member id → standing position entering the round (1 = top).
        Soft prohibitions are relaxed from the bottom of this order, so an
        unavoidable clash lands on the players/teams doing worst *now*. In
        round 1 the standings collapse to the initial seed."""
        tournament = self.tournament
        if tournament.is_team_tournament:
            return {
                row.team.id: row.rank
                for row in tournament.team_standings(after_round=after_round)
            }
        return {
            tp.id: rank
            for rank, tp in tournament.compute_tournament_player_ranks(
                after_round=after_round
            ).items()
        }

    def relaxation_inputs(
        self, after_round: int
    ) -> tuple[list[list[int]], list[list[int]], dict[int, int]]:
        """Split the round's configured prohibitions into the always-kept
        hard groups and the soft groups, plus each member's standing rank
        (1 = top) entering the round — the basis for soft relaxation.

        Relaxation is member-level (*protect the top N*), so there is no
        pairwise expansion: a soft group is relaxed by splitting its
        members at a rank cutoff. Skips the standings entirely when there
        are no soft groups."""
        groups = self.computed_groups(after_round + 1)
        hard_groups: list[list[int]] = [
            list(member_ids) for is_hard, member_ids in groups if is_hard
        ]
        soft_groups: list[list[int]] = [
            list(member_ids) for is_hard, member_ids in groups if not is_hard
        ]
        if not soft_groups:
            return hard_groups, [], {}
        return (
            hard_groups,
            soft_groups,
            self.member_weakness_ranks(after_round),
        )

    def applied_lines(
        self,
        hard_groups: list[list[int]],
        soft_groups: list[list[int]],
        protect_rank: int,
        rank_by_member: dict[int, int],
        round_: int,
    ) -> list[TrfProhibitedPairing]:
        """The round's effective 260 lines. Hard groups become one
        N-member line each. Each soft group is relaxed at ``protect_rank``:
        its members split into protected (rank ``<= protect_rank``) and
        unprotected, and the surviving prohibitions — every pairing
        incident to a protected member — are emitted as compact clique
        lines (never the pairwise expansion). Members with no pairing
        number drop out."""
        lines: list[TrfProhibitedPairing] = []
        for group in hard_groups:
            numbers = [
                n
                for n in (self._member_pairing_number(m) for m in group)
                if n is not None
            ]
            if len(numbers) >= 2:
                lines.append(
                    TrfProhibitedPairing(
                        first_round=round_, last_round=round_, pairing_numbers=numbers
                    )
                )
        bottom = max(rank_by_member.values(), default=0) + 1
        for group in soft_groups:
            protected = [
                m for m in group if rank_by_member.get(m, bottom) <= protect_rank
            ]
            unprotected = [
                m for m in group if rank_by_member.get(m, bottom) > protect_rank
            ]
            lines.extend(self._soft_clique_lines(protected, unprotected, round_))
        return lines

    def _soft_clique_lines(
        self, protected: list[int], unprotected: list[int], round_: int
    ) -> list[TrfProhibitedPairing]:
        """The surviving prohibitions of one relaxed soft group, as cliques.
        Pairings incident to a protected member survive (a protected member
        must avoid everyone in the group); pairings between two unprotected
        members are relaxed. That edge set is covered by ``protected ∪ {u}``
        for each unprotected ``u`` (or just ``protected`` when none are
        unprotected) — one line per unprotected member, not one per pair."""
        protected_numbers = [
            n
            for n in (self._member_pairing_number(m) for m in protected)
            if n is not None
        ]
        if not protected_numbers:
            return []
        if not unprotected:
            if len(protected_numbers) < 2:
                return []
            return [
                TrfProhibitedPairing(
                    first_round=round_,
                    last_round=round_,
                    pairing_numbers=protected_numbers,
                )
            ]
        lines: list[TrfProhibitedPairing] = []
        for member in unprotected:
            number = self._member_pairing_number(member)
            if number is None:
                continue
            lines.append(
                TrfProhibitedPairing(
                    first_round=round_,
                    last_round=round_,
                    pairing_numbers=[*protected_numbers, number],
                )
            )
        return lines

    def was_relaxed(self, round_: int) -> bool:
        """True iff this round actually released a soft separation — some
        soft member ranked below the chosen ``protect_rank``. When everyone
        could be protected, ``resolve_soft_protect_rank`` stores the bottom
        rank (full protection), which is *not* a relaxation; the display
        must not announce one."""
        groups = self.snapshot(round_)
        protect_rank = next(
            (g.protect_rank for g in groups if g.protect_rank is not None), None
        )
        if protect_rank is None:
            return False
        ranks = self.member_weakness_ranks(after_round=round_ - 1)
        bottom = max(ranks.values(), default=0) + 1
        return any(
            ranks.get(member, bottom) > protect_rank
            for group in groups
            if not group.is_hard
            for member in group.member_ids
        )

    def released_members(self, round_: int) -> list[int]:
        """The soft members released this round (standing rank below the
        chosen ``protect_rank``) — flat and de-duplicated across all soft
        groups. These are the only ones that may now be paired against an
        affiliated opponent; everyone else kept all their soft separations.
        Ordered by standing rank (weakest last)."""
        groups = self.snapshot(round_)
        protect_rank = next(
            (g.protect_rank for g in groups if g.protect_rank is not None), None
        )
        if protect_rank is None:
            return []
        ranks = self.member_weakness_ranks(after_round=round_ - 1)
        bottom = max(ranks.values(), default=0) + 1
        released = {
            member
            for group in groups
            if not group.is_hard
            for member in group.member_ids
            if ranks.get(member, bottom) > protect_rank
        }
        return sorted(released, key=lambda member: ranks.get(member, bottom))

    def write_snapshot(
        self, round_: int, protect_rank: int | None, database: 'EventDatabase'
    ) -> None:
        """Freeze the round's prohibited-pairing **groups** (the configured
        hard and soft groups that were the basis for this round's pairing)
        together with the soft-relaxation cutoff ``protect_rank`` chosen for
        the round. The configured groups drive the read-only modal; groups
        plus ``protect_rank`` let the TRF 260 export regenerate the exact
        effective set bbpPairings enforced — without persisting the (huge)
        pairwise expansion."""
        tournament = self.tournament
        database.replace_round_prohibited_pairing_snapshot(
            tournament.id,
            round_,
            self.computed_groups(round_),
            protect_rank,
        )
        tournament.stored_tournament.stored_prohibited_pairing_groups = (
            database.load_tournament_stored_prohibited_pairing_groups(tournament.id)
        )

    def delete_snapshot(self, round_: int, database: 'EventDatabase') -> None:
        tournament = self.tournament
        database.delete_round_prohibited_pairing_snapshot(tournament.id, round_)
        tournament.stored_tournament.stored_prohibited_pairing_groups = [
            group
            for group in tournament.stored_tournament.stored_prohibited_pairing_groups
            if group.round_ != round_
        ]
