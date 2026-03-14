from abc import ABC

from common.i18n import _
from utils.entity import IdentifiableEntity


class SCEEventStatus(IdentifiableEntity, ABC):
    @staticmethod
    def static_name() -> str:
        return ''

    @property
    def alert_message(self) -> str | None:
        """Message to display as warning on top of the modal."""
        return None

    @property
    def actions_disabled(self) -> bool:
        """Defines if the actions are disabled."""
        return False

    @property
    def retry_button(self) -> bool:
        """Defines if a retry button should be displayed alongside the warning message."""
        return False

    @property
    def oauth_button(self) -> bool:
        """Defines if an oauth button should be displayed alongside the warning message."""
        return False

    @property
    def alert_type(self) -> str:
        """Type of the alert displayed."""
        return 'error'


class PublishedSCEEventStatus(SCEEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'published'


class DraftSCEEventStatus(SCEEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'draft'


class ArchivedSCEEventStatus(SCEEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'archived'

    @property
    def alert_message(self) -> str:
        return _(
            'Event has been archived on Sharly-Chess.com, it no longer can be modified.'
        )

    @property
    def actions_disabled(self) -> bool:
        return True

    @property
    def alert_type(self) -> str:
        return 'warning'


class NoInternetSCEEventStatus(SCEEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'no-internet'

    @property
    def alert_message(self) -> str:
        return _('No internet connection.')

    @property
    def actions_disabled(self) -> bool:
        return True

    @property
    def retry_button(self) -> bool:
        return True


class InvalidRefreshTokenSCEEventStatus(SCEEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'invalid-refresh-token'

    @property
    def alert_message(self) -> str:
        return _('Authorisation failed or expired.')

    @property
    def actions_disabled(self) -> bool:
        return True

    @property
    def oauth_button(self) -> bool:
        return True


class NotFoundSCEEventStatus(SCEEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'not-found'

    @property
    def alert_message(self) -> str:
        return _('Sharly-Chess.com event not found, it most likely has been deleted.')

    @property
    def actions_disabled(self) -> bool:
        return True

    @property
    def retry_button(self) -> bool:
        return True


class NotReachableSCEEventStatus(SCEEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'not-reachable'

    @property
    def alert_message(self) -> str:
        return _('Sharly-Chess.com is not reachable at the moment.')

    @property
    def actions_disabled(self) -> bool:
        return True

    @property
    def retry_button(self) -> bool:
        return True


class UnexpectedHttpSCEEventStatus(SCEEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'unexpected-http'

    @property
    def alert_message(self) -> str:
        return _(
            'An unexpected error occurred while trying to reach '
            'Sharly-Chess.com. Consult the logs for more details.'
        )

    @property
    def actions_disabled(self) -> bool:
        return True

    @property
    def retry_button(self) -> bool:
        return True


class NotConnectedSCEEventStatus(SCEEventStatus):
    @staticmethod
    def static_id() -> str:
        return 'not-connected'

    @property
    def alert_message(self) -> str:
        return _('Event is not connected to a Sharly-Chess.com event.')

    @property
    def actions_disabled(self) -> bool:
        return True

    @property
    def oauth_button(self) -> bool:
        return True
