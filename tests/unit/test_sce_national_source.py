"""The source of a player's national id (the list it belongs to) through the
Sharly-Chess.com sync.

The source travels with the id. A Sharly-Chess.com that does not know sources
sends none: that must neither read as a change nor clear the local source.
"""

import dataclasses
from typing import Any

import pytest

from database.sqlite.event.event_database import EventDatabase
from plugins.sce.sce_data import SCEPlayerPluginData, SCEPlayerSyncData
from tests.unit.test_sce_multi_computer_sync import (
    EVENT_UNIQ_ID,
    LOCAL_SCE_TOURNAMENT_ID,
    MultiComputerSyncTestCase,
    OTHER_LOCAL_SCE_TOURNAMENT_ID,
    event_data,
    registration,
)


class NationalSourceSyncTestCase(MultiComputerSyncTestCase):
    def add_sourced_player(
        self,
        national_id: str = '105483B',
        national_source: str = 'ecf',
        synced_national_id: str = '105483B',
        synced_national_source: str | None = None,
    ) -> int:
        """A linked player whose national id comes from `national_source`,
        last synchronised with `synced_national_id`."""
        base = dataclasses.replace(
            self.sync_data(LOCAL_SCE_TOURNAMENT_ID),
            national_id=synced_national_id,
            national_source=synced_national_source,
        )
        player_id = self.add_player(
            'SCE-A',
            plugin_data=SCEPlayerPluginData(
                id='SCE-A', last_sync_data=base
            ).to_stored_value(),
        )
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            database.execute(
                'UPDATE `player` SET `national_id` = ?, `national_source` = ? '
                'WHERE `id` = ?',
                (national_id, national_source, player_id),
            )
        return player_id

    def national_id_and_source(self, player_id: int) -> tuple[str | None, str | None]:
        stored_player = self.player(player_id).stored_player
        return stored_player.national_id, stored_player.national_source

    @staticmethod
    def sce(**changes: Any) -> dict:
        reg = registration('SCE-A')
        reg['national_id'] = '105483B'
        reg.update(changes)
        return event_data(
            {LOCAL_SCE_TOURNAMENT_ID: [reg], OTHER_LOCAL_SCE_TOURNAMENT_ID: []}
        )


@pytest.mark.unit
class TestSharlyChessComWithoutSources(NationalSourceSyncTestCase):
    """A Sharly-Chess.com that predates sources: its registrations have none."""

    def test_local_source_is_not_sent_again_and_again(self) -> None:
        player_id = self.add_sourced_player()

        for _ in range(3):
            self.harness.run(self.sce())

        assert self.harness.ops == []
        assert self.national_id_and_source(player_id) == ('105483B', 'ecf')

    def test_change_pulled_from_sce_keeps_the_local_source(self) -> None:
        player_id = self.add_sourced_player()

        self.harness.run(self.sce(club='New club'))

        assert self.player(player_id).club.name == 'New club'
        assert self.national_id_and_source(player_id) == ('105483B', 'ecf')
        assert self.harness.ops == []

    def test_national_id_pulled_from_sce_comes_from_no_known_list(self) -> None:
        player_id = self.add_sourced_player()

        self.harness.run(self.sce(national_id='999999Z'))

        assert self.national_id_and_source(player_id) == ('999999Z', None)


@pytest.mark.unit
class TestSharlyChessComWithSources(NationalSourceSyncTestCase):
    def test_national_id_pulled_from_sce_brings_its_source(self) -> None:
        player_id = self.add_sourced_player()

        self.harness.run(self.sce(national_id='135795', national_source='fsi'))

        assert self.national_id_and_source(player_id) == ('135795', 'fsi')

    def test_local_national_id_change_is_sent_with_its_source(self) -> None:
        self.add_sourced_player(national_id='200002B', national_source='ecf')

        self.harness.run(self.sce())

        [op] = self.harness.ops_of('update')
        assert op['data'] == {'national_id': '200002B', 'national_source': 'ecf'}


@pytest.mark.unit
class TestSyncDataComparison:
    def test_source_alone_is_not_a_change(self) -> None:
        local = SCEPlayerSyncData(
            tournament_id='T1', last_name='DOE', national_id='A1', national_source='ecf'
        )
        remote = dataclasses.replace(local, national_source=None)

        assert local == remote
        assert local.changed_sce_data(remote) == {}

    def test_merge_keeps_the_source_of_the_id_it_keeps(self) -> None:
        ref = SCEPlayerSyncData(tournament_id='T1', last_name='DOE', national_id='A1')
        local = dataclasses.replace(ref, club='Local club')
        remote = dataclasses.replace(ref, national_id='B2', national_source='fsi')

        merged = local.merge_with_other_sync_data(remote, ref)

        assert (merged.club, merged.national_id, merged.national_source) == (
            'Local club',
            'B2',
            'fsi',
        )


@pytest.mark.unit
class TestRegistrationWithoutYearOfBirth(NationalSourceSyncTestCase):
    """Some lists have no years of birth (the ECF's): a player picked from one
    comes without."""

    def test_is_read_with_no_year_of_birth(self) -> None:
        reg = registration('SCE-A')
        reg['year_of_birth'] = None

        sync_data = SCEPlayerSyncData.from_sce_data(
            self.load_event(), reg, LOCAL_SCE_TOURNAMENT_ID
        )

        assert sync_data.year_of_birth is None
