"""The consistency check of the players' ratings against the lists."""

import asyncio
from collections import OrderedDict
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
import contextlib

import pytest

from data import rating_check
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from tests.test_config import TestUtils
from utils.enum import PlayerRatingType, Cadence

EVENT_ID = 'test-rating-check'
TOURNAMENT_NAME = 'tournament'
PLAYER_NAME = 'PLAYER'
FIDE_ID = 23456789
STANDARD = Cadence.STANDARD.value


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Drive a coroutine to completion on a loop of its own, out of the
    way of the loops pytest-asyncio and playwright already own."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


@pytest.mark.unit
class TestRatingCheck:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _setup(self, ratings: dict, monkeypatch, listed: dict):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME)
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name=PLAYER_NAME,
                    fide_id=FIDE_ID,
                    ratings={STANDARD: ratings},
                )
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(tournament_id=tournament_id, player_id=player_id)
            )
        monkeypatch.setattr(
            rating_check,
            '_fide_list',
            lambda players: {
                FIDE_ID: StoredPlayer(
                    id=None,
                    last_name=PLAYER_NAME,
                    fide_id=FIDE_ID,
                    ratings={STANDARD: listed},
                )
            },
        )
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return next(iter(self._event.players_by_id.values()))

    def _check(self, player):
        return _run(rating_check.check_ratings(self._event, [player]))

    def test_a_new_list_value_is_proposed(self, monkeypatch):
        player = self._setup(
            {
                'fide': 1800,
                'origins': {'f': {'source': 'fide', 'version': '2026-09-01'}},
            },
            monkeypatch,
            {
                'fide': 1820,
                'origins': {'f': {'source': 'fide', 'version': '2026-10-01'}},
            },
        )
        check = self._check(player)
        assert [row.proposed_rating.value for row in check.changes] == [1820]

    def test_a_new_snapshot_of_the_same_value_is_applied_unasked(self, monkeypatch):
        player = self._setup(
            {
                'fide': 1800,
                'origins': {'f': {'source': 'fide', 'version': '2026-09-01'}},
            },
            monkeypatch,
            {
                'fide': 1800,
                'origins': {'f': {'source': 'fide', 'version': '2026-10-01'}},
            },
        )
        check = self._check(player)
        assert check.changes == [] and check.arbiter_values == []
        [updated] = check.apply(set())
        origin = updated.ratings[Cadence.STANDARD].origins
        assert origin[next(iter(origin))].version == '2026-10-01'

    def test_a_correction_whose_list_value_moved_is_put_to_the_arbiter(
        self, monkeypatch
    ):
        player = self._setup(
            {
                'fide': 1850,
                'origins': {'f': {'source': 'fide', 'original': 1800}},
            },
            monkeypatch,
            {'fide': 1820, 'origins': {'f': {'source': 'fide'}}},
        )
        check = self._check(player)
        assert check.changes == []
        [row] = check.arbiter_values
        assert (row.current_rating.value, row.proposed_rating.value) == (1850, 1820)
        assert check.apply(set()) == []

    def test_a_correction_the_list_does_not_give_is_put_to_the_arbiter(
        self, monkeypatch
    ):
        """The list still gives what it gave when the arbiter corrected
        it: the correction is reported, and kept unless chosen."""
        player = self._setup(
            {
                'fide': 1850,
                'origins': {'f': {'source': 'fide', 'original': 1800}},
            },
            monkeypatch,
            {'fide': 1800, 'origins': {'f': {'source': 'fide'}}},
        )
        check = self._check(player)
        assert check.changes == []
        [row] = check.arbiter_values
        assert (row.current_rating.value, row.proposed_rating.value) == (1850, 1800)
        assert check.apply(set()) == []

    def test_a_correction_the_list_caught_up_with_is_dropped(self, monkeypatch):
        """The list now gives the arbiter's value: the tournament rating
        stays, the official one moves to it, and the correction goes."""
        player = self._setup(
            {
                'fide': 1850,
                'origins': {'f': {'source': 'fide', 'original': 1800}},
            },
            monkeypatch,
            {'fide': 1850, 'origins': {'f': {'source': 'fide'}}},
        )
        check = self._check(player)
        [row] = check.changes
        assert (row.current_rating.value, row.proposed_rating.value) == (1850, 1850)
        assert row.current_official is not None and row.proposed_official is not None
        assert (row.current_official.value, row.proposed_official.value) == (
            1800,
            1850,
        )
        [updated] = check.apply({player.id})
        assert not updated.ratings[Cadence.STANDARD].is_overridden(
            PlayerRatingType.FIDE
        )

    def test_a_typed_value_no_list_gives_is_offered_the_prescribed_one(
        self, monkeypatch
    ):
        """No list rates the player, so what the lists give is the rating
        the federation prescribes (the FFE's, in this event): the arbiter
        may take it in place of the value typed."""
        player = self._setup({'manual': 1500}, monkeypatch, {})
        check = self._check(player)
        [row] = check.arbiter_values
        assert row.changes_rating
        assert (row.proposed_rating.value, row.proposed_rating.prescribed) == (
            1399,
            True,
        )
        [updated] = check.apply({player.id})
        assert updated.ratings[Cadence.STANDARD].manual is None

    def _list_national(self, player, monkeypatch, listed: dict) -> None:
        """Make the player's national list give them *listed*."""
        from data.input_output import DataSourceManager

        player.stored_player.national_id = 'A12345'
        player.stored_player.national_source = 'ffe'
        data_source = SimpleNamespace(
            national_source_id='ffe',
            check_player_match=lambda player, match: True,
        )
        monkeypatch.setattr(
            DataSourceManager, 'national_source', lambda self, source: data_source
        )

        async def match_list(data_source, players):
            return [
                StoredPlayer(id=None, last_name=PLAYER_NAME, ratings={STANDARD: listed})
            ]

        monkeypatch.setattr(rating_check, '_match_list', match_list)

    def test_a_value_the_national_list_types_is_proposed(self, monkeypatch):
        player = self._setup({}, monkeypatch, {})
        self._list_national(player, monkeypatch, {'manual': 1450})
        check = self._check(player)
        assert check.arbiter_values == []
        [row] = check.changes
        assert (row.current_rating.prescribed, row.proposed_rating.value) == (
            True,
            1450,
        )
        [updated] = check.apply({player.id})
        assert updated.ratings[Cadence.STANDARD].manual == 1450

    def test_a_value_the_national_list_types_is_not_the_arbiters(self, monkeypatch):
        player = self._setup({'manual': 1450}, monkeypatch, {})
        self._list_national(player, monkeypatch, {'manual': 1450})
        check = self._check(player)
        assert check.changes == [] and check.arbiter_values == []

    def test_a_value_the_national_list_types_as_prescribed_is_left_out(
        self, monkeypatch
    ):
        player = self._setup({}, monkeypatch, {})
        self._list_national(player, monkeypatch, {'manual': 1399})
        check = self._check(player)
        assert check.changes == [] and check.arbiter_values == []

    def test_a_typed_value_superseded_by_a_list_is_put_to_the_arbiter(
        self, monkeypatch
    ):
        player = self._setup(
            {'manual': 1500},
            monkeypatch,
            {'fide': 1875, 'origins': {'f': {'source': 'fide'}}},
        )
        check = self._check(player)
        [row] = check.arbiter_values
        assert str(row.proposed_rating) == '1875\xa0F'


