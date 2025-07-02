from enum import IntEnum
from typing import Self

from common.i18n import _
from data.auth.entities import Device, Account
from data.auth.roles import Role


class ExecMode(IntEnum):
    """An enum representing the possible modes for the roles."""

    STAND_ALONE = 10
    STANDARD = 20
    CUSTOM = 30

    @classmethod
    def values(cls) -> tuple[int, ...]:
        return tuple(item.value for item in cls)

    @classmethod
    def exec_modes(cls) -> tuple[Self, ...]:
        return tuple(cls)

    @property
    def name(self) -> str:
        """Returns the name of the mode, used to select the mode on the UI."""
        match self:
            case ExecMode.STAND_ALONE:
                return _('Stand-alone')
            case ExecMode.STANDARD:
                return _('Standard')
            case ExecMode.CUSTOM:
                return _('Custom')
            case _:
                raise ValueError(f'mode={self}')

    @property
    def description(self) -> str:
        """Returns a short description of the mode."""
        match self:
            case ExecMode.STAND_ALONE:
                return _('Use Sharly Chess as a stand-alone application')
            case ExecMode.STANDARD:
                return _('Use connected devices')
            case ExecMode.CUSTOM:
                return _('Use customized permissions')
            case _:
                raise ValueError(f'mode={self}')

    @property
    def help(self) -> str:
        """Returns a string to help users to choose between the different modes."""
        match self:
            case ExecMode.STAND_ALONE:
                return _(
                    'You are the only one to manage your event, on the Sharly Chess server; other devices are not allowed to connect to your server (in particular you will have to share a display to the users to show pairings, results, rankings… or print them!).'
                )
            case ExecMode.STANDARD:
                return _(
                    'Other devices connected to your network can see your public screens. If you have created screens for player check-in and results entry then those features will be enabled.'
                )
            case ExecMode.CUSTOM:
                return _(
                    'You decide which devices and which accounts are allowed to display screens, check-in players, enter results, pair rounds… Sharly Chess offers you a powerful authorization system to easily delegate the management of your event to Organizers, Chief arbiters, Deputy Chief Arbiters, Sector Arbiters, pairings Officers, Check-in Officers, Results Officers, Screen Managers…'
                )
            case _:
                raise ValueError(f'mode={self}')

    @property
    def stand_alone(self) -> bool:
        return self == ExecMode.STAND_ALONE

    @property
    def custom(self) -> bool:
        return self == ExecMode.CUSTOM

    @property
    def predefined_devices(self) -> list[Device]:
        """Returns the list of the deices that correspond to predefined modes (all the roles but CUSTOM)."""
        localhost_device: Device = Device.localhost_device()
        unknown_device: Device = Device.unknown_device()
        match self:
            case ExecMode.STAND_ALONE:
                return [
                    localhost_device,
                    unknown_device,
                ]
            case ExecMode.STANDARD | ExecMode.CUSTOM:
                # we initialize the custom mode as the standard mode
                unknown_device.permissions_by_role |= {
                    Role.CHECK_IN_OFFICER: None,
                    Role.RESULTS_OFFICER: None,
                }
                return [
                    localhost_device,
                    unknown_device,
                ]
            case _:
                raise ValueError(f'mode={self}')

    @property
    def predefined_accounts(self) -> list[Account]:
        """Returns the list of the accounts that correspond to predefined modes (all the roles but CUSTOM)."""
        anonymous_account: Account = Account.anonymous_account()
        match self:
            case ExecMode.STAND_ALONE | ExecMode.STANDARD | ExecMode.CUSTOM:
                # we initialize the custom mode as the standard mode
                return [
                    anonymous_account,
                ]
            case _:
                raise ValueError(f'mode={self}')
