"""The backups of an event in the browser.

Only what needs one: the confirmation htmx swaps in, the expander Bootstrap
folds the tournaments behind, and the warning the event page raises by itself
when a backup fails. What the server answers is covered over HTTP, in
`tests/unit/http/test_snapshots.py`.
"""

import shutil

import pytest
from playwright.sync_api import Page, expect

from common import EVENTS_DIR
from data.loader import EventLoader
from data.snapshot import SnapshotReason, snapshots_dir, write_snapshot
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils
from utils.enum import Extension

EVENT_ID = 'test-snapshots-e2e'


@pytest.fixture(scope='module', autouse=True)
def remove_the_events_afterwards():
    """The events of this module are left behind otherwise, and an event that
    outlives its test is an event every other test then sees."""
    yield
    for file in EVENTS_DIR.glob(f'test-snapshots-*e2e.{Extension.EVENT_DB}'):
        EventLoader.unload_event(file.stem)
        file.unlink()
        shutil.rmtree(snapshots_dir(file.stem), ignore_errors=True)


def open_panel(page: Page, uniq_id: str):
    page.goto('/current_events')
    # Addressed by the button's own URL: the row shows the name of the event,
    # which these tests change to tell the states apart.
    button = page.locator(f'button[hx-get*="event-snapshots-modal/{uniq_id}"]').first
    expect(button).to_be_visible()
    button.click()
    modal = page.locator('#event-snapshots-modal')
    expect(modal).to_be_visible()
    return modal


def event_name(uniq_id: str) -> str:
    with EventDatabase(uniq_id) as database:
        return database.load_stored_event_metadata().name


def set_event_name(uniq_id: str, name: str) -> None:
    with EventDatabase(uniq_id, write=True) as database:
        database.execute('UPDATE `info` SET `name` = ?', (name,))


@pytest.mark.e2e
class TestRestoringFromThePanel:
    @pytest.fixture
    def event(self):
        TestUtils.create_event(EVENT_ID)
        for file in snapshots_dir(EVENT_ID).glob('*'):
            file.unlink()
        yield EVENT_ID

    def test_restoring_in_place_asks_first_and_rolls_the_event_back(
        self, page: Page, event
    ):
        set_event_name(event, 'The state to come back to')
        write_snapshot(event, SnapshotReason.BEFORE_PAIRING)
        set_event_name(event, 'The mistake')

        modal = open_panel(page, event)
        modal.locator('button:has(.bi-arrow-counterclockwise)').first.click()

        confirm = page.locator('#event-snapshot-restore-modal')
        expect(confirm).to_be_visible()
        expect(confirm).to_contain_text('The event will be replaced by this backup')
        confirm.locator('#snapshot-restore-button').click()

        expect(page.locator('#event-snapshot-restore-modal')).not_to_be_visible()
        assert event_name(event) == 'The state to come back to'

    def test_declining_the_confirmation_leaves_the_event_alone(self, page: Page, event):
        write_snapshot(event, SnapshotReason.BEFORE_PAIRING)
        set_event_name(event, 'Left alone')

        modal = open_panel(page, event)
        modal.locator('button:has(.bi-arrow-counterclockwise)').first.click()

        confirm = page.locator('#event-snapshot-restore-modal')
        expect(confirm).to_be_visible()
        confirm.get_by_role('button', name='Cancel').click()

        expect(confirm).not_to_be_visible()
        assert event_name(event) == 'Left alone'


@pytest.mark.e2e
class TestSnapshotState:
    MANY_ID = 'test-snapshots-many-e2e'

    def test_many_tournaments_are_folded_behind_an_expander(self, page: Page):
        TestUtils.create_event(self.MANY_ID)
        for index in range(4):
            TestUtils.create_tournament(
                self.MANY_ID, f'Tournament {index}', overrides={'rounds': 3}
            )
        write_snapshot(self.MANY_ID, SnapshotReason.BEFORE_PAIRING)

        modal = open_panel(page, self.MANY_ID)

        row = modal.locator('tbody tr').first
        expect(row).to_contain_text('4 tournaments')
        detail = row.locator('.collapse')
        expect(detail).not_to_be_visible()

        row.locator('button[data-bs-toggle="collapse"]').click()

        expect(detail).to_be_visible()
        expect(detail).to_contain_text('Tournament 0')
        expect(detail).to_contain_text('Tournament 3')


@pytest.mark.e2e
class TestAFailingBackupIsSeen:
    """A backup fails on the worker thread, long after the request that caused
    it, so the event page has to say so by itself."""

    EVENT_ID = 'test-snapshots-failing-e2e'

    def test_the_event_page_warns_that_the_backups_stopped(self, page: Page):
        TestUtils.create_event(self.EVENT_ID)
        directory = snapshots_dir(self.EVENT_ID)
        directory.mkdir(parents=True, exist_ok=True)
        # A folder that cannot be written to: a memory stick pulled out, a
        # share gone, rights changed.
        directory.chmod(0o500)
        try:
            modal = open_panel(page, self.EVENT_ID)
            modal.get_by_role('button', name='Back up now').click()

            # The panel says so, and so does the event page from then on.
            expect(page.locator('body')).to_contain_text('failed')
            page.goto(f'/event/{self.EVENT_ID}')
            warning = page.locator('#backup-message').get_by_text(
                'This event is no longer being backed up'
            )
            expect(warning).to_have_count(1)
            # One warning, not one per page shown.
            page.goto(f'/event/{self.EVENT_ID}/tournaments')
            expect(warning).to_have_count(1)
        finally:
            directory.chmod(0o700)
