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
from database.access.access_database import AccessDatabase
from database.access.papi.papi_template import create_empty_papi_database

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


class PapiDatabase(AccessDatabase):
    """The database class, using the Papi format of the French Chess Federation
    Tournament manager."""

    def __init__(
        self, file: Path, write: bool = False, on_exit: Callable | None = None
    ):
        super().__init__(file, write)
        self.date_of_birth_pattern: Pattern = re.compile(r'^\d{1,2}/\d{1,2}/(\d{1,4})$')
        self.on_exit = on_exit

    def __exit__(self, exc_type, exc_val, tb):
        super().__exit__(exc_type, exc_val, tb)
        if self.on_exit:
            self.on_exit()

    def create_empty(self):
        assert not self.file.exists()
        create_empty_papi_database(self.file)

    def commit(self):
        self._commit()

    def read_variables(self, variables: list[PapiVariable]) -> dict[PapiVariable, str]:
        if not variables:
            return {}
        self._execute(
            (
                'SELECT `Variable`, `Value` FROM `info` WHERE `Variable` '
                f'IN ({", ".join("?" for _ in range(len(variables)))})'
            ),
            tuple(variable.value for variable in variables),
        )
        return {PapiVariable(row['Variable']): row['Value'] for row in self._fetchall()}

    def update_variable(self, variable: PapiVariable, value: str | int):
        query: str = 'UPDATE `info` SET `Value` = ? WHERE `Variable` = ?'
        self._execute(query, (value, variable.value))

    def read_info(self) -> PapiTournamentInfo:
        """Reads the database and returns basic information about the
        tournament."""
        values = self.read_variables(
            [
                PapiVariable.ROUNDS,
                PapiVariable.PAIRING_VARIATION,
                PapiVariable.RATING,
                PapiVariable.RATING_LIMIT1,
                PapiVariable.RATING_LIMIT2,
                PapiVariable.TIE_BREAK1,
                PapiVariable.TIE_BREAK2,
                PapiVariable.TIE_BREAK3,
                PapiVariable.THREE_POINTS_FOR_A_WIN,
                PapiVariable.ARBITER,
            ]
        )
        tie_break_type_by_id = PapiTieBreakManager.type_by_papi_id()
        tie_breaks: list[TieBreak] = []
        for variable in (
            PapiVariable.TIE_BREAK1,
            PapiVariable.TIE_BREAK2,
            PapiVariable.TIE_BREAK3,
        ):
            papi_id = values[variable]
            if tie_break_type := tie_break_type_by_id.get(papi_id, None):
                tie_breaks.append(tie_break_type())

        from plugins.ffe.utils import PapiPairingVariation, PapiThreePointsForAWin

        return PapiTournamentInfo(
            rounds=int(values[PapiVariable.ROUNDS]),
            pairing_variation=PapiPairingVariation.get_core_object(
                values[PapiVariable.PAIRING_VARIATION]
            ),
            rating=TournamentRating.from_papi_value(values[PapiVariable.RATING]),
            rating_limit1=int(values[PapiVariable.RATING_LIMIT1]),
            rating_limit2=int(values[PapiVariable.RATING_LIMIT2]),
            tie_breaks=tie_breaks,
            three_points_for_a_win=PapiThreePointsForAWin.get_core_object(
                values[PapiVariable.THREE_POINTS_FOR_A_WIN]
            ),
            arbiter=values[PapiVariable.ARBITER],
        )

    def write_info(self, info: dict[PapiVariable, str | int]):
        for name, value in info.items():
            self.update_variable(name, value)

    def write_player_dict(
        self,
        data: dict[str, str | int | float | None],
    ) -> int:
        """Writes the information of a Papi player extracted from another database to this database,
        returns the papi_id."""
        field_names: list[str] = list(data.keys())
        params: tuple = tuple([data[field] for field in field_names])
        fields = ', '.join(f'`{f}`' for f in field_names)
        values = ', '.join(['?'] * len(field_names))
        self._execute(f'INSERT INTO `joueur`({fields}) VALUES ({values})', params)
        assert isinstance(data['Ref'], int)
        return data['Ref']

    def update_tie_breaks(self, tie_breaks: list[TieBreak]):
        for variable in (
            PapiVariable.TIE_BREAK1,
            PapiVariable.TIE_BREAK2,
            PapiVariable.TIE_BREAK3,
        ):
            while tie_breaks and tie_breaks[0].papi_id is None:
                tie_breaks.pop(0)
            self.update_variable(
                variable, (tie_breaks.pop(0).papi_id or '') if tie_breaks else ''
            )

    @staticmethod
    def timestamp_to_papi_date(ts: float) -> str:
        dt: datetime
        if ts >= 0:
            dt = datetime.fromtimestamp(ts)
        else:
            dt = datetime(1970, 1, 2) + timedelta(seconds=ts)
        return dt.strftime('%d/%m/%Y')

    def delete_players_personal_data(self):
        """Delete all personal data (email and phone number) from the database."""
        query: str = 'UPDATE `joueur` SET Tel = ?, EMail = ?'
        self._execute(
            query,
            (
                '',
                '',
            ),
        )

    def remove_zpbs_if_no_pairings(self):
        """Delete all ZPBs if no pairings are found (at any round).
        This fixes a display issue on the FFE website."""
        condition: str = ' OR '.join(
            f'`{RoundFields(round_).opponent}` IS NOT NULL' for round_ in range(1, 25)
        )
        query: str = f'SELECT COUNT(`Ref`) FROM `joueur` WHERE {condition}'
        self._execute(query)
        if self._fetchval() == 0:
            logger.info('Deleting ZPBs...')
            data: dict[str, str | int | None] = {}
            for round_ in range(1, 25):
                rf = RoundFields(round_)
                data |= {
                    rf.color: UNPLAYED_COLOR,
                    rf.opponent: None,
                    rf.result: Result.NO_RESULT.to_papi_value,
                }
            actions: str = ', '.join([f'`{key}` = ?' for key in data])
            query: str = f'UPDATE `joueur` SET {actions} WHERE Ref <> ?'
            params = tuple(data.values()) + (EXEMPT_PLAYER_ID,)
            self._execute(query, params)
            logger.info('Done.')
        else:
            logger.info('No ZPBs to delete.')
