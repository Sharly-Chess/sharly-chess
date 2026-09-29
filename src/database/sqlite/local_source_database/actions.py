from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from common.i18n import _
from common.network import NetworkMonitor
from utils.entity import IdentifiableEntity

if TYPE_CHECKING:
    from database.sqlite.local_source_database import LocalSourceDatabase


class OutdatedAction(IdentifiableEntity, ABC):
    """Abstract class representing the actions to execute
    once a database turns outdated"""

    @abstractmethod
    def on_outdated(self, database: 'LocalSourceDatabase') -> None:
        """Action to execute."""


class NotifOutdatedAction(OutdatedAction):
    @staticmethod
    def static_id() -> str:
        return 'notif'

    @staticmethod
    def static_name() -> str:
        return _('Notification')

    def on_outdated(self, database: 'LocalSourceDatabase') -> None:
        database.outdated_warning = True


class AutoUpdateOutdatedAction(OutdatedAction):
    @staticmethod
    def static_id() -> str:
        return 'auto_update'

    @staticmethod
    def static_name() -> str:
        return _('Auto-update')

    def on_outdated(self, database: 'LocalSourceDatabase') -> None:
        if database.is_updating:
            return
        if not NetworkMonitor.connected():
            # An update would fail and be reported as an error, again at
            # every check, so the database is only signalled as outdated
            # until the connection comes back.
            database.outdated_warning = True
            return
        database.update(notify=False)
