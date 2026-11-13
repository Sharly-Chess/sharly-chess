import logging
from typing import Any

from litestar.plugins.htmx import HTMXRequest, HTMXTemplate

from common.i18n import _, pgettext
from data.access_levels.actions import AuthAction
from data.access_levels.client_tracker import ClientTracker
from data.event import Event
from plugins.manager import plugin_manager
from data.tournament import Tournament
from plugins.utils import NavDataTransferItem
from utils.enum import (
    FormAction,
    PlayersScreenPlayerFormat,
    PlayersScreenBoardFormat,
    PlayersScreenOpponentFormat,
)
from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
    BaseAdminController,
    nav_count,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard
from web.messages import Message
from web.session import SessionLastDisplayTab, SessionPrintLastTournaments
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

    def check_admin_tab(self) -> None:
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
                    'title': pgettext('with shortcut indication', 'Configuration'),
                    'modal': 'admin-event-modal',
                    'action': FormAction.UPDATE,
                    'icon_class': 'bi-gear',
                    'shortcut': f'{pgettext("keyboard shortcut for the configuration tab", "SC_C")} from:body',
                },
            }
        if self.client.can_view_tournaments_tab:
            tournaments = self.client.allowed_tournaments_for_action(
                AuthAction.VIEW_TOURNAMENTS_TAB
            )
            nav_tabs |= {
                'admin-event-tournaments-tab': {
                    'title': pgettext('with shortcut indication', 'Tournaments'),
                    'count': nav_count(len(tournaments)),
                    'template': 'tournaments/tab.html',
                    'icon_class': 'bi-diagram-3',
                    'shortcut': f'{pgettext("keyboard shortcut for the tournaments tab", "SC_T")} from:body',
                },
            }
        if self.client.can_view_players_tab:
            nav_tabs |= {
                'admin-event-players-tab': {
                    'title': pgettext('with shortcut indication', 'Players'),
                    'count': nav_count(len(self.client.allowed_players_by_id)),
                    'template': 'players/tab.html',
                    'icon_class': 'bi-people',
                    'shortcut': f'{pgettext("keyboard shortcut for the players tab", "SC_P")} from:body',
                },
            }
        if event.is_team_event and self.client.can_view_tournaments_tab:
            nav_tabs |= {
                'admin-event-teams-tab': {
                    'title': _('Teams'),
                    'count': nav_count(len(event.teams_by_id)),
                    'template': 'teams/tab.html',
                    'icon_class': 'bi-flag',
                },
            }
        if self.client.can_view_pairings_tab:
            nav_tabs |= {
                'admin-event-pairings-tab': {
                    'title': pgettext('with shortcut indication', 'Pairings'),
                    'template': 'pairings/tab.html',
                    'icon_class': 'bi-arrow-left-right',
                    'shortcut': f'{pgettext("keyboard shortcut for the pairings tab", "SC_A")} from:body',
                },
            }
        if self.client.can_view_prizes_tab and not event.is_team_event:
            nav_tabs |= {
                'admin-event-prizes-tab': {
                    'title': pgettext('with shortcut indication', 'Prizes'),
                    'template': 'prizes/tab.html',
                    'icon_class': 'bi-trophy',
                    'shortcut': f'{pgettext("keyboard shortcut for the prizes tab", "SC_Z")} from:body',
                },
            }
        if self.client.can_manage_screens:
            display_tabs: dict[str, dict[str, str | bool]] = {
                'admin-event-display-controllers-tab': {
                    'title': pgettext('with shortcut indication', 'Channels'),
                    'name': _('Channels'),
                    'icon_class': 'bi-box-arrow-in-right',
                    'map_key': 'displays',
                    'count': nav_count(len(event.display_controllers_by_id)),
                    'template': 'display_controllers/tab.html',
                    'shortcut': f'{pgettext("keyboard shortcut for the display controllers tab", "SC_N")} from:body',
                },
                'admin-event-screens-tab': {
                    'title': pgettext('with shortcut indication', 'Screens'),
                    'name': _('Screens'),
                    'icon_class': 'bi-window',
                    'map_key': 'screens',
                    'count': nav_count(
                        len(event.basic_screens_by_id) + len(event.families_by_id)
                    ),
                    'template': 'screens/tab.html',
                    'shortcut': f'{pgettext("keyboard shortcut for the single screens tab", "SC_S")} from:body',
                },
                'admin-event-rotators-tab': {
                    'title': pgettext('with shortcut indication', 'Rotators'),
                    'name': _('Rotators'),
                    'icon_class': 'bi-repeat',
                    'map_key': 'rotators',
                    'count': nav_count(len(event.rotators_by_id)),
                    'template': 'rotators/tab.html',
                    'shortcut': f'{pgettext("keyboard shortcut for the rotators tab", "SC_R")} from:body',
                },
                'admin-event-menus-tab': {
                    'title': _('Menus'),
                    'name': _('Menus'),
                    'icon_class': 'bi-list-nested',
                    'map_key': 'menus',
                    'count': nav_count(len(event.menus_by_id)),
                    'template': 'menus/tab.html',
                },
                'admin-event-timers-tab': {
                    'title': _('Timers'),
                    'name': _('Timers'),
                    'icon_class': 'bi-clock',
                    'map_key': 'timers',
                    'count': nav_count(len(event.timers_by_id)),
                    'template': 'timers/tab.html',
                },
            }
            nav_tabs |= {
                'admin-event-views': {
                    'title': _('Display'),
                    'icon_class': 'bi-display',
                    'submenu': display_tabs,
                    'switcher_target': self._last_display_tab(event, display_tabs),
                },
            }
        elif self.client.can_view_public_screens:
            nav_tabs |= {
                'admin-event-display-tab': {
                    'title': _('Display'),
                    'template': 'screens/display_tab.html',
                    'icon_class': 'bi-display',
                },
            }
        if self.client.can_manage_accounts:
            nav_tabs |= {
                'admin-event-accounts-tab': {
                    'title': _('Staff'),
                    'count': (
                        ''
                        if event.predefined_accounts
                        else nav_count(len(event.accounts_by_id))
                    ),
                    'template': 'accounts/tab.html',
                    'icon_class': 'bi-person-lock',
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
                        'icon_class': 'bi-share',
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
            # With only the display page to offer, the page goes without a
            # side menu.
            'display_only': list(nav_tabs) == ['admin-event-display-tab']
            and not self.client.can_generate_documents
            and not self.client.can_manage_source_databases
            and not self.client.can_manage_application_settings,
        }

    def _last_display_tab(self, event: Event, display_tabs: dict[str, Any]) -> str:
        """The display tab the Display entry of the side menu opens: the one
        being shown, else the last one opened, else the screens."""
        last_display_tab = SessionLastDisplayTab(self.request, event)
        route_name = self.request.route_handler.name
        if route_name in display_tabs:
            last_display_tab.set(route_name)
            return route_name
        stored = last_display_tab.get()
        return stored if stored in display_tabs else 'admin-event-screens-tab'

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
    # Litestar declares `guards` on `Controller` as an instance variable, so
    # it cannot be narrowed to a class variable here.
    guards = [EventGuard()]  # noqa: RUF012

    @staticmethod
    def _display_controller_destination_context(event: Event) -> dict[str, Any]:
        """The display controllers the destination field of the modals offers."""
        return {
            'display_controller_destination_options': {
                str(display_controller.id): display_controller.name
                for display_controller in event.sorted_display_controllers
            },
        }

    @staticmethod
    def _read_display_controller_ids(
        data: dict[str, str],
        errors: dict[str, str],
        event: Event,
    ) -> list[int]:
        field = 'display_controller_ids'
        try:
            display_controller_ids = list(
                dict.fromkeys(WebContext.form_data_to_list_int(data, field))
            )
        except ValueError:
            errors[field] = _('Invalid value.')
            return []
        if not set(display_controller_ids) <= set(event.display_controllers_by_id):
            errors[field] = _('Invalid value.')
            return []
        return display_controller_ids

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
