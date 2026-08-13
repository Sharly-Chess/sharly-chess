"""The migration that puts the points at the head of saved tie-break sets.

Sets saved before the points became a ranking criterion list only what
came after the score. Applying one of those to a tournament would rank
the field on tie-breaks alone, so the migration gives each set the
criterion back.
"""

import json

import pytest

from common.sharly_chess_config import SharlyChessConfig
from data.loader import EventLoader
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredTieBreakSet
from database.sqlite.config.migrations.m013_points_in_tie_break_sets import (
    Migration,
    POINTS_TYPE,
)
from tests.test_config import TestUtils
from web.controllers.admin.tournament_admin_controller import (
    TournamentAdminController,
)

BUCHHOLZ = {'type': 'BUCHHOLZ', 'options': {}}
WINS = {'type': 'WINS', 'options': {}}


def _add_set(name: str, tie_breaks: list[dict]) -> int:
    with ConfigDatabase(True) as database:
        return database.add_stored_tie_break_set(
            StoredTieBreakSet(
                id=None,
                name=name,
                pairing_system_id='SWISS',
                stored_tie_breaks=tie_breaks,
            )
        )


def _tie_breaks_of(set_id: int) -> list[dict]:
    with ConfigDatabase() as database:
        database.execute(
            'SELECT `stored_tie_breaks` FROM `tie_break_set` WHERE `id` = ?', (set_id,)
        )
        return json.loads(database.fetchone()['stored_tie_breaks'])


def _run(direction: str) -> None:
    with ConfigDatabase(True) as database:
        getattr(Migration(database), direction)()


@pytest.mark.unit
class TestPointsInTieBreakSets:
    @pytest.fixture(autouse=True)
    def _cleanup(self):
        created: list[int] = []
        self.created = created
        yield
        with ConfigDatabase(True) as database:
            for set_id in created:
                database.delete_stored_tie_break_set(set_id)

    def _make(self, name: str, tie_breaks: list[dict]) -> int:
        set_id = _add_set(name, tie_breaks)
        self.created.append(set_id)
        return set_id

    def test_the_points_are_added_at_the_head(self):
        set_id = self._make('test-migration-plain', [BUCHHOLZ, WINS])
        _run('forward')
        assert _tie_breaks_of(set_id) == [
            {'type': POINTS_TYPE, 'options': {}},
            BUCHHOLZ,
            WINS,
        ]

    def test_a_set_that_already_ranks_on_points_is_left_alone(self):
        original = [BUCHHOLZ, {'type': POINTS_TYPE, 'options': {}}]
        set_id = self._make('test-migration-has-points', original)
        _run('forward')
        # Not moved to the front: where the arbiter put it is a choice.
        assert _tie_breaks_of(set_id) == original

    def test_running_it_twice_changes_nothing_more(self):
        set_id = self._make('test-migration-twice', [BUCHHOLZ])
        _run('forward')
        once = _tie_breaks_of(set_id)
        _run('forward')
        assert _tie_breaks_of(set_id) == once

    def test_the_rollback_takes_the_points_back_out(self):
        set_id = self._make('test-migration-rollback', [BUCHHOLZ, WINS])
        _run('forward')
        _run('backward')
        assert _tie_breaks_of(set_id) == [BUCHHOLZ, WINS]


@pytest.mark.unit
class TestSetsModalGrouping:
    """The sets are global to the installation, so the management modal
    has to list one saved for a system the open event does not offer —
    a team set while an individual event is open, or the reverse."""

    EVENT_ID = 'test-tie-break-sets-modal'

    @pytest.fixture
    def event(self):
        TestUtils.create_event(self.EVENT_ID)
        TestUtils.create_tournament(self.EVENT_ID, 'tournament')
        yield EventLoader().load_event(self.EVENT_ID)
        TestUtils.delete_event(self.EVENT_ID)

    def test_a_set_from_another_system_is_still_listed(self, event):
        set_id = _add_set('test-modal-team-set', [BUCHHOLZ])
        with ConfigDatabase(True) as database:
            database.execute(
                'UPDATE `tie_break_set` SET `pairing_system_id` = ? WHERE `id` = ?',
                ('TEAM_SWISS', set_id),
            )
        SharlyChessConfig().load_and_set_env()
        try:
            context = TournamentAdminController._tie_break_sets_modal_context(event)
            groups = context['custom_sets_by_pairing_system_name']
            listed = {
                tie_break_set.name for sets in groups.values() for tie_break_set in sets
            }
            assert 'test-modal-team-set' in listed
        finally:
            with ConfigDatabase(True) as database:
                database.delete_stored_tie_break_set(set_id)
            SharlyChessConfig().load_and_set_env()
