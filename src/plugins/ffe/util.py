from enum import IntEnum
from typing import Self

from common.i18n import _


class PlayerFFELicence(IntEnum):
    NONE = 0
    N = 1
    A = 2
    B = 3

    @classmethod
    def from_papi_value(cls, value: str) -> Self:
        match value:
            case '':
                return cls.NONE
            case 'N':
                return cls.N
            case 'A':
                return cls.A
            case 'B':
                return cls.B
            case _:
                raise ValueError(f'Unknown value: {value}')

    @property
    def to_papi_value(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return ''
            case PlayerFFELicence.N:
                return 'N'
            case PlayerFFELicence.A:
                return 'A'
            case PlayerFFELicence.B:
                return 'B'
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def name(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return _('No FFE Licence')
            case PlayerFFELicence.N:
                return _('Expired FFE licence')
            case PlayerFFELicence.B:
                return _('FFE licence B (leisure)')
            case PlayerFFELicence.A:
                return _('FFE licence A (competition)')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return '-'
            case PlayerFFELicence.N:
                return 'N'
            case PlayerFFELicence.A:
                return 'A'
            case PlayerFFELicence.B:
                return 'B'
            case _:
                raise ValueError(f'Unknown value: {self}')