"""Roster cap enforcement when importing players into a team event.

A team tournament may cap its rosters. The import fills each team in
row order and flags the rows the team has no room for, counting the
players the team already holds unless the import empties it first.
A flagged row keeps its resolved player, so the preview can still name
who was turned away.
"""

import asyncio
import contextlib
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
from utils.enum import EventType
from web.controllers.admin.player_admin_controller import PlayerAdminController

EVENT_ID = 'test-player-import-roster-cap'
TOURNAMENT_NAME = 'team-tournament'
ROSTER_MAX_SIZE = 2


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
class TeamImportRosterCapTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 3,
                'team_player_count': 1,
                'roster_max_size': ROSTER_MAX_SIZE,
                'pairing': 'TEAM_SWISS_STANDARD',
            },
        )

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _load_event(self):
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        return EventLoader().load_event(EVENT_ID)

    def _add_team(self, name: str, *, assigned: bool, player_count: int) -> None:
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = None
            if assigned:
                tournament_id = next(
                    tournament.id
                    for tournament in database.load_stored_tournaments()
                    if tournament.name == TOURNAMENT_NAME
                )
            team_id = database.add_stored_team(
                StoredTeam(id=None, name=name, tournament_id=tournament_id)
            )
            for index in range(player_count):
                database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'{name} {index}',
                        team_id=team_id,
                        team_index=index,
                    )
                )

    def _import(
        self, team_names: list[str], *, overwrite: bool = False, in_tournament=False
    ) -> tuple[set[int], dict[int, dict[str, str]]]:
        event = self._load_event()
        by_id = {
            column.id: column for column in PlayerDatasheetColumnHandler(event).columns
        }
        used = [by_id['last_name'], by_id['team']]
        content = {
            'last_name': [f'IMPORTED {index}' for index in range(len(team_names))],
            'team': team_names,
        }
        web_context = stub_web_context(event)
        if in_tournament:
            web_context.admin_tournament = next(iter(event.tournaments_by_id.values()))
        stored_players, errors, __ = _run(
            PlayerAdminController._get_imported_stored_players(
                web_context, used, content, overwrite
            )
        )
        return set(stored_players) - set(errors), errors

    def test_rows_beyond_the_cap_are_rejected_in_row_order(self):
        self._add_team('A', assigned=True, player_count=0)
        kept, errors = self._import(['A', 'A', 'A', 'B'])
        assert kept == {0, 1, 3}
        assert set(errors[2]) == {'team'}

    def test_a_rejected_row_keeps_its_player_for_the_preview(self):
        self._add_team('A', assigned=True, player_count=ROSTER_MAX_SIZE)
        event = self._load_event()
        by_id = {
            column.id: column for column in PlayerDatasheetColumnHandler(event).columns
        }
        stored_players, errors, __ = _run(
            PlayerAdminController._get_imported_stored_players(
                stub_web_context(event),
                [by_id['last_name'], by_id['team']],
                {'last_name': ['REJECTED'], 'team': ['A']},
                False,
            )
        )
        assert set(errors[0]) == {'team'}
        assert stored_players[0].last_name == 'REJECTED'

    def test_existing_roster_players_count_towards_the_cap(self):
        self._add_team('A', assigned=True, player_count=1)
        kept, __ = self._import(['A', 'A'])
        assert kept == {0}

    def test_overwriting_empties_the_rosters_first(self):
        self._add_team('A', assigned=True, player_count=ROSTER_MAX_SIZE)
        kept, __ = self._import(['A', 'A'], overwrite=True)
        assert kept == {0, 1}

    def test_overwriting_still_caps_the_refilled_rosters(self):
        self._add_team('A', assigned=True, player_count=ROSTER_MAX_SIZE)
        kept, errors = self._import(['A', 'A', 'A'], overwrite=True)
        assert kept == {0, 1}
        assert set(errors[2]) == {'team'}

    def test_an_unassigned_team_has_no_cap(self):
        self._add_team('A', assigned=False, player_count=ROSTER_MAX_SIZE)
        kept, __ = self._import(['A', 'A'])
        assert kept == {0, 1}

    def test_a_team_created_in_a_tournament_takes_its_cap(self):
        kept, __ = self._import(['NEW', 'NEW', 'NEW'], in_tournament=True)
        assert kept == {0, 1}

    def test_a_team_created_at_event_level_has_no_cap(self):
        kept, __ = self._import(['NEW', 'NEW', 'NEW'])
        assert kept == {0, 1, 2}
