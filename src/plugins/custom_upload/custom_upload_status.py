from abc import ABC, abstractmethod

from common.i18n import _
from data.tournament import Tournament
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
