import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from logging import Logger
from pathlib import Path
from typing import Pattern

from common.logger import get_logger
from data.pairings import PairingVariation
from data.pairings.variations import StandardSwissVariation
from data.tie_breaks import TieBreak, PapiTieBreakManager
from utils.enum import (
    Result,
    TournamentRating,
)

logger: Logger = get_logger()


EXEMPT_PLAYER_ID = 1
BYE_COLOR = 'F'
UNPLAYED_COLOR = 'R'


class RoundFields:
    def __init__(self, round_: int):
        assert 1 <= round_ <= 24
        self.color = f'Rd{round_:0>2}Cl'
        self.opponent = f'Rd{round_:0>2}Adv'
        self.result = f'Rd{round_:0>2}Res'

    @property
    def all(self) -> list[str]:
        return [self.color, self.opponent, self.result]

    @property
    def field_sets(self) -> str:
        return ', '.join(f'`{field}` = ?' for field in self.all)


@dataclass
class PapiTournamentInfo:
    """Basic tournament information tuple."""

    rounds: int = 1
    pairing_variation: PairingVariation = field(default_factory=StandardSwissVariation)
    rating: TournamentRating = TournamentRating.STANDARD
    rating_limit1: int = 0
    rating_limit2: int = 0
    tie_breaks: list[TieBreak] = field(default_factory=list[TieBreak])
    three_points_for_a_win: bool = False
    arbiter: str = ''


class PapiVariable(StrEnum):
    NAME = 'Nom'
    TYPE = 'Genre'
    ROUNDS = 'NbrRondes'
    PAIRING_SYSTEM = 'Genre'
    PAIRING_VARIATION = 'Pairing'
    TIME_CONTROL = 'Cadence'
    RATING = 'ClassElo'
    RATING_LIMIT1 = 'EloBase1'
    RATING_LIMIT2 = 'EloBase2'
    TIE_BREAK1 = 'Dep1'
    TIE_BREAK2 = 'Dep2'
    TIE_BREAK3 = 'Dep3'
    THREE_POINTS_FOR_A_WIN = 'DecomptePoints'
    LOCATION = 'Lieu'
    START_DATE = 'DateDebut'
    END_DATE = 'DateFin'
    ARBITER = 'Arbitre'
    FFE_ID = 'Homologation'
