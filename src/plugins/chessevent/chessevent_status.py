from abc import ABC, abstractmethod

from common.i18n import _
from utils.entity import IdentifiableEntity


class ChessEventStatus(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def tooltip(self) -> str | None:
        """Tooltip explaining the status of the tournament."""

    @property
    def sync_disabled_message(self) -> str | None:
        """Message indicating why the sync is disabled. If None, the sync is enabled."""
        return None

    @property
    def settings_disabled_message(self) -> str | None:
        """Message indicating why the settings are disabled. If None, the settings are enabled."""
        return None

    @property
    @abstractmethod
    def css_classes(self) -> str:
        """CSS classes to apply to the status."""


class SuccessChessEventStatus(ChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'SUCCESS'

    @staticmethod
    def static_name() -> str:
        return _('Success')

    @property
    def tooltip(self) -> str | None:
        return None

    @property
    def css_classes(self) -> str:
        return 'text-success'


class NeverSyncedChessEventStatus(ChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'NEVER_SYNCED'

    @staticmethod
    def static_name() -> str:
        return _('Never synchronized')

    @property
    def tooltip(self) -> str | None:
        return None

    @property
    def css_classes(self) -> str:
        return 'text-secondary fst-italic'


class UnsetChessEventStatus(ChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'UNSET'

    @staticmethod
    def static_name() -> str:
        return _('Not configured')

    @property
    def tooltip(self) -> str | None:
        return _('Tournament has not been configured to be used with ChessEvent.')

    @property
    def sync_disabled_message(self) -> str | None:
        return _(
            'You have to update the ChessEvent settings '
            'before being able to use synchronisation.'
        )

    @property
    def css_classes(self) -> str:
        return 'text-secondary fst-italic'


class SettingsErrorChessEventStatus(ChessEventStatus, ABC):
    @staticmethod
    def static_id() -> str:
        return 'SETTINGS_ERROR'

    @staticmethod
    def static_name() -> str:
        return _('Settings error')

    @property
    def sync_disabled_message(self) -> str | None:
        return _(
            'You have to update the ChessEvent settings '
            'before being able to use synchronisation.'
        )

    @property
    def css_classes(self) -> str:
        return 'text-danger'


class EventSettingsErrorChessEventStatus(SettingsErrorChessEventStatus):
    @property
    def tooltip(self) -> str | None:
        return _('ChessEvent event not defined.')


class UserSettingsErrorChessEventStatus(SettingsErrorChessEventStatus):
    @property
    def tooltip(self) -> str | None:
        return _('ChessEvent user not defined.')


class PasswordSettingsErrorChessEventStatus(SettingsErrorChessEventStatus):
    @property
    def tooltip(self) -> str | None:
        return _('ChessEvent password not defined.')


class StartedChessEventStatus(ChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'STARTED'

    @staticmethod
    def static_name() -> str:
        return _('Started')

    @property
    def tooltip(self) -> str | None:
        return None

    @property
    def sync_disabled_message(self) -> str | None:
        return _(
            'ChessEvent actions are no longer available '
            'once the tournament has started.'
        )

    @property
    def settings_disabled_message(self) -> str | None:
        return self.sync_disabled_message

    @property
    def css_classes(self) -> str:
        return 'text-secondary fst-italic'


class RequestErrorChessEventStatus(ChessEventStatus, ABC):
    @property
    def css_classes(self) -> str:
        return 'text-danger'


class ConnectionErrorChessEventStatus(RequestErrorChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'CONNECTION_ERROR'

    @staticmethod
    def static_name() -> str:
        return _('Connection failed')

    @property
    def tooltip(self) -> str | None:
        return _('Connection to the ChessEvent server failed.')


class AuthErrorChessEventStatus(RequestErrorChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'AUTH_ERROR'

    @staticmethod
    def static_name() -> str:
        return _('Authentication failed')

    @property
    def tooltip(self) -> str | None:
        return _('Check the username and the password then try again.')


class UnauthorizedErrorChessEventStatus(RequestErrorChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'UNAUTHORIZED_ERROR'

    @staticmethod
    def static_name() -> str:
        return _('Unauthorized access')

    @property
    def tooltip(self) -> str | None:
        return _(
            'The username / password provided are not '
            'allowed to access this ChessEvent event.'
        )


class EventNotFoundChessEventStatus(RequestErrorChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'EVENT_NOT_FOUND_ERROR'

    @staticmethod
    def static_name() -> str:
        return _('Event not found')

    @property
    def tooltip(self) -> str | None:
        return _('Check the event ID then try again.')


class TournamentNotFoundChessEventStatus(RequestErrorChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'TOURNAMENT_NOT_FOUND_ERROR'

    @staticmethod
    def static_name() -> str:
        return _('Tournament not found')

    @property
    def tooltip(self) -> str | None:
        return _('Check the tournament name then try again.')


class UnexpectedErrorChessEventStatus(RequestErrorChessEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'UNEXPECTED_ERROR'

    @staticmethod
    def static_name() -> str:
        return _('Unexpected error')

    @property
    def tooltip(self) -> str | None:
        return _(
            'An unexpected error occurred, either in Sharly Chess '
            'or in ChessEvent. Consult the logs for more details.'
        )
