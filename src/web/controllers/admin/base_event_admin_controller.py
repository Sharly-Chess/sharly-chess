import logging
from functools import cached_property
from typing import Annotated, Any

from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body

from common.i18n import _
from data.access_levels.client import Client
from data.access_levels.client_tracker import ClientTracker
from data.display_controller import DisplayController
from data.event import Event
from data.rotator import Rotator
from data.screen import Screen
from data.tournament import Tournament
from plugins.manager import plugin_manager
from plugins.utils import PluginNavBarItem
from utils.enum import FormAction, ScreenType
from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
    BaseAdminController,
)
from web.messages import Message
from web.session import SessionHandler


class BaseEventAdminWebContext(AdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str | None,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ] = None,
    ):
        super().__init__(
            request, event_uniq_id=event_uniq_id, data=data, admin_tab=None
        )

        # tracks the visit of the client
        ClientTracker().track_client(
            self.client.host,
            self.client.event.uniq_id if self.client.event else None,
            self.client.account.id,
        )

    @cached_property
    def client(self) -> Client:
        """Returns the client of the request."""
        return Client(self.request, self.admin_event)

    def get_admin_event(self) -> Event:
        assert self.admin_event is not None
        return self.admin_event

    def check_admin_tab(self):
        pass

    def default_tournament_for_print_modal(
        self, tournament_id: int | None
    ) -> list[int] | None:
        tournament_ids: list[int] | None = None
        if (
            tournament_id is None
            and (
                last_tournaments
                := SessionHandler.get_session_admin_print_last_tournaments(self.request)
            )
            is not None
        ):
            event_uniq_id, tids = last_tournaments
            if event_uniq_id == self.get_admin_event().uniq_id:
                tournament_ids = tids

        return tournament_ids

    @property
    def template_context(self) -> dict[str, Any]:
        logging_levels: dict[int, dict[str, str]] = {
            logging.DEBUG: {
                'name': 'DEBUG',
                'class': 'bg-secondary-subtle text-secondary-emphasis',
                'icon_class': 'bi-search',
            },
            logging.INFO: {
                'name': 'INFO',
                'class': 'bg-info-subtle text-info-emphasis',
                'icon_class': 'bi-info-circle',
            },
            logging.WARNING: {
                'name': 'WARNING',
                'class': 'bg-warning-subtle text-warning-emphasis',
                'icon_class': 'bi-exclamation-triangle',
            },
            logging.ERROR: {
                'name': 'ERROR',
                'class': 'bg-danger-subtle text-danger-emphasis',
                'icon_class': 'bi-bug',
            },
            logging.CRITICAL: {
                'name': 'CRITICAL',
                'class': 'bg-danger text-white',
                'icon_class': 'bi-sign-stop',
            },
        }
        event: Event = self.get_admin_event()
        nav_tabs: dict[
            str, dict[str, str | bool | dict[str, dict[str, str | bool]]]
        ] = {}
        if self.client.can_view_event_config:
            nav_tabs |= {
                'admin-event-config-tab': {
                    'title': _('Configuration'),
                    'modal': 'admin-event-modal',
                    'action': FormAction.UPDATE,
                    'icon_class': 'bi-gear-fill',
                },
            }
        if self.client.can_view_tournaments_tab:
            nav_tabs |= {
                'admin-event-tournaments-tab': {
                    'title': _('Tournaments ({num})').format(
                        num=len(event.tournaments_by_id) or '-'
                    ),
                    'template': 'tournaments/tab.html',
                    'icon_class': 'bi-diagram-3-fill',
                },
            }
        if self.client.can_view_players_tab:
            nav_tabs |= {
                'admin-event-players-tab': {
                    'title': _('Players ({num})').format(num=event.player_count or '-'),
                    'template': 'players/tab.html',
                    'icon_class': 'bi-people-fill',
                },
            }
        if self.client.can_view_pairings_tab:
            nav_tabs |= {
                'admin-event-pairings-tab': {
                    'title': _('Pairings'),
                    'template': 'pairings/tab.html',
                    'icon_class': 'bi-arrow-left-right',
                },
            }
        if self.client.can_view_prizes_tab:
            nav_tabs |= {
                'admin-event-prizes-tab': {
                    'title': _('Prizes'),
                    'template': 'prizes/tab.html',
                    'icon_class': 'bi-trophy-fill',
                },
            }
        if self.client.can_manage_screens:
            nav_tabs |= {
                'admin-event-views': {
                    'title': _('Screens'),
                    'icon_class': 'bi-display-fill',
                    'submenu': {
                        'admin-event-screens-tab': {
                            'title': _('Single Screens ({num})').format(
                                num=len(event.basic_screens_by_id) or '-'
                            ),
                            'template': 'screens/tab.html',
                        },
                        'admin-event-families-tab': {
                            'title': _('Families ({num})').format(
                                num=len(event.families_by_id) or '-'
                            ),
                            'template': 'families/tab.html',
                        },
                        'admin-event-rotators-tab': {
                            'title': _('Rotators ({num})').format(
                                num=len(event.rotators_by_id) or '-'
                            ),
                            'template': 'rotators/tab.html',
                        },
                        'admin-event-timers-tab': {
                            'title': _('Timers ({num})').format(
                                num=len(event.timers_by_id) or '-'
                            ),
                            'template': 'timers/tab.html',
                        },
                        'admin-event-display-controllers-tab': {
                            'title': _('Display controllers ({num})').format(
                                num=len(event.display_controllers_by_id) or '-'
                            ),
                            'template': 'display_controllers/tab.html',
                        },
                    },
                },
            }
        elif self.client.can_view_public_screens:
            screens_by_screen_type_sorted_by_uniq_id: dict[ScreenType, list[Screen]]
            rotators: list[Rotator]
            display_controllers: list[DisplayController]
            if self.client.can_view_private_screens:
                screens_by_screen_type_sorted_by_uniq_id = (
                    event.screens_by_screen_type_sorted_by_uniq_id
                )
                rotators = event.rotators_sorted_by_uniq_id
                display_controllers = event.display_controllers_sorted_by_uniq_id
            else:
                screens_by_screen_type_sorted_by_uniq_id = (
                    event.public_screens_by_screen_type_sorted_by_uniq_id
                )
                rotators = event.public_rotators_sorted_by_uniq_id
                display_controllers = event.public_display_controllers_sorted_by_uniq_id
            screens: list[Screen]
            screens = screens_by_screen_type_sorted_by_uniq_id[ScreenType.BOARDS]
            nav_tabs |= {
                'admin-event-boards-screens-tab': {
                    'title': _('Pairings by board ({num})').format(
                        num=len(screens) or '-'
                    ),
                    'template': 'screens/view_tab.html',
                    'disabled': not screens,
                    'icon_class': ScreenType.BOARDS.icon_str,
                },
            }
            screens = screens_by_screen_type_sorted_by_uniq_id[ScreenType.INPUT]
            nav_tabs |= {
                'admin-event-input-screens-tab': {
                    'title': _('Check-in / Results entry ({num})').format(
                        num=len(screens) or '-'
                    ),
                    'template': 'screens/view_tab.html',
                    'disabled': not screens,
                    'icon_class': ScreenType.INPUT.icon_str,
                },
            }
            screens = screens_by_screen_type_sorted_by_uniq_id[ScreenType.PLAYERS]
            nav_tabs |= {
                'admin-event-players-screens-tab': {
                    'title': _('Pairings by player ({num})').format(
                        num=len(screens) or '-'
                    ),
                    'template': 'screens/view_tab.html',
                    'disabled': not screens,
                    'icon_class': ScreenType.PLAYERS.icon_str,
                },
            }
            screens = screens_by_screen_type_sorted_by_uniq_id[ScreenType.RESULTS]
            nav_tabs |= {
                'admin-event-results-screens-tab': {
                    'title': _('Last results ({num})').format(num=len(screens) or '-'),
                    'template': 'screens/view_tab.html',
                    'disabled': not screens,
                    'icon_class': ScreenType.RESULTS.icon_str,
                },
            }
            screens = screens_by_screen_type_sorted_by_uniq_id[ScreenType.RANKING]
            nav_tabs |= {
                'admin-event-ranking-screens-tab': {
                    'title': _('Ranking ({num})').format(num=len(screens) or '-'),
                    'template': 'screens/view_tab.html',
                    'disabled': not screens,
                    'icon_class': ScreenType.RANKING.icon_str,
                },
            }
            screens = screens_by_screen_type_sorted_by_uniq_id[ScreenType.IMAGE]
            nav_tabs |= {
                'admin-event-image-screens-tab': {
                    'title': _('Image ({num})').format(num=len(screens) or '-'),
                    'template': 'screens/view_tab.html',
                    'disabled': not screens,
                    'icon_class': ScreenType.IMAGE.icon_str,
                },
            }
            nav_tabs |= {
                'admin-event-rotators-tab': {
                    'title': _('Rotators ({num})').format(num=len(rotators) or '-'),
                    'template': 'rotators/tab.html',
                    'disabled': not rotators,
                    'icon_class': 'bi-repeat',
                },
            }
            nav_tabs |= {
                'admin-event-display-controllers-tab': {
                    'title': _('Display controllers ({num})').format(
                        num=len(display_controllers) or '-'
                    ),
                    'template': 'display_controllers/tab.html',
                    'disabled': not display_controllers,
                    'icon_class': 'bi-box-arrow-in-right',
                },
            }
        if self.client.can_manage_accounts:
            nav_tabs |= {
                'admin-event-accounts-tab': {
                    'title': _('Staff').format(num=len(event.accounts_by_id) or '-'),
                    'template': 'accounts/tab.html',
                    'icon_class': 'bi-key',
                },
            }

        return super().template_context | {
            'messages': Message.messages(self.request),
            'logging_levels': logging_levels,
            'nav_tabs': nav_tabs,
        }

    def get_tournament_options(
        self, tournaments: list[Tournament] | None = None
    ) -> dict[str, str]:
        if not tournaments:
            tournaments = self.get_admin_event().tournaments_sorted_by_uniq_id
        return {
            self.value_to_form_data(tournament.id): tournament.name
            for tournament in tournaments
        }


