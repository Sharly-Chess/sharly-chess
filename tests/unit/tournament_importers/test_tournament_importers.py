from datetime import date
from pathlib import Path
from unittest import TestCase

import pytest

from data.event import Event
from data.input_output import TournamentImporter
from data.input_output.tournament_importer_options import FileOption
from data.input_output.trf.trf_importer import TrfTournamentImporter
from data.loader import EventLoader
from data.pairings.settings import ColorSeedSetting
from data.tournament import Tournament
from plugins.ffe.ffe_tournament_importers import (
    PapiJsonTournamentImporter,
    PapiTournamentImporter,
)
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from plugins.pairing_acceleration.pairing_variations import BakuSwissVariation
from tests.test_config import TestUtils
from utils.enum import PlayerRatingType, BoardColor, PlayerGender, PlayerTitle, Result

EVENT_ID = 'test-tournament-importers-event'
BASE_PATH = Path(__file__).parent


@pytest.mark.unit
class TournamentImporterTestCase(TestCase):
    event: Event

    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        self.event = EventLoader().load_event(EVENT_ID)

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    def _import_tournament(self, importer: TournamentImporter) -> Tournament:
        tournament_id = importer.load_tournament(self.event)
        self.event = EventLoader().load_event(EVENT_ID)
        return self.event.tournaments_by_id[tournament_id]

    def test_trf_import(self):
        file_path = BASE_PATH / 'trf-import-test.trf'
        importer = TrfTournamentImporter([FileOption(file_path)])
        tournament = self._import_tournament(importer)
        self.assertEqual(tournament.name, 'TRF import test')
        self.assertEqual(tournament.location, 'Sharly-Chess HQ')
        first_day = date(year=2025, month=9, day=13)
        second_day = date(year=2025, month=9, day=14)
        self.assertEqual(tournament.start_date, first_day)
        self.assertEqual(tournament.stop_date, second_day)
        date_by_round = {
            round_: datetime_.date() if datetime_ else None
            for round_, datetime_ in tournament.round_datetimes.items()
        }
        expected_date_by_round = {
            1: first_day,
            2: first_day,
            3: first_day,
            4: second_day,
            5: second_day,
        }
        self.assertEqual(date_by_round, expected_date_by_round)
        self.assertEqual(tournament.rounds, 5)
        self.assertEqual(
            tournament.pairing_settings.get(ColorSeedSetting().id), BoardColor.BLACK
        )
        self.assertEqual(tournament.player_rating_type, PlayerRatingType.NATIONAL)
        self.assertEqual(tournament.pairing_variation.id, BakuSwissVariation().id)

        self.assertEqual(len(tournament.players), 16)
        player = tournament.tournament_players_by_pairing_number.get(1)
        self.assertIsNotNone(player)
        self.assertEqual(player.gender, PlayerGender.MAN)
        self.assertEqual(player.title, PlayerTitle.GRANDMASTER)
        self.assertEqual(player.last_name, 'CARLSEN')
        self.assertEqual(player.first_name, 'Magnus')
        self.assertEqual(player.fide_rating_value, 2840)
        self.assertEqual(player.federation.name, 'NOR')
        self.assertEqual(player.date_of_birth, date(year=1990, month=11, day=30))

        self.assertEqual(player.national_rating_value, 2200)
        ffe_data = FFEUtils.get_player_plugin_data(player)
        self.assertEqual(ffe_data.ffe_licence, PlayerFFELicence.A)
        self.assertEqual(ffe_data.ffe_licence_number, 'D50113')
        self.assertEqual(ffe_data.league, 'IDF')

        results_player = tournament.tournament_players_by_pairing_number[9]
        results = [pairing.result for pairing in results_player.pairings.values()]
        expected_results = [
            Result.LOSS,
            Result.LOSS,
            Result.HALF_POINT_BYE,
            Result.FORFEIT_LOSS,
            Result.PAIRING_ALLOCATED_BYE,
        ]
        self.assertEqual(results, expected_results)

    def test_papi_import(self):
        file_path = BASE_PATH / 'papi-import-test.papi'
        importer = PapiTournamentImporter([FileOption(file_path)])
        tournament = self._import_tournament(importer)
        self.assertEqual(tournament.name, 'Papi import test')
        self.assertEqual(len(tournament.players), 16)

    def test_papi_json_import(self):
        file_path = BASE_PATH / 'papi-json-import-test.json'
        importer = PapiJsonTournamentImporter([FileOption(file_path)])
        tournament = self._import_tournament(importer)
        self.assertEqual(tournament.name, 'Papi JSON import test')
        self.assertEqual(len(tournament.players), 16)
