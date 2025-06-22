import fnmatch
from contextlib import suppress
from functools import cached_property
from typing import TYPE_CHECKING

from litestar_htmx import HTMXRequest

from data.auth.entities import (
    Computer,
    Account,
    anonymous_account,
    unknown_computer,
    localhost_computer,
)
from data.auth.roles import Role, RoleScope
from data.tournament import Tournament
from web.session import SessionHandler

if TYPE_CHECKING:
    from data.event import Event


class Client:
    """A class that represents a client, built from an HTTP request."""

    def __init__(
        self,
        request: HTMXRequest,
        event: 'Event | None' = None,
    ):
        self.request = request
        self.host: str = (
            self.request.client.host
            if self.request.client and self.request.client.host
            else None
        ) or '?'
        self.event: 'Event | None' = event
        self.computer: Computer = self._find_computer()
        self.active_computer: Computer = (
            self.computer if self.computer.active else unknown_computer
        )
        self.account: Account = self._find_account()
        self.active_account: Account = (
            self.account if self.account.active else anonymous_account
        )

    def _find_computer(
        self,
    ) -> Computer:
        if Computer.host_is_localhost(self.host):
            return localhost_computer
        if self.event is None:
            return unknown_computer
        with suppress(KeyError):
            return self.event.computers_by_ip[self.host]
        return unknown_computer

    def _find_account(
        self,
    ) -> Account:
        if self.event is None:
            return anonymous_account
        return SessionHandler.get_account(self.request, self.event)

    @staticmethod
    def _tournament_matches_permission(
        tournament: Tournament,
        permission: str | None,
    ) -> bool:
        if permission is None:
            return True
        for permission_part in permission.split(','):
            if '*' in permission_part:
                if fnmatch.fnmatch(tournament.uniq_id, permission_part):
                    return True
            elif tournament.uniq_id == permission_part:
                return True
        return False

    def _has_tournament_role(
        self,
        tournament: Tournament,
        search_roles: Role | list[Role],
    ) -> bool:
        """Returns True if the client has ont of the given *search_roles* for the given tournament, False otherwise."""
        if isinstance(search_roles, Role):
            search_roles = [
                search_roles,
            ]
        assert all(
            search_role.scope == RoleScope.TOURNAMENT for search_role in search_roles
        )
        for (
            computer_role,
            computer_permission,
        ) in self.active_computer.permissions_by_role.items():
            for search_role in search_roles:
                if (
                    search_role == computer_role
                    or search_role in computer_role.sub_roles
                ):
                    if self._tournament_matches_permission(
                        tournament, computer_permission
                    ):
                        return True
        for (
            account_role,
            account_permission,
        ) in self.active_account.permissions_by_role.items():
            for search_role in search_roles:
                if search_role == account_role or search_role in account_role.sub_roles:
                    if self._tournament_matches_permission(
                        tournament, account_permission
                    ):
                        return True
        return False

    def _has_event_role(
        self,
        search_roles: Role | list[Role],
    ) -> bool:
        """Returns True if the client has one of the given *search_roles* for the given event, False otherwise."""
        if isinstance(search_roles, Role):
            search_roles = [
                search_roles,
            ]
        assert all(
            search_role.scope
            in [
                RoleScope.EVENT,
                RoleScope.TOURNAMENT,
            ]
            for search_role in search_roles
        )
        for (
            computer_role,
            computer_permission,
        ) in self.active_computer.permissions_by_role.items():
            for search_role in search_roles:
                if (
                    search_role == computer_role
                    or search_role in computer_role.sub_roles
                ):
                    return True
        for (
            account_role,
            account_permission,
        ) in self.active_account.permissions_by_role.items():
            for search_role in search_roles:
                if search_role == account_role or search_role in account_role.sub_roles:
                    return True
        return False

    def _has_application_role(
        self,
        search_roles: Role | list[Role],
    ) -> bool:
        """Returns True if the client has one of the given *search_roles* for the application, False otherwise."""
        if isinstance(search_roles, Role):
            search_roles = [
                search_roles,
            ]
        assert all(role.scope == RoleScope.APPLICATION for role in search_roles)
        return self.active_computer.localhost

    @property
    def permissions_by_role(
        self,
    ) -> dict[Role, str | None]:
        """Returns all the permissions by role, granted or inherited as a computer or an account."""
        computer_permissions_by_role: dict[Role, str | None] = {}
        for (
            computer_role,
            computer_permission,
        ) in self.active_computer.permissions_by_role.items():
            computer_permissions_by_role[computer_role] = computer_permission
            for sub_role in computer_role.sub_roles:
                computer_permissions_by_role[sub_role] = computer_permission
        account_permissions_by_role: dict[Role, str | None] = {}
        for (
            account_role,
            account_permission,
        ) in self.active_account.permissions_by_role.items():
            account_permissions_by_role[account_role] = account_permission
            for sub_role in account_role.sub_roles:
                account_permissions_by_role[sub_role] = account_permission
        permissions_by_role: dict[Role, str | None] = {}
        for role in Role.roles():
            if role in computer_permissions_by_role:
                # computer allowed
                if role in account_permissions_by_role:
                    # account also allowed
                    if (
                        computer_permissions_by_role[role] is None
                        or account_permissions_by_role[role] is None
                    ):
                        # allowed for all the tournaments
                        permissions_by_role[role] = None
                    else:
                        assert computer_permissions_by_role[role] is not None
                        computer_permission_parts: set[str] = set(
                            computer_permissions_by_role[role].split(',')
                        )
                        assert account_permissions_by_role[role] is not None
                        account_permission_parts: set[str] = set(
                            account_permissions_by_role[role].split(',')
                        )
                        permissions_by_role[role] = ','.join(
                            computer_permission_parts | account_permission_parts
                        )
                else:
                    permissions_by_role[role] = computer_permissions_by_role[role]
            else:
                # computer not allowed
                if role in account_permissions_by_role:
                    # account allowed
                    permissions_by_role[role] = account_permissions_by_role[role]
                else:
                    # account not allowed
                    pass
        return permissions_by_role

    @property
    def can_view_application_settings(
        self,
    ) -> bool:
        """Returns true if the client can view the applications settings."""
        return self._has_application_role(Role.ADMINISTRATOR)

    @property
    def can_update_application_settings(
        self,
    ) -> bool:
        """Returns true if the client can update the application settings."""
        return self._has_application_role(Role.ADMINISTRATOR)

    @property
    def can_view_private_events(
        self,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_application_role(Role.ADMINISTRATOR)

    @property
    def can_add_event(
        self,
    ) -> bool:
        """Returns true if the client can add an event."""
        return self._has_application_role(Role.ADMINISTRATOR)

    @property
    def can_view_detailed_event_cards(
        self,
    ) -> bool:
        """Returns true if the client can view the details on the event cards."""
        return self._has_application_role(Role.ADMINISTRATOR)

    @property
    def can_manage_source_databases(
        self,
    ) -> bool:
        """Returns true if the client can manage the local source databases."""
        return self._has_application_role(Role.ADMINISTRATOR)

    @property
    def can_delete_event(
        self,
    ) -> bool:
        """Returns true if the client can delete the event."""
        return self._has_application_role(Role.ADMINISTRATOR)

    @property
    def can_rename_event(
        self,
    ) -> bool:
        """Returns true if the client can rename the event (change the URLs)."""
        return self._has_application_role(Role.ADMINISTRATOR)

    @property
    def can_update_event(
        self,
    ) -> bool:
        """Returns true if the client can update the event."""
        return self._has_event_role(
            [
                Role.ORGANIZER,
                Role.CHIEF_ARBITER,
            ],
        )

    @property
    def can_view_event_complete_config(
        self,
    ) -> bool:
        """Returns true if the client can the event complete config."""
        return self._has_event_role(
            [
                Role.ORGANIZER,
                Role.DEPUTY_CHIEF_ARBITER,
            ],
        )

    @property
    def can_view_event_basic_config(
        self,
    ) -> bool:
        """Returns true if the client can the basic event config."""
        return self._has_event_role(
            [
                Role.ORGANIZER,
                Role.SECTOR_ARBITER,
                Role.PAIRINGS_OFFICER,
                Role.RESULTS_OFFICER,
                Role.CHECK_IN_OFFICER,
            ],
        )

    @cached_property
    def role_management(
        self,
    ) -> dict[Role, bool]:
        """Returns a dict of bool indicating if the client can manage the given role or not."""
        return {
            Role.ADMINISTRATOR: False,
            Role.ORGANIZER: self._has_application_role(
                Role.ADMINISTRATOR,
            ),
            Role.DISPLAY_MANAGER: self._has_event_role(
                Role.ORGANIZER,
            ),
            Role.CHIEF_ARBITER: self._has_event_role(
                Role.ORGANIZER,
            ),
            Role.DEPUTY_CHIEF_ARBITER: self._has_event_role(
                Role.CHIEF_ARBITER,
            ),
            Role.PAIRINGS_OFFICER: self._has_event_role(
                Role.DEPUTY_CHIEF_ARBITER,
            ),
            Role.SECTOR_ARBITER: self._has_event_role(
                Role.DEPUTY_CHIEF_ARBITER,
            ),
            Role.CHECK_IN_OFFICER: self._has_event_role(
                Role.DEPUTY_CHIEF_ARBITER,
            ),
            Role.RESULTS_OFFICER: self._has_event_role(
                Role.DEPUTY_CHIEF_ARBITER,
            ),
            Role.SPECTATOR: self._has_event_role(
                [
                    Role.DISPLAY_MANAGER,
                    Role.DEPUTY_CHIEF_ARBITER,
                ],
            ),
        }

    @property
    def can_manage_accounts(
        self,
    ) -> bool:
        """Returns true if the client can manage (add/update/delete) accounts."""
        return self._has_event_role(
            [
                Role.DISPLAY_MANAGER,
                Role.DEPUTY_CHIEF_ARBITER,
            ]
        )

    def can_manage_account(
        self,
        account: Account,
    ) -> bool:
        """Returns true if the client can manage (update/delete)
        the given account (the client must manage all the roles of the account)."""
        return all(self.role_management[role] for role in account.permissions_by_role)

    @property
    def can_manage_computers(
        self,
    ) -> bool:
        """Returns true if the client can manage (add/update/delete) accounts."""
        return self._has_event_role(
            [
                Role.DISPLAY_MANAGER,
                Role.DEPUTY_CHIEF_ARBITER,
            ]
        )

    def can_manage_computer(
        self,
        computer: Computer,
    ) -> bool:
        """Returns true if the client can manage (update/delete)
        the given account (the client must manage all the roles of the account)."""
        return all(self.role_management[role] for role in computer.permissions_by_role)

    @property
    def can_manage_roles(
        self,
    ) -> bool:
        """Returns true if the client can manage at least one role."""
        return any(self.role_management)

    @property
    def can_view_tournaments(
        self,
    ) -> bool:
        """Returns true if the client can access the Tournaments tab and view the tournament cards."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @property
    def can_add_tournament(
        self,
    ) -> bool:
        """Returns true if the client can add a tournament to the event."""
        return self._has_event_role(
            Role.CHIEF_ARBITER,
        )

    def can_update_tournament(
        self,
    ) -> bool:
        """Returns true if the client can update a tournament of the event."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_delete_tournament(
        self,
    ) -> bool:
        """Returns true if the client can delete a tournament of the event."""
        return self._has_event_role(
            Role.CHIEF_ARBITER,
        )

    @property
    def can_view_players(
        self,
    ) -> bool:
        """Returns true if the client can access the Players tab."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_open_close_check_in(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_use_pairing_engine(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.PAIRINGS_OFFICER,
        )

    def can_manually_pair_players(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.PAIRINGS_OFFICER,
        )

    def can_view_draft_pairings(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.PAIRINGS_OFFICER,
        )

    def can_publish_pairings(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_view_draft_rankings(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_publish_rankings(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_manage_displays(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            [
                Role.ORGANIZER,
                Role.DEPUTY_CHIEF_ARBITER,
            ],
        )

    def can_add_player(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_edit_player(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_delete_player(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_check_in_player(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.CHECK_IN_OFFICER,
        )

    def can_enter_result(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.RESULTS_OFFICER,
        )

    def can_change_result(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.RESULTS_OFFICER,
        )

    def can_use_special_result(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    def can_view_private_displays(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            [
                Role.DISPLAY_MANAGER,
                Role.PAIRINGS_OFFICER,
                Role.CHECK_IN_OFFICER,
                Role.RESULTS_OFFICER,
            ],
        )

    def can_view_public_displays(
        self,
        tournament: Tournament,
    ) -> bool:
        """Returns true if the client can ."""
        return self._has_tournament_role(
            tournament,
            Role.SPECTATOR,
        )

    def __repr__(self) -> str:
        return f'{self.__class__}(account={self.account}, computer={self.computer}, host={self.host})'
