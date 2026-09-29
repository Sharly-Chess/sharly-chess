import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace
from typing import cast

from data.player import Player
from database.sqlite.event.event_store import StoredPlayer
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_data_sources import _FfeDataSource
from plugins.ffe.utils import FfeNameKey, ffe_database_name_keys


def _stored_player(
    licence_number: str | None = None,
    fide_id: int | None = None,
    last_name: str = 'DUPONT',
    first_name: str = 'Jean',
    date_of_birth: date | None = date(1980, 5, 12),
    year_of_birth: int | None = None,
) -> StoredPlayer:
    stored_player = StoredPlayer(
        id=None,
        last_name=last_name,
        first_name=first_name,
        date_of_birth=date_of_birth,
        year_of_birth=year_of_birth,
        fide_id=fide_id,
    )
    stored_player.plugin_data = {PLUGIN_NAME: {'ffe_licence_number': licence_number}}
    return stored_player


class _FakeFfeDataSource(_FfeDataSource):
    def __init__(self, database: list[StoredPlayer]) -> None:
        self.database = database
        self.queries: list[tuple[list[str], list[int], list[FfeNameKey]]] = []

    async def _get_ffe_match_stored_players(
        self,
        ffe_licence_numbers: list[str],
        fide_ids: list[int],
        name_keys: list[FfeNameKey],
    ) -> list[StoredPlayer] | None:
        self.queries.append((ffe_licence_numbers, fide_ids, name_keys))
        return [
            stored_player
            for stored_player in self.database
            if self._get_licence_number(stored_player) in ffe_licence_numbers
            or stored_player.fide_id in fide_ids
            or not ffe_database_name_keys(stored_player).isdisjoint(name_keys)
        ]


def _match(
    data_source: _FakeFfeDataSource, stored_player: StoredPlayer
) -> StoredPlayer | None:
    player = cast(Player, SimpleNamespace(stored_player=stored_player))
    with ThreadPoolExecutor(max_workers=1) as executor:
        matches = executor.submit(
            asyncio.run, data_source._get_match_stored_players([player])
        ).result()
    assert matches is not None
    return next(
        (
            match
            for match in matches
            if data_source._check_player_match(stored_player, match)
        ),
        None,
    )


def test_unknown_licence_number_falls_back_to_name_and_date_of_birth() -> None:
    ffe_player = _stored_player(licence_number='Z81840')
    data_source = _FakeFfeDataSource([ffe_player])
    assert _match(data_source, _stored_player(licence_number='Z81841')) is ffe_player
    assert len(data_source.queries) == 2


def test_unknown_licence_number_falls_back_to_name_and_year_of_birth() -> None:
    ffe_player = _stored_player(licence_number='Z81840')
    data_source = _FakeFfeDataSource([ffe_player])
    player = _stored_player(
        licence_number='Z81841', date_of_birth=None, year_of_birth=1980
    )
    assert _match(data_source, player) is ffe_player


def test_name_match_ignores_case_and_accents() -> None:
    ffe_player = _stored_player(last_name='DUPONT', first_name='Helene')
    data_source = _FakeFfeDataSource([ffe_player])
    player = _stored_player(last_name='Dupont', first_name='HÉLÈNE')
    assert _match(data_source, player) is ffe_player


def test_different_date_of_birth_does_not_match() -> None:
    data_source = _FakeFfeDataSource([_stored_player()])
    player = _stored_player(licence_number='Z81841', date_of_birth=date(1980, 5, 13))
    assert _match(data_source, player) is None


def test_unknown_licence_number_falls_back_to_fide_id() -> None:
    ffe_player = _stored_player(licence_number='Z81840', fide_id=123, last_name='X')
    data_source = _FakeFfeDataSource([ffe_player])
    assert (
        _match(data_source, _stored_player(licence_number='Z81841', fide_id=123))
        is ffe_player
    )


def test_known_licence_number_is_not_looked_up_further() -> None:
    ffe_player = _stored_player(licence_number='Z81840', last_name='MARTIN')
    data_source = _FakeFfeDataSource([ffe_player])
    assert _match(data_source, _stored_player(licence_number='Z81840')) is ffe_player
    assert len(data_source.queries) == 1


def test_player_found_by_no_key_has_no_match() -> None:
    data_source = _FakeFfeDataSource([_stored_player(last_name='MARTIN')])
    assert _match(data_source, _stored_player(licence_number='Z81841')) is None


def test_only_players_with_a_licence_number_are_expected_to_be_found() -> None:
    data_source = _FakeFfeDataSource([])
    assert data_source._expects_match(_stored_player(licence_number='Z81841'))
    assert not data_source._expects_match(_stored_player(fide_id=123))
