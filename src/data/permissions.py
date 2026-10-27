from dataclasses import dataclass
from enum import IntEnum, StrEnum

from common.exception import SharlyChessException


class WarningLevel(IntEnum):
    """How much the user is asked before an action runs, as defined by the
    FIDE Technical Commission for tournament handling programs.

    Warnings cannot be disabled or downgraded."""

    NONE = 1
    """Non-standard action, allowed without warning."""
    INFORMATION = 2
    """Action not described by the regulations: acknowledgement only."""
    CONFIRMATION = 3
    """Action not compliant with the regulations but harmless: proceed or
    cancel."""
    DOUBLE_CONFIRMATION = 4
    """Action not compliant but possibly necessary: a first confirmation,
    then a second one spelling out the consequences."""
    FIDE_PROHIBITED = 5
    """Action prohibited in FIDE mode: rejected, unless the user leaves FIDE
    mode first."""

    def effective(self, fide_mode: bool) -> 'WarningLevel':
        """The level actually applied: outside FIDE mode, a FIDE-prohibited
        action only asks for confirmation."""
        if self == WarningLevel.FIDE_PROHIBITED and not fide_mode:
            return WarningLevel.CONFIRMATION
        return self

    @property
    def asks_user(self) -> bool:
        """Whether the action waits for the user's answer before running."""
        return self >= WarningLevel.CONFIRMATION


class RoundStatus(StrEnum):
    PAST = 'PAST'
    PREVIOUS = 'PREVIOUS'
    CURRENT = 'CURRENT'
    NEXT = 'NEXT'
    FUTURE = 'FUTURE'

    @classmethod
    def from_round(cls, round_: int, current_round: int) -> 'RoundStatus':
        if round_ == current_round:
            return cls.CURRENT
        if round_ == current_round - 1:
            return cls.PREVIOUS
        if round_ == current_round + 1:
            return cls.NEXT
        if round_ < current_round - 1:
            return cls.PAST
        return cls.FUTURE


class PairingAction(StrEnum):
    FULL_PAIRING = 'FULL_PAIRING'
    PARTIAL_PAIRING = 'PARTIAL_PAIRING'
    MANUAL_PAIRING = 'MANUAL_PAIRING'
    FULL_UNPAIRING = 'FULL_UNPAIRING'
    MANUAL_UNPAIRING = 'MANUAL_UNPAIRING'
    COLOR_PERMUTE = 'COLOR_PERMUTE'
    RESULT_UPDATE = 'RESULT_UPDATE'
    BYE_UPDATE = 'BYE_UPDATE'


@dataclass
class Permission[Action: StrEnum]:
    action: Action
    rules: dict[RoundStatus, WarningLevel]


class PermissionHandler[Action: StrEnum]:
    def __init__(self, permissions: list[Permission[Action]]):
        self.permissions = permissions

    def existing_actions(self, round_status: RoundStatus) -> list[Action]:
        """List of all the actions that are possible for *round_status*,
        whatever the warning they raise."""
        return [
            permission.action
            for permission in self.permissions
            if round_status in permission.rules
        ]

    def allowed_actions(
        self,
        round_status: RoundStatus,
        unlocked_level: WarningLevel,
        fide_mode: bool,
    ) -> list[Action]:
        """List of all the actions that run at *round_status* without asking
        the user, once warnings up to *unlocked_level* have been confirmed."""
        return [
            permission.action
            for permission in self.permissions
            if round_status in permission.rules
            and self._runs_without_asking(
                permission.rules[round_status].effective(fide_mode), unlocked_level
            )
        ]

    @staticmethod
    def _runs_without_asking(level: WarningLevel, unlocked_level: WarningLevel) -> bool:
        return not level.asks_user or level <= unlocked_level

    def required_level(self, round_status: RoundStatus, action: Action) -> WarningLevel:
        """The warning level of *action* at *round_status*, before FIDE mode
        is taken into account."""
        permission = next(
            permission for permission in self.permissions if permission.action == action
        )
        if round_status not in permission.rules:
            raise SharlyChessException(f'{action=}, {round_status=}')
        return permission.rules[round_status]

    @staticmethod
    def confirmation_unlocks_round(round_status: RoundStatus, fide_mode: bool) -> bool:
        """Whether confirming a warning lets the next actions of the same
        level on the round run without asking again.

        Not in FIDE mode: each change to the previous round is a correction
        of a round the current one was paired from, confirmed and logged one
        by one, and the pairings of the current round are edited within a
        manual pairing, which unlocks them until they are validated."""
        return not fide_mode


MANUAL_PAIRING_ACTIONS = frozenset(
    {
        PairingAction.MANUAL_PAIRING,
        PairingAction.MANUAL_UNPAIRING,
        PairingAction.COLOR_PERMUTE,
        PairingAction.PARTIAL_PAIRING,
    }
)


PREVIOUS_ROUND_MANUAL_PAIRING_ACTIONS = frozenset(
    {PairingAction.MANUAL_PAIRING, PairingAction.MANUAL_UNPAIRING}
)


def starts_manual_pairing(
    action: PairingAction, round_status: RoundStatus, fide_mode: bool
) -> bool:
    """Whether *action* edits the pairings of a round, which in FIDE mode is
    done within a manual pairing: explicitly validated at the end, when the
    pairings are checked against the pairing engine's. In the previous
    round, the games are taken apart or put together that way; its colours,
    like its results, are corrected one by one."""
    if not fide_mode:
        return False
    if round_status == RoundStatus.PREVIOUS:
        return action in PREVIOUS_ROUND_MANUAL_PAIRING_ACTIONS
    return (
        round_status in (RoundStatus.CURRENT, RoundStatus.NEXT)
        and action in MANUAL_PAIRING_ACTIONS
    )
