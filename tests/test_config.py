"""Test configuration and utilities."""

from pathlib import Path
from typing import Dict
import re
from playwright.sync_api import Page, Locator


class TestConfig:
    """Configuration for test environment."""

    # Server configuration
    TEST_HOST = '127.0.0.1'  # Use IP instead of localhost
    TEST_PORT = 9000
    TEST_TIMEOUT = 8  # seconds to wait for server startup

    # Test data configuration
    TEST_DATA_DIR = Path(__file__).parent / 'data'

    @classmethod
    def get_test_env_vars(cls) -> Dict[str, str]:
        """Get environment variables for test environment."""
        return {
            'TEST_ENV': 'true',
        }


class TestUtils:
    """Utility functions for tests."""

    @staticmethod
    def button_by_text(page: Page, text: str) -> Locator:
        """
        Returns a button by visible text (case-insensitive), ignoring icons or extra whitespace.
        """
        return page.get_by_role(
            'button', name=re.compile(rf'\b{text}\b', re.IGNORECASE)
        )

    @staticmethod
    def take_screenshot(page, name: str):
        """Take a screenshot for debugging."""
        screenshot_dir = Path(__file__).parent / 'screenshots'
        screenshot_dir.mkdir(exist_ok=True)
        screenshot_path = screenshot_dir / f'{name}.png'
        return page.screenshot(path=screenshot_path)
