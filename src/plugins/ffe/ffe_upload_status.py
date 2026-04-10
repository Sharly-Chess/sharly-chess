from abc import ABC, abstractmethod

from common.i18n import _
from data.tournament import Tournament
from utils.date_time import format_date, format_time
from utils.entity import IdentifiableEntity


class FFEUploadStatus(IdentifiableEntity, ABC):
    @abstractmethod
    def tooltip_message(self, tournament: Tournament) -> str | None:
        """Tooltip explaining the status of the tournament."""

    @property
    @abstractmethod
    def css_classes(self) -> str:
        """CSS classes to apply to the status."""


class NeverUploadedFFEUploadStatus(FFEUploadStatus):
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


class NotConfiguredFFEUploadStatus(FFEUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'NOT_CONFIGURED'

    @staticmethod
    def static_name() -> str:
        return _('Not configured')

    def tooltip_message(self, tournament: Tournament) -> str | None:
        from plugins.ffe.utils import FFEUtils

        return FFEUtils.ffe_actions_unavailable_message(tournament)

    @property
    def css_classes(self) -> str:
        return 'message-warning'


class WarningFFEUploadStatus(FFEUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'WARNING'

    @staticmethod
    def static_name() -> str:
        return _('Warning')

    def tooltip_message(self, tournament: Tournament) -> str | None:
        from plugins.ffe.papi_converter import PapiConverter

        return PapiConverter.papi_export_warning(tournament)

    @property
    def css_classes(self) -> str:
        return 'message-warning'


class IncompatibleFFEUploadStatus(FFEUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'INCOMPATIBLE'

    @staticmethod
    def static_name() -> str:
        return _('Incompatible')

    def tooltip_message(self, tournament: Tournament) -> str | None:
        from plugins.ffe.papi_converter import PapiConverter

        return PapiConverter.papi_export_unavailable_message(tournament)

    @property
    def css_classes(self) -> str:
        return 'message-error'


class UpToDateFFEUploadStatus(FFEUploadStatus):
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


class ModifiedFFEUploadStatus(FFEUploadStatus):
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


class PendingFFEUploadStatus(FFEUploadStatus):
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


class OngoingFFEUploadStatus(FFEUploadStatus):
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


class FailureFFEUploadStatus(FFEUploadStatus, ABC):
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
        from plugins.ffe.utils import FFEUtils

        last_attempt_at = FFEUtils.get_tournament_plugin_data(
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


class NetworkFailureFFEUploadStatus(FailureFFEUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'NETWORK_FAILURE'

    @property
    def details(self) -> str:
        return _('no internet connection')


class UnexpectedFailureFFEUploadStatus(FailureFFEUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'UNEXPECTED_FAILURE'

    @property
    def details(self) -> str:
        return _('consult the logs')


class NotReachableFFEUploadStatus(FailureFFEUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'NOT_REACHABLE'

    @property
    def details(self) -> str:
        return _('FFE website could not be reached')


class AuthFailureFFEUploadStatus(FailureFFEUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'AUTH_FAILURE'

    @property
    def details(self) -> str:
        return _('authentication failed, check the password and certification number')


class FinishedFailureFFEUploadStatus(FailureFFEUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'FINISHED_FAILURE'

    @property
    def details(self) -> str:
        return _('tournament most likely marked as finished on the FFE website')


class PapiConversionFailureFFEUploadStatus(FailureFFEUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'PAPI_CONVERSION_FAILURE'

    @property
    def details(self) -> str:
        return _('tournament could not be converted to the Papi format')
