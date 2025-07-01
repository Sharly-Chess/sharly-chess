"""Basic end-to-end tests using Playwright."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestBasicFunctionality:
    """Basic end-to-end tests for the application."""

    def test_page_fixture_works(self, page: Page):
        """Test that the page fixture is working."""

        # First check if page is not None
        assert page is not None, 'Page fixture should not be None'

        # Check if page has the expected attributes
        assert hasattr(page, 'goto'), 'Page should have goto method'
        assert hasattr(page, 'base_url'), 'Page should have base_url attribute'

        print(f'Page type: {type(page)}')
        print(f'Base URL: {page.base_url}')

    def test_homepage_loads(self, page: Page):
        """Test that the homepage loads successfully."""

        # Test basic Playwright navigation with data URL
        page.goto(page.base_url)
        expect(page).to_have_title('Sharly Chess')
