import weakref
from functools import cached_property
from typing import TYPE_CHECKING

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTeam,
    StoredTeamRoundLineupEntry,
)

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.event import Event
    from data.player import Player
    from data.tournament import Tournament


class Team:
    """A team of players competing as a unit in a team tournament."""

    def __init__(self, event: 'Event', stored_team: StoredTeam):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_team = stored_team

    @property
    def event(self) -> 'Event':
        if (event := self._event_ref()) is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int:
        assert self.stored_team.id is not None
        return self.stored_team.id

    @property
    def name(self) -> str:
        return self.stored_team.name

    @property
    def tournament_id(self) -> int | None:
        return self.stored_team.tournament_id

    @property
    def tournament(self) -> 'Tournament | None':
        if self.tournament_id is None:
            return None
        return self.event.tournaments_by_id.get(self.tournament_id)

    @property
    def pairing_number(self) -> int | None:
        return self.stored_team.pairing_number

    @property
    def is_paired(self) -> bool:
        """True if this team appears in any team_board record (i.e. has been
        paired in at least one round). Used to lock cross-tournament drag."""
        tournament = self.tournament
        if tournament is None:
            return False
        return any(
            tb.stored_team_board.team_a_id == self.id
            or tb.stored_team_board.team_b_id == self.id
            for tb in tournament.team_boards_by_id.values()
        )

    @cached_property
    def players(self) -> list['Player']:
        """Players belonging to this team, ordered by *team_index*.
        Players without an index are sorted last by id."""
        return sorted(
            (
                player
                for player in self.event.players_by_id.values()
                if player.stored_player.team_id == self.id
            ),
            key=lambda p: (
                p.team_index if p.team_index is not None else float('inf'),
                p.id,
            ),
        )

    @cached_property
    def players_by_id(self) -> dict[int, 'Player']:
        return {player.id: player for player in self.players}

    @property
    def lineups_by_round(self) -> dict[int, list['Player']]:
        """Per-round lineup as a list of players ordered by board index.
        Missing rounds are absent from the dict."""
        result: dict[int, list['Player']] = {}
        players_by_id = self.event.players_by_id
        for round_, entries in self.stored_team.stored_round_lineups.items():
            ordered = sorted(entries, key=lambda e: e.index)
            result[round_] = [
                players_by_id[entry.player_id]
                for entry in ordered
                if entry.player_id in players_by_id
            ]
        return result

    def get_round_lineup(self, round_: int) -> list['Player']:
        return self.lineups_by_round.get(round_, [])

    def has_explicit_round_lineup(self, round_: int) -> bool:
        return round_ in self.stored_team.stored_round_lineups

    def effective_round_lineup(self, round_: int) -> list['Player']:
        """Lineup applied for *round_*. Returns the stored override if any,
        otherwise the first *team_player_count* roster players."""
        if self.has_explicit_round_lineup(round_):
            return self.get_round_lineup(round_)
        tournament = self.tournament
        if tournament is None or tournament.team_player_count is None:
            return []
        return self.players[: tournament.team_player_count]

    # -------------------------------------------------------------------------
    # Mutations
    # -------------------------------------------------------------------------

    def update(self, database: EventDatabase):
        database.update_stored_team(self.stored_team)

    def set_tournament(self, tournament_id: int | None, database: EventDatabase):
        self.stored_team.tournament_id = tournament_id
        database.set_team_tournament(self.id, tournament_id)

    def set_pairing_number(self, pairing_number: int | None, database: EventDatabase):
        self.stored_team.pairing_number = pairing_number
        database.set_team_pairing_number(self.id, pairing_number)

    def set_round_lineup(
        self,
        round_: int,
        player_ids: list[int],
        database: EventDatabase,
    ):
        """Replace the team's lineup for the given round.
        Order in *player_ids* determines the board index (0-based)."""
        entries = [
            StoredTeamRoundLineupEntry(
                team_id=self.id,
                round_=round_,
                player_id=player_id,
                index=index,
            )
            for index, player_id in enumerate(player_ids)
        ]
        database.replace_team_round_lineup(self.id, round_, entries)
        self.stored_team.stored_round_lineups[round_] = entries

    def delete_round_lineup(self, round_: int, database: EventDatabase):
        database.delete_team_round_lineup(self.id, round_)
        self.stored_team.stored_round_lineups.pop(round_, None)

    # -------------------------------------------------------------------------
    # Roster
    # -------------------------------------------------------------------------

    def _invalidate_players(self):
        if 'players' in self.__dict__:
            del self.__dict__['players']
        if 'players_by_id' in self.__dict__:
            del self.__dict__['players_by_id']

    def add_player(self, player: 'Player', database: EventDatabase):
        """Add a player to the team's roster.
        Removes the player from any previous team (event-wide uniqueness).
        Appends at the end of the roster ordering."""
        previous_team_id = player.stored_player.team_id
        if previous_team_id == self.id:
            return
        next_index = (
            max(
                (p.team_index for p in self.players if p.team_index is not None),
                default=-1,
            )
            + 1
        )
        player.stored_player.team_id = self.id
        player.stored_player.team_index = next_index
        database.set_player_team(player.id, self.id, next_index)
        self._invalidate_players()
        if previous_team_id is not None:
            previous_team = self.event.teams_by_id.get(previous_team_id)
            if previous_team is not None:
                previous_team._invalidate_players()
                previous_team._compact_indexes(database)

    def remove_player(self, player: 'Player', database: EventDatabase):
        """Remove a player from this team. Compacts remaining indexes."""
        if player.stored_player.team_id != self.id:
            return
        player.stored_player.team_id = None
        player.stored_player.team_index = None
        database.set_player_team(player.id, None, None)
        self._invalidate_players()
        self._compact_indexes(database)

    def _compact_indexes(self, database: EventDatabase):
        """Renumber remaining players' team_index sequentially from 0."""
        remaining = self.players
        if not remaining:
            return
        ids = [p.id for p in remaining]
        for new_index, p in enumerate(remaining):
            p.stored_player.team_index = new_index
        database.reorder_team_players(self.id, ids)
        self._invalidate_players()

    def reorder_players(self, ordered_player_ids: list[int], database: EventDatabase):
        """Reorder roster players. Silently ignores ids not on this team."""
        current_ids = {p.id for p in self.players}
        filtered = [pid for pid in ordered_player_ids if pid in current_ids]
        # Append any missing roster members (defensive)
        for pid in current_ids:
            if pid not in filtered:
                filtered.append(pid)
        for new_index, pid in enumerate(filtered):
            player = self.event.players_by_id[pid]
            player.stored_player.team_index = new_index
        database.reorder_team_players(self.id, filtered)
        self._invalidate_players()

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}(id={self.id!r}, name={self.name!r}, '
            f'tournament_id={self.tournament_id!r}, '
            f'pairing_number={self.pairing_number!r})'
        )
