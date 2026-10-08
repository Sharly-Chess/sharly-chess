"""The Sharly-Chess.com transfer modal, rendered in this process.

A player removed on Sharly-Chess.com after playing waits for the arbiter,
who withdraws them or keeps them; conflicts no longer stop the
synchronisation.
"""

import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser, AdvancedTag
from litestar.testing import TestClient

from data.player import TournamentPlayer
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPairing,
    StoredPlayer,
    StoredTournamentPlayer,
)
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce import SCEPlugin
from plugins.sce.sce_data import (
    SCEEventPluginData,
    SCEPlayerPluginData,
    SCETokens,
    SCETournamentPluginData,
    SCETournamentSyncData,
)
from plugins.sce.utils import SCEUtils
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-sce-removed-players-http'
TOURNAMENT_NAME = 'test-sce-removed-players-http-tournament'
ROUNDS = 7

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)
HTMX = {'HX-Request': 'true'}


def add_player(tournament_id: int, last_name: str, plugin_data: dict) -> int:
    with EventDatabase(EVENT_ID, write=True) as database:
        player_id = database.add_stored_player(
            StoredPlayer(
                id=None,
                last_name=last_name,
                first_name='Player',
                year_of_birth=1990,
                federation='FRA',
                plugin_data={PLUGIN_NAME: plugin_data},
            )
        )
        database.add_stored_tournament_player(
            StoredTournamentPlayer(player_id=player_id, tournament_id=tournament_id)
        )
        database.add_stored_pairing(
            StoredPairing(
                tournament_id=tournament_id,
                player_id=player_id,
                round_=1,
                result=Result.PAIRING_ALLOCATED_BYE.value,
                board_id=None,
            )
        )
    return player_id


@pytest.fixture
def removed_player_id() -> Iterator[int]:
    """A linked event whose tournament holds one player removed on
    Sharly-Chess.com after round 1, and one still registered."""
    EVENT.create(tournament={'rounds': ROUNDS})
    tournament_id = EVENT.tournament().id
    with EventDatabase(EVENT_ID, write=True) as database:
        stored_event = database.load_stored_event()
        stored_event.plugin_data[PLUGIN_NAME] = SCEEventPluginData(
            id='SCE-EVT',
            status='published',
            tokens=SCETokens(
                access_token='ACCESS',
                refresh_token='REFRESH',
                expires_at=datetime.now() + timedelta(hours=1),
            ),
        ).to_stored_value()
        stored_event.enabled_plugins = [*stored_event.enabled_plugins, PLUGIN_NAME]
        database.update_stored_event(stored_event)
        database.execute(
            'UPDATE `tournament` SET `plugin_data` = ? WHERE `id` = ?',
            (
                json.dumps(
                    {
                        PLUGIN_NAME: SCETournamentPluginData(
                            id='SCE-T1'
                        ).to_stored_value()
                    }
                ),
                tournament_id,
            ),
        )
    removed_id = add_player(
        tournament_id,
        'REMOVED',
        SCEPlayerPluginData(deleted_id='SCE-R', removal_pending=True).to_stored_value(),
    )
    add_player(
        tournament_id, 'REGISTERED', SCEPlayerPluginData(id='SCE-K').to_stored_value()
    )
    yield removed_id
    EVENT.delete()


def player(player_id: int) -> TournamentPlayer:
    return EVENT.load().players_by_id[player_id].single_tournament_player


def parse(html: str) -> AdvancedHTMLParser:
    parser = AdvancedHTMLParser()
    parser.parseStr(html)
    return parser


def buttons(html: str) -> list[AdvancedTag]:
    return list(parse(html).getElementsByTagName('button'))


def sync_modal(http: TestClient) -> str:
    response = http.get(f'/sce/sync-modal/{EVENT_ID}?no_refresh=True', headers=HTMX)
    assert response.status_code == 200
    return response.text


