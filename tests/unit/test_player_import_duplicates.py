"""Duplicate detection when importing players into a team event.

A team event imports at the event level — a team, not a tournament,
places its players — so the import has no tournament to compare against.
The clash it has to find is with the *event's* players, including those
whose team isn't assigned to any tournament.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from unittest import TestCase
import pytest

from data.columns.handlers import PlayerDatasheetColumnHandler
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTeam
from tests.test_config import TestUtils
from web.controllers.admin.player_admin_controller import PlayerAdminController
from utils.enum import EventType

EVENT_ID = 'test-player-import-duplicates'
TOURNAMENT_NAME = 'team-tournament'


@dataclass
class StubWebContext:
    """The import only reads these three things off the context."""

    admin_event: Any
    admin_tournament: Any = None
    admin_data_source: Any = None

    def get_admin_event(self):
        return self.admin_event


def stub_web_context(event: Any) -> Any:
    """Typed as Any: the stub carries only the three attributes the
    import reads, not the whole PlayerAdminWebContext surface."""
    return StubWebContext(admin_event=event)


def _run(coroutine) -> Any:
    """Drive a coroutine to completion on a loop of its own.

    The suite runs under pytest-asyncio's auto mode alongside the
    playwright fixtures, both of which already own a loop here; a private
    loop on a worker thread keeps this test out of that argument.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


@pytest.mark.unit
class TeamImportDuplicateTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 3,
                'team_player_count': 1,
                'pairing': 'TEAM_SWISS_STANDARD',
            },
        )

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _load_event(self):
        try:
            EventLoader.unload_event(EVENT_ID)
        except KeyError:
            pass
        return EventLoader().load_event(EVENT_ID)

    def _add_player(self, *, assigned_to_tournament: bool, fide_id: int) -> None:
        """Add a player through a team, the way a team event holds them."""
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = None
            if assigned_to_tournament:
                tournament_id = next(
                    tournament.id
                    for tournament in database.load_stored_tournaments()
                    if tournament.name == TOURNAMENT_NAME
                )
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'Team {fide_id}',
                    tournament_id=tournament_id,
                )
            )
            database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name='EXISTING',
                    first_name='Player',
                    fide_id=fide_id,
                    team_id=team_id,
                    team_index=0,
                )
            )

    def _duplicated_indexes(self, fide_id: int, overwrite: bool) -> set[int]:
        event = self._load_event()
        columns = PlayerDatasheetColumnHandler(event).columns
        by_id = {column.id: column for column in columns}
        used = [by_id['last_name'], by_id['fide_id']]
        content = {'last_name': ['IMPORTED'], 'fide_id': [str(fide_id)]}
        __, __, duplicated = _run(
            PlayerAdminController._get_imported_stored_players(
                stub_web_context(event), used, content, overwrite
            )
        )
        return duplicated

    def test_duplicate_found_when_the_team_has_a_tournament(self):
        self._add_player(assigned_to_tournament=True, fide_id=111)
        assert self._duplicated_indexes(111, overwrite=False) == {0}

    def test_duplicate_found_when_the_team_has_no_tournament(self):
        self._add_player(assigned_to_tournament=False, fide_id=222)
        assert self._duplicated_indexes(222, overwrite=False) == {0}

    def test_a_new_player_is_not_flagged(self):
        self._add_player(assigned_to_tournament=False, fide_id=333)
        assert self._duplicated_indexes(444, overwrite=False) == set()

    def test_nothing_clashes_when_everything_is_deleted_first(self):
        self._add_player(assigned_to_tournament=False, fide_id=555)
        assert self._duplicated_indexes(555, overwrite=True) == set()
