"""FFE leagues Sharly-Chess.com does not know, such as "EXP".

FFE data holds values outside the regional leagues. They are never sent to
Sharly-Chess.com, and a synchronisation never clears them locally.
"""

import dataclasses
import json
from typing import Any

import pytest

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer
from plugins.ffe import PLUGIN_NAME as FFE_PLUGIN_NAME
from plugins.ffe.ffe import FfePlugin
from plugins.ffe.utils import (
    FFEUtils,
    FfePlayerPluginData,
    PlayerFFELicence,
    regional_league,
)
from plugins.sce import PLUGIN_NAME as SCE_PLUGIN_NAME
from plugins.sce.sce_data import SCEPlayerPluginData, SCEPlayerSyncData
from tests.unit.test_sce_multi_computer_sync import (
    EVENT_UNIQ_ID,
    LOCAL_SCE_TOURNAMENT_ID,
    MultiComputerSyncTestCase,
    OTHER_LOCAL_SCE_TOURNAMENT_ID,
    event_data,
    registration,
)


@pytest.mark.unit
class TestRegionalLeague:
    @pytest.mark.parametrize(
        ('league', 'expected'),
        [
            (None, None),
            ('', None),
            ('IDF', 'IDF'),
            ('idf', 'IDF'),
            (' BRE ', 'BRE'),
            ('EXP', None),
            ('XYZ', None),
        ],
    )
    def test_league_is_kept_only_when_regional(
        self, league: str | None, expected: str | None
    ) -> None:
        assert regional_league(league) == expected


def stored_player(league: str | None) -> StoredPlayer:
    return StoredPlayer(
        id=None,
        last_name='LOCAL',
        plugin_data={
            FFE_PLUGIN_NAME: FfePlayerPluginData(
                ffe_licence=PlayerFFELicence.NONE, league=league
            ).to_stored_value()
        },
    )


def stored_league(player: StoredPlayer) -> str | None:
    return FfePlayerPluginData.from_stored_value(
        player.plugin_data[FFE_PLUGIN_NAME]
    ).league


@pytest.mark.unit
class TestLeagueFromSCE:
    @pytest.mark.parametrize(
        ('local', 'incoming', 'expected'),
        [
            ('EXP', None, 'EXP'),
            ('EXP', 'BRE', 'BRE'),
            ('IDF', None, None),
            ('IDF', 'BRE', 'BRE'),
            (None, 'BRE', 'BRE'),
            (None, None, None),
        ],
    )
    def test_unknown_local_league_is_only_replaced_by_a_known_one(
        self, local: str | None, incoming: str | None, expected: str | None
    ) -> None:
        player = stored_player(local)
        sync_data = SCEPlayerSyncData(
            tournament_id='T1', last_name='LOCAL', ffe_league=incoming
        )

        FfePlugin().augment_stored_player_from_sce_player_sync_data(
            event=None,
            stored_player=player,
            sync_data=sync_data,
            database=None,
        )

        assert stored_league(player) == expected

    def test_unknown_league_from_sce_is_read_as_none(self) -> None:
        sync_data = SCEPlayerSyncData(tournament_id='T1', last_name='LOCAL')

        FfePlugin().augment_sce_player_sync_data_from_sce_data(
            sce_data={
                'national_id': None,
                'ffe_licence_type': None,
                'ffe_league': 'EXP',
            },
            sync_data=sync_data,
        )

        assert sync_data.ffe_league is None


class FFELeagueSyncTestCase(MultiComputerSyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_event = database.load_stored_event()
            if FFE_PLUGIN_NAME not in stored_event.enabled_plugins:
                stored_event.enabled_plugins = [
                    *stored_event.enabled_plugins,
                    FFE_PLUGIN_NAME,
                ]
            database.update_stored_event(stored_event)

    def add_league_player(
        self, league: str | None, synced_league: str | None = None
    ) -> int:
        """A linked player whose local league is `league`, last synchronised
        with `synced_league`."""
        base = dataclasses.replace(
            self.sync_data(LOCAL_SCE_TOURNAMENT_ID), ffe_league=synced_league
        )
        player_id = self.add_player('SCE-A')
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            database.execute(
                'UPDATE `player` SET `plugin_data` = ? WHERE `id` = ?',
                (
                    json.dumps(
                        {
                            SCE_PLUGIN_NAME: SCEPlayerPluginData(
                                id='SCE-A', last_sync_data=base
                            ).to_stored_value(),
                            FFE_PLUGIN_NAME: FfePlayerPluginData(
                                ffe_licence=PlayerFFELicence.NONE, league=league
                            ).to_stored_value(),
                        }
                    ),
                    player_id,
                ),
            )
        return player_id

    def local_league(self, player_id: int) -> str | None:
        return FFEUtils.get_player_plugin_data(self.player(player_id)).league

    @staticmethod
    def sce(**changes: Any) -> dict:
        reg = registration('SCE-A')
        reg.update(changes)
        return event_data(
            {LOCAL_SCE_TOURNAMENT_ID: [reg], OTHER_LOCAL_SCE_TOURNAMENT_ID: []}
        )


@pytest.mark.unit
class TestUnknownLeagueSync(FFELeagueSyncTestCase):
    def test_unknown_local_league_is_not_sent(self) -> None:
        player_id = self.add_league_player('EXP')

        self.harness.run(self.sce())

        assert self.harness.ops == []
        assert self.local_league(player_id) == 'EXP'

    def test_unknown_local_league_survives_repeated_syncs(self) -> None:
        player_id = self.add_league_player('EXP')

        for _ in range(3):
            self.harness.run(self.sce())

        assert self.harness.ops == []
        assert self.local_league(player_id) == 'EXP'

    def test_unknown_local_league_survives_a_change_pulled_from_sce(self) -> None:
        player_id = self.add_league_player('EXP')

        self.harness.run(self.sce(club='New club'))

        player = self.player(player_id)
        assert player.club.name == 'New club'
        assert self.local_league(player_id) == 'EXP'
        assert self.harness.ops == []

    def test_known_league_from_sce_replaces_an_unknown_local_one(self) -> None:
        player_id = self.add_league_player('EXP')

        self.harness.run(self.sce(ffe_league='BRE'))

        assert self.local_league(player_id) == 'BRE'
        assert self.harness.ops == []

    def test_unknown_league_on_sce_is_read_as_none(self) -> None:
        player_id = self.add_league_player(None)

        self.harness.run(self.sce(ffe_league='EXP'))

        assert self.harness.ops == []
        assert self.local_league(player_id) is None

    def test_local_known_league_is_sent(self) -> None:
        self.add_league_player('IDF')

        self.harness.run(self.sce())

        updates = self.harness.ops_of('update')
        assert len(updates) == 1
        assert updates[0]['data'] == {'ffe_league': 'IDF'}

    def test_known_league_replaced_by_unknown_one_clears_it_on_sce(self) -> None:
        """A player leaving the regional leagues has none on SC.com either."""
        player_id = self.add_league_player('EXP', synced_league='IDF')

        self.harness.run(self.sce(ffe_league='IDF'))

        updates = self.harness.ops_of('update')
        assert len(updates) == 1
        assert updates[0]['data'] == {'ffe_league': None}
        assert self.local_league(player_id) == 'EXP'
