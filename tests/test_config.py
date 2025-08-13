"""Test configuration and utilities."""

import time
from urllib import parse
from common import BASE_DIR
from common.sharly_chess_config import SharlyChessConfig
from data.pairings.systems import SwissPairingSystem
from data.pairings.variations import StandardSwissVariation
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Optional, Any
import re
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredEvent,
    StoredTournament,
)
from playwright.sync_api import Page, Locator, APIRequestContext, APIResponse
from utils.enum import ScreenType


class TestConfig:
    """Configuration for test environment."""

    # Server configuration
    TEST_HOST = '127.0.0.1'  # Use IP instead of localhost
    TEST_PORT = 9000
    TEST_TIMEOUT = 30  # seconds to wait for server startup

    # Test data configuration
    TEST_DATA_DIR = Path(__file__).parent / 'tmp'

    @classmethod
    def get_test_env_vars(cls) -> Dict[str, str]:
        """Get environment variables for test environment."""
        return {
            'TEST_ENV': 'true',
        }


class TestUtils:
    """Utility functions for tests."""

    event_defaults = {
        'name': 'Test Event',
        'custom_exec_mode': SharlyChessConfig.default_custom_exec_mode,
        'federation': 'FRA',
        'public': True,
        'location': 'Paris',
        'hide_background_image': True,
        'background_image': None,
        'background_color': '#ffffff',
        'record_illegal_moves': 0,
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

    @staticmethod
    def prepare_form_data(data: dict[str, object]) -> str:
        out: dict[str, object] = {}

        for k, v in data.items():
            if v is None:
                continue
            if isinstance(v, bool):
                if v:
                    # HTML checkbox semantics
                    out[k] = 'on'
                else:
                    continue
            elif isinstance(v, (list, tuple)):
                # leave as sequence; urlencode(doseq=True) expands it
                out[k] = [str(x) for x in v]
            else:
                out[k] = str(v)

        return parse.urlencode(out, doseq=True)

    @staticmethod
    def check_api_response(response: APIResponse):
        assert response.ok
        body = response.body().decode('utf-8')

        # Match divs with class containing 'invalid-feedback', extract id and inner text
        matches = re.findall(
            r'<div[^>]*\bid="([^"]+)"[^>]*class="[^"]*\binvalid-feedback\b[^"]*"[^>]*>(.*?)</div>',
            body,
            re.DOTALL | re.IGNORECASE,
        )

        # Create list of (id, trimmed text)
        errors = [(div_id, text.strip()) for div_id, text in matches]

        assert not errors, errors

    @staticmethod
    def wait_for_htmx_idle(page, timeout=5000):
        page.wait_for_function(
            "() => !document.querySelector('.htmx-request, .htmx-swapping')",
            timeout=timeout,
        )

    @staticmethod
    def poll_expect_with_reload(
        page,
        assertion: Callable[[], None],
        retries: int = 5,
        delay_secs: float = 0.2,
    ):
        for attempt in range(retries):
            page.reload()
            try:
                assertion()
                return
            except AssertionError:
                if attempt == retries - 1:
                    raise
                time.sleep(delay_secs)

    @classmethod
    def create_event(
        cls,
        uniq_id: str,
        via_api_request_context: APIRequestContext | None = None,
        overrides: Optional[dict] = None,
    ):
        overrides = overrides or {}

        now = datetime.now()
        start_ts = now.strftime('%Y-%m-%dT%H:%M')
        stop_ts = (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')

        # Provide defaults
        defaults = {
            **cls.event_defaults,
            'uniq_id': uniq_id,
            'start': start_ts,
            'stop': stop_ts,
        }

        # Merge overrides
        data = {**defaults, **overrides}

        form_data = cls.prepare_form_data(data)

        database = EventDatabase(uniq_id)
        database.file.unlink(missing_ok=True)

        if via_api_request_context:
            res = via_api_request_context.post(
                '/admin/config/create-event',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data=form_data,
            )
            cls.check_api_response(res)
        else:
            database.create()
            stored_event = StoredEvent(**data)
            with EventDatabase(uniq_id, write=True) as event_database:
                event_database.update_stored_event(stored_event)
                event_database.commit()

    @classmethod
    def delete_event(
        cls,
        uniq_id: str,
        via_api_request_context: APIRequestContext | None = None,
    ):
        if via_api_request_context:
            form_data = cls.prepare_form_data({'uniq_id': uniq_id})
            res = via_api_request_context.post(
                f'/admin/event-delete/{uniq_id}',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data=form_data,
            )
            TestUtils.check_api_response(res)
        else:
            EventDatabase(uniq_id).delete()

    @classmethod
    def create_tournament(
        cls,
        event_uniq_id: str,
        uniq_id: str,
        via_api_request_context: APIRequestContext | None = None,
        overrides: dict | None = None,
        json_file: str | None = None,
    ):
        overrides = overrides or {}

        # Provide defaults
        defaults: dict[str, Any] = {
            'id': None,
            'uniq_id': uniq_id,
            'name': uniq_id,
            'time_control_initial_time': None,
            'time_control_increment': None,
            'time_control_handicap_penalty_step': None,
            'time_control_handicap_penalty_value': None,
            'time_control_handicap_min_time': None,
            'record_illegal_moves': None,
            'rules': None,
            'first_board_number': None,
            'paired_bye_result': None,
            'max_byes': None,
            'last_rounds_no_byes': None,
            'tie_breaks': None,
            'location': None,
            'start': None,
            'stop': None,
            'pairing': SwissPairingSystem.static_id(),
            'current_round': None,
            'check_in_open': False,
            'rounds': 7,
            'rating': 1,
            'last_update': 0.0,
            'last_result_update': 0.0,
            'last_illegal_move_update': 0.0,
            'last_check_in_update': 0.0,
            'stored_prize_groups': [],
            'errors': {},
            'plugin_data': None,
        }

        # Merge overrides
        data = {**defaults, **overrides}

        if via_api_request_context:
            data['SWISS_pairing_variation'] = StandardSwissVariation.static_id()
            form_data = cls.prepare_form_data(data)
            res = via_api_request_context.post(
                f'/admin/tournament-create/{event_uniq_id}',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data=form_data,
            )
            cls.check_api_response(res)
        else:
            with EventDatabase(event_uniq_id, write=True) as event_database:
                stored_tournament = StoredTournament(**data)
                event_database.add_stored_tournament(stored_tournament)
                event_database.commit()

        with EventDatabase(event_uniq_id) as event_database:
            tournaments = event_database.load_stored_tournaments()
            stored_tournament = next(t for t in tournaments if t.uniq_id == uniq_id)

        if json_file and via_api_request_context:
            json_path = BASE_DIR / 'tests' / 'json' / f'{json_file}.json'
            assert json_path.exists(), f'Missing test file: {json_path}'

            # Send as multipart/form-data with a real file field named "file"
            res = via_api_request_context.post(
                f'/admin/tournament-import/{event_uniq_id}/{stored_tournament.id}/PAPI_JSON',
                multipart={
                    # UploadFile field name in your handler is "file"
                    'file': {
                        'name': f'{json_file}.json',
                        'mimeType': 'application/json',
                        'buffer': json_path.read_bytes(),
                    },
                },
            )
            cls.check_api_response(res)

        return stored_tournament

    @classmethod
    def delete_tournament(
        cls,
        api_request_context: APIRequestContext,
        event_uniq_id: str,
        stored_tournament: StoredTournament,
    ):
        form_data = cls.prepare_form_data({'uniq_id': stored_tournament.uniq_id})
        res = api_request_context.post(
            f'/admin/tournament-delete/{event_uniq_id}/{stored_tournament.id}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=form_data,
        )
        cls.check_api_response(res)

    @classmethod
    def create_screen(
        cls,
        api_request_context: APIRequestContext,
        event_uniq_id: str,
        uniq_id: str,
        screen_type: ScreenType,
        overrides: Optional[dict] = None,
    ):
        overrides = overrides or {}

        # Provide defaults
        defaults: dict[str, Any] = {
            'id': None,
            'uniq_id': uniq_id,
            'name': uniq_id,
            'init_set_tournament_id': None,
            'columns': None,
            'font_size': None,
            'menu_link': None,
            'menu_text': None,
            'menu': None,
            'timer_id': None,
            'input_exit_button': None,
            'players_show_unpaired': None,
            'players_show_opponent': None,
            'results_limit': None,
            'results_max_age': None,
            'background_image': None,
            'background_color': None,
            'results_tournament_ids': [],
            'ranking_crosstable': False,
            'ranking_round': None,
            'ranking_min_points': None,
            'ranking_max_points': None,
            'stored_screen_sets': [],
            'last_update': 0.0,
            'public': True,
            'message_default': True,
            'message_text': None,
            'errors': {},
        }

        # Merge overrides
        data = {**defaults, **overrides}

        form_data = cls.prepare_form_data(data)
        res = api_request_context.post(
            f'/admin/screen-create/{event_uniq_id}/{screen_type.value}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=form_data,
        )
        cls.check_api_response(res)

        with EventDatabase(event_uniq_id) as event_database:
            stored_screens = event_database.load_stored_screens()
            stored_screen = next(s for s in stored_screens if s.uniq_id == uniq_id)
            return stored_screen

    @classmethod
    def delete_screen(
        cls, api_request_context: APIRequestContext, event_uniq_id: str, screen_id: int
    ):
        res = api_request_context.delete(
            f'/admin/screen-delete/{event_uniq_id}/{screen_id}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        cls.check_api_response(res)

    @classmethod
    def create_family(
        cls,
        api_request_context: APIRequestContext,
        event_uniq_id: str,
        tournament: StoredTournament,
        uniq_id: str,
        family_type: ScreenType,
        overrides: Optional[dict] = None,
    ):
        overrides = overrides or {}

        # Provide defaults
        defaults = {
            'id': None,
            'uniq_id': uniq_id,
            'name': uniq_id,
            'tournament_id': tournament.id,
            'columns': None,
            'font_size': None,
            'menu_link': True,
            'menu_text': '',
            'menu': '@input',
            'timer_id': None,
            'input_exit_button': None,
            'players_show_unpaired': None,
            'players_show_opponent': None,
            'ranking_crosstable': False,
            'ranking_round': None,
            'ranking_min_points': None,
            'ranking_max_points': None,
            'first': None,
            'last': None,
            'parts': None,
            'number': None,
            'last_update': 0.0,
            'public': True,
            'message_default': True,
            'message_text': None,
            'errors': {},
        }

        # Merge overrides
        data = {**defaults, **overrides}

        form_data = cls.prepare_form_data(data)
        res = api_request_context.post(
            f'/admin/family-create/{event_uniq_id}/{family_type.value}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=form_data,
        )
        cls.check_api_response(res)

        with EventDatabase(event_uniq_id) as event_database:
            stored_families = event_database.load_stored_families()
            stored_family = next(f for f in stored_families if f.uniq_id == uniq_id)
            return stored_family

    @classmethod
    def delete_family(
        cls, api_request_context: APIRequestContext, event_uniq_id: str, family_id: int
    ):
        res = api_request_context.delete(
            f'/admin/family-delete/{event_uniq_id}/{family_id}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        cls.check_api_response(res)

    @staticmethod
    def button_by_text(obj: Page | Locator, text: str) -> Locator:
        """
        Returns a button by visible text (case-insensitive), ignoring icons or extra whitespace.
        """
        return obj.get_by_role('button', name=re.compile(rf'\b{text}\b', re.IGNORECASE))

    @staticmethod
    def take_screenshot(page, name: str):
        """Take a screenshot for debugging."""
        screenshot_dir = Path(__file__).parent / 'screenshots'
        screenshot_dir.mkdir(exist_ok=True)
        screenshot_path = screenshot_dir / f'{name}.png'
        return page.screenshot(path=screenshot_path)
