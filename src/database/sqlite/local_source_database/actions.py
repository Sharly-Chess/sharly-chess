from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from common.i18n import _
from utils.entity import IdentifiableEntity

if TYPE_CHECKING:
    from database.sqlite.local_source_database import LocalSourceDatabase


class OutdatedAction(IdentifiableEntity, ABC):
    """Abstract class representing the actions to execute
    once a database turns outdated"""

    @abstractmethod
    def on_outdated(self, database: 'LocalSourceDatabase'):
        """Action to execute."""


class NotifOutdatedAction(OutdatedAction):
    @staticmethod
    def static_id() -> str:
        return 'notif'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Notification', locale)

    def on_outdated(self, database: 'LocalSourceDatabase'):
        database.outdated_warning = True


class AutoUpdateOutdatedAction(OutdatedAction):
    @staticmethod
    def static_id() -> str:
        return 'auto_update'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Auto-update', locale)

    def on_outdated(self, database: 'LocalSourceDatabase'):
        if not database.is_updating:
            database.update()
