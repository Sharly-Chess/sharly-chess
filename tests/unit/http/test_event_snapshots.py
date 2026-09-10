"""The backups of an event, over HTTP: the panel, the restorations it offers
and the way out of an event whose file cannot be read."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from common import EVENTS_DIR
from data.loader import ArchiveLoader, EventLoader
from data.snapshot import Snapshot, SnapshotLoader, SnapshotReason, snapshots_dir
from data.snapshot import write_snapshot
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils
from utils.enum import Extension

EVENT_ID = 'test-snapshots-http'
DAMAGED_EVENT_ID = 'test-snapshots-damaged-http'


def event_name(uniq_id: str) -> str:
    with EventDatabase(uniq_id) as database:
        return database.load_stored_event_metadata().name


def set_event_name(uniq_id: str, name: str) -> None:
    with EventDatabase(uniq_id, write=True) as database:
        database.execute('UPDATE `info` SET `name` = ?', (name,))


def only_snapshot(uniq_id: str) -> Snapshot:
    snapshots = SnapshotLoader.snapshots(uniq_id)
    assert len(snapshots) == 1
    return snapshots[0]


def panel(http: TestClient, uniq_id: str) -> str:
    response = http.get(f'/event-snapshots-modal/{uniq_id}')
    assert response.status_code == 200
    return response.text


@pytest.fixture
def event() -> Iterator[str]:
    TestUtils.create_event(EVENT_ID)
    for file in snapshots_dir(EVENT_ID).glob('*'):
        file.unlink()
    yield EVENT_ID
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_panel_lists_the_backups_with_their_reason(http: TestClient, event: str):
    write_snapshot(event, SnapshotReason.BEFORE_PAIRING, round_=3)
    write_snapshot(event, SnapshotReason.AUTO)

    body = panel(http, event)

    assert 'Before round 3 was paired' in body
    assert 'Automatic' in body


@pytest.mark.unit
def test_an_event_with_no_backup_says_so(http: TestClient, event: str):
    assert 'No backup has been taken of this event yet' in panel(http, event)


@pytest.mark.unit
def test_backing_up_now_takes_one(http: TestClient, event: str):
    response = http.post(f'/event-snapshot-now/{event}')

    assert response.is_success
    assert only_snapshot(event).reason == SnapshotReason.AUTO


@pytest.mark.unit
def test_restoring_in_place_rolls_the_event_back(http: TestClient, event: str):
    set_event_name(event, 'The state to come back to')
    snapshot = write_snapshot(event, SnapshotReason.BEFORE_PAIRING)
    set_event_name(event, 'The mistake')

    response = http.post(f'/event-snapshot-restore/{event}/{snapshot.file.name}')

    assert response.is_success
    assert event_name(event) == 'The state to come back to'


@pytest.mark.unit
def test_the_confirmation_says_the_restoration_can_be_undone(
    http: TestClient, event: str
):
    """The state being replaced is kept as a backup of its own, and the
    confirmation is where that is said."""
    snapshot = write_snapshot(event, SnapshotReason.BEFORE_PAIRING)

    response = http.get(f'/event-snapshot-restore-modal/{event}/{snapshot.file.name}')

    assert response.status_code == 200
    assert 'The event will be replaced by this backup' in response.text
    assert 'can be undone' in response.text


@pytest.mark.unit
def test_restoring_as_a_copy_leaves_the_event_alone(http: TestClient, event: str):
    set_event_name(event, 'A past state')
    snapshot = write_snapshot(event, SnapshotReason.BEFORE_PAIRING)
    set_event_name(event, 'The state now')

    response = http.post(f'/event-snapshot-restore-copy/{event}/{snapshot.file.name}')

    assert response.is_success
    assert event_name(event) == 'The state now'
    copies = [file.stem for file in EVENTS_DIR.glob(f'{event}-*.{Extension.EVENT_DB}')]
    assert len(copies) == 1
    assert event_name(copies[0]) == 'A past state'
    EventLoader.unload_event(copies[0])
    TestUtils.delete_event(copies[0])


@pytest.mark.unit
def test_a_few_tournaments_are_listed_on_the_row(http: TestClient, event: str):
    """What a backup holds is read from the backup itself, so the row says
    what restoring it would give back."""
    TestUtils.create_tournament(event, 'Main', overrides={'rounds': 5})
    TestUtils.create_tournament(event, 'Junior', overrides={'rounds': 4})
    write_snapshot(event, SnapshotReason.BEFORE_PAIRING)

    body = panel(http, event)

    assert 'Main' in body
    assert 'Junior' in body
    assert 'not started' in body


@pytest.mark.unit
def test_many_tournaments_are_folded_behind_an_expander(http: TestClient, event: str):
    for index in range(4):
        TestUtils.create_tournament(
            event, f'Tournament {index}', overrides={'rounds': 3}
        )
    write_snapshot(event, SnapshotReason.BEFORE_PAIRING)

    body = panel(http, event)

    assert '4 tournaments' in body
    assert 'data-bs-toggle="collapse"' in body


@pytest.fixture
def damaged_event() -> Iterator[str]:
    TestUtils.create_event(DAMAGED_EVENT_ID)
    for file in snapshots_dir(DAMAGED_EVENT_ID).glob('*'):
        file.unlink()
    yield DAMAGED_EVENT_ID
    EventLoader.unload_event(DAMAGED_EVENT_ID)
    if EventDatabase.event_database_path(DAMAGED_EVENT_ID).is_file():
        TestUtils.delete_event(DAMAGED_EVENT_ID)


def damage(uniq_id: str) -> None:
    EventLoader.unload_event(uniq_id)
    EventDatabase.event_database_path(uniq_id).write_bytes(b'not a database any more')


@pytest.mark.unit
def test_an_event_that_cannot_be_read_offers_its_backups(
    http: TestClient, damaged_event: str
):
    """The page of a damaged event cannot be reached, so the way back is
    offered where the event is listed."""
    set_event_name(damaged_event, 'Before the damage')
    snapshot = write_snapshot(damaged_event, SnapshotReason.BEFORE_PAIRING)
    damage(damaged_event)

    # The damage is found where the events are listed, which is where the
    # panel is reached from.
    assert http.get('/current_events').status_code == 200
    body = panel(http, damaged_event)
    assert 'This event could not be opened' in body

    confirmation = http.get(
        f'/event-snapshot-restore-modal/{damaged_event}/{snapshot.file.name}'
    )
    assert confirmation.status_code == 200
    # Nothing can be kept of a state that cannot be read.
    assert 'there is nothing to keep' in confirmation.text

    restored = http.post(
        f'/event-snapshot-restore/{damaged_event}/{snapshot.file.name}'
    )
    assert restored.is_success
    assert event_name(damaged_event) == 'Before the damage'


@pytest.mark.unit
def test_an_event_that_cannot_be_read_can_be_archived(
    http: TestClient, damaged_event: str
):
    """Without this the only thing to do with a damaged event is restore it,
    leaving a row that cannot be got rid of."""
    damage(damaged_event)

    modal = http.get(f'/current_events/event-damaged-delete-modal/{damaged_event}')
    assert modal.status_code == 200
    assert 'This event could not be read' in modal.text

    archived = http.delete(f'/current_events/event-damaged-delete/{damaged_event}')

    assert archived.is_success
    assert 'the database has been archived' in archived.text
    assert not EventDatabase.event_database_path(damaged_event).is_file()
    assert ArchiveLoader.get_archive(damaged_event) is not None
