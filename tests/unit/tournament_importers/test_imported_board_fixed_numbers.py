import json

import pytest

from common import BASE_DIR
from data.input_output.tournament_importer_options import FileOption
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from plugins.ffe.ffe_tournament_importers import PapiJsonTournamentImporter
from tests.test_config import TestUtils


@pytest.mark.unit
def test_an_imported_tournament_freezes_the_fixed_numbers_of_its_boards(
    tmp_path,
) -> None:
    papi = json.loads((BASE_DIR / 'tests' / 'json' / 'tec-swiss.json').read_text())
    papi['players'][0]['fixedBoard'] = 7
    papi['players'][1]['fixedBoard'] = 9
    json_path = tmp_path / 'fixed.json'
    json_path.write_text(json.dumps(papi))
    uniq_id = 'test-imported-board-fixed-numbers'
    TestUtils.create_event(uniq_id)
    try:
        TestUtils.create_tournament(uniq_id, 'Swiss')
        event = EventLoader().load_event(uniq_id)
        PapiJsonTournamentImporter([FileOption(json_path)]).load_tournament(
            event, event.tournaments_by_name['Swiss']
        )
        EventLoader.unload_event(uniq_id)
        event = EventLoader().load_event(uniq_id)
        tournament = event.tournaments_by_name['Swiss']
        boards = list(tournament.boards_by_id.values())
        assert boards
        assert all(
            board.stored_board.fixed_number == (board.live_fixed_number or 0)
            for board in boards
        )
        assert {board.stored_board.fixed_number for board in boards} >= {7, 9}
    finally:
        EventDatabase(uniq_id).delete()
