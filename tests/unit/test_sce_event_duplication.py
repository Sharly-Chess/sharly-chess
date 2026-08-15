"""Unit tests for what an event duplication does to the SCE plugin.

A duplicate must not inherit the link to Sharly-Chess.com: the plugin is
only ever enabled by importing an event from the platform, so both the
plugin data (ids, tokens, sync stamps) and the enabled flag have to go.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from plugins.sce.sce import PLUGIN_NAME, SCEPlugin
from plugins.sce.sce_data import SCEEventPluginData, SCETokens


@dataclass
class _FakeStored:
    plugin_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeStoredEvent(_FakeStored):
    enabled_plugins: list[str] = field(default_factory=list)
    stored_tournaments: list[_FakeStored] = field(default_factory=list)
    stored_players: list[_FakeStored] = field(default_factory=list)


class _FakeEventDatabase:
    def __init__(self, stored_event: _FakeStoredEvent):
        self.stored_event = stored_event
        self.updated_tournaments: list[_FakeStored] = []
        self.updated_players: list[_FakeStored] = []

    def load_stored_event(self) -> _FakeStoredEvent:
        return self.stored_event

    def update_stored_event(self, stored_event: _FakeStoredEvent):
        self.stored_event = stored_event

    def update_stored_tournament(self, stored_tournament: _FakeStored):
        self.updated_tournaments.append(stored_tournament)

    def update_stored_player(self, stored_player: _FakeStored):
        self.updated_players.append(stored_player)


def _linked_event() -> _FakeStoredEvent:
    return _FakeStoredEvent(
        plugin_data={
            PLUGIN_NAME: {
                'id': 'evt-42',
                'slug': 'open-de-paris',
                'tokens': {'access_token': 'secret', 'refresh_token': 'refresh'},
            },
            'ffe': {'id': '12345'},
        },
        enabled_plugins=[PLUGIN_NAME, 'ffe', 'pairing_acceleration'],
        stored_tournaments=[_FakeStored({PLUGIN_NAME: {'id': 'trn-1'}})],
        stored_players=[_FakeStored({PLUGIN_NAME: {'registration_id': 'reg-1'}})],
    )


@pytest.mark.unit
class TestSCEOnEventDuplicated:
    def test_plugin_data_is_erased_at_every_level(self):
        database = _FakeEventDatabase(_linked_event())

        SCEPlugin().on_event_duplicated(event_database=database)

        assert database.stored_event.plugin_data[PLUGIN_NAME] == {}
        assert [t.plugin_data[PLUGIN_NAME] for t in database.updated_tournaments] == [
            {}
        ]
        assert [p.plugin_data[PLUGIN_NAME] for p in database.updated_players] == [{}]

    def test_plugin_is_disabled_on_the_duplicate(self):
        database = _FakeEventDatabase(_linked_event())

        SCEPlugin().on_event_duplicated(event_database=database)

        assert PLUGIN_NAME not in database.stored_event.enabled_plugins

    def test_other_plugins_are_left_alone(self):
        database = _FakeEventDatabase(_linked_event())

        SCEPlugin().on_event_duplicated(event_database=database)

        assert database.stored_event.enabled_plugins == ['ffe', 'pairing_acceleration']
        assert database.stored_event.plugin_data['ffe'] == {'id': '12345'}

    def test_nothing_happens_when_the_plugin_is_not_enabled(self):
        stored_event = _linked_event()
        stored_event.enabled_plugins = ['ffe']
        database = _FakeEventDatabase(stored_event)

        SCEPlugin().on_event_duplicated(event_database=database)

        # Untouched: there is no link to break.
        assert database.stored_event.plugin_data[PLUGIN_NAME]['id'] == 'evt-42'
        assert database.updated_tournaments == []


@pytest.mark.unit
class TestSCEEventPluginDataFromFormData:
    @staticmethod
    def _populated() -> SCEEventPluginData:
        return SCEEventPluginData(
            id='evt-42',
            slug='open-de-paris',
            organiser_slug='club-42',
            status='published',
            tournament_names_by_id={'trn-1': 'Open A'},
            tokens=SCETokens(
                access_token='secret',
                refresh_token='refresh',
                expires_at=datetime(2026, 1, 1, 12, 0),
            ),
        )

    def test_update_keeps_the_previous_data(self):
        previous = self._populated()

        data = SCEEventPluginData.from_form_data({}, previous, action='update')

        assert data is previous

    def test_clone_drops_the_previous_data(self):
        data = SCEEventPluginData.from_form_data({}, self._populated(), action='clone')

        assert data.id is None
        assert data.slug is None
        assert data.organiser_slug is None
        assert data.status is None
        assert data.tournament_names_by_id == {}
        assert data.tokens is None
