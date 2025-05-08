from enum import IntEnum
from logging import Logger
from typing import Any

from common.i18n import _
from common.logger import get_logger
from utils.enum import (
    PlayerGender,
    PlayerCategory,
    PlayerRatingType,
)
from plugins.chessevent.data.chessevent_field_reader import ChessEventFieldReader
from plugins.ffe.utils import PlayerFFELicence

logger: Logger = get_logger()


class ChessEventPlayerTitle(IntEnum):
    """The possible FIDE titles for ChessEvent players: GM, WGM, IM, WIM, FM, WFM.
    Also includes the "no title" case, but does not include CM nor WCM.
    This is for Papi-compatibility reasons."""

    NONE = 0
    WOMAN_FIDE_MASTER = 1
    FIDE_MASTER = 2
    WOMAN_INTERNATIONAL_MASTER = 3
    INTERNATIONAL_MASTER = 4
    WOMAN_GRANDMASTER = 5
    GRANDMASTER = 6

    @property
    def to_papi_value(self) -> str:
        match self:
            case ChessEventPlayerTitle.NONE:
                return ''
            case ChessEventPlayerTitle.WOMAN_FIDE_MASTER:
                return 'ff'
            case ChessEventPlayerTitle.FIDE_MASTER:
                return 'f'
            case ChessEventPlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return 'mf'
            case ChessEventPlayerTitle.INTERNATIONAL_MASTER:
                return 'm'
            case ChessEventPlayerTitle.WOMAN_GRANDMASTER:
                return 'gf'
            case ChessEventPlayerTitle.GRANDMASTER:
                return 'g'
            case _:
                raise ValueError(f'Unknown title: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case ChessEventPlayerTitle.NONE:
                return ''
            case ChessEventPlayerTitle.WOMAN_FIDE_MASTER:
                return _('WFM *** SHORT NAME FOR Woman Fide Master')
            case ChessEventPlayerTitle.FIDE_MASTER:
                return _('FM *** SHORT NAME FOR Fide Master')
            case ChessEventPlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return _('WIM *** SHORT NAME FOR Woman International Master')
            case ChessEventPlayerTitle.INTERNATIONAL_MASTER:
                return _('IM *** SHORT NAME FOR International Master')
            case ChessEventPlayerTitle.WOMAN_GRANDMASTER:
                return _('WGM *** SHORT NAME FOR Woman Grand Master')
            case ChessEventPlayerTitle.GRANDMASTER:
                return _('GM *** SHORT NAME FOR Grand Master')
            case _:
                raise ValueError(f'Unknown title: {self}')

    def __str__(self) -> str:
        return self.short_name


class ChessEventPlayer:
    """A class representing a player information on ChessEvent."""

    @staticmethod
    def ffe_license_from_chessevent_value(value: int) -> PlayerFFELicence:
        match value:
            case 0:
                return PlayerFFELicence.NONE
            case 1:
                return PlayerFFELicence.N
            case 2:
                return PlayerFFELicence.B
            case 3:
                return PlayerFFELicence.A
            case _:
                raise ValueError(f'Unknown value: {value}')

    def __init__(
        self,
        chessevent_player_info: dict[str, Any],
    ):
        self.error = True
        reader = ChessEventFieldReader(chessevent_player_info)

        try:
            self.last_name = reader.get('last_name', str)
            self.first_name = reader.get('first_name', str)
            self.federation = reader.get('federation', str)
            self.fide_id = reader.get('fide_id', int, 0)
            self.gender = reader.get_enum('gender', PlayerGender, PlayerGender.NONE)
            self.birth = float(reader.get('birth', int))

            self.ffe_id = reader.get('ffe_id', int)
            self.ffe_license = self.ffe_license_from_chessevent_value(
                reader.get('ffe_license', int)
            )
            self.ffe_license_number = reader.get('ffe_license_number', str)
            self.ffe_league = reader.get('ffe_league', str)
            self.ffe_club_id = reader.get('ffe_club_id', int, 0)
            self.ffe_club = reader.get('ffe_club', str, '')

            self.category = reader.get_enum(
                'category', PlayerCategory, PlayerCategory.NONE
            )
            self.standard_rating = reader.get('standard_rating', int)
            self.standard_rating_type = reader.get_enum(
                'standard_rating_type', PlayerRatingType, PlayerRatingType.ESTIMATED
            )
            self.rapid_rating = reader.get('rapid_rating', int)
            self.rapide_rating_type = reader.get_enum(
                'rapid_rating_type', PlayerRatingType, PlayerRatingType.ESTIMATED
            )
            self.blitz_rating = reader.get('blitz_rating', int)
            self.blitz_rating_type = reader.get_enum(
                'blitz_rating_type', PlayerRatingType, PlayerRatingType.ESTIMATED
            )
            self.title = reader.get_enum(
                'title', ChessEventPlayerTitle, ChessEventPlayerTitle.NONE
            )

            self.email = reader.get('email', str)
            self.phone = reader.get('phone', str)
            self.fee = float(reader.get('fee', (int, float)))
            self.paid = float(reader.get('paid', (int, float)))
            self.check_in = bool(reader.get('check_in', (bool, int)))
            self.board = reader.get('board', int)

            self.skipped_rounds: dict[int, float] = {}
            skipped = reader.get('skipped_rounds', dict, {})
            for round_, val in skipped.items():
                if int(round_) in range(1, 25) and val in [0.0, 0.5]:
                    self.skipped_rounds[int(round_)] = val
                else:
                    raise ValueError

        except KeyError:
            logger.error(
                'Field [%s] not found for player [%s %s]',
                reader.last_key,
                self.last_name,
                self.first_name,
            )
            return
        except (TypeError, ValueError):
            logger.error(
                'Invalid value [%s] for field [%s] for player [%s %s]',
                chessevent_player_info[reader.last_key or ''],
                reader.last_key,
                self.last_name,
                self.first_name,
            )
            return

        self.error = False

    def __str__(self) -> str:
        return '\n'.join(
            [
                f'  - Name: {self.last_name} {self.first_name}',
                f'  - Title / FFE ID / FIDE ID: {self.title} / {self.ffe_id} / {self.fide_id}',
                f'  - FFE Licence / Licence number / Category / Gender: '
                f'{self.ffe_license} / {self.ffe_license_number} / {self.category} / {self.gender}',
                f'  - Birth date: {self.birth}',
                f'  - Standard rating / rapid / blitz: {self.standard_rating}{self.standard_rating_type} '
                f'/ {self.rapid_rating}{self.rapide_rating_type} / {self.blitz_rating}{self.blitz_rating_type}',
                f'  - Federation / League / Club: '
                f'{self.federation} / {self.ffe_league} / {self.ffe_club_id} {self.ffe_club}',
                f'  - Mail / Phone: {self.email} / {self.phone}',
                f'  - Owed / Paid / Check-in: {self.fee} / {self.paid} / {self.check_in}',
                f'  - Fixed board / Rounds : {self.board} / {self.skipped_rounds}',
            ]
        )
