from enum import IntEnum
from typing import Self

from common.i18n import _
from data.auth.roles import Role


class Mode(IntEnum):
    """An enum representing the possible modes for the roles."""

    STAND_ALONE = 0
    VIEW = 10
    VIEW_CHECK_IN = 20
    VIEW_ENTER_RESULTS = 30
    VIEW_CHECK_IN_ENTER_RESULTS = 40
    CUSTOM = 100

    @classmethod
    def values(cls) -> tuple[int, ...]:
        return tuple(item.value for item in cls)

    @classmethod
    def modes(cls) -> tuple[Self, ...]:
        return tuple(cls)

    @property
    def short_text(self) -> str:
        """Returns the name of the mode, used to select the mode on the UI."""
        match self:
            case Mode.STAND_ALONE:
                return _('Use Sharly Chess as a stand-alone application')
            case Mode.VIEW:
                return _('…display screens')
            case Mode.VIEW_CHECK_IN:
                return _('…display screens and check-in players')
            case Mode.VIEW_ENTER_RESULTS:
                return _('…display screens and enter results')
            case Mode.VIEW_CHECK_IN_ENTER_RESULTS:
                return _('…display screens, check-in players and enter results')
            case Mode.CUSTOM:
                return _('Customize the permissions (advanced feature)')
            case _:
                raise ValueError(f'mode={self}')

    @property
    def long_text(self) -> str:
        """Returns the name of the mode, used to select the mode on the UI."""
        match self:
            case Mode.STAND_ALONE:
                return self.short_text
            case Mode.VIEW:
                return _('Use connected devices to display screens')
            case Mode.VIEW_CHECK_IN:
                return _(
                    'Use connected devices to display screens and check-in players'
                )
            case Mode.VIEW_ENTER_RESULTS:
                return _('Use connected devices to display screens and enter results')
            case Mode.VIEW_CHECK_IN_ENTER_RESULTS:
                return _(
                    'Use connected devices to display screens, check-in players and enter results'
                )
            case Mode.CUSTOM:
                return self.short_text
            case _:
                raise ValueError(f'mode={self}')

    @property
    def help(self) -> str:
        """Returns a string to help users to choose between the different modes."""
        match self:
            case Mode.STAND_ALONE:
                return _(
                    'You are the only one to manage your event, on the Sharly Chess server; other devices are not allowed to connect to your computer (in particular you will have to share a display to the users to show pairings, results, rankings... or print them!).'
                )
            case Mode.VIEW:
                return _(
                    'Other devices connected to your network can display screens (pairings, results, rankings...), they are not allowed to do anything else.'
                )
            case Mode.VIEW_CHECK_IN:
                return _(
                    'Other devices connected to your network can display screens and check-in players.'
                )
            case Mode.VIEW_ENTER_RESULTS:
                return _(
                    'Other devices connected to your network can display screens and enter results.'
                )
            case Mode.VIEW_CHECK_IN_ENTER_RESULTS:
                return _(
                    'Other devices connected to your network can display screens, check-in players and enter results.'
                )
            case Mode.CUSTOM:
                return _(
                    'You decide which computers and which accounts are allowed to display screens, check-in players, enter results, pair rounds... Sharly Chess offers you a powerful authorization system to easily delegate the management of your event to Organizers, Chief arbiters, Deputy Chief Arbiters, Sector Arbiters, pairings Officers, Check-in Officers, Results Officers, Screen Managers...'
                )
            case _:
                raise ValueError(f'mode={self}')

    @property
    def stand_alone(self) -> bool:
        return self == Mode.STAND_ALONE

    @property
    def custom(self) -> bool:
        return self == Mode.CUSTOM

    @property
    def unknown_computer_reset_roles(self) -> tuple[bool, list[Role]]:
        """Returns the status and list of the roles to set to localhost when resetting the computer permissions for the mode."""
        match self:
            case Mode.STAND_ALONE:
                return False, []
            case Mode.VIEW:
                return True, [
                    Role.SPECTATOR,
                ]
            case Mode.VIEW_CHECK_IN:
                return True, [
                    Role.CHECK_IN_OFFICER,
                ]
            case Mode.VIEW_ENTER_RESULTS:
                return True, [
                    Role.RESULTS_OFFICER,
                ]
            case Mode.VIEW_CHECK_IN_ENTER_RESULTS:
                return True, [
                    Role.CHECK_IN_OFFICER,
                    Role.RESULTS_OFFICER,
                ]
            case Mode.CUSTOM:
                return True, [
                    Role.SPECTATOR,
                ]
            case _:
                raise ValueError(f'mode={self}')

    @property
    def anonymous_account_reset_roles(self) -> tuple[bool, list[Role]]:
        """Returns the list of the roles to set to anonymous accounts when resetting the account permissions for the mode."""
        return False, []
