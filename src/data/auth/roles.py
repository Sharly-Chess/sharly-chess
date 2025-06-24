from enum import IntEnum
from typing import Self

from common.i18n import _


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


class Role(IntEnum):
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
            case Role.ADMINISTRATOR:
                return _('Administrator')
            case Role.ORGANIZER:
                return _('Organizer')
            case Role.DISPLAY_MANAGER:
                return _('Display manager')
            case Role.CHIEF_ARBITER:
                return _('Chief Arbiter')
            case Role.DEPUTY_CHIEF_ARBITER:
                return _('Deputy Chief Arbiter')
            case Role.PAIRINGS_OFFICER:
                return _('Pairings Officer')
            case Role.SECTOR_ARBITER:
                return _('Sector arbiter')
            case Role.CHECK_IN_OFFICER:
                return _('Check-in Officer')
            case Role.RESULTS_OFFICER:
                return _('Results Officer')
            case Role.SPECTATOR:
                return _('Spectator')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def scope(self) -> RoleScope:
        """Returns the scope of a role."""
        match self:
            case Role.ADMINISTRATOR:
                return RoleScope.APPLICATION
            case (
                Role.ORGANIZER
                | Role.DISPLAY_MANAGER
                | Role.CHIEF_ARBITER
                | Role.DEPUTY_CHIEF_ARBITER
                | Role.SPECTATOR
            ):
                return RoleScope.EVENT
            case (
                Role.SECTOR_ARBITER
                | Role.PAIRINGS_OFFICER
                | Role.CHECK_IN_OFFICER
                | Role.RESULTS_OFFICER
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
    def sub_roles(self) -> list['Role']:
        """Returns the sub roles automatically given to the roles."""
        match self:
            case Role.ADMINISTRATOR:
                return [
                    Role.ORGANIZER,
                    Role.DISPLAY_MANAGER,
                    Role.CHIEF_ARBITER,
                    Role.DEPUTY_CHIEF_ARBITER,
                    Role.PAIRINGS_OFFICER,
                    Role.SECTOR_ARBITER,
                    Role.CHECK_IN_OFFICER,
                    Role.RESULTS_OFFICER,
                    Role.SPECTATOR,
                ]
            case Role.ORGANIZER:
                return [
                    Role.DISPLAY_MANAGER,
                    Role.SPECTATOR,
                ]
            case Role.DISPLAY_MANAGER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.CHIEF_ARBITER:
                return [
                    Role.DEPUTY_CHIEF_ARBITER,
                    Role.PAIRINGS_OFFICER,
                    Role.SECTOR_ARBITER,
                    Role.CHECK_IN_OFFICER,
                    Role.RESULTS_OFFICER,
                    Role.SPECTATOR,
                ]
            case Role.DEPUTY_CHIEF_ARBITER:
                return [
                    Role.PAIRINGS_OFFICER,
                    Role.SECTOR_ARBITER,
                    Role.CHECK_IN_OFFICER,
                    Role.RESULTS_OFFICER,
                    Role.SPECTATOR,
                ]
            case Role.PAIRINGS_OFFICER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.SECTOR_ARBITER:
                return [
                    Role.CHECK_IN_OFFICER,
                    Role.RESULTS_OFFICER,
                    Role.SPECTATOR,
                ]
            case Role.CHECK_IN_OFFICER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.RESULTS_OFFICER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.SPECTATOR:
                return []
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def tooltip(self) -> str:
        """Returns the tooltip to show when choosing roles."""
        match self:
            case Role.ADMINISTRATOR:
                return _(
                    'This role inherits all the other roles and can do anything on the application; ONLY PEOPLE CONNECTED ON THE SHARLY CHESS SERVER OWN THIS ROLE.'
                )
            case Role.ORGANIZER:
                return _(
                    'This role allows to nominate Chief Arbiters, edit the event; it inherits the Display Manager role.'
                )
            case Role.DISPLAY_MANAGER:
                return _('This role allows to manage the displays.')
            case Role.CHIEF_ARBITER:
                return _(
                    'This role allows to nominate Deputy Chief Arbiters, edit the event, manage tournaments; it inherits the Deputy Chief Arbiter role).'
                )
            case Role.DEPUTY_CHIEF_ARBITER:
                return _(
                    'This role allows to manage players, results (including special results and results modification), check-in, pairing and displays; it inherits the Sector Arbiter, Pairings Officer, Check-in Officer, Results Officer roles for all the tournaments of the event.'
                )
            case Role.PAIRINGS_OFFICER:
                return _(
                    'This role allows to pair the players using a pairing engine or manually, for some or all the tournaments of the event.'
                )
            case Role.SECTOR_ARBITER:
                return _(
                    'This role inherits the Check-in Officer and Results Officer roles for some or all the tournaments of the event.'
                )
            case Role.CHECK_IN_OFFICER:
                return _(
                    'This role allows to check-in players for some or all the tournaments of the event.'
                )
            case Role.RESULTS_OFFICER:
                return _(
                    'This role allows to enter results for some or all the tournaments of the event.'
                )
            case Role.SPECTATOR:
                return _('This role allows to view the public displays of the event.')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def can_manage_method(self) -> str:
        """Returns the tooltip to show when choosing roles."""
        match self:
            case Role.ADMINISTRATOR:
                return _(
                    'This role inherits all the other roles and can do anything on the application; ONLY PEOPLE CONNECTED ON THE SHARLY CHESS SERVER OWN THIS ROLE.'
                )
            case Role.ORGANIZER:
                return _(
                    'This role allows to nominate Chief Arbiters, edit the event; it inherits the Display Manager role.'
                )
            case Role.DISPLAY_MANAGER:
                return _('This role allows to manage the displays.')
            case Role.CHIEF_ARBITER:
                return _(
                    'This role allows to nominate Deputy Chief Arbiters, edit the event, manage tournaments; it inherits the Deputy Chief Arbiter role).'
                )
            case Role.DEPUTY_CHIEF_ARBITER:
                return _(
                    'This role allows to manage players, results (including special results and results modification), check-in, pairing and displays; it inherits the Sector Arbiter, Pairings Officer, Check-in Officer, Results Officer roles for all the tournaments of the event.'
                )
            case Role.PAIRINGS_OFFICER:
                return _(
                    'This role allows to pair the players using a pairing engine or manually, for some or all the tournaments of the event.'
                )
            case Role.SECTOR_ARBITER:
                return _(
                    'This role inherits the Check-in Officer and Results Officer roles for some or all the tournaments of the event.'
                )
            case Role.CHECK_IN_OFFICER:
                return _(
                    'This role allows to check-in players for some or all the tournaments of the event.'
                )
            case Role.RESULTS_OFFICER:
                return _(
                    'This role allows to enter results for some or all the tournaments of the event.'
                )
            case Role.SPECTATOR:
                return _('This role allows to view the public displays of the event.')
            case _:
                raise ValueError(f'Unknown value: {self}')
