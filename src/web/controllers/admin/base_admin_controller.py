from functools import partial
from typing import Any

from litestar.exceptions import NotFoundException
from litestar.plugins.htmx import HTMXRequest

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from utils.enum import Cadence
from data.screens.manager import ScreenTypeManager
from plugins.manager import plugin_manager
from web.admin.collection import (
    AdminCollectionSpec,
    get_admin_collection_spec,
    resolve_admin_collection_show_details,
    resolve_admin_collection_view_mode,
)
from web.controllers.base_controller import BaseController, WebContext
from web.session import SessionAdminTheme
from web.utils import RequestUtils


def nav_count(num: int) -> str:
    """The count shown next to a sidebar entry, empty when there is none."""
    return str(num) if num else ''


class AdminWebContext(WebContext):
    """
    The basic admin web context.
    """

    def __init__(
        self,
        request: HTMXRequest,
        admin_tab: str | None = None,
        reload_event: bool = False,
    ):
        self.admin_event = RequestUtils.get_optional_event(request, reload_event)
        super().__init__(request, reload_client=reload_event)
        self.admin_tab = admin_tab
        self.check_admin_tab()

    def get_admin_event(self) -> Event:
        if self.admin_event is None:
            # get_optional_event swallows a locked/inaccessible event to keep page
            # rendering working, so admin_event may be None here. A handler that
            # truly needs the event re-requests it via get_event, which raises the
            # proper 423 (locked) or 404 (missing) error rather than asserting.
            return RequestUtils.get_event(self.request)
        return self.admin_event

    def check_admin_tab(self) -> None:
        if self.admin_tab not in [
            None,
            'home',
            'passed_events',
            'current_events',
            'coming_events',
            'archives',
            'championships',
            'coming_championships',
            'passed_championships',
            'championship_archives',
        ]:
            raise NotFoundException(
                f'Invalid value [{self.admin_tab}] for parameter [admin_tab]'
            )

    @property
    def background_color(self) -> str:
        return SharlyChessConfig.admin_background_color

    @property
    def theme(self) -> str:
        """The theme set in the application window on the server; a client
        connected over the network chooses its own, following its system's
        appearance until it does."""
        if self.client.is_local:
            return SharlyChessConfig().stored_config.admin_theme
        return SessionAdminTheme(self.request).get()

    @property
    def interface(self) -> str:
        return 'admin'

    def get_admin_collection_spec(self, collection_key: str) -> AdminCollectionSpec:
        collection_spec = get_admin_collection_spec(collection_key)
        plugin_manager.hook_for_event(self.admin_event, 'extend_admin_collection')(
            collection_key=collection_key,
            collection_spec=collection_spec,
            event=self.admin_event,
        )
        return collection_spec

    @property
    def template_context(self) -> dict[str, Any]:
        per_plugin_context = plugin_manager.hook_for_event(
            self.admin_event, 'get_base_admin_template_context'
        )()
        plugin_context = {
            key: value
            for context in per_plugin_context
            for key, value in context.items()
        }

        return (
            super().template_context
            | {
                'admin_tab': self.admin_tab,
                'admin_event': self.admin_event,
                'get_admin_collection_spec': self.get_admin_collection_spec,
                'get_admin_collection_view_mode': partial(
                    resolve_admin_collection_view_mode, self.request
                ),
                'get_admin_collection_show_details': partial(
                    resolve_admin_collection_show_details, self.request
                ),
            }
            | plugin_context
        )


class BaseAdminController(BaseController):
    """A base class inherited by all the admin controllers."""

    @staticmethod
    def _get_federation_options() -> dict[str, str]:
        return {
            federation_id: f'{federation_id} - {federation_name}'
            for federation_id, federation_name in SharlyChessConfig().federations.items()
        }

    @staticmethod
    def _months_options() -> dict[str, str]:
        return {
            '1': _('January'),
            '2': _('February'),
            '3': _('March'),
            '4': _('April'),
            '5': _('May'),
            '6': _('June'),
            '7': _('July'),
            '8': _('August'),
            '9': _('September'),
            '10': _('October'),
            '11': _('November'),
            '12': _('December'),
        }

    @staticmethod
    def _get_rating_options() -> dict[str, str]:
        return {
            WebContext.value_to_form_data(rating.value): rating.short_name
            for rating in Cadence
        }

    @staticmethod
    def _get_timer_delay_texts(delays: dict[int, int]) -> dict[int, str]:
        return {
            1: _(
                'The timer is green until {delay_1} minutes before the start of the rounds, then turns gradually orange until {delay_2} minutes before the start of the rounds.'
            ).format(delay_1=delays[1], delay_2=delays[2]),
            2: _(
                'The timer is orange {delay_2} minutes before the start of the rounds, then turns gradually red until the start of the rounds.'
            ).format(delay_2=delays[2]),
            3: _(
                'The timer stays red from the start of the rounds and for {delay_3} minutes after.'
            ).format(delay_3=delays[3]),
        }

    @staticmethod
    def _get_screen_type_options(
        family_screens_only: bool, event: Event
    ) -> dict[str, str]:
        return {'': '-'} | {
            screen_type.id: screen_type.name
            for screen_type in ScreenTypeManager(event).objects()
            if (not family_screens_only or screen_type.families_allowed)
            and screen_type.supports_event_type(event.event_type)
        }

    @staticmethod
    def _get_timer_options(event: Event) -> dict[str, str]:
        return {'': '-'} | {
            str(timer.id): timer.name for timer in event.timers_by_id.values()
        }

    @staticmethod
    def _get_ranking_crosstable_options() -> dict[str, str]:
        options: dict[str, str] = {
            'on': _('Crosstable'),
            'off': _('Ranking only'),
        }
        return options

    @staticmethod
    def _admin_validate_record_illegal_moves_update_data(
        data: dict[str, str],
        errors: dict[str, str],
    ) -> int | None:
        field = 'record_illegal_moves'
        record_illegal_moves: int | None
        try:
            record_illegal_moves = WebContext.form_data_to_int(data, field)
            assert record_illegal_moves is None or 0 <= record_illegal_moves <= 3
        except (ValueError, AssertionError):
            record_illegal_moves = None
            errors['record_illegal_moves'] = _('Invalid value [{value}].').format(
                value=data[field]
            )
        return record_illegal_moves

    @staticmethod
    def _admin_validate_background_color_update_data(
        data: dict[str, str],
        errors: dict[str, str],
    ) -> str | None:
        field = 'background_color'
        background_color: str | None = None
        color_checkbox = WebContext.form_data_to_bool(data, field + '_checkbox')
        if not color_checkbox:
            try:
                background_color = WebContext.form_data_to_rgb(data, field)
            except ValueError:
                errors[field] = _(
                    'Invalid colour [{color}] ([#RRGGBB] expected).'
                ).format(color={data[field]})
        return background_color
