from abc import ABC, abstractmethod

from common.i18n import _
from data.tournament import Tournament
from utils.date_time import format_date, format_time
from utils.entity import IdentifiableEntity


class CRUploadStatus(IdentifiableEntity, ABC):
    @abstractmethod
    def tooltip_message(self, tournament: Tournament) -> str | None:
        """Tooltip explaining the status of the tournament."""

    @property
    @abstractmethod
    def css_classes(self) -> str:
        """CSS classes to apply to the status."""


class NeverUploadedCRUploadStatus(CRUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'NEVER'

    @staticmethod
    def static_name() -> str:
        return _('Never uploaded')

    @property
    def css_classes(self) -> str:
        return 'bg-secondary'

    def tooltip_message(self, tournament: Tournament) -> str | None:
        return None


class UpToDateCRUploadStatus(CRUploadStatus):
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


class ModifiedCRUploadStatus(CRUploadStatus):
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


class PendingCRUploadStatus(CRUploadStatus):
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


class OngoingCRUploadStatus(CRUploadStatus):
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


class FailureCRUploadStatus(CRUploadStatus, ABC):
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
        from plugins.chess_results.utils import CRUtils

        last_attempt_at = CRUtils.get_tournament_plugin_data(
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


class NetworkFailureCRUploadStatus(FailureCRUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'NETWORK_FAILURE'

    @property
    def details(self) -> str:
        return _('no internet connection')


class UnexpectedFailureCRUploadStatus(FailureCRUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'UNEXPECTED_FAILURE'

    @property
    def details(self) -> str:
        return _('consult the logs')


class FinishedFailureCRUploadStatus(FailureCRUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'FINISHED_FAILURE'

    @property
    def details(self) -> str:
        return _('tournament finished, upload no longer possible')
