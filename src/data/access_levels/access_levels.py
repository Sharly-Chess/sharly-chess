from abc import ABC, abstractmethod
from enum import IntEnum
from functools import cache

from common.i18n import _
from data.access_levels.actions import AuthAction
from utils.entity import IdentifiableEntity


class AccessLevelScope(IntEnum):
    """An enum representing the scope of the access levels."""

    APPLICATION = 1
    EVENT = 2
    TOURNAMENT = 3

    @classmethod
    def values(cls) -> tuple[int, ...]:
        return tuple(item.value for item in cls)

    @property
    def name(self) -> str:
        """Returns the name of the scope."""
        match self:
            case AccessLevelScope.APPLICATION:
                return _('Application')
            case AccessLevelScope.EVENT:
                return _('Event')
            case AccessLevelScope.TOURNAMENT:
                return _('Tournament')
            case _:
                raise ValueError(f'access_level_scope={self}')


class AccessLevel(IdentifiableEntity, ABC):
    @staticmethod
    @abstractmethod
    def short_name() -> str:
        """Short name to use in docs."""

    @property
    def card_name(self) -> str:
        """Name to use on the card to avoid overflowing the layout."""
        return self.name

    @property
    @abstractmethod
    def scope(self) -> AccessLevelScope:
        """The scope of effect of the access level."""

    @property
    def has_application_scope(self) -> bool:
        """Returns True if the access level has an application scope."""
        return self.scope == AccessLevelScope.APPLICATION

    @property
    def has_event_scope(self) -> bool:
        """Returns True if the access level has an event scope."""
        return self.scope == AccessLevelScope.EVENT

    @property
    def has_tournament_scope(self) -> bool:
        """Returns True if the access level has a tournament scope."""
        return self.scope == AccessLevelScope.TOURNAMENT

    @staticmethod
    @abstractmethod
    def direct_sub_access_levels() -> set[type['AccessLevel']]:
        """Access levels to inherit the permissions of."""

    @property
    @abstractmethod
    def help_text(self) -> str:
        """Explanation of the access level's actions"""

    @staticmethod
    @abstractmethod
    def access_level_actions() -> list[AuthAction]:
        """Actions specifically allowed to this access level.
        The access level also is allowed to execute all the actions of its sub-access levels."""

    @classmethod
    @cache
    def allowed_actions(cls) -> set[AuthAction]:
        """Set of all the actions allowed to this access level."""
        actions: set[AuthAction] = set(cls.access_level_actions())
        for sub_access_level in cls.sub_access_levels():
            actions |= set(sub_access_level.access_level_actions())
        return actions

    @classmethod
    @cache
    def _sub_access_level_types(cls) -> set[type['AccessLevel']]:
        sub_access_level_types: set[type['AccessLevel']] = (
            cls.direct_sub_access_levels()
        )
        for direct_sub_access_level_type in cls.direct_sub_access_levels():
            sub_access_level_types |= (
                direct_sub_access_level_type._sub_access_level_types()
            )
        return sub_access_level_types

    @classmethod
    @cache
    def sub_access_levels(cls) -> set['AccessLevel']:
        """Set of all the access levels inherited by this access level."""
        return set(type_() for type_ in cls._sub_access_level_types())

    @classmethod
    def can_manage_access_levels(cls) -> bool:
        return AuthAction.MANAGE_ACCOUNTS in cls.allowed_actions()

    @classmethod
    def manageable_access_levels(cls) -> set['AccessLevel']:
        """Set of all the access levels which can be managed by this access level."""
        return cls.sub_access_levels() if cls.can_manage_access_levels() else set()


class SpectatorAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'SPECTATOR'

    @staticmethod
    def static_name() -> str:
        return _('Spectator')

    @staticmethod
    def short_name() -> str:
        return _('SPE')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.EVENT

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return set()

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [AuthAction.VIEW_PUBLIC_SCREENS]

    @property
    def help_text(self) -> str:
        return _('Allows access to Screens marked as public.')


class ResultsEntryAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'RESULTS_ENTRY'

    @staticmethod
    def static_name() -> str:
        return _('Results entry via public screens')

    @staticmethod
    def short_name() -> str:
        return _('RES')

    @property
    def card_name(self) -> str:
        return _('Results entry')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.TOURNAMENT

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return {
            SpectatorAccessLevel,
        }

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [AuthAction.ENTER_RESULTS]

    @property
    def help_text(self) -> str:
        return _(
            'Allows entry of results via any input Screens that have been marked as public.'
        )


class CheckInAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'CHECK_IN'

    @staticmethod
    def static_name() -> str:
        return _('Check-in via public screens')

    @staticmethod
    def short_name() -> str:
        return _('CHE')

    @property
    def card_name(self) -> str:
        return _('Check-in')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.TOURNAMENT

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return {
            SpectatorAccessLevel,
        }

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [
            AuthAction.UPDATE_PLAYERS_HISTORY,
            AuthAction.CHECK_IN_PLAYERS,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'Allows check-in via any input Screens that have been marked as public.'
        )


class SectorArbitrationAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'SECTOR_ARBITRATION'

    @staticmethod
    def static_name() -> str:
        return _('Sector arbitration')

    @staticmethod
    def short_name() -> str:
        return _('SEC')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.TOURNAMENT

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return {
            CheckInAccessLevel,
            ResultsEntryAccessLevel,
        }

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [
            AuthAction.VIEW_EVENT_BASIC_CONFIG,
            AuthAction.VIEW_PLAYERS_TAB,
            AuthAction.VIEW_PAIRINGS_TAB,
            AuthAction.UPDATE_RESULTS,
            AuthAction.SET_ILLEGAL_MOVES,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'Allows access to the Players and Pairings tabs, results and illegal moves update.'
        )


class PairingAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'PAIRING'

    @staticmethod
    def static_name() -> str:
        return _('Pairing')

    @staticmethod
    def short_name() -> str:
        return _('PAI')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.TOURNAMENT

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return {
            SectorArbitrationAccessLevel,
        }

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [
            AuthAction.UPDATE_PLAYERS_HISTORY,
            AuthAction.VIEW_PLAYERS_TAB,
            AuthAction.VIEW_PAIRINGS_TAB,
            AuthAction.USE_PAIRING_ENGINE,
            AuthAction.MANUALLY_PAIR_PLAYERS,
            AuthAction.UNPAIR_ROUND,
            AuthAction.UNPAIR_BOARD,
            AuthAction.PERMUTE_BOARD,
            AuthAction.SET_CURRENT_ROUND,
            AuthAction.SET_ZPB,
            AuthAction.SET_HPB,
            AuthAction.VIEW_DRAFT_PAIRINGS,
            AuthAction.PUBLISH_PAIRINGS,
            AuthAction.VIEW_DRAFT_RANKINGS,
            AuthAction.PUBLISH_RANKINGS,
            AuthAction.OPEN_CLOSE_CHECK_IN,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'Allows pairing of the players, either using a pairing engine or manually.'
        )


class DeputyChiefArbitrationAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'DEPUTY_CHIEF_ARBITRATION'

    @staticmethod
    def static_name() -> str:
        return _('Deputy Chief Arbitration')

    @staticmethod
    def short_name() -> str:
        return _('DCA')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.TOURNAMENT

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return {
            PairingAccessLevel,
        }

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [
            AuthAction.VIEW_EVENT_COMPLETE_CONFIG,
            AuthAction.VIEW_TOURNAMENTS_TAB,
            AuthAction.UPDATE_TOURNAMENTS,
            AuthAction.PUBLISH_RESULTS,
            AuthAction.PUBLISH_RULES,
            AuthAction.DOWNLOAD_FEES,
            AuthAction.ADD_PLAYERS,
            AuthAction.UPDATE_PLAYERS,
            AuthAction.DELETE_PLAYERS,
            AuthAction.SET_FPB,
            AuthAction.SET_SPECIAL_RESULTS,
            AuthAction.MANAGE_SCREENS,
            AuthAction.VIEW_PRIVATE_SCREENS,
            AuthAction.VIEW_PRIZES_TAB,
            AuthAction.MANAGE_PRIZES,
            AuthAction.PRINT,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'Allows managing players, entering results (including special results and their modification), handling check-ins, pairings, and displays.'
        )


class ChiefArbitrationAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'CHIEF_ARBITRATION'

    @staticmethod
    def static_name() -> str:
        return _('Chief Arbitration')

    @staticmethod
    def short_name() -> str:
        return _('CA')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.EVENT

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return {
            DeputyChiefArbitrationAccessLevel,
        }

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [
            AuthAction.UPDATE_EVENTS,
            AuthAction.MANAGE_ACCOUNTS,
            AuthAction.ADD_TOURNAMENTS,
            AuthAction.DELETE_TOURNAMENTS,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'Allows granting or revoking the Deputy Chief Arbitration access level, editing the event, and managing tournaments; Also includes the permissions of the Deputy Chief Arbitration access level.'
        )


class ScreenManagementAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'SCREEN_MANAGEMENT'

    @staticmethod
    def static_name() -> str:
        return _('Screen Management')

    @staticmethod
    def short_name() -> str:
        return _('SCR')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.EVENT

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return {
            SpectatorAccessLevel,
        }

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [
            AuthAction.MANAGE_ACCOUNTS,
            AuthAction.MANAGE_SCREENS,
            AuthAction.VIEW_PRIVATE_SCREENS,
        ]

    @property
    def help_text(self) -> str:
        return _('Allows management of Screens and the accounts that can access them.')


class OrganizationAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'ORGANIZATION'

    @staticmethod
    def static_name() -> str:
        return _('Organization')

    @staticmethod
    def short_name() -> str:
        return _('ORG')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.EVENT

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return {
            ScreenManagementAccessLevel,
        }

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [
            AuthAction.UPDATE_EVENTS,
            AuthAction.VIEW_EVENT_COMPLETE_CONFIG,
            AuthAction.VIEW_EVENT_BASIC_CONFIG,
            AuthAction.DOWNLOAD_FEES,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'Allows granting or revoking the Chief Arbitration access level and editing the event. Also includes the permissions of the Screen Management access level.'
        )

    @classmethod
    def manageable_access_levels(cls) -> set[AccessLevel]:
        return super().manageable_access_levels() | {
            ChiefArbitrationAccessLevel(),
        }


class AdministrationAccessLevel(AccessLevel):
    @staticmethod
    def static_id() -> str:
        return 'ADMINISTRATION'

    @staticmethod
    def static_name() -> str:
        return _('Administration')

    @staticmethod
    def short_name() -> str:
        return _('ADM')

    @property
    def scope(self) -> AccessLevelScope:
        return AccessLevelScope.APPLICATION

    @staticmethod
    def direct_sub_access_levels() -> set[type[AccessLevel]]:
        return {
            OrganizationAccessLevel,
            ChiefArbitrationAccessLevel,
        }

    @staticmethod
    def access_level_actions() -> list[AuthAction]:
        return [
            AuthAction.MANAGE_APPLICATION_SETTINGS,
            AuthAction.MANAGE_SOURCE_DATABASES,
            AuthAction.VIEW_PRIVATE_EVENTS,
            AuthAction.VIEW_PASSED_COMING_EVENTS,
            AuthAction.ADD_EVENTS,
            AuthAction.VIEW_DETAILED_EVENT_CARDS,
            AuthAction.DELETE_EVENTS,
            AuthAction.RENAME_EVENTS,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'Includes all other access levels and grants full access to the application. This access level is granted only when accessing Sharly Chess from the device it is running on (not from another device on the network).'
        )