@pytest.mark.unit
class TestAutomaticCheck:
    """When the check behind the players tab banner is made again."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        self.calls = 0
        self.now = 1000.0
        self.versions = {'ffe': 1.0}
        self.reads_online = True
        self.event: Any = SimpleNamespace(uniq_id='event', players_by_id={})

        async def check_ratings(event, players):
            self.calls += 1
            return SimpleNamespace(attention_count=self.calls)

        monkeypatch.setattr(rating_check, 'check_ratings', check_ratings)
        monkeypatch.setattr(rating_check, 'list_versions', lambda: self.versions)
        monkeypatch.setattr(rating_check, 'monotonic', lambda: self.now)
        monkeypatch.setattr(rating_check, '_reads_online', lambda _: self.reads_online)
        monkeypatch.setattr(rating_check, '_automatic_checks', OrderedDict())

    def _check(self) -> int:
        return _run(rating_check.automatic_check(self.event))

    def test_the_count_is_kept_between_visits(self):
        assert self._check() == 1
        self.now += rating_check._AUTOMATIC_CHECK_LIFETIME - 1
        assert self._check() == 1

    def test_the_check_runs_out(self):
        self._check()
        self.now += rating_check._AUTOMATIC_CHECK_LIFETIME
        assert self._check() == 2

    def test_a_changed_list_is_checked_again(self):
        self._check()
        self.versions = {'ffe': 2.0}
        assert self._check() == 2

    def test_a_forgotten_check_is_made_again(self):
        self._check()
        rating_check.forget_automatic_check(self.event)
        assert self._check() == 2

    def test_an_edit_does_not_ask_the_server_again(self):
        self._check()
        rating_check.player_edited(self.event)
        assert self._check() == 1

    def test_an_edit_is_checked_again_when_no_server_is_asked(self):
        self.reads_online = False
        self._check()
        rating_check.player_edited(self.event)
        assert self._check() == 2


@pytest.mark.unit
def test_the_list_versions_follow_what_the_source_published(monkeypatch):
    def database(published_at, updated_at):
        return SimpleNamespace(
            id=f'list-{published_at}',
            exists=lambda: True,
            updated_at_timestamp=updated_at,
            stored_source_database=SimpleNamespace(published_at=published_at),
        )

    manager = SimpleNamespace(objects=lambda: [database(5.0, 9.0), database(None, 9.0)])
    monkeypatch.setattr(
        'database.sqlite.local_source_database.LocalSourceDatabaseManager',
        lambda: manager,
    )
    assert rating_check.list_versions() == {'list-5.0': 5.0, 'list-None': 9.0}
