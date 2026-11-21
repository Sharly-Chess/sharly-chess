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
class TestCommentingABackup:
    """The comment is asked for in a modal of its own, between the panel and
    the backup: nothing but the browser says whether what is typed travels
    with the press, and whether the panel comes back after it."""

    EVENT_ID = 'test-snapshots-comment-e2e'

    def test_the_comment_is_what_the_new_backup_reads_as(self, page: Page):
        TestUtils.create_event(self.EVENT_ID)

        modal = open_panel(page, self.EVENT_ID)
        modal.get_by_role('button', name='Back up now').click()

        # The cursor lands in the field, and Enter is enough to take the
        # backup: a comment is typed and the modal left in one go.
        ask = page.locator('#event-snapshot-now-modal')
        expect(ask.locator('#snapshot-comment')).to_be_focused()
        page.keyboard.type('Essai n°2')
        page.keyboard.press('Enter')

        # The panel is back, with the backup it was left for in it.
        panel = page.locator('#event-snapshots-modal')
        expect(panel).to_be_visible()
        expect(panel.locator('tbody tr').first).to_contain_text('Essai n°2')

    def test_going_back_from_the_comment_takes_no_backup(self, page: Page):
        uniq_id = 'test-snapshots-comment-back-e2e'
        TestUtils.create_event(uniq_id)

        modal = open_panel(page, uniq_id)
        modal.get_by_role('button', name='Back up now').click()
        ask = page.locator('#event-snapshot-now-modal')
        expect(ask).to_be_visible()
        ask.get_by_role('button', name='Back', exact=True).click()

        panel = page.locator('#event-snapshots-modal')
        expect(panel).to_be_visible()
        expect(panel).to_contain_text('No backup has been taken of this event yet')

    def test_a_backup_commented_with_a_space_is_restored_from_the_panel(
        self, page: Page
    ):
        """The comment ends up in the backup's file name, which the browser
        asks for in a URL: a space escaped as a URL escapes it was looked for
        under a name the file did not have, and the backup could not be
        restored."""
        uniq_id = 'test-snapshots-comment-restore-e2e'
        TestUtils.create_event(uniq_id)
        set_event_name(uniq_id, 'The state to come back to')
        write_snapshot(uniq_id, SnapshotReason.MANUAL, comment='deux mots')
        set_event_name(uniq_id, 'The mistake')

        modal = open_panel(page, uniq_id)
        modal.locator('button:has(.bi-arrow-counterclockwise)').first.click()

        confirm = page.locator('#event-snapshot-restore-modal')
        expect(confirm).to_be_visible()
        confirm.locator('#snapshot-restore-button').click()

        expect(confirm).not_to_be_visible()
        assert event_name(uniq_id) == 'The state to come back to'


@pytest.mark.e2e
class TestAFailingBackupIsSeen:
    """A backup fails on the worker thread, long after the request that caused
    it, so the event page has to say so by itself."""

    EVENT_ID = 'test-snapshots-failing-e2e'

    def test_the_event_page_warns_that_the_backups_stopped(self, page: Page):
        TestUtils.create_event(self.EVENT_ID)
        directory = snapshots_dir(self.EVENT_ID)
        directory.parent.mkdir(parents=True, exist_ok=True)
        # A folder that cannot be written to: a memory stick pulled out, a
        # share gone, rights changed. A file in its place fails on every
        # system, where a folder's rights do not on Windows.
        directory.write_bytes(b'')
        try:
            modal = open_panel(page, self.EVENT_ID)
            modal.get_by_role('button', name='Back up now').click()
            ask = page.locator('#event-snapshot-now-modal')
            expect(ask).to_be_visible()
            ask.get_by_role('button', name='Back up now').click()

            # The panel says so, and so does the event page from then on.
            expect(page.locator('body')).to_contain_text(
                'The last backup could not be written.'
            )
            page.goto(f'/event/{self.EVENT_ID}')
            warning = page.locator('#backup-message').get_by_text(
                'This event is no longer being backed up'
            )
            expect(warning).to_have_count(1)
            # One warning, not one per page shown.
            page.goto(f'/event/{self.EVENT_ID}/tournaments')
            expect(warning).to_have_count(1)
        finally:
            directory.unlink()


@pytest.mark.e2e
class TestThePanelIsReachedFromTheEvent:
    """The backups are listed from the event's own configuration, not only
    from the list of events."""

    EVENT_ID = 'test-snapshots-config-e2e'

    def test_the_configuration_opens_the_panel(self, page: Page):
        TestUtils.create_event(self.EVENT_ID)
        write_snapshot(self.EVENT_ID, SnapshotReason.BEFORE_PAIRING)

        page.goto('/current_events')
        page.locator(
            f'button[hx-get*="event-modal/update/{self.EVENT_ID}"]'
        ).first.click()
        modal = page.locator('.admin-event-edit-modal')
        expect(modal).to_be_visible()
        modal.get_by_role('button', name='Backups').click()

        panel = page.locator('#event-snapshots-modal')
        expect(panel).to_be_visible()
        expect(panel.locator('tbody tr')).to_have_count(1)
