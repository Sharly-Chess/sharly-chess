import logging
from typing import Any

from litestar.plugins.htmx import HTMXRequest, HTMXTemplate

from common.i18n import _
from data.access_levels.actions import AuthAction
from data.access_levels.client_tracker import ClientTracker
from data.display_controller import DisplayController
from data.event import Event
from data.pairings.managers import plugin_manager
from data.rotator import Rotator
from data.screen import Screen
from data.tournament import Tournament
from plugins.utils import NavDataTransferItem
from utils.enum import (
    FormAction,
    ScreenType,
    PlayersScreenPlayerFormat,
    PlayersScreenBoardFormat,
    PlayersScreenOpponentFormat,
)
from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
    BaseAdminController,
)
from web.guards import EventGuard
from web.messages import Message
from web.session import SessionPrintLastTournaments
from web.urls import data_transfer_item_url


class BaseEventAdminWebContext(AdminWebContext):
    def __init__(self, request: HTMXRequest, reload_event: bool = False):
        super().__init__(request, reload_event=reload_event)

        # tracks the visit of the client
        ClientTracker().track_client(
            self.client.host,
            self.client.event.uniq_id if self.client.event else None,
            self.client.account.id,
        )

    def get_admin_event(self) -> Event:
        assert self.admin_event is not None
        return self.admin_event

    def check_admin_tab(self):
        pass

    def default_tournament_for_print_modal(
        self, tournament_id: int | None
    ) -> list[int] | None:
        if tournament_id:
            return [tournament_id]
        event = self.get_admin_event()
        tournament_ids: list[int] | None = None
        if last_tournament_ids := (
            SessionPrintLastTournaments(self.request, event).get()
        ):
            # Remove ids that are not in the event anymore
            tournament_ids = [
                tid for tid in last_tournament_ids if tid in event.tournaments_by_id
            ]

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
            tournaments = self.client.allowed_tournaments_for_action(
                AuthAction.VIEW_TOURNAMENTS_TAB
            )
            nav_tabs |= {
                'admin-event-tournaments-tab': {
                    'title': _('Tournaments ({num})').format(
                        num=len(tournaments) or '-'
                    ),
                    'template': 'tournaments/tab.html',
                    'icon_class': 'bi-diagram-3-fill',
                },
            }
        if self.client.can_view_players_tab:
            nav_tabs |= {
                'admin-event-players-tab': {
                    'title': _('Players ({num})').format(
                        num=len(self.client.allowed_players_by_id) or '-'
                    ),
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
            sorted_screens_by_screen_type: dict[ScreenType, list[Screen]]
            rotators: list[Rotator]
            display_controllers: list[DisplayController]
            if self.client.can_view_private_screens:
                sorted_screens_by_screen_type = event.sorted_screens_by_screen_type
                rotators = event.sorted_rotators
                display_controllers = event.sorted_display_controllers
            else:
                sorted_screens_by_screen_type = (
                    event.sorted_public_screens_by_screen_type
                )
                rotators = event.public_sorted_rotators
                display_controllers = event.sorted_public_display_controllers
            screens: list[Screen]
            screens = sorted_screens_by_screen_type[ScreenType.BOARDS]
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
            screens = sorted_screens_by_screen_type[ScreenType.INPUT]
            nav_tabs |= {
                'admin-event-input-screens-tab': {
                    'title': _('Check-in / Results ({num})').format(
                        num=len(screens) or '-'
                    ),
                    'template': 'screens/view_tab.html',
                    'disabled': not screens,
                    'icon_class': ScreenType.INPUT.icon_str,
                },
            }
            screens = sorted_screens_by_screen_type[ScreenType.PLAYERS]
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
            screens = sorted_screens_by_screen_type[ScreenType.RESULTS]
            nav_tabs |= {
                'admin-event-results-screens-tab': {
                    'title': _('Last results ({num})').format(num=len(screens) or '-'),
                    'template': 'screens/view_tab.html',
                    'disabled': not screens,
                    'icon_class': ScreenType.RESULTS.icon_str,
                },
            }
            screens = sorted_screens_by_screen_type[ScreenType.RANKING]
            nav_tabs |= {
                'admin-event-ranking-screens-tab': {
                    'title': _('Ranking ({num})').format(num=len(screens) or '-'),
                    'template': 'screens/view_tab.html',
                    'disabled': not screens,
                    'icon_class': ScreenType.RANKING.icon_str,
                },
            }
            screens = sorted_screens_by_screen_type[ScreenType.IMAGE]
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
                    'title': (
                        _('Staff')
                        if event.predefined_accounts
                        else _('Staff ({num})').format(num=len(event.accounts_by_id))
                    ),
                    'template': 'accounts/tab.html',
                    'icon_class': 'bi-person-fill-lock',
                },
            }
        if self.client.can_publish_results:
            event = self.get_admin_event()
            per_plugin_data_transfer_items = plugin_manager.hook_for_event(
                event, 'get_nav_data_transfer_items'
            )(event=event)
            data_transfer_items: list[NavDataTransferItem] = [
                item for items in per_plugin_data_transfer_items for item in items
            ]
            has_error = any(item.has_upload_error for item in data_transfer_items)

            if data_transfer_items:
                nav_tabs |= {
                    'admin-data-transfer-item': {
                        'title': _('Data transfer'),
                        'icon_class': 'bi-share-fill',
                        'has_error': has_error,
                        'refresh_trigger_event': 'ws:upload-event from:body',
                        'refresh_url': data_transfer_item_url(
                            self.request, self.get_admin_event().uniq_id
                        ),
                        'submenu': {
                            item.key: {
                                'title': item.title,
                                'icon_path': item.icon_path,
                                'modal': item.modal_route_name,
                                'action': 'upload',
                                'has_error': item.has_upload_error,
                            }
                            for item in data_transfer_items
                        },
                    }
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
            tournaments = self.get_admin_event().sorted_tournaments
        return {
            self.value_to_form_data(tournament.id): tournament.name
            for tournament in tournaments
        }

    def get_account_options(self) -> dict[str, str]:
        return {
            self.value_to_form_data(account.id): account.full_name
            for account in self.get_admin_event().sorted_active_user_accounts
            if not account.administrator and not account.anonymous
        }

    @staticmethod
    def get_players_screen_player_format_options() -> dict[str, str]:
        return {
            str(player_format.value): player_format.example
            for player_format in PlayersScreenPlayerFormat
        }

    @staticmethod
    def get_players_screen_board_format_options() -> dict[str, str]:
        return {
            str(player_format.value): player_format.example
            for player_format in PlayersScreenBoardFormat
        }

    @staticmethod
    def get_players_screen_opponent_format_options() -> dict[str, str]:
        return {
            str(player_format.value): player_format.example
            for player_format in PlayersScreenOpponentFormat
        }


class BaseEventAdminController(BaseAdminController):
    guards = [EventGuard()]

    @classmethod
    def _admin_base_event_render(
        cls,
        template_context: dict[str, Any],
    ) -> HTMXTemplate:
        if 'modal' in template_context:
            return cls._render_modal('admin/modals.html', template_context)

        return HTMXTemplate(
            template_name='admin/event_layout.html',
            context=template_context,
        )

    @staticmethod
    def get_default_players_screen_player_format(
        event: Event,
    ) -> PlayersScreenPlayerFormat:
        return (
            plugin_manager.hook_for_event(
                event, 'get_default_players_screen_player_format'
            )()
            or PlayersScreenPlayerFormat.NAME_RATING_TYPE_POINTS
        )

    @staticmethod
    def get_default_players_screen_board_format(
        event: Event,
    ) -> PlayersScreenBoardFormat:
        return (
            plugin_manager.hook_for_event(
                event, 'get_default_players_screen_board_format'
            )()
            or PlayersScreenBoardFormat.FULL
        )

    @staticmethod
    def get_default_players_screen_opponent_format(
        event: Event,
    ) -> PlayersScreenOpponentFormat:
        return (
            plugin_manager.hook_for_event(
                event, 'get_default_players_screen_opponent_format'
            )()
            or PlayersScreenOpponentFormat.NAME_RATING_TYPE_POINTS
        )

    @staticmethod
    def get_default_players_screen_columns(
        event: Event,
    ) -> int | None:
        return plugin_manager.hook_for_event(
            event, 'get_default_players_screen_columns'
        )()
