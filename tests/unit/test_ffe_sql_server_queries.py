"""The queries of the remote _FFE_ SQL Server cannot be run against an
in-memory database: these tests check what they are built from."""

import asyncio
import re
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

import pytest

from plugins.ffe.ffe_sql_server import FFESqlServer


class _QueryCapture(FFESqlServer):
    # The queries of all the connections, the searches opening a second one
    queries: list[tuple[str, list[Any]]]
    first_players: list[Any]
    cancellations: int

    def __init__(self) -> None:
        self.cancelled = False

    async def __aenter__(self) -> '_QueryCapture':
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def cancel(self) -> None:
        self.cancelled = True
        _QueryCapture.cancellations += 1

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
        return self.first_players if _ranked_below_the_words(condition) else []


def _ranked_below_the_words(condition: str) -> bool:
    return re.search(r'END\s*< \d+(?= ORDER BY|$)', condition) is not None


@pytest.fixture(autouse=True)
def _reset_capture() -> None:
    _QueryCapture.queries = []
    _QueryCapture.first_players = []
    _QueryCapture.cancellations = 0
    FFESqlServer._first_players_counts.clear()


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
    assert len(server.queries) == 2
    for query, params in server.queries:
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
    for query, _params in server.queries:
        for field in ('joueur.Nom', 'joueur.Prenom'):
            assert query.count(f'WHEN LEN({field}) = 20') == words_cut_at_length
            assert query.count(f"WHEN RIGHT({field}, 1) = '.'") == abbreviated_words


def test_the_players_whose_last_name_a_word_starts_fill_the_page_alone() -> None:
    _QueryCapture.first_players = ['DUPONT Jean'] * 20
    server = _QueryCapture()
    players: list[Any] = []

    async def search() -> None:
        players.extend(await server.search_player('DUPONT JEAN', 'FRA', 0, 20))
        await asyncio.gather(*FFESqlServer._background_scans)

    _run(search())
    assert players == _QueryCapture.first_players
    [first_players_query] = [
        query for query, _params in server.queries if _ranked_below_the_words(query)
    ]
    assert first_players_query.count('< 2 ORDER BY') == 1
    assert _QueryCapture.cancellations == 1


def test_the_scan_gives_the_page_the_first_players_do_not_fill() -> None:
    _QueryCapture.first_players = ['DUPONT Jean'] * 19
    server = _QueryCapture()
    players: list[Any] = []

    async def search() -> None:
        players.extend(await server.search_player('DUPONT JEAN', 'FRA', 0, 20))

    _run(search())
    assert players == []
    assert len(server.queries) == 2
    assert _QueryCapture.cancellations == 0


def test_the_pages_past_the_first_players_are_only_scanned() -> None:
    _QueryCapture.first_players = ['DUPONT Jean'] * 5
    server = _QueryCapture()
    _run(server.search_player('DUPONT JEAN', 'FRA', 0, 20))
    assert len(server.queries) == 2
    _QueryCapture.queries = []
    _run(server.search_player('DUPONT JEAN', 'FRA', 1, 20))
    [(query, _params)] = server.queries
    assert not _ranked_below_the_words(query)
    _QueryCapture.queries = []
    _run(server.search_player('DUPONT JEAN', 'FRA', 1, 20, {'gender_filter': 'F'}))
    assert len(server.queries) == 2


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
