import json
import sqlite3
from typing import Any, cast

import pytest

from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.migration_database import MigrationDatabase
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.migrations.m009_ffe_arbiter_title_reform import Migration
from plugins.ffe.utils import FFEArbiterTitle, FfeAccountPluginData


@pytest.mark.parametrize(
    'old_title, title, fide_title, expected_fide_title',
    [
        ('', '', '', ''),
        ('AS', '', '', ''),
        ('AFJ', 'AFJ', '', ''),
        ('AFC', 'AFM', '', ''),
        ('AFO1', 'AFO', None, None),
        ('AFO2', 'AFO', 'NA', 'NA'),
        ('AFE1', 'AFO', '', 'FA'),
        ('AFE1', 'AFO', None, 'FA'),
        ('AFE1', 'AFO', 'IA', 'IA'),
        ('AFE2', 'AFO', '', 'IA'),
    ],
)
def test_migration_converts_titles_to_the_reform(
    old_title: str,
    title: str,
    fide_title: str | None,
    expected_fide_title: str | None,
) -> None:
    connection = sqlite3.connect(':memory:')
    connection.execute(
        'CREATE TABLE `account` (`fide_arbiter_title` TEXT, `plugin_data` TEXT)'
    )
    connection.execute(
        'INSERT INTO `account` VALUES (?, ?)',
        (fide_title, json.dumps({'ffe': {'ffe_arbiter_title': old_title}})),
    )
    Migration(cast(MigrationDatabase, connection)).forward()
    stored_fide_title, stored_plugin_data = connection.execute(
        'SELECT `fide_arbiter_title`, `plugin_data` FROM `account`'
    ).fetchone()
    connection.close()
    assert stored_fide_title == expected_fide_title
    plugin_data = json.loads(stored_plugin_data)['ffe']
    assert plugin_data['ffe_arbiter_title'] == title
    assert FfeAccountPluginData.from_stored_value(
        plugin_data
    ).ffe_arbiter_title == FFEArbiterTitle(title)


def test_account_plugin_data_round_trip() -> None:
    plugin_data = FfeAccountPluginData(
        ffe_licence_number='V68338',
        ffe_arbiter_title=FFEArbiterTitle.AFO,
    )
    assert (
        FfeAccountPluginData.from_stored_value(plugin_data.to_stored_value())
        == plugin_data
    )
    assert FfeAccountPluginData.from_form_data(plugin_data.to_form_data()) == (
        plugin_data
    )


def _ffe_database_row(
    arbiter_title: str | None, fide_arbiter_title: str | None
) -> dict[str, Any]:
    return {
        'first_name': 'Alice',
        'last_name': 'DUPONT',
        'date_of_birth': '2000-01-01',
        'gender': 'F',
        'fide_title': '',
        'standard_rating': 1500,
        'standard_rating_type': 3,
        'rapid_rating': 1500,
        'rapid_rating_type': 3,
        'blitz_rating': 1500,
        'blitz_rating_type': 3,
        'fide_id': None,
        'federation': 'FRA',
        'club': 'Club',
        'ffe_arbiter_title': arbiter_title,
        'fide_arbiter_title': fide_arbiter_title,
        'ffe_id': 1,
        'ffe_licence': 'A',
        'ffe_licence_number': 'V68338',
        'league': 'ARA',
    }


@pytest.mark.parametrize(
    'arbiter_title, fide_arbiter_title, expected_title',
    [
        (None, None, FFEArbiterTitle.NONE),
        ('AFM', None, FFEArbiterTitle.AFM),
        ('AFO', 'FA', FFEArbiterTitle.AFO),
        ('AFO', 'IA', FFEArbiterTitle.AFO),
    ],
)
def test_account_from_ffe_database_player(
    arbiter_title: str | None,
    fide_arbiter_title: str | None,
    expected_title: FFEArbiterTitle,
) -> None:
    stored_player: StoredPlayer = FfeDatabase.get_stored_player_from_row(
        _ffe_database_row(arbiter_title, fide_arbiter_title)
    )
    assert stored_player.transient_arbiter_titles['fide'] == (fide_arbiter_title or '')
    plugin_data = FfeAccountPluginData.from_stored_player(stored_player)
    assert plugin_data.ffe_arbiter_title == expected_title
    assert plugin_data.ffe_licence_number == 'V68338'
