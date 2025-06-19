import fnmatch
from typing import TYPE_CHECKING

from litestar_htmx import HTMXRequest

from data.auth.entities import Computer, Account
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
        event: Event | None = None,
    ):
        self.host: str = request.client.host if request.client else ''
        self.account: Account | None
        if event:
            self.account = SessionHandler.get_account(request, event)
        else:
            self.account = None


class AuthManager:
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

    @classmethod
    def _has_tournament_role(
        cls,
        request: HTMXRequest,
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
        client: Client = Client(request, tournament.event)
        for computer in tournament.event.computers_by_id.values():
            if computer.active and computer.matches(client.host):
                for (
                    computer_role,
                    computer_permission,
                ) in computer.permissions_by_role.items():
                    for search_role in search_roles:
                        if (
                            search_role == computer_role
                            or search_role in computer_role.sub_roles
                        ):
                            if cls._tournament_matches_permission(
                                tournament, computer_permission
                            ):
                                return True
        for account in tournament.event.accounts_by_id.values():
            if account.active and account.matches(client.account):
                for (
                    account_role,
                    account_permission,
                ) in account.permissions_by_role.items():
                    for search_role in search_roles:
                        if (
                            search_role == account_role
                            or search_role in account_role.sub_roles
                        ):
                            if cls._tournament_matches_permission(
                                tournament, account_permission
                            ):
                                return True
        return False

    @staticmethod
    def _has_event_role(
        request: HTMXRequest,
        event: Event,
        search_roles: Role | list[Role],
    ) -> bool:
        """Returns True if the client has one of the given *search_roles* for the given event, False otherwise."""
        if isinstance(search_roles, Role):
            search_roles = [
                search_roles,
            ]
        assert all(search_role.scope == RoleScope.EVENT for search_role in search_roles)
        client: Client = Client(request, event)
        for computer in event.computers_by_id.values():
            if computer.active and computer.matches(client.host):
                for (
                    computer_role,
                    computer_permission,
                ) in computer.permissions_by_role.items():
                    for search_role in search_roles:
                        if (
                            search_role == computer_role
                            or search_role in computer_role.sub_roles
                        ):
                            return True
        for account in event.accounts_by_id.values():
            if account.active and account.matches(client.account):
                for (
                    account_role,
                    account_permission,
                ) in account.permissions_by_role.items():
                    for search_role in search_roles:
                        if (
                            search_role == account_role
                            or search_role in account_role.sub_roles
                        ):
                            return True
        return False

    @staticmethod
    def _has_application_role(
        request: HTMXRequest,
        search_roles: Role | list[Role],
    ) -> bool:
        """Returns True if the client has one of the given *search_roles* for the application, False otherwise."""
        if isinstance(search_roles, Role):
            search_roles = [
                search_roles,
            ]
        assert all(role.scope == RoleScope.EVENT for role in search_roles)
        client: Client = Client(request)
        return Computer.host_is_localhost(client.host)

    @classmethod
    def update_application_settings(
        cls,
        request: HTMXRequest,
    ) -> bool:
        return cls._has_application_role(
            request,
            Role.ADMINISTRATOR,
        )

    @classmethod
    def manage_administrators(
        cls,
        request: HTMXRequest,
    ) -> bool:
        return cls._has_application_role(
            request,
            Role.ADMINISTRATOR,
        )

    @classmethod
    def add_event(
        cls,
        request: HTMXRequest,
    ) -> bool:
        return cls._has_application_role(
            request,
            Role.ADMINISTRATOR,
        )

    @classmethod
    def delete_event(
        cls,
        request: HTMXRequest,
        _: Event,
    ) -> bool:
        return cls._has_application_role(
            request,
            Role.ADMINISTRATOR,
        )

    @classmethod
    def rename_event(
        cls,
        request: HTMXRequest,
        _: Event,
    ) -> bool:
        return cls._has_application_role(
            request,
            Role.ADMINISTRATOR,
        )

    @classmethod
    def edit_event(
        cls,
        request: HTMXRequest,
        event: Event,
    ) -> bool:
        return cls._has_event_role(
            request,
            event,
            [
                Role.ORGANIZER,
                Role.CHIEF_ARBITER,
            ],
        )

    @classmethod
    def manage_organizers(
        cls,
        request: HTMXRequest,
        _: Event,
    ) -> bool:
        return cls._has_application_role(
            request,
            Role.ADMINISTRATOR,
        )

    @classmethod
    def manage_chief_arbiters(
        cls,
        request: HTMXRequest,
        event: Event,
    ) -> bool:
        return cls._has_event_role(
            request,
            event,
            Role.ORGANIZER,
        )

    @classmethod
    def manage_deputy_chief_arbiters(
        cls,
        request: HTMXRequest,
        event: Event,
    ) -> bool:
        return cls._has_event_role(
            request,
            event,
            Role.CHIEF_ARBITER,
        )

    @classmethod
    def add_tournament(
        cls,
        request: HTMXRequest,
        event: Event,
    ) -> bool:
        return cls._has_event_role(
            request,
            event,
            Role.CHIEF_ARBITER,
        )

    @classmethod
    def edit_tournament(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.CHIEF_ARBITER,
        )

    @classmethod
    def delete_tournament(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.CHIEF_ARBITER,
        )

    @classmethod
    def open_close_check_in(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @classmethod
    def use_pairing_engine(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.PAIRINGS_OFFICER,
        )

    @classmethod
    def manually_pair_players(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.PAIRINGS_OFFICER,
        )

    @classmethod
    def view_draft_pairings(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.PAIRINGS_OFFICER,
        )

    @classmethod
    def publish_pairings(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @classmethod
    def view_draft_rankings(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @classmethod
    def publish_rankings(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @classmethod
    def manage_displays(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            [
                Role.ORGANIZER,
                Role.DEPUTY_CHIEF_ARBITER,
            ],
        )

    @classmethod
    def add_player(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @classmethod
    def edit_player(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @classmethod
    def delete_player(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @classmethod
    def check_in_player(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.CHECK_IN_OFFICER,
        )

    @classmethod
    def enter_result(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.RESULTS_OFFICER,
        )

    @classmethod
    def change_result(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.RESULTS_OFFICER,
        )

    @classmethod
    def use_special_result(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.DEPUTY_CHIEF_ARBITER,
        )

    @classmethod
    def view_private_displays(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            [
                Role.DISPLAY_MANAGER,
                Role.PAIRINGS_OFFICER,
                Role.CHECK_IN_OFFICER,
                Role.RESULTS_OFFICER,
            ],
        )

    @classmethod
    def view_public_displays(
        cls,
        request: HTMXRequest,
        tournament: Tournament,
    ) -> bool:
        return cls._has_tournament_role(
            request,
            tournament,
            Role.SPECTATOR,
        )
