from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from common.exception import PapiWebException


class SafetyMode(StrEnum):
    SAFE = 'SAFE'
    UNSAFE = 'UNSAFE'
    FIDE_INCOMPATIBLE = 'FIDE_INCOMPATIBLE'

    @property
    def danger_level(self) -> int:
        cls = self.__class__
        match self:
            case cls.SAFE:
                return 1
            case cls.UNSAFE:
                return 2
            case cls.FIDE_INCOMPATIBLE:
                return 3
            case _:
                raise ValueError(f'Unknown value: {self}')


class RoundStatus(StrEnum):
    PAST = 'PAST'
    PREVIOUS = 'PREVIOUS'
    CURRENT = 'CURRENT'
    NEXT = 'NEXT'
    FUTURE = 'FUTURE'

    @classmethod
    def from_round(cls, round_: int, current_round: int):
        if round_ == current_round:
            return cls.CURRENT
        if round_ == current_round - 1:
            return cls.PREVIOUS
        if round_ == current_round + 1:
            return cls.NEXT
        if round_ < current_round - 1:
            return cls.PAST
        return cls.FUTURE


class Action(StrEnum):
    FULL_PAIRING = 'FULL_PAIRING'
    PARTIAL_PAIRING = 'PARTIAL_PAIRING'
    MANUAL_PAIRING = 'MANUAL_PAIRING'
    FULL_UNPAIRING = 'FULL_UNPAIRING'
    MANUAL_UNPAIRING = 'MANUAL_UNPAIRING'
    COLOR_PERMUTE = 'COLOR_PERMUTE'
    RESULT_UPDATE = 'RESULT_UPDATE'
    BYE_UPDATE = 'BYE_UPDATE'


@dataclass
class Permission:
    action: Action
    rules: dict[RoundStatus, SafetyMode]

    def is_allowed(self, round_status: RoundStatus, action_mode: SafetyMode) -> bool:
        if round_status not in self.rules:
            return False
        return self.rules[round_status].danger_level <= action_mode.danger_level


class PermissionHandler:
    PERMISSIONS: list[Permission] = [
        Permission(Action.FULL_PAIRING, {RoundStatus.NEXT: SafetyMode.SAFE}),
        Permission(Action.PARTIAL_PAIRING, {RoundStatus.CURRENT: SafetyMode.UNSAFE}),
        Permission(
            Action.MANUAL_PAIRING,
            {
                RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                RoundStatus.CURRENT: SafetyMode.UNSAFE,
                RoundStatus.NEXT: SafetyMode.FIDE_INCOMPATIBLE,
            },
        ),
        Permission(
            Action.FULL_UNPAIRING, {RoundStatus.CURRENT: SafetyMode.FIDE_INCOMPATIBLE}
        ),
        Permission(
            Action.MANUAL_UNPAIRING,
            {
                RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                RoundStatus.CURRENT: SafetyMode.UNSAFE,
            },
        ),
        Permission(
            Action.COLOR_PERMUTE,
            {
                RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                RoundStatus.CURRENT: SafetyMode.UNSAFE,
            },
        ),
        Permission(
            Action.RESULT_UPDATE,
            {
                RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                RoundStatus.CURRENT: SafetyMode.SAFE,
            },
        ),
        Permission(
            Action.BYE_UPDATE,
            {
                RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                RoundStatus.CURRENT: SafetyMode.SAFE,
                RoundStatus.NEXT: SafetyMode.SAFE,
                RoundStatus.FUTURE: SafetyMode.SAFE,
            },
        ),
    ]

    @classmethod
    @cache
    def existing_actions(cls, round_status: RoundStatus) -> list[Action]:
        """List of all the actions that are possible for *round_status*
        regardless of the security mode"""
        return [
            permission.action
            for permission in cls.PERMISSIONS
            if round_status in permission.rules
        ]

    @classmethod
    @cache
    def allowed_actions(
        cls, round_status: RoundStatus, safety_mode: SafetyMode
    ) -> list[Action]:
        """List of all the actions allowed at *round_status* for *safety_mode*"""
        return [
            permission.action
            for permission in cls.PERMISSIONS
            if permission.is_allowed(round_status, safety_mode)
        ]

    @classmethod
    @cache
    def unsafe_actions(cls, round_status: RoundStatus) -> list[Action]:
        return [
            permission.action
            for permission in cls.PERMISSIONS
            if round_status in permission.rules
            and permission.rules[round_status] == SafetyMode.UNSAFE
        ]

    @classmethod
    @cache
    def fide_incompatible_actions(cls, round_status: RoundStatus) -> list[Action]:
        return [
            permission.action
            for permission in cls.PERMISSIONS
            if round_status in permission.rules
            and permission.rules[round_status] == SafetyMode.FIDE_INCOMPATIBLE
        ]

    @classmethod
    @cache
    def required_mode(cls, round_status: RoundStatus, action: Action) -> SafetyMode:
        permission = next(
            permission for permission in cls.PERMISSIONS if permission.action == action
        )
        if round_status not in permission.rules:
            raise PapiWebException(f'{action=}, {round_status=}')
        return permission.rules[round_status]

    @classmethod
    def validate_action(
        cls, action: Action, round_status: RoundStatus, safety_mode: SafetyMode
    ) -> bool:
        """Validate that an action can be used.
        Returns True if it can be executed, False if it needs another safety mode.
        Raises if the action is impossible."""
        if action not in cls.existing_actions(round_status):
            raise PapiWebException(f'{action=}, {round_status=}, {safety_mode=}')
        return action in cls.allowed_actions(round_status, safety_mode)
