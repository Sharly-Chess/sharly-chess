from collections.abc import Iterator
from pathlib import Path

import pytest

from common.exception import ImporterError
from tests.gacrux.harness import (
    export_trf,
    gacrux_report_header,
    trf_export_unavailable,
)
from tests.gacrux.sources import LoadedTournament, TournamentSource, all_sources


def pytest_report_collectionfinish(items: list[pytest.Item]) -> str:
    """Which Gacrux the run checked against, so that a failure can be told
    apart from a change in Gacrux.

    Says nothing when the run selected none of these tests.
    """
    if not any(item.get_closest_marker('gacrux') for item in items):
        return ''
    return gacrux_report_header()


@pytest.fixture(params=all_sources(), ids=str)
def loaded(request: pytest.FixtureRequest) -> Iterator[LoadedTournament]:
    source: TournamentSource = request.param
    try:
        loaded = LoadedTournament(source)
    except ImporterError as error:
        # A file the importer refuses (a TRF16-era date, say) has no
        # export to check.
        pytest.skip(f'import refused: {error}')
    yield loaded
    loaded.delete()


@pytest.fixture
def trf_path(loaded: LoadedTournament, tmp_path: Path) -> Path:
    """The TRF26 export of the loaded tournament, or a skip when the
    tournament has nothing a checker could read."""
    tournament = loaded.tournament
    if message := trf_export_unavailable(tournament):
        pytest.skip(message)
    if not tournament.tournament_players_by_id:
        pytest.skip('no player')
    if tournament.current_round == 0:
        pytest.skip('no round paired')
    return export_trf(tournament, tmp_path, 'tournament')
