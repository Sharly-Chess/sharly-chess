"""The queries of the remote _FFE_ SQL Server cannot be run against an
in-memory database: these tests check what they are built from."""

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

import pytest

from plugins.ffe.ffe_sql_server import FFESqlServer


class _QueryCapture(FFESqlServer):
    def __init__(self) -> None:
        self.queries: list[tuple[str, list[Any]]] = []

    async def _get_stored_players_by_condition(
        self,
        condition: str,
        params: list,
        order_by: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        recompile: bool = False,
    ) -> list:
        self.queries.append((f'{condition} ORDER BY {order_by}', params))
        return []


def _run(coroutine: Coroutine[Any, Any, Any]) -> None:
    # The playwright fixtures of the suite already run a loop here
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, coroutine).result()


@pytest.mark.parametrize(
    'search', ['DUPONT', 'LOUSTALOT-BARBE SERGENT', "O'NEILL KIAN", '1503014 X']
)
def test_search_binds_every_parameter(search: str) -> None:
    server = _QueryCapture()
    _run(server.search_player(search, 'FRA', 0, 20, {'gender_filter': 'F'}))
    [(query, params)] = server.queries
    # The driver formats the query with the % operator
    assert query % tuple(f'@P{i}' for i in range(len(params)))


@pytest.mark.parametrize(
    ('search', 'words_cut_at_length', 'abbreviated_words'),
    [
        ('LE', 0, 0),
        ('DUPONT', 0, 0),
        ('DUPONT JEAN', 0, 0),
        ('MERCIER PIQUEMAL', 0, 2),
        ('FOURNIERE DE SAINT', 0, 2),
        ('DE LA FOURNIERE DE SAINT', 5, 5),
        ('SERGENT LOUSTALOT BARBE', 3, 3),
    ],
)
def test_only_searches_longer_than_the_names_match_cut_names(
    search: str, words_cut_at_length: int, abbreviated_words: int
) -> None:
    server = _QueryCapture()
    _run(server.search_player(search, 'FRA', 0, 20))
    [(query, _params)] = server.queries
    for field in ('joueur.Nom', 'joueur.Prenom'):
        assert query.count(f'WHEN LEN({field}) = 20') == words_cut_at_length
        assert query.count(f"WHEN RIGHT({field}, 1) = '.'") == abbreviated_words


def test_names_are_read_without_doubled_apostrophes_and_trailing_spaces() -> None:
    assert FFESqlServer._read_name("O''NEILL") == "O'NEILL"
    assert FFESqlServer._read_name('DUPONT ') == 'DUPONT'


def test_names_with_an_apostrophe_are_looked_up_both_ways() -> None:
    assert FFESqlServer._held_names("O'NEILL") == ["O'NEILL", "O''NEILL"]
    assert FFESqlServer._held_names('DUPONT') == ['DUPONT']


def test_name_keys_bind_both_ways_of_holding_an_apostrophe() -> None:
    server = _QueryCapture()
    _run(
        server.get_stored_players_by_name_keys([("O'NEILL", 'KIAN', date(2001, 1, 1))])
    )
    # Nothing found, the abbreviated names are looked up next
    [(query, params), (abbreviation_query, abbreviation_params)] = server.queries
    assert sorted(params) == sorted(["O'NEILL", 'KIAN', "O''NEILL", 'KIAN'])
    assert query % tuple(f'@P{i}' for i in range(len(params)))
    assert abbreviation_params == ["O'NEILL", "O'N%"]
    assert abbreviation_query % tuple(f'@P{i}' for i in range(len(abbreviation_params)))
