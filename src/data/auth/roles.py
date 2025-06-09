from enum import IntEnum

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
    PAIRING_OFFICER = 25
    CHECK_IN_OFFICER = 26
    RESULT_OFFICER = 27

    # Other skills
    SPECTATOR = 31

    @classmethod
    def values(cls) -> tuple[int, ...]:
        return tuple(item.value for item in cls)

    @property
    def name(self) -> str:
        """Returns the name of the role."""
        match self:
            case Role.ADMINISTRATOR:
                return _('Administrator')
            case Role.ORGANIZER:
                return _('Organizer')
            case Role.CHIEF_ARBITER:
                return _('Chief Arbiter')
            case Role.DEPUTY_CHIEF_ARBITER:
                return _('Deputy Chief Arbiter')
            case Role.SECTOR_ARBITER:
                return _('Sector arbiter')
            case Role.PAIRING_OFFICER:
                return _('Pairing Officer')
            case Role.CHECK_IN_OFFICER:
                return _('Check-in Officer')
            case Role.RESULT_OFFICER:
                return _('Result Officer')
            case Role.DISPLAY_MANAGER:
                return _('Display manager')
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
                | Role.PAIRING_OFFICER
                | Role.CHECK_IN_OFFICER
                | Role.RESULT_OFFICER
            ):
                return RoleScope.TOURNAMENT
            case _:
                raise ValueError(f'scope={self}')

    @property
    def sub_roles(self) -> list['Role']:
        """Returns the sub roles automatically given to the roles."""
        match self:
            case Role.ADMINISTRATOR:
                return [
                    Role.ADMINISTRATOR,
                    Role.ORGANIZER,
                    Role.CHIEF_ARBITER,
                    Role.DEPUTY_CHIEF_ARBITER,
                    Role.PAIRING_OFFICER,
                    Role.SECTOR_ARBITER,
                    Role.CHECK_IN_OFFICER,
                    Role.RESULT_OFFICER,
                    Role.SPECTATOR,
                ]
            case Role.ORGANIZER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.DISPLAY_MANAGER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.CHIEF_ARBITER:
                return [
                    Role.DEPUTY_CHIEF_ARBITER,
                    Role.PAIRING_OFFICER,
                    Role.SECTOR_ARBITER,
                    Role.CHECK_IN_OFFICER,
                    Role.RESULT_OFFICER,
                    Role.SPECTATOR,
                ]
            case Role.DEPUTY_CHIEF_ARBITER:
                return [
                    Role.PAIRING_OFFICER,
                    Role.SECTOR_ARBITER,
                    Role.CHECK_IN_OFFICER,
                    Role.RESULT_OFFICER,
                    Role.SPECTATOR,
                ]
            case Role.SECTOR_ARBITER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.PAIRING_OFFICER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.CHECK_IN_OFFICER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.RESULT_OFFICER:
                return [
                    Role.SPECTATOR,
                ]
            case Role.SPECTATOR:
                return []
            case _:
                raise ValueError(f'Unknown value: {self}')
