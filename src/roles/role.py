from enum import IntEnum

from common.i18n import _
from roles.role_scope import RoleScope


class Role(IntEnum):
    """An enum representing the roles clients can have in the application."""

    ADMINISTRATOR = 1
    ORGANIZER = 2
    CHIEF_ARBITER = 3
    DEPUTY_CHIEF_ARBITER = 4
    SECTOR_ARBITER = 5
    PAIRING_OFFICER = 6
    CHECK_IN_OFFICER = 7
    RESULT_OFFICER = 8
    SPECTATOR = 9

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
            case Role.SPECTATOR:
                return _('Spectator')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def scope(self) -> RoleScope:
        """Returns the scope of a role."""
        match self:
            case Role.ADMINISTRATOR | Role.SPECTATOR:
                return RoleScope.APPLICATION
            case Role.ORGANIZER | Role.CHIEF_ARBITER | Role.DEPUTY_CHIEF_ARBITER:
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
                    self.ADMINISTRATOR,
                    self.SPECTATOR,
                ]
            case Role.ORGANIZER:
                return [
                    self.SPECTATOR,
                ]
            case Role.CHIEF_ARBITER:
                return [
                    self.DEPUTY_CHIEF_ARBITER,
                    self.PAIRING_OFFICER,
                    self.SECTOR_ARBITER,
                    self.CHECK_IN_OFFICER,
                    self.RESULT_OFFICER,
                    self.SPECTATOR,
                ]
            case Role.DEPUTY_CHIEF_ARBITER:
                return [
                    self.PAIRING_OFFICER,
                    self.SECTOR_ARBITER,
                    self.CHECK_IN_OFFICER,
                    self.RESULT_OFFICER,
                    self.SPECTATOR,
                ]
            case Role.SECTOR_ARBITER:
                return [
                    self.SPECTATOR,
                ]
            case Role.PAIRING_OFFICER:
                return [
                    self.SPECTATOR,
                ]
            case Role.CHECK_IN_OFFICER:
                return [
                    self.SPECTATOR,
                ]
            case Role.RESULT_OFFICER:
                return [
                    self.SPECTATOR,
                ]
            case Role.SPECTATOR:
                return []
            case _:
                raise ValueError(f'Unknown value: {self}')
