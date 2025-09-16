from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from common.i18n import _
from data.access_levels.manager import AccessLevelManager
from data.player import Player
from database.sqlite.event.event_store import StoredAccount
from data.access_levels.access_levels import (
    AccessLevel,
    AdministrationAccessLevel,
    CheckInAccessLevel,
    ResultsEntryAccessLevel,
)

if TYPE_CHECKING:
    from data.event import Event


@dataclass
class Permission:
    tournament_ids: set[int] | None = None
    inherited: bool = False

    def tournaments_tooltip_message(self, event: 'Event') -> str:
        if not self.tournament_ids:
            return ''
        tournament_names = sorted(
            event.tournaments_by_id[tournament_id].name
            for tournament_id in self.tournament_ids
        )
        return ''.join(
            f'<div class="text-center text-nowrap">{name}</div>'
            for name in tournament_names
        )


class Account:
    """A data wrapper around a stored account.
    The class that represents an account."""

    ADMINISTRATOR_ID: int = 1
    ANONYMOUS_ID: int = 2

    def __init__(self, stored_account: StoredAccount):
        self.stored_account = stored_account

    @property
    def id(self) -> int:
        assert self.stored_account.id is not None
        return self.stored_account.id

    @property
    def administrator(self) -> bool:
        """Returns True for the administrator account, False otherwise."""
        return self.id == self.ADMINISTRATOR_ID

    @property
    def anonymous(self) -> bool:
        """Returns True for the anonymous account, False otherwise."""
        return self.id == self.ANONYMOUS_ID

    @property
    def user_account(self) -> bool:
        """Returns True if a 'real' user account (not administrator or anonymous), False otherwise."""
        return self.id not in (
            self.ADMINISTRATOR_ID,
            self.ANONYMOUS_ID,
        )

    @property
    def first_name(self) -> str | None:
        """Returns the first name of the account."""
        if self.administrator:
            return None
        if self.anonymous:
            return None
        return self.stored_account.first_name

    @property
    def last_name(self) -> str:
        """Returns the last name of the account."""
        if self.administrator:
            return _('Administrator')
        if self.anonymous:
            return _('Anonymous')
        assert self.stored_account.last_name is not None
        return self.stored_account.last_name

    @property
    def full_name(self) -> str:
        return Player.player_full_name(self.first_name, self.last_name)

    @property
    def password_hash(self) -> str | None:
        """Returns the password hash of the account."""
        return self.stored_account.password_hash

    def update_password(self, new_hash: str):
        self.stored_account.password_hash = new_hash

    @property
    def active(self) -> bool:
        return self.stored_account.active

    @property
    def access_levels(self) -> list[AccessLevel]:
        return [
            AccessLevelManager.get_object(access_level_id)
            for access_level_id in self.stored_account.access_levels
        ]

    @property
    def tournament_ids(self) -> set[int] | None:
        if self.stored_account.tournament_ids is None:
            return None
        return set(self.stored_account.tournament_ids)

    @property
    def edit_properties(self) -> bool:
        """Returns False if the account is locked (can not be updated or deleted)."""
        return not self.administrator and not self.anonymous

    @property
    def edit_permissions(self) -> bool:
        """Returns True if the permissions of the account can be updated."""
        return not self.administrator

    @cached_property
    def permissions_by_access_level(
        self,
    ) -> dict[AccessLevel, Permission]:
        """Returns all the permissions by access level, granted or inherited for an account."""
        permissions_by_access_level: dict[AccessLevel, Permission] = {}
        tournament_ids = self.tournament_ids
        for access_level in self.access_levels:
            permissions_by_access_level[access_level] = self.merge(
                Permission(tournament_ids),
                permissions_by_access_level.get(access_level, None),
            )
            for sub_access_level in access_level.sub_access_levels():
                permissions_by_access_level[sub_access_level] = self.merge(
                    Permission(tournament_ids),
                    permissions_by_access_level.get(sub_access_level, None),
                )
        return {
            access_level: permissions_by_access_level[access_level]
            for access_level in AccessLevelManager.objects()
            if access_level in permissions_by_access_level
        }

    @staticmethod
    def merge(permission1: Permission, permission2: Permission | None) -> Permission:
        if not permission2:
            return permission1
        tournament_ids: set[int] | None = None
        if (
            permission1.tournament_ids is not None
            and permission2.tournament_ids is not None
        ):
            tournament_ids = permission1.tournament_ids | permission2.tournament_ids
        return Permission(
            tournament_ids=tournament_ids,
            inherited=permission1.inherited or permission2.inherited,
        )

    def __repr__(self) -> str:
        return f'Account(id={self.id}, administrator={self.administrator}, anonymous={self.anonymous}, first_name={self.first_name}, last_name={self.last_name})'

    # Accounts are stored at event-level, the methods below provide event-free
    # instances that can be used when no events are available (welcome page, ...)

    @classmethod
    def predefined_administrator_account(cls) -> 'Account':
        return cls(
            StoredAccount(
                id=cls.ADMINISTRATOR_ID,
                active=True,
                access_levels=[
                    AdministrationAccessLevel.static_id(),
                ],
                tournament_ids=None,
                first_name=None,
                last_name=None,
                password_hash=None,
            )
        )

    @classmethod
    def predefined_anonymous_account(cls) -> 'Account':
        return cls(
            StoredAccount(
                id=cls.ANONYMOUS_ID,
                active=True,
                access_levels=[
                    CheckInAccessLevel.static_id(),
                    ResultsEntryAccessLevel.static_id(),
                ],
                tournament_ids=None,
                first_name=None,
                last_name=None,
                password_hash=None,
            )
        )
