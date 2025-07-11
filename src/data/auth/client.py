from contextlib import suppress
from dataclasses import dataclass
from functools import cached_property, cache
from typing import TYPE_CHECKING, Optional

from litestar_htmx import HTMXRequest

from data.auth.actions import AuthAction
from data.auth.entities import (
    Device,
    Account,
)
from data.auth.managers import RoleManager
from data.auth.roles import Role
from web.session import SessionHandler

if TYPE_CHECKING:
    from data.event import Event


@dataclass
class Permission:
    tournament_ids: set[int] | None = None
    inherited: bool = False


class Client:
    """A class that represents a client, built from an HTTP request."""

    def __init__(
        self,
        request: HTMXRequest,
        event: Optional['Event'] = None,
    ):
        self.request = request
        self.host: str = (
            self.request.client.host
            if self.request.client and self.request.client.host
            else '?'
        )
        self.event: Optional['Event'] = event
        self.device: Device = self._find_device()
        self.active_device: Device = (
            self.device if self.device.active else Device.unknown_device()
        )
        self.account: Account = self._find_account()
        self.active_account: Account = (
            self.account if self.account.active else Account.anonymous_account()
        )

    def _find_device(
        self,
    ) -> Device:
        """Returns a Device object that corresponds to the host of the request."""
        if Device.host_is_localhost(self.host):
            return Device.localhost_device()
        if self.event is None:
            return Device.unknown_device()
        with suppress(KeyError):
            return self.event.devices_by_ip[self.host]
        return self.event.devices_by_id[Device.ANY_DEVICE_ID]

    def _find_account(
        self,
    ) -> Account:
        """Returns an Account object that corresponds to the session."""
        if self.event is None:
            return Account.anonymous_account()
        return SessionHandler.get_account(self.request, self.event)

    def __repr__(self) -> str:
        return f'{self.__class__}(account={self.account}, device={self.device}, host={self.host}, permissions={self.permissions_by_role})'

    # ---------------------------------------------------------------------------------
    # Permissions / actions
    # ---------------------------------------------------------------------------------

    @cached_property
    def permissions_by_role(self) -> dict[Role, Permission]:
        """Returns all the permissions by role, granted or inherited as a device or an account."""
        permissions_by_role: dict[Role, Permission] = {}
        for access_entity in (self.active_account, self.active_device):
            tournament_ids = access_entity.tournament_ids
            for role in access_entity.roles:
                permissions_by_role[role] = self._merge_permissions(
                    Permission(tournament_ids),
                    permissions_by_role.get(role, None),
                )
                for sub_role in role.sub_roles():
                    permissions_by_role[sub_role] = self._merge_permissions(
                        Permission(tournament_ids),
                        permissions_by_role.get(sub_role, None),
                    )
        return {
            role: permissions_by_role[role]
            for role in RoleManager.objects()
            if role in permissions_by_role
        }

    @staticmethod
    def _merge_permissions(
        permission1: Permission, permission2: Permission | None
    ) -> Permission:
        if not permission2:
            return permission1
        tournament_ids: set[int] | None = None
        if (
            permission1.tournament_ids is not None
            and permission2.tournament_ids is not None
        ):
            tournament_ids = permission1.tournament_ids | permission2.tournament_ids
        return Permission(
            tournament_ids=tournament_ids,
            inherited=permission1.inherited or permission2.inherited,
        )

    @staticmethod
    @cache
    def roles_by_action() -> dict[AuthAction, list[Role]]:
        roles_by_action: dict[AuthAction, list[Role]] = {
            action: [] for action in AuthAction
        }
        for role in RoleManager.objects():
            for action in role.allowed_actions():
                roles_by_action[action].append(role)
        return roles_by_action

    @cached_property
    def allowed_actions(self) -> set[AuthAction]:
        actions: set[AuthAction] = set()
        for auth_entity in (self.active_device, self.active_account):
            for role in auth_entity.roles:
                actions |= role.allowed_actions()
        return actions

    def tournament_ids_allowing_action(self, action: AuthAction) -> list[int]:
        """Returns the IDs of the tournaments for which the action is allowed."""
        assert self.event is not None
        return list(
            filter(
                lambda tournament_id: self._action_allowed_for_tournament(
                    action, tournament_id
                ),
                self.event.tournaments_by_id.keys(),
            )
        )

    def _action_allowed_for_tournament(
        self, action: AuthAction, tournament_id: int
    ) -> bool:
        """Returns True if the action is allowed for a tournament, False otherwise."""
        if action not in self.allowed_actions:
            return False
        for role in self.roles_by_action()[action]:
            permission = self.permissions_by_role.get(role, None)
            if permission and (
                permission.tournament_ids is None
                or tournament_id in permission.tournament_ids
            ):
                return True
        return False

    # ---------------------------------------------------------------------------------
    # Application
    # ---------------------------------------------------------------------------------

    @property
    def can_view_application_settings(self) -> bool:
        """Returns true if the client can view the applications settings."""
        return AuthAction.VIEW_APPLICATION_SETTINGS in self.allowed_actions

    @property
    def can_update_application_settings(self) -> bool:
        """Returns true if the client can update the application settings."""
        return AuthAction.UPDATE_APPLICATION_SETTINGS in self.allowed_actions

    @property
    def can_manage_source_databases(self) -> bool:
        """Returns true if the client can manage the source databases."""
        return AuthAction.MANAGE_SOURCE_DATABASES in self.allowed_actions

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @property
    def can_view_private_events(self) -> bool:
        """Returns true if the client can view the private events."""
        return AuthAction.VIEW_PRIVATE_EVENTS in self.allowed_actions

    @property
    def can_add_event(self) -> bool:
        """Returns true if the client can add an event."""
        return AuthAction.ADD_EVENTS in self.allowed_actions

    @property
    def can_view_detailed_event_cards(self) -> bool:
        """Returns true if the client can view the details on the event cards."""
        return AuthAction.VIEW_DETAILED_EVENT_CARDS in self.allowed_actions

    @property
    def can_delete_event(self) -> bool:
        """Returns true if the client can delete the event."""
        return AuthAction.DELETE_EVENTS in self.allowed_actions

    @property
    def can_rename_event(self) -> bool:
        """Returns true if the client can rename the event (change the URLs)."""
        return AuthAction.RENAME_EVENTS in self.allowed_actions

    @property
    def can_update_event(self) -> bool:
        """Returns true if the client can update the event."""
        return AuthAction.UPDATE_EVENTS in self.allowed_actions

    @property
    def can_view_event_complete_config(self) -> bool:
        """Returns true if the client can the event complete config."""
        return AuthAction.VIEW_EVENT_COMPLETE_CONFIG in self.allowed_actions

    @property
    def can_view_event_basic_config(self) -> bool:
        """Returns true if the client can the basic event config."""
        return AuthAction.VIEW_EVENT_BASIC_CONFIG in self.allowed_actions

    # ---------------------------------------------------------------------------------
    # Accounts and devices
    # ---------------------------------------------------------------------------------

    @cached_property
    def manageable_roles(self) -> list[Role]:
        """Returns the roles the client can manage."""
        manageable_roles: set[Role] = set()
        for auth_entity in (self.active_account, self.active_device):
            for role in auth_entity.roles:
                manageable_roles |= role.manageable_roles()
        return sorted(manageable_roles, key=lambda r: r.order)

    @property
    def can_manage_accounts(self) -> bool:
        """Returns true if the client can manage (add/update/delete) accounts
        (the client may not be able to manage all the accounts but there may
        be accounts that it can manage)."""
        return AuthAction.MANAGE_ACCOUNTS in self.allowed_actions

    @property
    def manageable_account_ids(self) -> list[int]:
        """Returns the IDs of the accounts that the client can manage
        (the client must manage all the roles of the accounts)."""
        assert self.event is not None
        return [
            account.id
            for account in self.event.accounts_by_id.values()
            if all(role in self.manageable_roles for role in account.roles)
        ]

    @property
    def can_manage_devices(self) -> bool:
        """Returns true if the client can manage (add/update/delete) accounts."""
        return AuthAction.MANAGE_DEVICES in self.allowed_actions

    @property
    def manageable_device_ids(self) -> list[int]:
        """Returns the IDs of the devices that the client can manage
        (the client must manage all the roles of the devices)."""
        assert self.event is not None
        return [
            device.id
            for device in self.event.devices_by_id.values()
            if all(role in self.manageable_roles for role in device.roles)
        ]

    @property
    def can_manage_roles(self) -> bool:
        """Returns true if the client can manage at least one role."""
        return bool(self.manageable_roles)

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @property
    def can_view_tournaments_tab(self) -> bool:
        """Returns true if the client can access the Tournaments tab and view the tournament cards."""
        return AuthAction.VIEW_TOURNAMENTS_TAB in self.allowed_actions

    @property
    def can_add_tournament(self) -> bool:
        """Returns true if the client can add a tournament to the event."""
        return AuthAction.ADD_TOURNAMENTS in self.allowed_actions

    @property
    def can_update_tournaments(self) -> bool:
        """Returns true if the client can update a tournament of the event."""
        return AuthAction.UPDATE_TOURNAMENTS in self.allowed_actions

    @property
    def can_delete_tournaments(self) -> bool:
        """Returns true if the client can delete a tournament of the event."""
        return AuthAction.DELETE_TOURNAMENTS in self.allowed_actions

    @property
    def can_publish_results(self) -> bool:
        """Returns true if the client can publish the results of tournaments (e.g.: to an external website)."""
        return AuthAction.PUBLISH_RESULTS in self.allowed_actions

    @property
    def can_publish_rules(self) -> bool:
        """Returns true if the client can publish the rules or tournaments (e.g.: to an external website)."""
        return AuthAction.PUBLISH_RULES in self.allowed_actions

    @property
    def can_download_fees(self) -> bool:
        """Returns true if the client can download the fees of tournaments (e.g.: from an external website)."""
        return AuthAction.DOWNLOAD_FEES in self.allowed_actions

    # ---------------------------------------------------------------------------------
    # Players
    # ---------------------------------------------------------------------------------

    @property
    def can_view_players_tab(self) -> bool:
        """Returns true if the client can access the Players tab."""
        return AuthAction.VIEW_PLAYERS_TAB in self.allowed_actions

    @property
    def can_add_player(self) -> bool:
        """Returns true if the client can add a player to the event
        (it may be impossible, e.g. the tournament is finished)."""
        return AuthAction.ADD_PLAYERS in self.allowed_actions

    @property
    def can_update_players(self) -> bool:
        """Returns true if the client can update the players
        (including with local or remote databases)."""
        return AuthAction.UPDATE_PLAYERS in self.allowed_actions

    @property
    def tournament_ids_allowing_update_players_history(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        update the players' history (byes).
        See also tournament_ids_allowing_set_xxx_point_bye()."""
        return self.tournament_ids_allowing_action(AuthAction.UPDATE_PLAYERS_HISTORY)

    @property
    def can_delete_players(self) -> bool:
        """Returns true if the client can delete players of the event
        (it may be impossible, e.g. if they have no game)."""
        return AuthAction.DELETE_PLAYERS in self.allowed_actions

    # ---------------------------------------------------------------------------------
    # Check-in
    # ---------------------------------------------------------------------------------

    @property
    def can_open_close_check_in(self) -> bool:
        """Returns true if the client can open and close the check-in."""
        return AuthAction.OPEN_CLOSE_CHECK_IN in self.allowed_actions

    @property
    def tournament_ids_allowing_check_in_players(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can check-in players."""
        return self.tournament_ids_allowing_action(AuthAction.CHECK_IN_PLAYERS)

    # ---------------------------------------------------------------------------------
    # Pairings
    # ---------------------------------------------------------------------------------

    @property
    def can_view_pairings_tab(self) -> bool:
        """Returns true if the client can access the Pairings tab."""
        return AuthAction.VIEW_PAIRINGS_TAB in self.allowed_actions

    @property
    def tournament_ids_allowing_use_pairing_engine(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        use the pairing engine."""
        return self.tournament_ids_allowing_action(AuthAction.USE_PAIRING_ENGINE)

    @property
    def tournament_ids_allowing_manually_pair_players(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        use manually pair players."""
        return self.tournament_ids_allowing_action(AuthAction.MANUALLY_PAIR_PLAYERS)

    @property
    def tournament_ids_allowing_unpair_round(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        unpair all the boards of a round."""
        return self.tournament_ids_allowing_action(AuthAction.UNPAIR_ROUND)

    @property
    def tournament_ids_allowing_unpair_board(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        (manually) unpair boards."""
        return self.tournament_ids_allowing_action(AuthAction.UNPAIR_BOARD)

    @property
    def tournament_ids_allowing_permute_board(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        permute paired players."""
        return self.tournament_ids_allowing_action(AuthAction.PERMUTE_BOARD)

    @property
    def tournament_ids_allowing_set_current_round(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        set the current round."""
        return self.tournament_ids_allowing_action(AuthAction.SET_CURRENT_ROUND)

    @property
    def tournament_ids_allowing_set_zero_point_bye(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        set HPB to players."""
        return self.tournament_ids_allowing_action(AuthAction.SET_ZPB)

    @property
    def tournament_ids_allowing_set_half_point_bye(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        set HPB to players."""
        return self.tournament_ids_allowing_action(AuthAction.SET_HPB)

    @property
    def tournament_ids_allowing_set_full_point_bye(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        set FPB to players."""
        return self.tournament_ids_allowing_action(AuthAction.SET_FPB)

    @property
    def tournament_ids_allowing_view_draft_pairings(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        view draft pairings (before they are published)."""
        return self.tournament_ids_allowing_action(AuthAction.VIEW_DRAFT_PAIRINGS)

    @property
    def tournament_ids_allowing_publish_pairings(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        publish pairings."""
        return self.tournament_ids_allowing_action(AuthAction.PUBLISH_PAIRINGS)

    # ---------------------------------------------------------------------------------
    # Rankings
    # ---------------------------------------------------------------------------------

    @property
    def tournament_ids_alowing_view_draft_rankings(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        view draft rankings (before they are published)."""
        return self.tournament_ids_allowing_action(AuthAction.VIEW_DRAFT_RANKINGS)

    @property
    def tournament_ids_allowing_publish_rankings(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        publish rankings."""
        return self.tournament_ids_allowing_action(AuthAction.PUBLISH_RANKINGS)

    # ---------------------------------------------------------------------------------
    # Results
    # ---------------------------------------------------------------------------------

    @property
    def tournament_ids_allowing_enter_results(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        enter results."""
        return self.tournament_ids_allowing_action(AuthAction.ENTER_RESULTS)

    @property
    def tournament_ids_allowing_update_results(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        update previously entered results."""
        return self.tournament_ids_allowing_action(AuthAction.UPDATE_RESULTS)

    @property
    def tournament_ids_allowing_set_special_results(self) -> list[int]:
        """Returns the IDs of the tournaments of which the client can
        set special results (such as O.0-F, 0.0-0.5)."""
        return self.tournament_ids_allowing_action(AuthAction.SET_SPECIAL_RESULTS)

    # ---------------------------------------------------------------------------------
    # Screens
    # ---------------------------------------------------------------------------------

    @property
    def can_manage_screens(self) -> bool:
        """Returns true if the client can manage the screens of the event."""
        return AuthAction.MANAGE_SCREENS in self.allowed_actions

    @property
    def can_view_private_screens(self) -> bool:
        """Returns true if the client can view private screens."""
        return AuthAction.VIEW_PRIVATE_SCREENS in self.allowed_actions

    @property
    def can_view_public_screens(self) -> bool:
        """Returns true if the client can view public screens."""
        return AuthAction.VIEW_PUBLIC_SCREENS in self.allowed_actions

    # ---------------------------------------------------------------------------------
    # Prizes
    # ---------------------------------------------------------------------------------

    @property
    def can_view_prizes_tab(self) -> bool:
        """Returns true if the client can access the Prizes tab."""
        return AuthAction.VIEW_PRIZES_TAB in self.allowed_actions

    @property
    def can_manage_prizes(self) -> bool:
        """Returns a dict indicating if the client can
        manage the prizes."""
        return AuthAction.MANAGE_PRIZES in self.allowed_actions

    # ---------------------------------------------------------------------------------
    # Print
    # ---------------------------------------------------------------------------------

    # TODO Printing privileges should be granted to other roles
    #  on a per-tournament basis but this needs an important
    #  work on the print modal.
    @property
    def can_print(self) -> bool:
        """Returns true if the client can access the Prizes tab."""
        return AuthAction.PRINT in self.allowed_actions
