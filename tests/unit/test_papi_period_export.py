"""The Papi file of one slice of a tournament reported in slices.

The FFE submits each tranche under its own homologation number, as a
Papi "dans lequel on aura préalablement supprimé les rondes avant la
tranche" — so the slice's file holds that slice's rounds, numbered from
1, and names the registration it is submitted under.
"""

import contextlib
from datetime import datetime, timedelta

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredPlayerPeriod,
    StoredTournamentPlayer,
)
from plugins.ffe.papi_converter import PapiConverter
from tests.test_config import TestUtils
from utils.enum import TournamentRating

EVENT_ID = 'test-papi-period-export'
TOURNAMENT_NAME = 'tournament'
PLAYERS = {'ALPHA': 2000, 'BETA': 1900}
LATER_RATINGS = {'ALPHA': 1950, 'BETA': 1975}


@pytest.mark.unit
class TestPeriodPapi:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _setup(self):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 4,
                'multi_period': True,
                'round_datetimes': {
                    round_nb: datetime.now() + timedelta(days=14 * (round_nb - 4))
                    for round_nb in range(1, 5)
                },
                'plugin_data': {'ffe': {'ffe_id': 49943, 'password': 'AAAAAAAAAA'}},
            },
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            database.set_tournament_periods(tournament_id, [3])
            second_period = database.load_tournament_stored_periods(tournament_id)[1]
            assert second_period.id is not None
            database.set_tournament_period_plugin_data(
                second_period.id, {'ffe': {'ffe_id': 49944, 'password': 'BBBBBBBBBB'}}
            )
            for name, rating in PLAYERS.items():
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=name,
                        ratings={TournamentRating.STANDARD.value: {'fide': rating}},
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id, player_id=player_id
                    )
                )
                database.set_player_period(
                    player_id,
                    second_period.id,
                    StoredPlayerPeriod(
                        ratings={
                            TournamentRating.STANDARD.value: {
                                'fide': LATER_RATINGS[name]
                            }
                        }
                    ),
                )
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def test_a_slice_holds_its_own_rounds(self):
        tournament = self._setup()
        papi = PapiConverter().tournament_to_papi_data(
            tournament, period=tournament.periods[1]
        )
        assert papi.variables.rounds == '2'

    def test_a_slice_names_the_registration_it_is_submitted_under(self):
        tournament = self._setup()
        papi = PapiConverter().tournament_to_papi_data(
            tournament, period=tournament.periods[1]
        )
        assert papi.variables.homologation == '49944'

    def test_the_first_slice_is_submitted_under_the_tournament_s_own(self):
        """The FFE publishes the whole tournament there, so the first
        tranche and the tournament share a registration."""
        tournament = self._setup()
        papi = PapiConverter().tournament_to_papi_data(
            tournament, period=tournament.periods[0]
        )
        assert papi.variables.homologation == '49943'

    def test_the_whole_tournament_is_still_converted_in_full(self):
        tournament = self._setup()
        papi = PapiConverter().tournament_to_papi_data(tournament)
        assert papi.variables.rounds == '4'
        assert papi.variables.homologation == '49943'
