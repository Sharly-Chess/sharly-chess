from enum import IntEnum

from common.i18n import _
from data.auth.entities import Device, Account
from data.auth.roles import CheckInRole, ResultsEntryRole


class ExecMode(IntEnum):
    """An enum representing the possible modes for the roles."""

    STANDARD = 10
    CUSTOM = 20

    @property
    def name(self) -> str:
        """Returns the name of the mode, used to select the mode on the UI."""
        match self:
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
            case ExecMode.STANDARD:
                return _(
                    'Use connected devices to check-in players and enter results on public screens'
                )
            case ExecMode.CUSTOM:
                return _('Use customized permissions')
            case _:
                raise ValueError(f'mode={self}')

    @property
    def help(self) -> str:
        """Returns a string to help users to choose between the different modes."""
        match self:
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
    def custom(self) -> bool:
        return self == ExecMode.CUSTOM

    @property
    def predefined_devices(self) -> list[Device]:
        """Returns the list of the deices that correspond to predefined modes (all the roles but CUSTOM)."""
        localhost_device: Device = Device.localhost_device()
        unknown_device: Device = Device.unknown_device()
        match self:
            case ExecMode.CUSTOM:
                return [
                    localhost_device,
                    unknown_device,
                ]
            case ExecMode.STANDARD:
                # we initialize the custom mode as the standard mode
                unknown_device.stored_device.roles += [
                    CheckInRole.static_id(),
                    ResultsEntryRole.static_id(),
                ]
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
            case ExecMode.STANDARD | ExecMode.CUSTOM:
                # we initialize the custom mode as the standard mode
                return [
                    anonymous_account,
                ]
            case _:
                raise ValueError(f'mode={self}')
