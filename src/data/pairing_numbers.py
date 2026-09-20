"""The pairing numbers of a tournament's players.

A player's number is their place in the starting rank. Once the system
has frozen the numbering — a Swiss after its first pairing — a player
inserted later takes the place their rank gives them and the others
shift, as do the settings that address numbers.
"""

from functools import cached_property
from operator import attrgetter
from typing import TYPE_CHECKING

from database.sqlite.event.event_database import EventDatabase

if TYPE_CHECKING:
    from data.player import TournamentPlayer
    from data.tournament import Tournament


class PairingNumbers:
    """The pairing numbers of one tournament's players, assigned on first
    read and kept until the field changes."""

    def __init__(self, tournament: 'Tournament') -> None:
        self.tournament = tournament

    @cached_property
    def by_number(self) -> dict[int, 'TournamentPlayer']:
        """Every player by pairing number, in number order; the numbers
        are assigned first if they are not yet."""
        self._assign()
        return {
            tournament_player.pairing_number or 0: tournament_player
            for tournament_player in sorted(
                self.tournament.tournament_players, key=attrgetter('pairing_number')
            )
        }

    def assign(self) -> None:
        """Make sure every player has a pairing number."""
        __ = self.by_number

    def _assign(self) -> None:
        """Number every player of the tournament."""
        tournament = self.tournament
        inserted_tournament_players: list[TournamentPlayer] = []
        current_tournament_players: list[TournamentPlayer] = []
        current_pairing_numbers: set[int] = set()
        for tournament_player in tournament.tournament_players:
            if tournament_player.pairing_number is None:
                inserted_tournament_players.append(tournament_player)
            else:
                current_tournament_players.append(tournament_player)
                current_pairing_numbers.add(tournament_player.pairing_number)
        # Holes in the numbering, i.e. numbers that were attributed and
        # since freed. Counted over the players that *have* a number, not
        # the whole field: a player still waiting for one has never held
        # a number, so counting them would report the numbers about to be
        # handed out as deleted — and on the first pairing, where nobody
        # is numbered yet, that means all of them.
        deleted_pairing_numbers = set(
            range(1, len(current_tournament_players) + 1)
        ).difference(current_pairing_numbers)
        settings_updated = (
            tournament.pairing_variation.update_settings_from_deleted_pairing_numbers(
                tournament, deleted_pairing_numbers
            )
        )
        if tournament.pairing_system.pairing_numbers_are_frozen(tournament):
            # The numbering stands: keep it, and number only the players
            # inserted into it or freed from it.
            if (
                not inserted_tournament_players
                and not deleted_pairing_numbers
                and not settings_updated
            ):
                return
            sorted_tournament_players = sorted(
                current_tournament_players, key=attrgetter('pairing_number')
            )
        else:
            sorted_tournament_players = sorted(
                current_tournament_players, key=attrgetter('starting_rank_sort_key')
            )
        # Handing out the numbers for the first time is not an insertion:
        # nobody is being slotted into an existing order, so the pairing
        # settings that address numbers (acceleration rules) must not be
        # shifted — they were written against the numbering about to be
        # created. Shifting them once per player would march a rule for
        # numbers 1-2 clear off the end of the field.
        numbers_already_attributed = bool(current_tournament_players)
        for tournament_player in inserted_tournament_players:
            tournament_player_index = next(
                (
                    index
                    for index, player_ in enumerate(sorted_tournament_players)
                    if player_.starting_rank_sort_key
                    > tournament_player.starting_rank_sort_key
                ),
                len(sorted_tournament_players),
            )
            sorted_tournament_players.insert(tournament_player_index, tournament_player)
            if numbers_already_attributed:
                settings_updated |= tournament.pairing_variation.update_settings_from_added_pairing_number(
                    tournament, tournament_player_index + 1
                )

        tournament_players_by_updated_pairing_number = {
            pairing_number: player
            for pairing_number, player in enumerate(sorted_tournament_players, start=1)
            if pairing_number != player.pairing_number
        }
        if not tournament_players_by_updated_pairing_number:
            return
        for (
            pairing_number,
            tournament_player,
        ) in tournament_players_by_updated_pairing_number.items():
            tournament_player.stored_tournament_player.pairing_number = pairing_number
        if tournament.is_team_tournament:
            # A team tournament's players are synthesised from the team
            # rosters and have no stored tournament_player row to persist
            # to, so their numbering lives in memory only. Skipping the
            # write also keeps the FFE-upload conversion — which runs on a
            # throwaway copy whose database is already closed — from
            # reopening a database that is no longer there.
            return
        with EventDatabase(tournament.event.uniq_id, True) as database:
            for (
                tournament_player
            ) in tournament_players_by_updated_pairing_number.values():
                database.set_tournament_player_pairing_number(
                    tournament_player.stored_tournament_player
                )
            if settings_updated:
                database.set_tournament_pairing_settings(
                    tournament.id, tournament.stored_pairing_settings
                )
