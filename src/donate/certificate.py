import datetime
from dataclasses import dataclass
from typing import Self

from data.player import Player


@dataclass
class DonationCertificate:
    """A data class used to store the donation certificates."""

    email: str
    last_name: str
    first_name: str
    date: datetime.date | None = None
    signature: str | None = None

    @property
    def tooltip(self) -> str:
        return f'{Player.player_full_name(self.first_name, self.last_name)}<br/>{self.email}<br/>{self.date}'

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {
            'email': self.email,
            'last_name': self.last_name,
            'first_name': self.first_name,
        }
        if self.date:
            d |= {
                'date': self.date.strftime('%Y-%m-%d'),
            }
        if self.signature:
            d |= {
                'date': self.signature,
            }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Self:
        date_string: str | None = d.get('date', None)
        return cls(
            d['email'],
            d['last_name'],
            d['first_name'],
            datetime.datetime.strptime(date_string, '%Y-%m-%d').date()
            if date_string
            else None,
            d.get('signature', None),
        )

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.date=}, {self.email=}, {self.last_name=}, {self.first_name=})'
