import weakref
from typing import TYPE_CHECKING

from database.sqlite.event.event_store import StoredTeamPairingBlock

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.team import Team
    from data.tournament import Tournament


class TeamPairingBlock:
    """A prohibited team-vs-team pairing.
    *round* of None means: applies to all rounds of the tournament."""

    def __init__(
        self,
        tournament: 'Tournament',
        stored_block: StoredTeamPairingBlock,
    ):
        self._tournament_ref: 'ReferenceType[Tournament]' = weakref.ref(tournament)
        self.stored_block = stored_block

    @property
    def tournament(self) -> 'Tournament':
        if (tournament := self._tournament_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return tournament

    @property
    def id(self) -> int:
        assert self.stored_block.id is not None
        return self.stored_block.id

    @property
    def round(self) -> int | None:
        return self.stored_block.round_

    @property
    def team_a(self) -> 'Team':
        return self.tournament.event.teams_by_id[self.stored_block.team_a_id]

    @property
    def team_b(self) -> 'Team':
        return self.tournament.event.teams_by_id[self.stored_block.team_b_id]

    @property
    def reason(self) -> str | None:
        return self.stored_block.reason

    def applies_to_round(self, round_: int) -> bool:
        return self.round is None or self.round == round_

    def involves(self, team_id_a: int, team_id_b: int) -> bool:
        pair = {self.stored_block.team_a_id, self.stored_block.team_b_id}
        return pair == {team_id_a, team_id_b}

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}(id={self.id!r}, round={self.round!r}, '
            f'teams=({self.stored_block.team_a_id!r}, '
            f'{self.stored_block.team_b_id!r}), reason={self.reason!r})'
        )