class BaseEventAdminController(BaseAdminController):
    @classmethod
    def _admin_base_event_render(
        cls,
        template_context: dict[str, Any],
    ) -> HTMXTemplate:
        if 'modal' in template_context:
            return HTMXTemplate(
                template_name='admin/modals.html',
                context=template_context,
                re_target='#modal-wrapper',
                re_swap='innerHTML',
                trigger_event='modal_opened',
                after='settle',
            )

        assert 'admin_event' in template_context

        nav_bar_items_and_data = plugin_manager.hook.get_event_nav_bar_items_and_data(
            event=template_context['admin_event']
        )
        per_plugin_nav_bar_items = [
            nav_bar_items for (nav_bar_items, data) in nav_bar_items_and_data
        ]
        plugin_nav_bar_data = {
            key: value
            for (nav_bar_items, data) in nav_bar_items_and_data
            for key, value in data.items()
        }

        extra_admin_nav_items: dict[str, list[PluginNavBarItem]] = {}

        for plugin_nav_bar_items in per_plugin_nav_bar_items:
            for nav_bar_item in plugin_nav_bar_items:
                c = extra_admin_nav_items.setdefault(nav_bar_item.at, [])
                c.append(nav_bar_item)

        return HTMXTemplate(
            template_name='admin/event_layout.html',
            context=template_context
            | {
                'extra_admin_nav_items': extra_admin_nav_items,
            }
            | plugin_nav_bar_data,
        )
