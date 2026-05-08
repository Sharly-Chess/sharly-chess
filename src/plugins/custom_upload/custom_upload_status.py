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

    @property
    def css_classes(self) -> str:
        return 'bg-secondary'

    def tooltip_message(self, tournament: Tournament) -> str | None:
        return None


class NotConfiguredCustomUploadStatus(CustomUploadStatus):
    @staticmethod
    def static_id() -> str:
        return 'NOT_CONFIGURED'

    @staticmethod
    def static_name() -> str:
        return _('Not configured')

    @property
    def css_classes(self) -> str:
        return 'message-warning'

    def tooltip_message(self, tournament: Tournament) -> str | None:
        from plugins.custom_upload.utils import CustomUploadUtils

        return CustomUploadUtils.custom_upload_configuration_verification_message(
            tournament
        )
