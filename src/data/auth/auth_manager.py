from typing import TYPE_CHECKING

from litestar_htmx import HTMXRequest

from data.auth.entities import Computer, User
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
        self.user: User | None
        if event:
            self.user = SessionHandler.get_user(request, event)
        else:
            self.user = None


class AuthManager:
    @staticmethod
    def _has_tournament_role(
        request: HTMXRequest,
        tournament: Tournament,
        roles: Role | list[Role],
    ) -> bool:
        """Returns True if the client has the given roles for the given tournament, False otherwise."""
        if isinstance(roles, Role):
            roles = [
                roles,
            ]
        assert all(role.scope == RoleScope.TOURNAMENT for role in roles)
        client: Client = Client(request, tournament.event)
        for computer in tournament.event.computers_by_id.values():
            if computer.matches(client.host):
                for computer_permission in computer.permissions_by_id.values():
                    for role in roles:
                        if (
                            computer_permission.role == role
                            or role in computer_permission.role.sub_roles
                        ):
                            if computer_permission.tournament_matches(tournament):
                                return True
        for user in tournament.event.users_by_id.values():
            if user.matches(client.user):
                for user_permission in user.permissions_by_id.values():
                    for role in roles:
                        if (
                            user_permission.role == role
                            or role in user_permission.role.sub_roles
                        ):
                            if user_permission.tournament_matches(tournament):
                                return True
        return False

    @staticmethod
    def _has_event_role(
        request: HTMXRequest,
        event: Event,
        roles: Role | list[Role],
    ) -> bool:
        """Returns True if the client has the given role for the given event, False otherwise."""
        if isinstance(roles, Role):
            roles = [
                roles,
            ]
        assert all(role.scope == RoleScope.EVENT for role in roles)
        client: Client = Client(request, event)
        for computer in event.computers_by_id.values():
            if computer.matches(client.host):
                for computer_permission in computer.permissions_by_id.values():
                    for role in roles:
                        if (
                            computer_permission.role == role
                            or role in computer_permission.role.sub_roles
                        ):
                            return True
        for user in event.users_by_id.values():
            if user.matches(client.user):
                for user_permission in user.permissions_by_id.values():
                    for role in roles:
                        if (
                            user_permission.role == role
                            or role in user_permission.role.sub_roles
                        ):
                            return True
        return False

    @staticmethod
    def _has_application_role(
        request: HTMXRequest,
        roles: Role | list[Role],
    ) -> bool:
        """Returns True if the client has the given role for the application, False otherwise."""
        if isinstance(roles, Role):
            roles = [
                roles,
            ]
        assert all(role.scope == RoleScope.EVENT for role in roles)
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
            Role.PAIRING_OFFICER,
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
            Role.PAIRING_OFFICER,
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
            Role.PAIRING_OFFICER,
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
            Role.RESULT_OFFICER,
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
            Role.RESULT_OFFICER,
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
                Role.PAIRING_OFFICER,
                Role.CHECK_IN_OFFICER,
                Role.RESULT_OFFICER,
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
