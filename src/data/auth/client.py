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

    # ---------------------------------------------------------------------------------
    # Global permissions
    # ---------------------------------------------------------------------------------

    @cached_property
    def _permissions_by_role_dict(
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

    # ---------------------------------------------------------------------------------
    # Application scope
    # ---------------------------------------------------------------------------------

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

    # ---------------------------------------------------------------------------------
    # Event scope
    # ---------------------------------------------------------------------------------

    @cached_property
    def _allowed_for_event_by_role_dict(
        self,
    ) -> dict[Role, bool]:
        """Returns a dict of bool indicating if the client has a role for the event (at least for one tournament)."""
        return {role: role in self._permissions_by_role_dict for role in Role.roles()}

    def _has_event_role(
        self,
        search_roles: Role | list[Role],
    ) -> bool:
        """Returns True if the client has one of the given *search_roles* for the given event, False otherwise."""
        if isinstance(search_roles, Role):
            search_roles = [
                search_roles,
            ]
        return any(self._allowed_for_event_by_role_dict[role] for role in search_roles)

    # ---------------------------------------------------------------------------------
    # Tournament scope
    # ---------------------------------------------------------------------------------

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

    @cached_property
    def _allowed_for_tournament_by_role_dict(
        self,
    ) -> dict[Role, dict[int, bool]]:
        """Returns a dict of dict of bool indicating if the client
        has a role for the tournaments (key is the tournament id).
        usage: __allowed_for_tournament_by_role_dict[role][tournament.id]"""
        return {
            role: {
                tournament.id: self._tournament_matches_permission(
                    tournament, self._permissions_by_role_dict[role]
                )
                if role in self._permissions_by_role_dict
                else False
                for tournament in self.event.tournaments_by_id.values()
            }
            for role in Role.roles()
        }

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
        return any(
            self._allowed_for_tournament_by_role_dict[role][tournament.id]
            for role in search_roles
        )

    def _allowed_for_roles_by_tournament_id(
        self,
        search_roles: Role | list[Role],
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client is allowed for some roles on each tournament.
        Usage:
            @property
            def can_xxx_by_tournament_id(self) -> dict[int, bool]:
                return self._allowed_for_roles_by_tournament_id(search_roles)
        """
        if isinstance(search_roles, Role):
            search_roles = [
                search_roles,
            ]
        assert self.event is not None
        return {
            tournament.id: any(
                self._allowed_for_tournament_by_role_dict[role][tournament.id]
                for role in search_roles
            )
            for tournament in self.event.tournaments_by_id.values()
        }

    # ---------------------------------------------------------------------------------
    # Application
    # ---------------------------------------------------------------------------------

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
    def can_manage_source_databases(
        self,
    ) -> bool:
        """Returns true if the client can manage the local source databases."""
        return self._has_application_role(Role.ADMINISTRATOR)

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

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

    # ---------------------------------------------------------------------------------
    # Accounts and computers
    # ---------------------------------------------------------------------------------

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
        """Returns true if the client can manage (add/update/delete) accounts
        (the client may not be able to manage all the accounts but there may
        be accounts that it can manage)."""
        return self._has_event_role(
            [
                Role.DISPLAY_MANAGER,
                Role.DEPUTY_CHIEF_ARBITER,
            ]
        )

    @property
    def can_manage_account_by_account_id(
        self,
    ) -> dict[int, bool]:
        """Returns true if the client can manage (update/delete)
        the given account (the client must manage all the roles of the account)."""
        return {
            account.id: all(
                self.role_management[role] for role in account.permissions_by_role
            )
            for account in self.event.accounts_by_id.values()
        }

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

    @property
    def can_manage_computer_by_computer_id(
        self,
    ) -> dict[int, bool]:
        """Returns true if the client can manage (update/delete)
        the given computer (the client must manage all the roles of the computer)."""
        return {
            computer.id: all(
                self.role_management[role] for role in computer.permissions_by_role
            )
            for computer in self.event.computers_by_id.values()
        }

    @property
    def can_manage_roles(
        self,
    ) -> bool:
        """Returns true if the client can manage at least one role."""
        return any(self.role_management)

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @property
    def can_view_tournaments_tab(
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

    @property
    def can_update_tournaments(
        self,
    ) -> bool:
        """Returns true if the client can update a tournament of the event."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @property
    def can_delete_tournaments(
        self,
    ) -> bool:
        """Returns true if the client can delete a tournament of the event."""
        return self._has_event_role(
            Role.CHIEF_ARBITER,
        )

    @property
    def can_publish_results(
        self,
    ) -> bool:
        """Returns true if the client can publish the results of tournaments (e.g.: to an external website)."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @property
    def can_publish_rules(
        self,
    ) -> bool:
        """Returns true if the client can publish the rules or tournaments (e.g.: to an external website)."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @property
    def can_download_fees(
        self,
    ) -> bool:
        """Returns true if the client can download the fees of tournaments (e.g.: from an external website)."""
        return self._has_event_role(
            [
                Role.ORGANIZER,
                Role.DEPUTY_CHIEF_ARBITER,
            ]
        )

    # ---------------------------------------------------------------------------------
    # Players
    # ---------------------------------------------------------------------------------

    @property
    def can_view_players_tab(
        self,
    ) -> bool:
        """Returns true if the client can access the Players tab."""
        return self._has_event_role(
            [
                Role.SECTOR_ARBITER,
                Role.PAIRINGS_OFFICER,
            ],
        )

    @property
    def can_add_player(
        self,
    ) -> bool:
        """Returns true if the client can add a player to the event
        (it may be impossible, e.g. the tournament is finished)."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @property
    def can_update_players(
        self,
    ) -> bool:
        """Returns true if the client can update the players
        (including with local or remote databases)."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @property
    def can_update_players_history_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        update the players' history (byes) of the tournaments."""
        return self._allowed_for_roles_by_tournament_id(Role.CHECK_IN_OFFICER)

    @property
    def can_delete_players(
        self,
    ) -> bool:
        """Returns true if the client can delete players of the event
        (it may be impossible, e.g. if they have no game)."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    # ---------------------------------------------------------------------------------
    # Check-in
    # ---------------------------------------------------------------------------------

    @property
    def can_open_close_check_in(
        self,
    ) -> bool:
        """Returns true if the client can open and close the check-in."""
        return self._has_event_role(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @property
    def can_check_in_players_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        update the players' history (byes) of the tournaments."""
        return self._allowed_for_roles_by_tournament_id(Role.CHECK_IN_OFFICER)

    # ---------------------------------------------------------------------------------
    # Pairings
    # ---------------------------------------------------------------------------------

    @property
    def can_view_pairings_tab(
        self,
    ) -> bool:
        """Returns true if the client can access the Pairings tab."""
        return self._has_event_role(
            [
                Role.SECTOR_ARBITER,
                Role.PAIRINGS_OFFICER,
            ],
        )

    @property
    def can_use_pairing_engine_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        use the pairing engine for the tournaments."""
        return self._allowed_for_roles_by_tournament_id(
            Role.PAIRINGS_OFFICER,
        )

    @property
    def can_manually_pair_players_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        use manually pair players of the tournaments."""
        return self._allowed_for_roles_by_tournament_id(
            Role.PAIRINGS_OFFICER,
        )

    @property
    def can_view_draft_pairings_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        view draft pairings of the tournaments (before they are published)."""
        return self._allowed_for_roles_by_tournament_id(
            Role.PAIRINGS_OFFICER,
        )

    @property
    def can_publish_pairings_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        publish pairings of the tournaments."""
        return self._allowed_for_roles_by_tournament_id(
            Role.PAIRINGS_OFFICER,
        )

    # ---------------------------------------------------------------------------------
    # Rankings
    # ---------------------------------------------------------------------------------

    @property
    def can_view_draft_rankings_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        view draft rankings of the tournaments (before they are published)."""
        return self._allowed_for_roles_by_tournament_id(
            Role.PAIRINGS_OFFICER,
        )

    @property
    def can_publish_rankings_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        publish rankings of the tournaments."""
        return self._allowed_for_roles_by_tournament_id(
            Role.PAIRINGS_OFFICER,
        )

    # ---------------------------------------------------------------------------------
    # Results
    # ---------------------------------------------------------------------------------

    @property
    def can_enter_results_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        enter results for the tournaments."""
        return self._allowed_for_roles_by_tournament_id(
            Role.RESULTS_OFFICER,
        )

    @property
    def can_update_results_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        update previously entered results for the tournaments."""
        return self._allowed_for_roles_by_tournament_id(
            Role.SECTOR_ARBITER,
        )

    @property
    def can_set_special_results_by_tournament_id(
        self,
    ) -> dict[int, bool]:
        """Returns a dict indicating if the client can
        set special results (such as 0.0-0.5) for the tournaments."""
        return self._allowed_for_roles_by_tournament_id(
            Role.DEPUTY_CHIEF_ARBITER,
        )

    # ---------------------------------------------------------------------------------
    # Screens
    # ---------------------------------------------------------------------------------

    @property
    def can_manage_screens(
        self,
    ) -> bool:
        """Returns true if the client can manage the screens of the event."""
        return self._has_event_role(
            [
                Role.DISPLAY_MANAGER,
                Role.DEPUTY_CHIEF_ARBITER,
            ],
        )

    @property
    def can_view_private_screens(
        self,
    ) -> bool:
        """Returns true if the client can view private screens."""
        return self._has_event_role(
            [
                Role.DISPLAY_MANAGER,
                Role.PAIRINGS_OFFICER,
                Role.CHECK_IN_OFFICER,
                Role.RESULTS_OFFICER,
            ],
        )

    @property
    def can_view_public_screens(
        self,
    ) -> bool:
        """Returns true if the client can view public screens."""
        return self._has_event_role(
            Role.SPECTATOR,
        )

    def __repr__(self) -> str:
        return f'{self.__class__}(account={self.account}, computer={self.computer}, host={self.host})'
