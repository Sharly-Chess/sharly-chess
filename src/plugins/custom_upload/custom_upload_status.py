from abc import ABC, abstractmethod

from common.i18n import _
from data.tournament import Tournament
from utils.date_time import format_date, format_time
from utils.entity import IdentifiableEntity


class CustomUploadStatus(IdentifiableEntity, ABC):
    @abstractmethod
    def tooltip_message(self, tournament: Tournament) -> str | None:
        """Tooltip explaining the status of the tournament."""

    @property
    @abstractmethod
    def css_classes(self) -> str:
        """CSS classes to apply to the status."""


class NeverUploadedCustomUploadStatus(CustomUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'NEVER'

    @staticmethod
    def static_name() -> str:
        return _('Never uploaded')

    def tooltip_message(self, tournament: Tournament) -> str | None:
        return None

    @property
    def css_classes(self) -> str:
        return 'bg-secondary'


class UpToDateCustomUploadStatus(CustomUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'UP_TO_DATE'

    @staticmethod
    def static_name() -> str:
        return _('Up to date')

    def tooltip_message(self, tournament: Tournament) -> str | None:
        return _('No changes detected since the last upload.')

    @property
    def css_classes(self) -> str:
        return 'message-success'


class ModifiedCustomUploadStatus(CustomUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'MODIFIED'

    @staticmethod
    def static_name() -> str:
        return _('Modified')

    def tooltip_message(self, tournament: Tournament) -> str | None:
        return _('Tournament has been modified since the last upload.')

    @property
    def css_classes(self) -> str:
        return 'message-info'


class PendingCustomUploadStatus(CustomUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'PENDING'

    @staticmethod
    def static_name() -> str:
        return _('Pending')

    def tooltip_message(self, tournament: Tournament) -> str | None:
        return _('Tournament upload has been planned.')

    @property
    def css_classes(self) -> str:
        return 'bg-secondary'


class OngoingCustomUploadStatus(CustomUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'ONGOING'

    @staticmethod
    def static_name() -> str:
        return _('Ongoing')

    def tooltip_message(self, tournament: Tournament) -> str | None:
        return _('Tournament is currently being uploaded.')

    @property
    def css_classes(self) -> str:
        return 'message-info'


class NotConfiguredCustomUploadStatus(CustomUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'NOT_CONFIGURED'

    @staticmethod
    def static_name() -> str:
        return _('Not configured')

    def tooltip_message(self, tournament: Tournament) -> str | None:
        from plugins.custom_upload.utils import CustomUploadUtils

        return CustomUploadUtils.custom_upload_configuration_verification_message(
            tournament
        )

    @property
    def css_classes(self) -> str:
        return 'message-warning'


class FailureCustomUploadStatus(CustomUploadStatus, ABC):
    @staticmethod
    def static_name() -> str:
        return _('Failure')

    @property
    def css_classes(self) -> str:
        return 'message-error'

    @property
    @abstractmethod
    def details(self) -> str:
        """Reason why the upload failed, displayed in the tooltip."""

    def tooltip_message(self, tournament: Tournament) -> str | None:
        from plugins.custom_upload.utils import CustomUploadUtils

        last_attempt_at = CustomUploadUtils.get_tournament_plugin_data(
            tournament
        ).last_upload_attempt_at
        assert last_attempt_at is not None
        return _(
            'Last upload attempt failed on {last_attempt_date} '
            'at {last_attempt_time} (details: {details}).'
        ).format(
            last_attempt_date=format_date(last_attempt_at.date()),
            last_attempt_time=format_time(last_attempt_at),
            details=self.details,
        )


class TargetLocationNotFoundCustomUploadStatus(FailureCustomUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'TARGET_LOCATION_NOT_FOUND'

    @property
    def details(self) -> str:
        return _('target server path not found')


class UnexpectedFailureCustomUploadStatus(FailureCustomUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'UNEXPECTED_FAILURE'

    @property
    def details(self) -> str:
        return _('consult the logs')
