from pathlib import Path
from unittest import TestCase

import pytest

from data.event import Event
from data.input_output.tournament_importer_options import FileOption
from data.input_output.tournament_importers import TrfTournamentImporter
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from plugins.ffe.ffe_tournament_importers import (
    PapiJsonTournamentImporter,
    PapiTournamentImporter,
)
from tests.test_config import TestUtils


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

    def assert_tournament_imported(self, tournament_name: str, player_count: int):
        with EventDatabase(self.event.uniq_id) as database:
            database.execute(
                'SELECT `id` FROM `tournament` WHERE `name` = ?',
                (tournament_name,),
            )
            row = database.fetchone()
            self.assertIn('id', row)
            database.execute(
                'SELECT COUNT(*) AS `player_count` '
                'FROM `tournament_player` WHERE `tournament_id` = ?',
                (row['id'],),
            )
            self.assertEqual(database.fetchone()['player_count'], player_count)

    def test_trf_import(self):
        file_path = BASE_PATH / 'trf-import-test.trf'
        importer = TrfTournamentImporter([FileOption(file_path)])
        importer.load_tournament(self.event)
        self.assert_tournament_imported('TRF import test', 16)

    def test_papi_import(self):
        file_path = BASE_PATH / 'papi-import-test.papi'
        importer = PapiTournamentImporter([FileOption(file_path)])
        importer.load_tournament(self.event)
        self.assert_tournament_imported('Papi import test', 16)

    def test_papi_json_import(self):
        file_path = BASE_PATH / 'papi-json-import-test.json'
        importer = PapiJsonTournamentImporter([FileOption(file_path)])
        importer.load_tournament(self.event)
        self.assert_tournament_imported('Papi JSON import test', 16)
