from operator import attrgetter

from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.pairing_acceleration.pairing_settings import (
    GroupA2GroupsSetting,
    GroupB2GroupsSetting,
    GroupA3GroupsSetting,
    GroupB3GroupsSetting,
    GroupC3GroupsSetting,
)


class PairingAccelerationUtils:
    @classmethod
    def set_pairing_settings_from_rating_threshold(
        cls, tournament: Tournament, rating_threshold: int
    ):
        tournament.set_tournament_players_pairing_numbers()
        sorted_players = sorted(tournament.tournament_players, key=attrgetter('rating'))
        max_a = next(
            (
                player.pairing_number
                for player in sorted_players
                if player.rating >= rating_threshold
            ),
            None,
        )
        if not max_a:
            return
        tournament.stored_tournament.pairing_settings = {
            GroupA2GroupsSetting().id: (1, max_a),
            GroupB2GroupsSetting().id: (max_a + 1, tournament.player_count),
        }
        with EventDatabase(tournament.event.uniq_id, True) as database:
            database.set_tournament_pairing_settings(
                tournament.id, tournament.stored_pairing_settings
            )

    @classmethod
    def set_pairing_settings_from_dual_rating_thresholds(
        cls,
        tournament: Tournament,
        upper_rating_threshold: int,
        lower_rating_threshold: int,
    ):
        tournament.set_tournament_players_pairing_numbers()
        sorted_players = sorted(tournament.tournament_players, key=attrgetter('rating'))
        max_a = next(
            (
                player.pairing_number
                for player in sorted_players
                if player.rating >= upper_rating_threshold
            ),
            None,
        )
        max_b = next(
            (
                player.pairing_number
                for player in sorted_players
                if player.rating >= lower_rating_threshold
            ),
            None,
        )
        if not max_a or not max_b:
            return
        tournament.stored_tournament.pairing_settings |= {
            GroupA3GroupsSetting().id: (1, max_a),
            GroupB3GroupsSetting().id: (max_a + 1, max_b),
            GroupC3GroupsSetting().id: (max_b + 1, tournament.player_count),
        }
        with EventDatabase(tournament.event.uniq_id, True) as database:
            database.set_tournament_pairing_settings(
                tournament.id, tournament.stored_pairing_settings
            )
