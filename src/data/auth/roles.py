from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Self

from common.i18n import _
from data.auth.permissions import Permission
from utils.entity import IdentifiableEntity


class RoleScope(IntEnum):
    """An enum representing the scope of the roles."""

    APPLICATION = 1
    EVENT = 2
    TOURNAMENT = 3

    @classmethod
    def values(cls) -> tuple[int, ...]:
        return tuple(item.value for item in cls)

    @property
    def name(self) -> str:
        """Returns the name of the scope."""
        match self:
            case RoleScope.APPLICATION:
                return _('Application')
            case RoleScope.EVENT:
                return _('Event')
            case RoleScope.TOURNAMENT:
                return _('Tournament')
            case _:
                raise ValueError(f'role={self}')


class Role(IdentifiableEntity, ABC):
    @abstractmethod
    @property
    def scope(self) -> RoleScope:
        """The scope of effect of the role."""

    @abstractmethod
    @property
    def sub_roles(self) -> list[type['Role']]:
        """Roles to inherit the permissions of."""
        return []

    @abstractmethod
    @property
    def help_text(self) -> str:
        """Explanation of the role's actions"""

    @staticmethod
    @abstractmethod
    def role_permissions() -> list[Permission]:
        """Role-specific permissions. The role also inherits all the permissions of its sub-roles."""

    @property
    def permissions(self) -> list[Permission]:
        permissions: list[Permission] = self.role_permissions()
        for sub_role in self.sub_roles:
            permissions += sub_role.role_permissions()
        return permissions


class SpectatorRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'SPECTATOR'

    @staticmethod
    def static_name() -> str:
        return _('Spectator')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.EVENT

    @property
    def sub_roles(self) -> list[type[Role]]:
        return []

    @staticmethod
    def role_permissions() -> list[Permission]:
        return [Permission.CAN_VIEW_PUBLIC_SCREEN]

    @property
    def help_text(self) -> str:
        return _('This role allows to view the public displays of the event.')


class ResultOfficerRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'RESULT_OFFICER'

    @staticmethod
    def static_name() -> str:
        return _('Result officer')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.TOURNAMENT

    @property
    def sub_roles(self) -> list[type[Role]]:
        return [SpectatorRole]

    @staticmethod
    def role_permissions() -> list[Permission]:
        return [Permission.CAN_ENTER_RESULTS_BY_TOURNAMENT]

    @property
    def help_text(self) -> str:
        return _(
            'This role allows to enter results for some '
            'or all the tournaments of the event.'
        )


