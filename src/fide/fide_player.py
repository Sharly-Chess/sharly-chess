from dataclasses import dataclass
from enum import IntEnum
from typing import Self

from common.i18n import _


class FidePlayerGender(IntEnum):
    FEMALE = 1
    MALE = 2

    @classmethod
    def values(cls) -> tuple[int, ...]:
        return tuple(item.value for item in cls)

    @classmethod
    def from_fide_export(cls, value: str) -> Self:
        match value:
            case 'F':
                return cls.FEMALE
            case 'M':
                return cls.MALE
            case _:
                raise ValueError(f'Unknown FIDE export gender value: {value}')

    @property
    def name(self) -> str:
        match self:
            case FidePlayerGender.FEMALE:
                return _('Female *** NAME FOR GENDER FEMALE')
            case FidePlayerGender.MALE:
                return _('Male *** NAME FOR GENDER MALE')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case FidePlayerGender.FEMALE:
                return _('F *** SHORT NAME FOR GENDER FEMALE')
            case FidePlayerGender.MALE:
                return _('M *** SHORT NAME FOR GENDER MALE')
            case _:
                raise ValueError(f'Unknown value: {self}')



@dataclass
class FidePlayer:
    id: int
    name: str
    federation: str
    gender: FidePlayerGender
    title: FidePlayerTitle
    woman_title: FidePlayerWomanTitle
    other_title: FidePlayerOtherTitle


    @property
    def last_name(self) -> str:
        return ''

    @property
    def first_name(self) -> str:
        return ''
