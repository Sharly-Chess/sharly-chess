from abc import ABC, abstractmethod
from enum import IntEnum
from functools import cache

from common.i18n import _
from data.auth.actions import AuthAction
from utils.entity import IdentifiableEntity


class RoleScope(IntEnum):
    """An enum representing the scope of the roles."""

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
            case RoleScope.APPLICATION:
                return _('Application')
            case RoleScope.EVENT:
                return _('Event')
            case RoleScope.TOURNAMENT:
                return _('Tournament')
            case _:
                raise ValueError(f'role={self}')


class Role(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def scope(self) -> RoleScope:
        """The scope of effect of the role."""

    @staticmethod
    @abstractmethod
    def direct_sub_roles() -> list[type['Role']]:
        """Roles to inherit the permissions of."""
        return []

    @property
    @abstractmethod
    def help_text(self) -> str:
        """Explanation of the role's actions"""

    @staticmethod
    @abstractmethod
    def role_actions() -> list[AuthAction]:
        """Actions specifically allowed to this role.
        The role also is allowed to execute all the actions of its sub-roles."""

    @classmethod
    @cache
    def allowed_actions(cls) -> set[AuthAction]:
        """Set of all the actions allowed to this role."""
        actions: set[AuthAction] = set(cls.role_actions())
        for sub_role in cls.sub_roles():
            actions |= set(sub_role.role_actions())
        return actions

    @classmethod
    def _sub_role_types(cls) -> set[type['Role']]:
        sub_role_types: set[type['Role']] = set(cls.direct_sub_roles())
        for direct_sub_role_type in cls.direct_sub_roles():
            sub_role_types |= direct_sub_role_type._sub_role_types()
        return sub_role_types

    @classmethod
    @cache
    def sub_roles(cls) -> set['Role']:
        """Set of all the roles inherited by this role."""
        return set(type_() for type_ in cls._sub_role_types())

    @classmethod
    def can_manage_roles(cls) -> bool:
        return (
            AuthAction.MANAGE_DEVICES in cls.allowed_actions()
            or AuthAction.MANAGE_ACCOUNTS in cls.allowed_actions()
        )

    @classmethod
    def manageable_roles(cls) -> set['Role']:
        """Set of all the roles which can be managed by this role."""
        return cls.sub_roles() if cls.can_manage_roles() else set()


class SpectatorRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'SPECTATOR'

    @staticmethod
    def static_name() -> str:
        return _('Spectator')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.EVENT

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return []

    @staticmethod
    def role_actions() -> list[AuthAction]:
        return [AuthAction.VIEW_PUBLIC_SCREENS]

    @property
    def help_text(self) -> str:
        return _('This role allows to view the public displays of the event.')


class ResultOfficerRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'RESULT_OFFICER'

    @staticmethod
    def static_name() -> str:
        return _('Result Officer')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.TOURNAMENT

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return [SpectatorRole]

    @staticmethod
    def role_actions() -> list[AuthAction]:
        return [AuthAction.ENTER_RESULTS]

    @property
    def help_text(self) -> str:
        return _(
            'This role allows to enter results for some '
            'or all the tournaments of the event.'
        )


class CheckInOfficerRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'CHECK_IN_OFFICER'

    @staticmethod
    def static_name() -> str:
        return _('Check-in Officer')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.TOURNAMENT

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return [SpectatorRole]

    @staticmethod
    def role_actions() -> list[AuthAction]:
        return [
            AuthAction.UPDATE_PLAYERS_HISTORY,
            AuthAction.CHECK_IN_PLAYERS,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'This role allows to check-in players for some '
            'or all the tournaments of the event.'
        )


class PairingsOfficerRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'PAIRINGS_OFFICER'

    @staticmethod
    def static_name() -> str:
        return _('Pairings Officer')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.TOURNAMENT

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return [CheckInOfficerRole]

    @staticmethod
    def role_actions() -> list[AuthAction]:
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
            'This role allows to pair the players using a pairing engine '
            'or manually, for some or all the tournaments of the event.'
        )


class SectorArbiterRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'SECTOR_ARBITER'

    @staticmethod
    def static_name() -> str:
        return _('Sector arbiter')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.TOURNAMENT

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return [
            DeputyChiefArbiterRole,
            ResultOfficerRole,
        ]

    @staticmethod
    def role_actions() -> list[AuthAction]:
        return [
            AuthAction.VIEW_EVENT_BASIC_CONFIG,
            AuthAction.VIEW_PLAYERS_TAB,
            AuthAction.VIEW_PAIRINGS_TAB,
            AuthAction.UPDATE_RESULTS,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'This role inherits the Check-in Officer and Results Officer '
            'roles for some or all the tournaments of the event.'
        )


class DeputyChiefArbiterRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'DEPUTY_CHIEF_ARBITER'

    @staticmethod
    def static_name() -> str:
        return _('Deputy Chief Arbiter')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.EVENT

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return [
            PairingsOfficerRole,
            SectorArbiterRole,
        ]

    @staticmethod
    def role_actions() -> list[AuthAction]:
        return [
            AuthAction.VIEW_EVENT_COMPLETE_CONFIG,
            AuthAction.MANAGE_ACCOUNTS,
            AuthAction.MANAGE_DEVICES,
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
            'This role allows to manage players, results (including special '
            'results and results modification), check-in, pairing and displays; '
            'it inherits the Sector Arbiter, Pairings Officer, Check-in Officer, '
            'Results Officer roles for all the tournaments of the event.'
        )


class ChiefArbiterRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'CHIEF_ARBITER'

    @staticmethod
    def static_name() -> str:
        return _('Chief Arbiter')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.EVENT

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return [DeputyChiefArbiterRole]

    @staticmethod
    def role_actions() -> list[AuthAction]:
        return [
            AuthAction.UPDATE_EVENTS,
            AuthAction.ADD_TOURNAMENTS,
            AuthAction.DELETE_TOURNAMENTS,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'This role allows to nominate Deputy Chief Arbiters, edit the event, '
            'manage tournaments; it inherits the Deputy Chief Arbiter role.'
        )


class DisplayManagerRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'DISPLAY_MANAGER'

    @staticmethod
    def static_name() -> str:
        return _('Display manager')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.EVENT

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return [SpectatorRole]

    @staticmethod
    def role_actions() -> list[AuthAction]:
        return [
            AuthAction.MANAGE_ACCOUNTS,
            AuthAction.MANAGE_DEVICES,
            AuthAction.MANAGE_SCREENS,
        ]

    @property
    def help_text(self) -> str:
        return _('This role allows to manage the displays.')


class OrganizerRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'ORGANIZER'

    @staticmethod
    def static_name() -> str:
        return _('Organizer')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.EVENT

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return [DisplayManagerRole]

    @staticmethod
    def role_actions() -> list[AuthAction]:
        return [
            AuthAction.UPDATE_EVENTS,
            AuthAction.VIEW_EVENT_COMPLETE_CONFIG,
            AuthAction.VIEW_EVENT_BASIC_CONFIG,
            AuthAction.DOWNLOAD_FEES,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'This role allows to nominate Chief Arbiters, edit the event; '
            'it inherits the Display Manager role.'
        )

    @classmethod
    def manageable_roles(cls) -> set[Role]:
        return cls.sub_roles() | ChiefArbiterRole.sub_roles()


class AdministratorRole(Role):
    @staticmethod
    def static_id() -> str:
        return 'ADMINISTRATOR'

    @staticmethod
    def static_name() -> str:
        return _('Administrator')

    @property
    def scope(self) -> RoleScope:
        return RoleScope.APPLICATION

    @staticmethod
    def direct_sub_roles() -> list[type[Role]]:
        return [OrganizerRole, ChiefArbiterRole]

    @staticmethod
    def role_actions() -> list[AuthAction]:
        return [
            AuthAction.VIEW_APPLICATION_SETTINGS,
            AuthAction.UPDATE_APPLICATION_SETTINGS,
            AuthAction.MANAGE_SOURCE_DATABASES,
            AuthAction.VIEW_PRIVATE_EVENTS,
            AuthAction.ADD_EVENTS,
            AuthAction.VIEW_DETAILED_EVENT_CARDS,
            AuthAction.DELETE_EVENTS,
            AuthAction.RENAME_EVENTS,
        ]

    @property
    def help_text(self) -> str:
        return _(
            'This role inherits all the other roles and can do anything '
            'on the application; ONLY PEOPLE CONNECTED ON THE SHARLY CHESS '
            'SERVER OWN THIS ROLE.'
        )
