"""Unit tests for the championship database (``.scch``) and its loader.

A championship lives in its own SQLite file, one per championship, mirroring the
per-file event database. These tests exercise the migration machinery and the
loader in isolation: create from scratch, round-trip the stored record,
reference a tournament from an independent event, and resolve broken references.
"""

from datetime import date

import pytest

from data.championship.championship import Championship
from data.championship.championship_loader import (
    ChampionshipArchiveLoader,
    ChampionshipLoader,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.championship.championship_database import ChampionshipDatabase
from database.sqlite.championship.championship_store import (
    StoredChampionshipCategory,
    StoredChampionshipCriterion,
    StoredChampionship,
    StoredChampionshipSource,
)
from tests.test_config import TestUtils


CHAMPIONSHIP_ID = 'test-championship'
EVENT_ID = 'test-championship-event'


def test_sources_are_ordered_by_date_with_undated_sources_last():
    championship = Championship(
        StoredChampionship(
            stored_sources=[
                StoredChampionshipSource(
                    id=1,
                    event_uniq_id='missing-late',
                    tournament_id=1,
                    tournament_name='Late',
                    start_date=date(2026, 3, 1),
                    stop_date=date(2026, 3, 2),
                ),
                StoredChampionshipSource(
                    id=2,
                    event_uniq_id='missing-undated',
                    tournament_id=1,
                    tournament_name='Undated',
                ),
                StoredChampionshipSource(
                    id=3,
                    event_uniq_id='missing-early',
                    tournament_id=1,
                    tournament_name='Early',
                    start_date=date(2025, 11, 1),
                    stop_date=date(2025, 11, 3),
                ),
            ]
        ),
        'source-order-test',
    )

    assert [source.tournament_name for source in championship.sources] == [
        'Early',
        'Late',
        'Undated',
    ]
    assert championship.start_date == date(2025, 11, 1)
    assert championship.stop_date == date(2026, 3, 2)


@pytest.fixture
def championship_id():
    """A freshly created championship database, removed again afterwards."""
    ChampionshipDatabase(CHAMPIONSHIP_ID).file.unlink(missing_ok=True)
    ChampionshipDatabase(CHAMPIONSHIP_ID).create()
    yield CHAMPIONSHIP_ID
    ChampionshipDatabase(CHAMPIONSHIP_ID).file.unlink(missing_ok=True)


@pytest.fixture
def source_tournament():
    """An independent event with one tournament, to be referenced by a grand
    prix. Yields ``(event_uniq_id, tournament_id, tournament_name)``."""
    EventDatabase(EVENT_ID).file.unlink(missing_ok=True)
    TestUtils.create_event(EVENT_ID)
    stored_tournament = TestUtils.create_tournament(EVENT_ID, 'Etape 1')
    yield EVENT_ID, stored_tournament.id, 'Etape 1'
    EventDatabase(EVENT_ID).file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Database machinery
# ---------------------------------------------------------------------------


def test_create_and_round_trip(championship_id):
    with ChampionshipDatabase(championship_id, write=True) as database:
        assert database.load_stored_championship().name == ''
        database.update_stored_championship(StoredChampionship(name='Circuit Jeunes'))
    with ChampionshipDatabase(championship_id) as database:
        assert database.load_stored_championship().name == 'Circuit Jeunes'


def test_freshly_created_database_is_up_to_date(championship_id):
    assert ChampionshipDatabase(championship_id).check_status() is True


def test_uniq_id_derived_from_file_path(championship_id):
    path = ChampionshipDatabase.championship_database_path(championship_id)
    assert ChampionshipDatabase(file_path=path).uniq_id == championship_id


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_loader_create_and_load():
    loader = ChampionshipLoader()
    uniq_id = loader.create_championship('Circuit Jeunes de la Drome')
    try:
        assert uniq_id == 'circuit_jeunes_de_la_drome'
        assert uniq_id in loader.all_championship_ids()
        championship = loader.load_championship(uniq_id)
        assert championship.name == 'Circuit Jeunes de la Drome'
        assert championship.sources == []
        assert championship.age_category_base_date is None
    finally:
        loader.delete_championship(uniq_id)
        assert uniq_id not in loader.all_championship_ids()


def test_loader_normalizes_uniq_ids_derived_from_filenames():
    raw_id = 'test championship filename'
    normalized_id = 'test_championship_filename'
    raw_file = ChampionshipDatabase.championship_database_path(raw_id)
    normalized_file = ChampionshipDatabase.championship_database_path(normalized_id)
    raw_file.unlink(missing_ok=True)
    normalized_file.unlink(missing_ok=True)
    ChampionshipDatabase(raw_id).create()

    try:
        assert normalized_id in ChampionshipLoader.all_championship_ids()
        assert not raw_file.exists()
        assert normalized_file.exists()
    finally:
        raw_file.unlink(missing_ok=True)
        normalized_file.unlink(missing_ok=True)


def test_archive_and_restore(championship_id):
    loader = ChampionshipLoader()
    archive_path = ChampionshipArchiveLoader.get_archive_path(championship_id)
    archive_path.unlink(missing_ok=True)
    with ChampionshipDatabase(championship_id, write=True) as database:
        database.update_stored_championship(StoredChampionship(name='Archived circuit'))

    try:
        assert loader.archive_championship(championship_id) == archive_path
        assert championship_id not in loader.all_championship_ids()
        archive = ChampionshipArchiveLoader.get_archive(championship_id)
        assert archive is not None
        assert archive.display_name == 'Archived circuit'

        restored_id = archive.restore()
        assert restored_id is not None

        assert restored_id == championship_id
        assert ChampionshipArchiveLoader.get_archive(championship_id) is None
        assert loader.load_championship(restored_id).name == 'Archived circuit'
    finally:
        archive_path.unlink(missing_ok=True)


def test_categories_and_reference_date_round_trip(championship_id):
    loader = ChampionshipLoader()
    categories = [
        StoredChampionshipCategory(
            id=None,
            name='U10 girls',
            stored_criteria=[
                StoredChampionshipCriterion(
                    id=None,
                    type='AGE',
                    options={
                        'MIN_AGE_CATEGORY': 'U10',
                        'MAX_AGE_CATEGORY': 'U10',
                    },
                ),
                StoredChampionshipCriterion(
                    id=None,
                    type='GENDER',
                    options={'GENDER_VALUE': 'F'},
                ),
            ],
        )
    ]
    loader.set_age_category_base_date(championship_id, date(2025, 9, 1))
    loader.set_championship_categories(championship_id, categories)

    championship = loader.load_championship(championship_id)
    assert championship.age_category_base_date == date(2025, 9, 1)
    assert len(championship.categories) == 1
    category = championship.categories[0]
    assert category.name == 'U10 girls'
    assert [criterion.type for criterion in category.criteria] == ['AGE', 'GENDER']
    assert category.criteria[0].options['MIN_AGE_CATEGORY'] == 'U10'


def test_manual_tiebreak_round_trip(championship_id):
    loader = ChampionshipLoader()
    assert loader.load_championship(championship_id).manual_positions == {}
    loader.set_manual_tiebreaks(championship_id, {'a:1:1': 3, 'a:1:2': 1})
    assert loader.load_championship(championship_id).manual_positions == {
        'a:1:1': 3,
        'a:1:2': 1,
    }
    # None clears a key; the others are upserted.
    loader.set_manual_tiebreaks(championship_id, {'a:1:1': None, 'a:1:2': 2})
    assert loader.load_championship(championship_id).manual_positions == {'a:1:2': 2}
    loader.reset_manual_tiebreaks(championship_id)
    assert loader.load_championship(championship_id).manual_positions == {}


def test_default_reference_date_is_january_first_of_earliest_source_year(
    championship_id, source_tournament
):
    event_uniq_id, tournament_id, _ = source_tournament
    ChampionshipLoader().add_source(championship_id, event_uniq_id, tournament_id)

    championship = ChampionshipLoader().load_championship(championship_id)
    assert championship.age_category_base_date is None
    assert championship.default_age_category_base_date == date(date.today().year, 1, 1)
    assert championship.effective_age_category_base_date == date(
        date.today().year, 1, 1
    )


def test_add_source_resolves_live(championship_id, source_tournament):
    event_uniq_id, tournament_id, tournament_name = source_tournament
    loader = ChampionshipLoader()
    loader.add_source(championship_id, event_uniq_id, tournament_id)

    championship = loader.load_championship(championship_id)
    assert len(championship.sources) == 1
    source = championship.sources[0]
    assert not source.broken
    assert source.event_uniq_id == event_uniq_id
    assert source.tournament_id == tournament_id
    assert source.tournament_name == tournament_name
    assert source.tournament is not None
    assert source.start_date == source.tournament.start_date
    assert source.stop_date == source.tournament.stop_date


def test_broken_source_when_event_deleted(championship_id, source_tournament):
    event_uniq_id, tournament_id, tournament_name = source_tournament
    loader = ChampionshipLoader()
    loader.add_source(championship_id, event_uniq_id, tournament_id)

    # Delete the referenced event; the championship keeps the reference.
    EventDatabase(event_uniq_id).file.unlink(missing_ok=True)

    championship = loader.load_championship(championship_id)
    assert len(championship.broken_sources) == 1
    source = championship.sources[0]
    assert source.broken
    assert source.broken_reason == 'event_not_found'
    # Falls back to the snapshot captured when the source was added.
    assert source.tournament_name == tournament_name


def test_broken_source_when_tournament_missing(championship_id, source_tournament):
    event_uniq_id, tournament_id, _ = source_tournament
    loader = ChampionshipLoader()
    loader.add_source(championship_id, event_uniq_id, tournament_id + 999)

    championship = loader.load_championship(championship_id)
    source = championship.sources[0]
    assert source.broken
    assert source.broken_reason == 'tournament_not_found'


def test_reverse_lookup_finds_referencing_championship(
    championship_id, source_tournament
):
    event_uniq_id, tournament_id, _ = source_tournament
    loader = ChampionshipLoader()
    loader.add_source(championship_id, event_uniq_id, tournament_id)

    assert championship_id in ChampionshipLoader.championship_ids_referencing(
        event_uniq_id
    )
    assert championship_id in ChampionshipLoader.championship_ids_referencing(
        event_uniq_id, tournament_id
    )
    assert championship_id not in ChampionshipLoader.championship_ids_referencing(
        event_uniq_id, tournament_id + 999
    )
    assert ChampionshipLoader.championship_ids_referencing('no-such-event') == []


def test_rename_event_references_updates_sources(championship_id, source_tournament):
    event_uniq_id, tournament_id, _ = source_tournament
    loader = ChampionshipLoader()
    loader.add_source(championship_id, event_uniq_id, tournament_id)

    ChampionshipLoader.rename_event_references(event_uniq_id, 'renamed-event')

    source = loader.load_championship(championship_id).sources[0]
    assert source.event_uniq_id == 'renamed-event'
    assert championship_id in ChampionshipLoader.championship_ids_referencing(
        'renamed-event'
    )
    assert championship_id not in ChampionshipLoader.championship_ids_referencing(
        event_uniq_id
    )
