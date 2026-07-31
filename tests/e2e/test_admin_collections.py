import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.pairings.variations import StandardTeamSwissVariation
from tests.test_config import TestUtils
from utils.enum import EventType


TEAM_EVENT_ID = 'admin-collections-team-event'
PRIZE_EVENT_ID = 'admin-collections-prize-event'
TOURNAMENT_ID = 'admin-collections-test-tournament'
SECOND_TOURNAMENT_ID = 'admin-collections-second-tournament'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(
        TEAM_EVENT_ID,
        via_api_request_context=api_request_context,
        overrides={'event_type': EventType.TEAM.value},
    )
    TestUtils.create_tournament(
        TEAM_EVENT_ID,
        TOURNAMENT_ID,
        overrides={
            'pairing': StandardTeamSwissVariation.static_id(),
            'team_player_count': 4,
        },
    )
    TestUtils.create_tournament(
        TEAM_EVENT_ID,
        SECOND_TOURNAMENT_ID,
        overrides={
            'pairing': StandardTeamSwissVariation.static_id(),
            'team_player_count': 4,
        },
    )
    TestUtils.create_event(
        PRIZE_EVENT_ID,
        via_api_request_context=api_request_context,
    )
    TestUtils.create_tournament(
        PRIZE_EVENT_ID,
        TOURNAMENT_ID,
        via_api_request_context=api_request_context,
    )
    TestUtils.create_tournament(
        PRIZE_EVENT_ID,
        SECOND_TOURNAMENT_ID,
        via_api_request_context=api_request_context,
    )
    yield
    TestUtils.delete_event(TEAM_EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.delete_event(PRIZE_EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestAdminCollections:
    def test_event_row_opens_event_without_making_buttons_click_through(
        self, page: Page
    ):
        page.goto('/current_events?collection_view=list')
        item = page.get_by_test_id('events-item').filter(has_text=PRIZE_EVENT_ID)
        expect(item).to_be_visible()
        row = item.locator('.collection-list-row')
        expect(row).to_have_class(re.compile(r'\bcollection-list-row-actionable\b'))

        item.locator('.collection-details-button').click()
        expect(page).to_have_url(re.compile(r'/current_events'))

        item.locator('.collection-list-cell-identity').click()
        expect(page).to_have_url(re.compile(rf'/event/{PRIZE_EVENT_ID}/tournaments$'))

    def test_team_supports_list_card_and_details_views(self, page: Page):
        page.goto(f'/event/{TEAM_EVENT_ID}/teams')
        TestUtils.button_by_text(page, 'Create a team').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        name = 'Collection Team'
        modal.get_by_test_id('name').fill(name)
        modal.get_by_role('button', name='Create', exact=True).click()

        item = page.get_by_test_id('teams-item').filter(has_text=name)
        expect(item).to_be_visible()
        empty_drop_zones = page.locator('.team-sortable').filter(
            has=page.locator('.non-sortable')
        )
        expect(empty_drop_zones.first).to_have_class(
            re.compile(r'\bcollection-list-items\b')
        )
        details = item.locator('.collection-list-details')
        item.locator('.collection-details-button').click()
        expect(details).to_have_class(re.compile(r'\bshow\b'))
        details_toggle = page.get_by_role('checkbox', name='Details')
        details_toggle.check()
        expect(item.locator('.collection-list-details')).to_have_class(
            re.compile(r'\bshow\b')
        )
        details_toggle.uncheck()
        expect(details).not_to_have_class(re.compile(r'\bshow\b'))

        auto_sort_directions = item.evaluate(
            """element => {
                const container = element.closest('.team-sortable');
                const onMove = Sortable.get(container).options.onMove;
                const target = document.createElement('div');
                target.dataset.sortKey = 'lineup-avg';
                const related = element.cloneNode(true);
                const relatedInput = related.querySelector('.assignment-input');
                const draggedValue = Number(
                    element.querySelector('.assignment-input').dataset.lineupAvg
                );
                const directionFor = relatedValue => {
                    relatedInput.dataset.lineupAvg = relatedValue;
                    return onMove({
                        to: target,
                        dragged: element,
                        related,
                        willInsertAfter: false,
                    });
                };
                return {
                    beforeLower: directionFor(draggedValue - 1),
                    afterEqual: directionFor(draggedValue),
                    afterHigher: directionFor(draggedValue + 1),
                };
            }"""
        )
        assert auto_sort_directions == {
            'beforeLower': -1,
            'afterEqual': 1,
            'afterHigher': 1,
        }

        page.get_by_role('button', name='Card view').click()
        item = page.get_by_test_id('teams-item').filter(has_text=name)
        expect(page.get_by_role('checkbox', name='Rosters')).to_be_checked()
        expect(page.get_by_role('checkbox', name='Lineups')).to_be_checked()
        expect(item.locator('.collection-card-details')).to_have_count(0)
        expect(item.locator('.collection-component-card_content')).to_contain_text(
            'Roster'
        )
        expect(item.locator('.card-block-button button')).to_be_visible()

    def test_prize_category_uses_the_shared_collection(self, page: Page):
        page.goto(f'/event/{PRIZE_EVENT_ID}/prizes')
        TestUtils.button_by_text(page, 'Create a Prize Bracket').click()
        create_category = page.get_by_role('button', name='Create a category')
        create_category.first.click()
        create_category.last.click()

        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        name = 'Collection Category'
        modal.get_by_test_id('name').fill(name)
        modal.get_by_role('button', name='Create', exact=True).click()

        create_category = page.get_by_role('button', name='Create a category')
        create_category.first.click()
        create_category.last.click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_test_id('name').fill('Second Collection Category')
        modal.get_by_role('button', name='Create', exact=True).click()

        item = page.get_by_test_id('prize-categories-item').filter(has_text=name)
        expect(item).to_be_visible()
        expect(item.locator('.collection-component-drag_handle i')).to_have_class(
            re.compile(r'\bbi-grip-vertical\b')
        )

        page.get_by_role('button', name='Card view').click()
        item = page.get_by_test_id('prize-categories-item').filter(has_text=name)
        expect(item.locator('.collection-component-drag_handle i')).to_have_class(
            re.compile(r'\bbi-arrows-move\b')
        )

    def test_tournament_drag_icon_matches_the_view(self, page: Page):
        page.goto(f'/event/{PRIZE_EVENT_ID}/tournaments')
        expect(page.locator('.collection-list-header')).not_to_contain_text(
            'Project-Id-Version'
        )
        column_geometry = page.locator('.admin-collection-list').evaluate(
            """(collection) => {
                const headers = [
                    ...collection.querySelectorAll(
                        ':scope > .collection-list-header > '
                        + '.collection-list-header-cell'
                    ),
                ];
                const cells = [
                    ...collection.querySelector(
                        '.collection-list-row'
                    ).querySelectorAll(':scope > .collection-list-cell'),
                ];
                return headers.map((header, index) => {
                    const headerRect = header.getBoundingClientRect();
                    const cellRect = cells[index].getBoundingClientRect();
                    return {
                        leftDifference: headerRect.left - cellRect.left,
                        widthDifference: headerRect.width - cellRect.width,
                    };
                });
            }"""
        )
        assert all(
            abs(column['leftDifference']) < 1 and abs(column['widthDifference']) < 1
            for column in column_geometry
        )
        item = page.get_by_test_id('tournaments-item').filter(has_text=TOURNAMENT_ID)
        expect(item.locator('.collection-list-row')).not_to_have_class(
            re.compile(r'\bcollection-list-row-actionable\b')
        )
        expect(item.locator('.collection-component-drag_handle i')).to_have_class(
            re.compile(r'\bbi-grip-vertical\b')
        )
        tie_breaks = item.locator('.collection-component-tie_break_summary')
        expect(tie_breaks).to_contain_text('None')
        expect(tie_breaks.locator('[class*="bi-exclamation"]')).to_have_count(1)
        configuration_buttons = item.locator(
            'button[aria-label="Configure the tie-breaks of the tournament."]'
        )
        expect(configuration_buttons).to_have_count(1)
        expect(
            tie_breaks.get_by_role(
                'button',
                name='Configure the tie-breaks of the tournament.',
            )
        ).to_be_visible()
        configuration_button = tie_breaks.locator('button.collection-inline-edit')
        expect(configuration_button).to_be_visible()
        expect(
            configuration_button.locator('.collection-inline-edit-label')
        ).to_have_css('border-bottom-style', 'dotted')
        expect(configuration_button.locator('.bi-gear-fill')).to_have_count(0)

        page.get_by_role('button', name='Card view').click()
        item = page.get_by_test_id('tournaments-item').filter(has_text=TOURNAMENT_ID)
        expect(item.locator('.collection-component-drag_handle i')).to_have_class(
            re.compile(r'\bbi-arrows-move\b')
        )
        expect(
            item.get_by_role(
                'button',
                name='Configure the tie-breaks of the tournament.',
            )
        ).to_be_visible()

    def test_staff_rows_do_not_overflow_when_columns_fit(self, page: Page):
        page.set_viewport_size({'width': 1280, 'height': 800})
        page.goto(f'/event/{PRIZE_EVENT_ID}/accounts')
        get_started = page.get_by_role('button', name='Get started')
        if get_started.is_visible():
            get_started.click()

        list_scroll = page.locator('.admin-collection-list-scroll')
        expect(list_scroll).to_be_visible()
        has_unnecessary_overflow = list_scroll.evaluate(
            '(element) => element.scrollWidth > element.clientWidth + 1'
        )
        assert not has_unnecessary_overflow

        regular_cell = page.locator(
            '.collection-list-cell:not(.collection-list-cell-actions)'
            ':not(.collection-details-column):not(.collection-drag-column)'
        ).first
        expect(regular_cell).to_have_css('overflow', 'hidden')

        page.get_by_role('button', name='Card view').click()
        account = page.get_by_test_id('accounts-item').first
        expect(account.locator('.collection-card-body')).to_have_count(0)