def removed_player_modal(http: TestClient) -> str:
    response = http.get(f'/sce/removed-player-modal/{EVENT_ID}', headers=HTMX)
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_sync_modal_offers_the_removed_players(
    http: TestClient, removed_player_id: int
):
    html = sync_modal(http)

    opener = [
        b
        for b in buttons(html)
        if 'removed-player-modal' in (b.getAttribute('hx-get') or '')
    ]
    assert len(opener) == 1
    assert '(1)' in opener[0].textContent


@pytest.mark.unit
def test_removed_player_modal_lists_only_the_removed_player(
    http: TestClient, removed_player_id: int
):
    html = removed_player_modal(http)

    assert 'REMOVED' in html
    assert 'REGISTERED' not in html
    actions = [b.getAttribute('hx-post') or '' for b in buttons(html)]
    assert f'/sce/withdraw-removed-player/{EVENT_ID}/{removed_player_id}' in actions
    assert (
        f'/sce/register-removed-player-again/{EVENT_ID}/{removed_player_id}' in actions
    )


@pytest.mark.unit
def test_withdraw_gives_the_byes_and_closes_the_list(
    http: TestClient, removed_player_id: int
):
    response = http.post(
        f'/sce/withdraw-removed-player/{EVENT_ID}/{removed_player_id}', headers=HTMX
    )

    assert response.status_code == 200
    assert 'withdrawn' in response.text
    withdrawn = player(removed_player_id)
    assert SCEUtils.get_player_plugin_data(withdrawn).removal_pending is False
    assert withdrawn.pairings[1].result == Result.PAIRING_ALLOCATED_BYE
    for round_ in range(2, ROUNDS + 1):
        assert withdrawn.pairings[round_].result == Result.ZERO_POINT_BYE
    assert 'removed-player-modal' not in sync_modal(http)


@pytest.mark.unit
def test_keep_registers_again_and_starts_a_sync(
    http: TestClient, removed_player_id: int
):
    with patch('plugins.sce.sce_admin_controller.schedule_sync') as schedule_sync:
        response = http.post(
            f'/sce/register-removed-player-again/{EVENT_ID}/{removed_player_id}',
            headers=HTMX,
        )

    assert response.status_code == 200
    schedule_sync.assert_called_once()
    assert schedule_sync.call_args.kwargs == {'force': True}
    kept = player(removed_player_id)
    plugin_data = SCEUtils.get_player_plugin_data(kept)
    assert plugin_data.removal_pending is False
    assert plugin_data.deleted_id is None
    for round_ in range(2, ROUNDS + 1):
        assert kept.pairings[round_].unpaired


@pytest.mark.unit
def test_data_transfer_button_flags_the_removed_player(removed_player_id: int):
    assert SCEPlugin._event_has_sce_error_badge(EVENT.load())


@pytest.mark.unit
def test_data_transfer_button_is_clear_once_decided(
    http: TestClient, removed_player_id: int
):
    http.post(
        f'/sce/withdraw-removed-player/{EVENT_ID}/{removed_player_id}', headers=HTMX
    )

    assert not SCEPlugin._event_has_sce_error_badge(EVENT.load())


@pytest.mark.unit
def test_synchronisation_stays_available_with_conflicts(
    http: TestClient, removed_player_id: int
):
    tournament = EVENT.tournament()
    plugin_data = SCEUtils.get_tournament_plugin_data(tournament)
    plugin_data.conflict_sync_data = SCETournamentSyncData.from_tournament(tournament)
    SCEUtils.update_tournament_plugin_data(tournament, plugin_data)

    with patch('plugins.sce.utils.NetworkMonitor.connected', return_value=True):
        html = sync_modal(http)

    sync_buttons = [
        b for b in buttons(html) if 'sync-players' in (b.getAttribute('hx-post') or '')
    ]
    assert len(sync_buttons) == 1
    assert not sync_buttons[0].hasAttribute('disabled')
    switch = parse(html).getElementsByName('auto_player_sync')[0]
    assert not switch.hasAttribute('disabled')
    assert f'/sce/tournament-conflict-modal/{EVENT_ID}' in html
