"""Keyboard shortcuts: Shift+Enter submits a modal with the alternative of its
split submit button, and the players table is driven from the keyboard (↑/↓
between rows, Enter to open a player, Space or the check-in icon to check them
in or out)."""

import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.loader import EventLoader
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils

TOURNAMENT = 'Open'


@pytest.fixture
def event_id(request, api_request_context: APIRequestContext):
    """An event of its own for each test, which all change its players."""
    event_id = (
        f'keyboard-shortcuts-ui-{request.node.originalname.replace("_", "-")[5:]}'
    )
    TestUtils.create_event(event_id, via_api_request_context=api_request_context)
    TestUtils.create_tournament(event_id, TOURNAMENT)
    event = EventLoader().load_event(event_id)
    tournament = event.tournaments_by_name[TOURNAMENT]
    for index in range(2):
        event.add_player(
            StoredPlayer(id=None, last_name=f'PLAYER{index + 1}', check_in=False),
            [tournament],
        )
    yield event_id
    TestUtils.delete_event(event_id, via_api_request_context=api_request_context)


def _player_rows(page: Page):
    return page.locator('#players-table tbody tr[id^="player-"]')


def _open_players_tab(page: Page, event_id: str):
    page.goto(f'/event/{event_id}/players')
    rows = _player_rows(page)
    expect(rows).to_have_count(2)
    TestUtils.wait_for_htmx_bound(page, '#players-table [data-sc-row-check-in]')
    return rows


@pytest.mark.e2e
class TestKeyboardShortcuts:
    def test_shift_enter_creates_and_adds_another(self, page: Page, event_id: str):
        page.goto(f'/event/{event_id}/players')
        TestUtils.wait_for_htmx_bound(page, '[data-testid=add-player-button]')
        page.get_by_test_id('add-player-button').click()
        modal = page.locator('.modal-dialog')
        last_name = modal.locator('input[name="last_name"]')
        TestUtils.fill_and_confirm(last_name, 'SHIFTENTER')
        last_name.press('Shift+Enter')
        expect(
            modal.get_by_text('Player [SHIFTENTER] has been created.')
        ).to_be_visible()
        expect(modal.locator('input[name="last_name"]')).to_have_value('')

    def test_arrows_move_between_rows_and_space_checks_in(
        self, page: Page, event_id: str
    ):
        rows = _open_players_tab(page, event_id)
        rows.nth(0).focus()
        page.keyboard.press('ArrowDown')
        expect(rows.nth(1)).to_be_focused()

        page.keyboard.press('Space')
        check_in = rows.nth(1).locator('[data-sc-row-check-in]')
        expect(check_in).to_have_class(re.compile('bi-check-circle-fill'))
        expect(rows.nth(1)).to_be_focused()
        TestUtils.wait_for_htmx_idle(page)

        page.keyboard.press('Space')
        expect(rows.nth(1).locator('[data-sc-row-check-in]')).to_have_class(
            re.compile('bi-x-circle-fill')
        )

        page.keyboard.press('ArrowUp')
        expect(rows.nth(0)).to_be_focused()

    def test_the_check_in_icon_is_reachable_and_keeps_the_focus(
        self, page: Page, event_id: str
    ):
        rows = _open_players_tab(page, event_id)
        check_in = rows.nth(0).locator('[data-sc-row-check-in]')
        check_in.focus()
        page.keyboard.press('Enter')
        expect(rows.nth(0).locator('[data-sc-row-check-in]')).to_have_class(
            re.compile('bi-check-circle-fill')
        )
        expect(rows.nth(0).locator('[data-sc-row-check-in]')).to_be_focused()
        page.keyboard.press('ArrowDown')
        expect(rows.nth(1).locator('[data-sc-row-check-in]')).to_be_focused()
        page.keyboard.press('Space')
        expect(rows.nth(1).locator('[data-sc-row-check-in]')).to_have_class(
            re.compile('bi-check-circle-fill')
        )

    def test_enter_opens_the_player(self, page: Page, event_id: str):
        rows = _open_players_tab(page, event_id)
        rows.nth(0).focus()
        page.keyboard.press('Enter')
        modal = page.locator('.modal-dialog')
        expect(modal.locator('input[name="last_name"]')).to_have_value('PLAYER1')
