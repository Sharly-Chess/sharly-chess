"""Test configuration and utilities."""

from plugins.manager import plugin_manager  # Noqa
from datetime import datetime, timedelta
from pathlib import Path
import time
from typing import Dict, Optional
import re
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent
from playwright.sync_api import Page, Locator


class TestConfig:
    """Configuration for test environment."""

    # Server configuration
    TEST_HOST = '127.0.0.1'  # Use IP instead of localhost
    TEST_PORT = 9000
    TEST_TIMEOUT = 15  # seconds to wait for server startup

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
    def create_event(uniq_id: str, overrides: Optional[dict] = None):
        overrides = overrides or {}

        now = datetime.now()
        start_ts = time.mktime(now.timetuple())
        stop_ts = time.mktime((now + timedelta(hours=1)).timetuple())

        # Provide defaults
        defaults = {
            'uniq_id': uniq_id,
            'name': 'Test Event',
            'federation': 'FRA',
            'start': start_ts,
            'stop': stop_ts,
            'public': True,
            'path': '',
            'location': 'Paris',
            'hide_background_image': True,
            'background_image': None,
            'background_color': '#ffffff',
            'update_password': '',
            'record_illegal_moves': False,
            'rules': '',
            'message_text': '',
            'message_color': '#000000',
            'message_background_color': '#ffffff',
            'prize_currency': 'EUR',
            'errors': [],
            'timer_colors': {i: None for i in range(1, 4)},
            'timer_delays': {i: None for i in range(1, 4)},
            'plugin_data': {},
        }

        # Merge overrides
        data = {**defaults, **overrides}
        stored_event = StoredEvent(**data)

        EventDatabase(uniq_id).create()
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)
            event_database.commit()

    @staticmethod
    def delete_event(uniq_id: str):
        EventDatabase(uniq_id).delete()
        EventLoader.get(request=None).clear_cache(uniq_id)

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