class RoleEnum(IntEnum):
    """An enum representing the roles clients can have in the application."""

    # Administration skills
    ADMINISTRATOR = 1

    # Organization skills
    ORGANIZER = 11
    DISPLAY_MANAGER = 12

    # Arbitration skills
    CHIEF_ARBITER = 22
    DEPUTY_CHIEF_ARBITER = 23
    SECTOR_ARBITER = 24
    PAIRINGS_OFFICER = 25
    CHECK_IN_OFFICER = 26
    RESULTS_OFFICER = 27

    # Other skills
    SPECTATOR = 31

    @classmethod
    def values(cls) -> tuple[int, ...]:
        return tuple(item.value for item in cls)

    @classmethod
    def from_value(cls, value: int) -> Self:
        return cls(value)

    @classmethod
    def roles(cls) -> tuple[Self, ...]:
        return tuple(cls)

    @property
    def name(self) -> str:
        """Returns the name of the role."""
        match self:
            case RoleEnum.ADMINISTRATOR:
                return _('Administrator')
            case RoleEnum.ORGANIZER:
                return _('Organizer')
            case RoleEnum.DISPLAY_MANAGER:
                return _('Display manager')
            case RoleEnum.CHIEF_ARBITER:
                return _('Chief Arbiter')
            case RoleEnum.DEPUTY_CHIEF_ARBITER:
                return _('Deputy Chief Arbiter')
            case RoleEnum.PAIRINGS_OFFICER:
                return _('Pairings Officer')
            case RoleEnum.SECTOR_ARBITER:
                return _('Sector arbiter')
            case RoleEnum.CHECK_IN_OFFICER:
                return _('Check-in Officer')
            case RoleEnum.RESULTS_OFFICER:
                return _('Results Officer')
            case RoleEnum.SPECTATOR:
                return _('Spectator')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def scope(self) -> RoleScope:
        """Returns the scope of a role."""
        match self:
            case RoleEnum.ADMINISTRATOR:
                return RoleScope.APPLICATION
            case (
                RoleEnum.ORGANIZER
                | RoleEnum.DISPLAY_MANAGER
                | RoleEnum.CHIEF_ARBITER
                | RoleEnum.DEPUTY_CHIEF_ARBITER
                | RoleEnum.SPECTATOR
            ):
                return RoleScope.EVENT
            case (
                RoleEnum.SECTOR_ARBITER
                | RoleEnum.PAIRINGS_OFFICER
                | RoleEnum.CHECK_IN_OFFICER
                | RoleEnum.RESULTS_OFFICER
            ):
                return RoleScope.TOURNAMENT
            case _:
                raise ValueError(f'scope={self}')

    @property
    def has_application_scope(self) -> bool:
        return self.scope == RoleScope.APPLICATION

    @property
    def has_event_scope(self) -> bool:
        return self.scope == RoleScope.EVENT

    @property
    def has_tournament_scope(self) -> bool:
        return self.scope == RoleScope.TOURNAMENT

    @property
    def sub_roles(self) -> list['RoleEnum']:
        """Returns the sub roles automatically given to the roles."""
        match self:
            case RoleEnum.ADMINISTRATOR:
                return [
                    RoleEnum.ORGANIZER,
                    RoleEnum.DISPLAY_MANAGER,
                    RoleEnum.CHIEF_ARBITER,
                    RoleEnum.DEPUTY_CHIEF_ARBITER,
                    RoleEnum.PAIRINGS_OFFICER,
                    RoleEnum.SECTOR_ARBITER,
                    RoleEnum.CHECK_IN_OFFICER,
                    RoleEnum.RESULTS_OFFICER,
                    RoleEnum.SPECTATOR,
                ]
            case RoleEnum.ORGANIZER:
                return [
                    RoleEnum.DISPLAY_MANAGER,
                    RoleEnum.SPECTATOR,
                ]
            case RoleEnum.DISPLAY_MANAGER:
                return [
                    RoleEnum.SPECTATOR,
                ]
            case RoleEnum.CHIEF_ARBITER:
                return [
                    RoleEnum.DEPUTY_CHIEF_ARBITER,
                    RoleEnum.PAIRINGS_OFFICER,
                    RoleEnum.SECTOR_ARBITER,
                    RoleEnum.CHECK_IN_OFFICER,
                    RoleEnum.RESULTS_OFFICER,
                    RoleEnum.SPECTATOR,
                ]
            case RoleEnum.DEPUTY_CHIEF_ARBITER:
                return [
                    RoleEnum.PAIRINGS_OFFICER,
                    RoleEnum.SECTOR_ARBITER,
                    RoleEnum.CHECK_IN_OFFICER,
                    RoleEnum.RESULTS_OFFICER,
                    RoleEnum.SPECTATOR,
                ]
            case RoleEnum.PAIRINGS_OFFICER:
                return [
                    RoleEnum.SPECTATOR,
                ]
            case RoleEnum.SECTOR_ARBITER:
                return [
                    RoleEnum.CHECK_IN_OFFICER,
                    RoleEnum.RESULTS_OFFICER,
                    RoleEnum.SPECTATOR,
                ]
            case RoleEnum.CHECK_IN_OFFICER:
                return [
                    RoleEnum.SPECTATOR,
                ]
            case RoleEnum.RESULTS_OFFICER:
                return [
                    RoleEnum.SPECTATOR,
                ]
            case RoleEnum.SPECTATOR:
                return []
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def tooltip(self) -> str:
        """Returns the tooltip to show when choosing roles."""
        match self:
            case RoleEnum.ADMINISTRATOR:
                return _(
                    'This role inherits all the other roles and can do anything on the application; ONLY PEOPLE CONNECTED ON THE SHARLY CHESS SERVER OWN THIS ROLE.'
                )
            case RoleEnum.ORGANIZER:
                return _(
                    'This role allows to nominate Chief Arbiters, edit the event; it inherits the Display Manager role.'
                )
            case RoleEnum.DISPLAY_MANAGER:
                return _('This role allows to manage the displays.')
            case RoleEnum.CHIEF_ARBITER:
                return _(
                    'This role allows to nominate Deputy Chief Arbiters, edit the event, manage tournaments; it inherits the Deputy Chief Arbiter role).'
                )
            case RoleEnum.DEPUTY_CHIEF_ARBITER:
                return _(
                    'This role allows to manage players, results (including special results and results modification), check-in, pairing and displays; it inherits the Sector Arbiter, Pairings Officer, Check-in Officer, Results Officer roles for all the tournaments of the event.'
                )
            case RoleEnum.PAIRINGS_OFFICER:
                return _(
                    'This role allows to pair the players using a pairing engine or manually, for some or all the tournaments of the event.'
                )
            case RoleEnum.SECTOR_ARBITER:
                return _(
                    'This role inherits the Check-in Officer and Results Officer roles for some or all the tournaments of the event.'
                )
            case RoleEnum.CHECK_IN_OFFICER:
                return _(
                    'This role allows to check-in players for some or all the tournaments of the event.'
                )
            case RoleEnum.RESULTS_OFFICER:
                return _(
                    'This role allows to enter results for some or all the tournaments of the event.'
                )
            case RoleEnum.SPECTATOR:
                return _('This role allows to view the public displays of the event.')
            case _:
                raise ValueError(f'Unknown value: {self}')
