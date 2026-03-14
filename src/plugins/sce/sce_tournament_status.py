from abc import ABC, abstractmethod

from common.i18n import _
from utils.entity import IdentifiableEntity


class SCETournamentStatus(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def tooltip(self) -> str | None:
        """Tooltip explaining the status of the tournament."""

    @property
    def sync_disabled_message(self) -> str | None:
        """Message indicating why the sync is disabled. If None, the sync is enabled."""
        return None

    @property
    @abstractmethod
    def css_classes(self) -> str:
        """CSS classes to apply to the status."""

    @property
    def notify_error_status(self) -> bool:
        """Defines if the status is notified to the user via
        an error badge on the data transfer button."""
        return False


class NeverUploadedSCETournamentStatus(SCETournamentStatus):
    @staticmethod
    def static_id() -> str:
        return 'NEVER'

    @staticmethod
    def static_name() -> str:
        return _('Never uploaded')

    @property
    def css_classes(self) -> str:
        return 'bg-secondary'

    @property
    def tooltip(self) -> str | None:
        return None


class NotStartedSCETournamentStatus(SCETournamentStatus):
    @staticmethod
    def static_id() -> str:
        return 'NOT_STARTED'

    @staticmethod
    def static_name() -> str:
        return _('Not started')

    @property
    def tooltip(self) -> str | None:
        return _('Tournament has not started yet.')

    @property
    def css_classes(self) -> str:
        return 'bg-secondary'


class SuccessSCETournamentStatus(SCETournamentStatus):
    @staticmethod
    def static_id() -> str:
        return 'SUCCESS'

    @staticmethod
    def static_name() -> str:
        return _('Success')

    @property
    def tooltip(self) -> str | None:
        return _('Last upload ran successfully.')

    @property
    def css_classes(self) -> str:
        return 'message-success'


class ModifiedSCETournamentStatus(SCETournamentStatus):
    @staticmethod
    def static_id() -> str:
        return 'MODIFIED'

    @staticmethod
    def static_name() -> str:
        return _('Modified')

    @property
    def tooltip(self) -> str | None:
        return _('Tournament has been modified since the last upload.')

    @property
    def css_classes(self) -> str:
        return 'message-info'


class PendingSCETournamentStatus(SCETournamentStatus):
    @staticmethod
    def static_id() -> str:
        return 'PENDING'

    @staticmethod
    def static_name() -> str:
        return _('Pending')

    @property
    def tooltip(self) -> str | None:
        return _('Auto-upload of the tournament has been planned.')

    @property
    def css_classes(self) -> str:
        return 'bg-secondary'


class OngoingSCETournamentStatus(SCETournamentStatus):
    @staticmethod
    def static_id() -> str:
        return 'ONGOING'

    @staticmethod
    def static_name() -> str:
        return _('Ongoing')

    @property
    def tooltip(self) -> str | None:
        return _('Tournament is currently being uploaded.')

    @property
    def css_classes(self) -> str:
        return 'message-info'


class FailureSCETournamentStatus(SCETournamentStatus, ABC):
    @staticmethod
    def static_name() -> str:
        return _('Failure')

    @property
    def css_classes(self) -> str:
        return 'message-error'

    @property
    def notify_error_status(self) -> bool:
        return True

    @property
    def reason(self) -> str | None:
        """Reason why the upload failed, displayed in the tooltip."""
        return None

    @property
    def tooltip(self) -> str | None:
        if reason := self.reason:
            tooltip = _('Upload failed (reason: {reason}).').format(reason=reason)
        else:
            tooltip = _('Upload failed unexpectedly.')
        if self.consult_logs_message:
            tooltip += ' ' + _('Consult the logs for more details.')
        return tooltip

    @property
    def consult_logs_message(self) -> bool:
        """Defines if the tooltip contains a message sending to the logs."""
        return False


class NetworkFailureSCETournamentStatus(FailureSCETournamentStatus):
    @staticmethod
    def static_id() -> str:
        return 'NETWORK_FAILURE'

    @property
    def reason(self) -> str | None:
        return _('no internet connection')


class NotFoundFailureSCETournamentStatus(FailureSCETournamentStatus):
    @staticmethod
    def static_id() -> str:
        return 'NOT_FOUND_FAILURE'

    @property
    def reason(self) -> str | None:
        return _('tournament not found, most likely deleted')


class UnexpectedHTTPFailureSCETournamentStatus(FailureSCETournamentStatus):
    @staticmethod
    def static_id() -> str:
        return 'UNEXPECTED_HTTP_FAILURE'

    @property
    def consult_logs_message(self) -> bool:
        return True
