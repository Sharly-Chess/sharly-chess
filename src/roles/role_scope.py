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
